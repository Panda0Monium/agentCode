#!/usr/bin/env bash
# Deploy agentcode: sync to origin/main, install deps, migrate, collect static, restart services.
# Invoked by CI (GitHub Actions) via SSH as the `agentcode` user.
set -euo pipefail

REPO_DIR="/home/agentcode/agentCode"
cd "$REPO_DIR"

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

sudo /usr/bin/systemctl restart agentcode-web agentcode-worker

echo "Deploy complete: $(git rev-parse --short HEAD)"
