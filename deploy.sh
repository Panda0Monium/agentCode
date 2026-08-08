#!/usr/bin/env bash
# Deploy agentcode: sync to origin/main, install deps, migrate, collect static,
# rebuild sandbox images if they changed, restart services.
# Invoked by CI (GitHub Actions) via SSH as the `agentcode` user.
set -euo pipefail

REPO_DIR="/home/agentcode/agentCode"
cd "$REPO_DIR"

# Recorded before the reset so we can tell what this deploy actually changed.
PREVIOUS_HEAD="$(git rev-parse HEAD 2>/dev/null || true)"

git fetch --prune origin
git reset --hard origin/main

# shellcheck disable=SC1091
source .venv/bin/activate

pip install --quiet -r requirements.txt
pip install --quiet -r webserver/requirements.txt

cd webserver
python manage.py migrate --noinput
python manage.py collectstatic --noinput
cd ..

# ---------------------------------------------------------------------------
# Sandbox images
# ---------------------------------------------------------------------------
# These are part of the reward function, not just runtime dependencies: the
# pinned ruff decides lint_score and the pinned pytest decides what counts as a
# passing test. Leaving them outside the deploy meant production could score
# identical work differently from anywhere else, indefinitely and invisibly.
#
# Rebuild is triggered by any of three signals, because none is sufficient
# alone:
#
#   1. git diff of docker/ and Dockerfile between the previously deployed
#      commit and the new one. Exact, but blind to anything that happens
#      outside git.
#   2. A missing image tag. Covers a fresh droplet, a manual `docker rmi`, and
#      a previous deploy whose build failed — in all of which git correctly
#      reports no change.
#   3. Any change to docker/base.Dockerfile rebuilds everything, because the
#      other images are FROM agentcode-base and Docker will not rebuild them
#      just because their parent tag moved.
#
# When the previous revision cannot be determined the script rebuilds rather
# than skips: a redundant build costs seconds against a warm layer cache, a
# skipped one costs silently wrong scores until someone notices.

# Parallel arrays, not an associative array — build order matters here.
IMAGE_TAGS=(agentcode-base agentcode-classeval agentcode-flask agentcode-requests agentcode-sandbox)
IMAGE_FILES=(docker/base.Dockerfile docker/classeval.Dockerfile docker/flask.Dockerfile docker/requests.Dockerfile Dockerfile)

rebuild_all=false
changed=""

if [[ -z "$PREVIOUS_HEAD" ]] || ! git cat-file -e "${PREVIOUS_HEAD}^{commit}" 2>/dev/null; then
  echo "[images] previous revision unknown — considering all images stale"
  rebuild_all=true
else
  changed="$(git diff --name-only "$PREVIOUS_HEAD" HEAD -- docker/ Dockerfile || true)"
  if grep -qx 'docker/base\.Dockerfile' <<<"$changed"; then
    echo "[images] base image changed — rebuilding all (others are FROM agentcode-base)"
    rebuild_all=true
  fi
fi

build_tags=()
build_files=()
for i in "${!IMAGE_TAGS[@]}"; do
  tag="${IMAGE_TAGS[$i]}"
  file="${IMAGE_FILES[$i]}"

  if $rebuild_all; then
    reason="base image or unknown revision"
  elif grep -qx "$(sed 's/[.[\*^$]/\\&/g' <<<"$file")" <<<"$changed"; then
    reason="$file changed"
  elif ! docker image inspect "$tag" >/dev/null 2>&1; then
    reason="image missing"
  else
    continue
  fi

  echo "[images] $tag will be rebuilt ($reason)"
  build_tags+=("$tag")
  build_files+=("$file")
done

if [[ ${#build_tags[@]} -eq 0 ]]; then
  echo "[images] all sandbox images up to date"
else
  if ! docker info >/dev/null 2>&1; then
    echo "[images] ERROR: cannot reach the Docker daemon as $(whoami)." >&2
    echo "         Fix with: sudo usermod -aG docker $(whoami)  (then re-login)" >&2
    exit 1
  fi
  for i in "${!build_tags[@]}"; do
    echo "[images] building ${build_tags[$i]} from ${build_files[$i]}"
    docker build --quiet -f "${build_files[$i]}" -t "${build_tags[$i]}" .
  done
  echo "[images] rebuilt ${#build_tags[@]} image(s)"
fi

# Restart only after the images are in place, so the worker never picks up a
# job against an image that is mid-rebuild or failed to build. A build failure
# aborts the deploy here (set -e) rather than restarting into a broken state.
sudo /usr/bin/systemctl restart agentcode-web agentcode-worker

echo "Deploy complete: $(git rev-parse --short HEAD)"
