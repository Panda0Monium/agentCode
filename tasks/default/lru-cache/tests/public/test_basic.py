"""
Public tests — visible to the agent via session.run_tests(suite="public").
Cover the happy path and the most obvious edge cases.
"""

from lru_cache import LRUCache


def test_get_missing_key_returns_minus_one():
    cache = LRUCache(2)
    assert cache.get(1) == -1


def test_put_then_get():
    cache = LRUCache(2)
    cache.put(1, 10)
    assert cache.get(1) == 10


def test_put_overwrites_existing_key():
    cache = LRUCache(2)
    cache.put(1, 10)
    cache.put(1, 99)
    assert cache.get(1) == 99


def test_evicts_lru_when_over_capacity():
    cache = LRUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    cache.put(3, 3)   # should evict key 1
    assert cache.get(1) == -1
    assert cache.get(2) == 2
    assert cache.get(3) == 3


def test_get_refreshes_recency():
    cache = LRUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    cache.get(1)       # key 1 is now most recently used
    cache.put(3, 3)    # should evict key 2, not key 1
    assert cache.get(1) == 1
    assert cache.get(2) == -1
    assert cache.get(3) == 3


def test_capacity_one():
    cache = LRUCache(1)
    cache.put(1, 1)
    cache.put(2, 2)    # evicts key 1
    assert cache.get(1) == -1
    assert cache.get(2) == 2
