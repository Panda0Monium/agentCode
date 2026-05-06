import time

import pytest

from api_client import ApiClient


def test_get_returns_data(mock_server):
    mock_server.enqueue(200, {"key": "value", "num": 42})
    client = ApiClient(mock_server.url, requests_per_sec=10)
    result = client.get("/data")
    assert result == {"key": "value", "num": 42}


def test_post_returns_data(mock_server):
    mock_server.enqueue(200, {"created": True, "id": 7})
    client = ApiClient(mock_server.url, requests_per_sec=10)
    result = client.post("/items", {"name": "thing"})
    assert result == {"created": True, "id": 7}


def test_retries_on_429(mock_server):
    mock_server.enqueue(429)
    mock_server.enqueue(429)
    mock_server.enqueue(200, {"ok": True})
    client = ApiClient(mock_server.url, requests_per_sec=10, max_retries=3, backoff_base=0.01)
    result = client.get("/resource")
    assert result == {"ok": True}
    assert mock_server.request_count == 3


def test_retries_on_500(mock_server):
    mock_server.enqueue(500)
    mock_server.enqueue(200, {"recovered": True})
    client = ApiClient(mock_server.url, requests_per_sec=10, max_retries=3, backoff_base=0.01)
    result = client.get("/resource")
    assert result == {"recovered": True}
    assert mock_server.request_count == 2


def test_raises_after_max_retries_exhausted(mock_server):
    for _ in range(5):
        mock_server.enqueue(429)
    client = ApiClient(mock_server.url, requests_per_sec=10, max_retries=3, backoff_base=0.01)
    with pytest.raises(RuntimeError):
        client.get("/fail")


def test_rate_limit_slows_requests(mock_server):
    for _ in range(3):
        mock_server.enqueue(200, {})
    client = ApiClient(mock_server.url, requests_per_sec=1)
    start = time.monotonic()
    for _ in range(3):
        client.get("/data")
    elapsed = time.monotonic() - start
    assert elapsed >= 1.8, f"Expected >= 1.8s for 3 requests at 1 rps, got {elapsed:.2f}s"
