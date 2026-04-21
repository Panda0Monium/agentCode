import subprocess
import sys
import time

import pytest
import requests

sys.path.insert(0, "src")

_BASE_URL = "http://127.0.0.1:5000"


@pytest.fixture(scope="session")
def server():
    proc = subprocess.Popen(
        [sys.executable, "src/app.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Poll /health until the server is ready (up to 5 seconds)
    for _ in range(20):
        try:
            requests.get(f"{_BASE_URL}/health", timeout=0.5)
            break
        except Exception:
            time.sleep(0.25)
    else:
        proc.terminate()
        pytest.fail("Flask server did not start within 5 seconds")

    yield _BASE_URL

    proc.terminate()
    proc.wait(timeout=5)
