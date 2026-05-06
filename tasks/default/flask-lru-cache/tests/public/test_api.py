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


def test_health(server):
    r = requests.get(f"{server}/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_get_missing(server):
    _init(server, 2)
    assert _get(server, 1) == -1


def test_put_and_get(server):
    _init(server, 2)
    _put(server, 1, 10)
    assert _get(server, 1) == 10


def test_overwrite(server):
    _init(server, 2)
    _put(server, 1, 10)
    _put(server, 1, 99)
    assert _get(server, 1) == 99


def test_eviction(server):
    _init(server, 2)
    _put(server, 1, 10)
    _put(server, 2, 20)
    _put(server, 3, 30)   # key 1 is LRU → evicted
    assert _get(server, 1) == -1
    assert _get(server, 2) == 20
    assert _get(server, 3) == 30


def test_get_updates_recency(server):
    _init(server, 2)
    _put(server, 1, 10)
    _put(server, 2, 20)
    _get(server, 1)        # access 1 → 2 becomes LRU
    _put(server, 3, 30)   # evicts key 2
    assert _get(server, 1) == 10
    assert _get(server, 2) == -1
    assert _get(server, 3) == 30


def test_capacity_one(server):
    _init(server, 1)
    _put(server, 1, 10)
    _put(server, 2, 20)   # evicts key 1
    assert _get(server, 1) == -1
    assert _get(server, 2) == 20


def test_reinit_clears_cache(server):
    _init(server, 2)
    _put(server, 1, 10)
    _put(server, 2, 20)
    _init(server, 3)       # reset — all entries gone, new capacity
    assert _get(server, 1) == -1
    assert _get(server, 2) == -1


def test_concurrent_puts_no_crash(server):
    _init(server, 20)

    def put_many(thread_id):
        for i in range(25):
            key = thread_id * 25 + i
            r = requests.post(f"{server}/cache/{key}", json={"value": key})
            assert r.status_code == 200

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(put_many, t) for t in range(8)]
        for f in as_completed(futures):
            f.result()
