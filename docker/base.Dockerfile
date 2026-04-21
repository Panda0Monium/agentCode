FROM python:3.12-slim
RUN pip install --no-cache-dir \
    pytest>=8.0 \
    pytest-json-report>=1.5.0 \
    ruff>=0.4.0
WORKDIR /repo
CMD ["sleep", "infinity"]
