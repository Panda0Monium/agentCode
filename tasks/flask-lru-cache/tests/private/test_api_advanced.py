import requests
from concurrent.futures import ThreadPoolExecutor, as_completed


def _init(server, capacity):
    r = requests.post(f"{server}/cache", json={"capacity": capacity})
    assert r.status_code == 200


def _get(server, key):
    r = requests.get(f"{server}/cache/{key}")
    assert r.status_code == 200
    return r.json()["value"]


def _put(server, key, value):
    r = requests.post(f"{server}/cache/{key}", json={"value": value})
    assert r.status_code == 200


def test_update_does_not_evict(server):
    # Updating an existing key should not cause any eviction
    _init(server, 2)
    _put(server, 1, 10)
    _put(server, 2, 20)
    _put(server, 1, 99)   # update, not insert — cache still has keys 1 and 2
    assert _get(server, 1) == 99
    assert _get(server, 2) == 20


def test_update_refreshes_recency(server):
    # After updating key 1, key 2 becomes LRU and should be evicted next
    _init(server, 2)
    _put(server, 1, 10)
    _put(server, 2, 20)
    _put(server, 1, 11)   # update → key 1 is now MRU, key 2 is LRU
    _put(server, 3, 30)   # evicts key 2
    assert _get(server, 1) == 11
    assert _get(server, 2) == -1
    assert _get(server, 3) == 30


def test_interleaved_ops(server):
    # Sequence with known eviction order
    _init(server, 3)
    _put(server, 1, 1)
    _put(server, 2, 2)
    _put(server, 3, 3)
    _get(server, 1)       # order (LRU→MRU): 2, 3, 1
    _put(server, 4, 4)   # evicts 2
    assert _get(server, 2) == -1
    _get(server, 3)       # order: 1, 4, 3
    _put(server, 5, 5)   # evicts 1
    assert _get(server, 4) == 4
    assert _get(server, 1) == -1
    assert _get(server, 3) == 3
    assert _get(server, 5) == 5


def test_eviction_order_strict(server):
    # Oldest untouched key is always evicted first
    _init(server, 3)
    _put(server, 10, 10)
    _put(server, 20, 20)
    _put(server, 30, 30)
    _put(server, 40, 40)   # evicts 10
    assert _get(server, 10) == -1
    _put(server, 50, 50)   # evicts 20
    assert _get(server, 20) == -1
    assert _get(server, 30) == 30
    assert _get(server, 40) == 40
    assert _get(server, 50) == 50


def test_large_capacity(server):
    n = 100
    _init(server, n)
    for i in range(n):
        _put(server, i, i * 2)
    for i in range(n):
        assert _get(server, i) == i * 2


def test_large_eviction_sequence(server):
    _init(server, 50)
    for i in range(150):
        _put(server, i, i)
    # First 100 entries should be evicted, last 50 should remain
    for i in range(100):
        assert _get(server, i) == -1
    for i in range(100, 150):
        assert _get(server, i) == i


def test_single_key_repeated_put(server):
    _init(server, 5)
    for v in range(1000):
        _put(server, 42, v)
    assert _get(server, 42) == 999


def test_capacity_reinit(server):
    _init(server, 5)
    for i in range(5):
        _put(server, i, i)
    _init(server, 2)       # reinit with smaller capacity — all old entries gone
    for i in range(5):
        assert _get(server, i) == -1
    # New limit is 2
    _put(server, 10, 10)
    _put(server, 11, 11)
    _put(server, 12, 12)   # evicts 10
    assert _get(server, 10) == -1
    assert _get(server, 11) == 11
    assert _get(server, 12) == 12


def test_get_returns_minus_one_after_eviction(server):
    _init(server, 2)
    _put(server, 1, 100)
    _put(server, 2, 200)
    _put(server, 3, 300)   # evicts 1
    assert _get(server, 1) == -1
    _put(server, 4, 400)   # evicts 2
    assert _get(server, 2) == -1


def test_multiple_reinits(server):
    for capacity in [1, 5, 2, 10]:
        _init(server, capacity)
        _put(server, 0, capacity)
        assert _get(server, 0) == capacity
        # Fill to capacity then one more to confirm eviction
        for i in range(1, capacity + 1):
            _put(server, i, i)
        _put(server, capacity + 1, -1)   # evicts key 0 (oldest)
        assert _get(server, 0) == -1


def test_concurrent_gets_consistent(server):
    # Pre-fill 10 keys, then hammer GETs from 8 threads — values must match what was PUT
    capacity = 10
    _init(server, capacity)
    expected = {i: i * 7 for i in range(capacity)}
    for k, v in expected.items():
        _put(server, k, v)

    def get_all(thread_id):
        for key in range(capacity):
            r = requests.get(f"{server}/cache/{key}")
            assert r.status_code == 200
            val = r.json()["value"]
            assert val == expected[key], f"key={key} expected {expected[key]} got {val}"

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(get_all, t) for t in range(8)]
        for f in as_completed(futures):
            f.result()


def test_concurrent_capacity_respected(server):
    # 8 threads × 25 PUTs into a capacity-10 cache (200 distinct keys)
    # After all PUTs, at most 10 keys should be present
    _init(server, 10)

    def put_many(thread_id):
        for i in range(25):
            key = thread_id * 25 + i
            r = requests.post(f"{server}/cache/{key}", json={"value": key})
            assert r.status_code == 200

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(put_many, t) for t in range(8)]
        for f in as_completed(futures):
            f.result()

    present = sum(1 for key in range(200) if _get(server, key) != -1)
    assert present <= 10, f"Cache exceeded capacity: {present} keys present"


def test_concurrent_same_key_updates(server):
    # 8 threads each PUT key=0 with a unique value — final GET must return one of those values
    _init(server, 5)
    valid_values = set(range(8))

    def put_key_zero(thread_id):
        r = requests.post(f"{server}/cache/0", json={"value": thread_id})
        assert r.status_code == 200

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(put_key_zero, t) for t in range(8)]
        for f in as_completed(futures):
            f.result()

    final = _get(server, 0)
    assert final in valid_values, f"Unexpected value for key=0: {final}"


def test_concurrent_mixed_ops(server):
    # 4 threads PUT keys 0-49; 4 threads GET keys 0-49 simultaneously — no crashes
    _init(server, 15)

    def put_range(thread_id):
        for key in range(50):
            r = requests.post(f"{server}/cache/{key}", json={"value": key + thread_id})
            assert r.status_code == 200

    def get_range(thread_id):
        for key in range(50):
            r = requests.get(f"{server}/cache/{key}")
            assert r.status_code == 200

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(put_range, t) for t in range(4)]
        futures += [ex.submit(get_range, t) for t in range(4)]
        for f in as_completed(futures):
            f.result()
