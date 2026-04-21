# Base image for all task sandboxes.
# Built once with: docker build -t agentcode-sandbox .
# Never has network access at runtime (enforced by sandbox.py).

FROM python:3.12-slim

# Install grading tools
RUN pip install --no-cache-dir \
    pytest>=8.0 \
    pytest-json-report>=1.5.0 \
    ruff>=0.4.0 \
    flask>=3.0 \
    requests>=2.31

WORKDIR /repo

# Default: kept alive by sandbox.py via "sleep infinity"
CMD ["sleep", "infinity"]
