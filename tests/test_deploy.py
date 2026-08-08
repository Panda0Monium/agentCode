"""
deploy.sh's image-rebuild logic.

The sandbox images are part of the reward function, so a deploy that silently
skips rebuilding them produces wrong scores rather than an obvious failure.
These tests run the real script's detection logic against a throwaway git repo
with `docker` and `sudo` stubbed out, so nothing here touches the daemon.
"""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DEPLOY = REPO / "deploy.sh"


def _find_bash():
    """
    A POSIX bash that can execute scripts living at Windows paths.

    On Windows, `bash` on PATH is usually WSL's, which cannot exec the stub
    commands created here. Git Bash can, so prefer it explicitly.
    """
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ):
        if Path(candidate).exists():
            return candidate
    found = shutil.which("bash")
    if found and "System32" in found:  # WSL shim
        return None
    return found


BASH = _find_bash()

pytestmark = pytest.mark.skipif(BASH is None, reason="no usable bash")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


@pytest.fixture
def droplet(tmp_path):
    """A fake checkout plus stub `docker`/`sudo`/`python`/`pip` on PATH."""
    work = tmp_path / "agentCode"
    work.mkdir()

    (work / "docker").mkdir()
    for name in ("base", "classeval", "flask", "requests"):
        (work / "docker" / f"{name}.Dockerfile").write_text("FROM python:3.12-slim\n")
    (work / "Dockerfile").write_text("FROM python:3.12-slim\n")
    (work / "requirements.txt").write_text("")
    (work / "webserver").mkdir()
    (work / "webserver" / "requirements.txt").write_text("")
    (work / "webserver" / "manage.py").write_text("")
    (work / ".venv" / "bin").mkdir(parents=True)
    (work / ".venv" / "bin" / "activate").write_text("")

    _git(work, "init", "-q")
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "initial")
    _git(work, "branch", "-M", "main")

    # A bare "origin" the script can fetch/reset against.
    origin = tmp_path / "origin.git"
    _git(work, "clone", "-q", "--bare", str(work), str(origin))
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "fetch", "-q", "origin")

    # Stubs. `docker image inspect` fails for tags not listed in EXISTING.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(textwrap.dedent("""\
        #!/usr/bin/env bash
        case "$1" in
          info) exit 0 ;;
          image)
            shift 2
            grep -qw "$1" "$EXISTING_IMAGES" && exit 0 || exit 1 ;;
          build)
            for a in "$@"; do prev=$cur; cur=$a; [[ $prev == -t ]] && echo "BUILT $a" >> "$BUILD_LOG"; done
            exit 0 ;;
        esac
        exit 0
        """))
    for name in ("sudo", "pip", "python"):
        (bin_dir / name).write_text("#!/usr/bin/env bash\nexit 0\n")
    for f in bin_dir.iterdir():
        f.chmod(0o755)

    return work, bin_dir, tmp_path, origin


def _upstream_change(tmp_path, origin, rel_path, content, msg):
    """
    Land a change on origin/main without touching the deploy checkout.

    This is what a deploy actually looks like: the droplet sits on the old
    commit and the new one arrives from upstream. Committing in the checkout
    itself leaves PREVIOUS_HEAD == HEAD, so the diff is empty and nothing
    rebuilds — which is how the first version of these tests fooled itself.
    """
    clone = tmp_path / f"upstream-{rel_path.replace('/', '_')}"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _git(clone, "config", "user.email", "t@t")
    _git(clone, "config", "user.name", "t")
    target = clone / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", msg)
    _git(clone, "push", "-q", "origin", "HEAD:main")


def _run_deploy(droplet, existing_images):
    work, bin_dir, tmp_path, _origin = droplet
    script = work / "deploy.sh"
    # Point the script at the fake checkout.
    script.write_text(
        DEPLOY.read_text(encoding="utf-8").replace(
            'REPO_DIR="/home/agentcode/agentCode"', f'REPO_DIR="{work.as_posix()}"'
        ),
        encoding="utf-8",
    )
    build_log = tmp_path / "builds.txt"
    build_log.write_text("")
    images_file = tmp_path / "images.txt"
    images_file.write_text("\n".join(existing_images) + "\n")

    env = {
        **os.environ,
        "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}",
        "BUILD_LOG": build_log.as_posix(),
        "EXISTING_IMAGES": images_file.as_posix(),
    }
    proc = subprocess.run([BASH, script.as_posix()], capture_output=True,
                          text=True, env=env, cwd=work.as_posix())
    built = [ln.split()[1] for ln in build_log.read_text().splitlines() if ln.startswith("BUILT")]
    return proc, built


ALL = ["agentcode-base", "agentcode-classeval", "agentcode-flask",
       "agentcode-requests", "agentcode-sandbox"]


def test_nothing_changed_and_images_present_builds_nothing(droplet):
    proc, built = _run_deploy(droplet, existing_images=ALL)
    assert proc.returncode == 0, proc.stderr
    assert built == []
    assert "up to date" in proc.stdout


def test_missing_image_is_rebuilt_even_though_git_shows_no_change(droplet):
    # A manual `docker rmi`, or a build that failed on a previous deploy.
    proc, built = _run_deploy(droplet, existing_images=[t for t in ALL if t != "agentcode-flask"])
    assert proc.returncode == 0, proc.stderr
    assert built == ["agentcode-flask"]
    assert "image missing" in proc.stdout


def test_changed_leaf_dockerfile_rebuilds_only_that_image(droplet):
    _, _, tmp_path, origin = droplet
    _upstream_change(tmp_path, origin, "docker/flask.Dockerfile",
                     "FROM agentcode-base\nRUN true\n", "touch flask image")

    proc, built = _run_deploy(droplet, existing_images=ALL)
    assert proc.returncode == 0, proc.stderr
    assert built == ["agentcode-flask"]


def test_changed_base_rebuilds_everything(droplet):
    # The others are FROM agentcode-base; Docker will not rebuild them just
    # because the parent tag moved, so they would keep stale layers.
    _, _, tmp_path, origin = droplet
    _upstream_change(tmp_path, origin, "docker/base.Dockerfile",
                     "FROM python:3.12-slim\nRUN true\n", "touch base image")

    proc, built = _run_deploy(droplet, existing_images=ALL)
    assert proc.returncode == 0, proc.stderr
    assert built == ALL
    assert built[0] == "agentcode-base"  # parent first


def test_root_dockerfile_change_rebuilds_the_fallback_image(droplet):
    _, _, tmp_path, origin = droplet
    _upstream_change(tmp_path, origin, "Dockerfile",
                     "FROM python:3.12-slim\nRUN true\n", "touch fallback image")

    proc, built = _run_deploy(droplet, existing_images=ALL)
    assert proc.returncode == 0, proc.stderr
    assert built == ["agentcode-sandbox"]


def test_unrelated_change_builds_nothing(droplet):
    _, _, tmp_path, origin = droplet
    _upstream_change(tmp_path, origin, "requirements.txt",
                     "# unrelated\n", "unrelated change")

    proc, built = _run_deploy(droplet, existing_images=ALL)
    assert proc.returncode == 0, proc.stderr
    assert built == []


def test_images_are_built_before_services_restart(droplet):
    # Restarting into a half-built image is the failure mode this ordering
    # exists to prevent.
    text = DEPLOY.read_text(encoding="utf-8")
    assert text.index("docker build") < text.index("systemctl restart")
