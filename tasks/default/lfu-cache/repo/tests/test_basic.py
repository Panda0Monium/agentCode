"""
Public tests — visible to the agent via session.run_tests(suite="public").
Cover the happy path and core LFU behaviour.
"""

from lfu_cache import LFUCache


def test_get_missing_key_returns_minus_one():
    cache = LFUCache(2)
    assert cache.get(1) == -1


def test_put_then_get():
    cache = LFUCache(2)
    cache.put(1, 10)
    assert cache.get(1) == 10


def test_put_updates_existing_value():
    cache = LFUCache(2)
    cache.put(1, 10)
    cache.put(1, 99)
    assert cache.get(1) == 99


def test_frequency_beats_recency():
    """A more-frequently-used key survives over a more-recently-added key."""
    cache = LFUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    cache.get(1)       # freq[1]=2, freq[2]=1
    cache.put(3, 3)    # evicts key 2 (lowest freq), not key 1
    assert cache.get(2) == -1
    assert cache.get(1) == 1
    assert cache.get(3) == 3


def test_lru_tiebreak_among_equal_frequencies():
    """When all frequencies are equal the least recently used key is evicted."""
    cache = LFUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    # both have freq=1; key 1 is LRU
    cache.put(3, 3)    # evicts key 1
    assert cache.get(1) == -1
    assert cache.get(2) == 2
    assert cache.get(3) == 3


def test_capacity_one():
    cache = LFUCache(1)
    cache.put(1, 1)
    cache.put(2, 2)    # evicts key 1
    assert cache.get(1) == -1
    assert cache.get(2) == 2
