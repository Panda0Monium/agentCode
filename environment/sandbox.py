"""
Docker-backed sandbox for one task run.

Lifecycle:
    sandbox = Sandbox(repo_path)
    sandbox.start()           # copies repo to tmp dir, starts container
    sandbox.exec("pytest")    # runs command inside container
    sandbox.write_file(...)   # writes to tmp dir (visible in container via bind mount)
    sandbox.stop()            # kills container, deletes tmp dir

The task repo is never modified — work happens in a fresh temp copy every time.
"""

import shutil
import tempfile
from pathlib import Path

import docker
import docker.errors


class Sandbox:
    IMAGE = "agentcode-sandbox"
    MEM_LIMIT = "512m"
    CPU_PERIOD = 100_000
    CPU_QUOTA = 50_000  # 0.5 CPU

    def __init__(self, repo_path: str | Path, image: str = IMAGE):
        self.image = image
        self._repo_path = Path(repo_path)
        self._tmp: Path | None = None
        self._work: Path | None = None
        self._client = docker.from_env()
        self._container = None

    def start(self) -> "Sandbox":
        self._tmp = Path(tempfile.mkdtemp(prefix="agentcode_"))
        self._work = self._tmp / "repo"
        shutil.copytree(self._repo_path, self._work)

        self._container = self._client.containers.run(
            self.image,
            command="sleep infinity",
            volumes={str(self._work): {"bind": "/repo", "mode": "rw"}},
            working_dir="/repo",
            network_disabled=True,
            mem_limit=self.MEM_LIMIT,
            cpu_period=self.CPU_PERIOD,
            cpu_quota=self.CPU_QUOTA,
            detach=True,
            remove=False,
        )
        print(f"[sandbox] container started ({self._container.short_id})")
        return self

    def exec(self, cmd: str) -> tuple[int, str]:
        """Run a shell command inside the container. Returns (exit_code, output)."""
        if self._container is None:
            raise RuntimeError("Sandbox not started")
        result = self._container.exec_run(["bash", "-c", cmd], workdir="/repo")
        output = result.output.decode("utf-8", errors="replace")
        return result.exit_code, output

    def read_file(self, path: str) -> str:
        return self._file(path).read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        target = self._file(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def inject_dir(self, src: Path, dest: str) -> None:
        """Copy a host directory into the sandbox work dir (used by grader for private tests)."""
        target = self._work / dest
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target)

    def list_files(self, path: str = "") -> list[str]:
        root = self._work / path if path else self._work
        if not root.exists():
            return []
        return sorted(
            str(p.relative_to(self._work))
            for p in root.rglob("*")
            if p.is_file()
        )

    def logs(self) -> str:
        """Return stdout/stderr from the container (best-effort)."""
        if self._container is None:
            return ""
        try:
            return self._container.logs().decode("utf-8", errors="replace")
        except docker.errors.DockerException:
            return ""

    def stop(self) -> None:
        if self._container:
            try:
                print("[sandbox] container stopped")
                self._container.stop(timeout=5)
                self._container.remove()
            except docker.errors.DockerException:
                pass
            self._container = None
        if self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None
            self._work = None

    def __enter__(self) -> "Sandbox":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()

    def _file(self, path: str) -> Path:
        if self._work is None:
            raise RuntimeError("Sandbox not started")
        # Prevent path traversal
        resolved = (self._work / path).resolve()
        if not resolved.is_relative_to(self._work.resolve()):
            raise PermissionError(f"Path escapes sandbox: {path}")
        return resolved
