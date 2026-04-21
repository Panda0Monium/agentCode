import threading
import time

import pytest

from api_client import ApiClient


def test_exactly_n_plus_one_attempts(mock_server):
    for _ in range(5):
        mock_server.enqueue(429)
    client = ApiClient(mock_server.url, requests_per_sec=10, max_retries=3, backoff_base=0.01)
    with pytest.raises(RuntimeError):
        client.get("/fail")
    assert mock_server.request_count == 4  # 1 initial + 3 retries


def test_backoff_grows_exponentially(mock_server):
    mock_server.enqueue(429)
    mock_server.enqueue(429)
    mock_server.enqueue(200, {"ok": True})
    client = ApiClient(mock_server.url, requests_per_sec=10, max_retries=3, backoff_base=0.1)
    client.get("/resource")
    times = mock_server.request_times
    assert len(times) == 3
    gap0 = times[1] - times[0]
    gap1 = times[2] - times[1]
    assert gap0 >= 0.09, f"First backoff gap too small: {gap0:.3f}s"
    assert gap1 >= 0.18, f"Second backoff gap too small: {gap1:.3f}s"


def test_burst_allows_immediate_requests(mock_server):
    for _ in range(2):
        mock_server.enqueue(200, {})
    client = ApiClient(mock_server.url, requests_per_sec=2)
    start = time.monotonic()
    client.get("/a")
    client.get("/b")
    elapsed = time.monotonic() - start
    assert elapsed < 0.5, f"Burst of 2 at rps=2 should be fast, took {elapsed:.2f}s"


def test_rate_limit_spacing(mock_server):
    for _ in range(4):
        mock_server.enqueue(200, {})
    client = ApiClient(mock_server.url, requests_per_sec=2)
    start = time.monotonic()
    for _ in range(4):
        client.get("/data")
    elapsed = time.monotonic() - start
    assert 1.4 <= elapsed <= 3.0, f"4 requests at rps=2 took {elapsed:.2f}s, expected 1.4-3.0s"


def test_max_retries_zero_raises_immediately(mock_server):
    mock_server.enqueue(500)
    mock_server.enqueue(200, {})
    client = ApiClient(mock_server.url, requests_per_sec=10, max_retries=0, backoff_base=0.01)
    with pytest.raises(RuntimeError):
        client.get("/fail")
    assert mock_server.request_count == 1


def test_mixed_429_and_500_share_budget(mock_server):
    mock_server.enqueue(429)
    mock_server.enqueue(500)
    mock_server.enqueue(200, {"done": True})
    client = ApiClient(mock_server.url, requests_per_sec=10, max_retries=2, backoff_base=0.01)
    result = client.get("/mixed")
    assert result == {"done": True}
    assert mock_server.request_count == 3


def test_concurrent_requests_share_rate_limit(mock_server):
    for _ in range(3):
        mock_server.enqueue(200, {})
    client = ApiClient(mock_server.url, requests_per_sec=1)
    start = time.monotonic()
    threads = [threading.Thread(target=client.get, args=("/data",)) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start
    assert elapsed >= 1.8, f"3 concurrent requests at rps=1 should take >= 1.8s, got {elapsed:.2f}s"


def test_response_body_keys(mock_server):
    body = {"alpha": 1, "beta": "two", "gamma": [3, 4]}
    mock_server.enqueue(200, body)
    client = ApiClient(mock_server.url, requests_per_sec=10)
    result = client.get("/data")
    assert result == body
