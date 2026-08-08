# Fallback sandbox image, used by any task.yaml that omits `docker_image`
# (see Task.docker_image in tasks/task.py). Every shipped task names an image
# explicitly, so this is a safety net rather than the common path.
# Never has network access at runtime (enforced by sandbox.py).

FROM python:3.12-slim

# Quoted and pinned — see docker/base.Dockerfile. Unquoted `pytest>=8.0` is
# read by the shell as a redirection, so the constraint never applied and a
# file called `=8.0` was created at /. Versions are exact because ruff decides
# lint_score and pytest decides what counts as a passing test.
RUN pip install --no-cache-dir \
    "pytest==9.1.1" \
    "pytest-json-report==1.5.0" \
    "ruff==0.16.2" \
    "flask==3.1.3" \
    "requests==2.34.2"

WORKDIR /repo

# Default: kept alive by sandbox.py via "sleep infinity"
CMD ["sleep", "infinity"]
