"""
Private tests — grader-only, never shown to the agent.
Target the subtle correctness properties of LFU that agents most often get wrong,
plus an O(1) performance check.
"""

import time

from lfu_cache import LFUCache


# ------------------------------------------------------------------
# Correctness: tricky frequency and eviction edge cases
# ------------------------------------------------------------------

def test_put_to_existing_key_increments_frequency():
    """put(key, val) on an existing key raises its frequency like a get."""
    cache = LFUCache(2)
    cache.put(1, 1)    # freq[1]=1
    cache.put(2, 2)    # freq[2]=1
    cache.put(1, 10)   # update: freq[1]=2, freq[2]=1
    cache.put(3, 3)    # evicts key 2 (freq=1, LRU), not key 1
    assert cache.get(2) == -1
    assert cache.get(1) == 10
    assert cache.get(3) == 3


def test_new_key_resets_min_freq_to_one():
    """After eviction, inserting a new key must reset min_freq to 1."""
    cache = LFUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    cache.get(1)       # freq[1]=2, freq[2]=1
    cache.get(1)       # freq[1]=3, freq[2]=1
    cache.put(3, 3)    # evicts key 2 (min_freq=1); inserts key 3 at freq=1 → min_freq=1
    cache.put(4, 4)    # must evict key 3 (freq=1), not key 1 (freq=3)
    assert cache.get(3) == -1
    assert cache.get(1) == 1
    assert cache.get(4) == 4


def test_get_empties_min_freq_bucket():
    """Getting the sole key in the min_freq bucket must advance min_freq."""
    cache = LFUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    cache.get(1)       # freq[1]=2, freq[2]=1 → min_freq stays 1 (key 2)
    cache.get(2)       # freq[2]=2, freq-1 bucket now empty → min_freq becomes 2
    # Both keys at freq=2; key 1 is LRU between them.
    cache.put(3, 3)    # evicts key 1
    assert cache.get(1) == -1
    assert cache.get(2) == 2
    assert cache.get(3) == 3


def test_frequency_tiebreak_lru_order():
    """Among multiple keys at the same frequency, evictions follow LRU order."""
    cache = LFUCache(3)
    cache.put(1, 1)
    cache.put(2, 2)
    cache.put(3, 3)
    cache.get(2)       # freq[2]=2; freq[1]=freq[3]=1; LRU among freq-1 is key 1
    cache.put(4, 4)    # evicts key 1 (LRU at min_freq=1)
    assert cache.get(1) == -1
    cache.put(5, 5)    # evicts key 3 (now LRU at min_freq=1)
    assert cache.get(3) == -1
    assert cache.get(2) == 2
    assert cache.get(4) == 4
    assert cache.get(5) == 5


def test_update_does_not_evict_when_not_full():
    """Updating an existing key must never trigger an eviction."""
    cache = LFUCache(3)
    cache.put(1, 1)
    cache.put(2, 2)
    # Only 2 of 3 slots used — update should not evict anything.
    cache.put(1, 100)
    assert cache.get(1) == 100
    assert cache.get(2) == 2


def test_interleaved_ops_complex_sequence():
    """Longer mixed sequence with known expected results."""
    cache = LFUCache(3)
    cache.put(1, 1)
    cache.put(2, 2)
    cache.put(3, 3)
    cache.get(1)        # freq[1]=2
    cache.get(1)        # freq[1]=3
    cache.get(2)        # freq[2]=2
    cache.put(4, 4)     # min_freq=1 → evicts key 3; freq[4]=1
    assert cache.get(3) == -1
    cache.get(4)        # freq[4]=2
    cache.put(5, 5)     # min_freq=1 → no freq-1 keys; wait — 4 is now freq 2
    # After get(4): freq = {1:3, 2:2, 4:2}, none at freq 1 → min_freq=2
    # put(5,5): evict LRU at min_freq=2; key 2 and 4 are both at freq 2;
    # key 2 was moved to freq-2 bucket before key 4, so key 2 is LRU.
    assert cache.get(2) == -1
    assert cache.get(1) == 1
    assert cache.get(4) == 4
    assert cache.get(5) == 5


def test_repeated_puts_same_key_high_frequency():
    """Repeated puts to the same key drive its frequency very high."""
    cache = LFUCache(2)
    cache.put(1, 0)
    for i in range(1, 200):
        cache.put(1, i)      # freq[1] grows to 200, value becomes 199
    cache.put(2, 99)         # freq[2]=1; min_freq=1
    cache.put(3, 88)         # evicts key 2 (min_freq=1), not key 1
    assert cache.get(2) == -1
    assert cache.get(1) == 199
    assert cache.get(3) == 88


def test_large_sequential_correctness():
    n = 500
    cache = LFUCache(n)
    for i in range(n):
        cache.put(i, i * 3)
    for i in range(n):
        assert cache.get(i) == i * 3


# ------------------------------------------------------------------
# Performance: get and put must both be O(1)
# ------------------------------------------------------------------

def test_performance_o1():
    n = 200_000
    cache = LFUCache(n // 2)

    start = time.perf_counter()
    for i in range(n):
        cache.put(i % (n // 2), i)
    for i in range(n):
        cache.get(i % (n // 2))
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0, (
        f"Expected O(1) ops to finish 400k operations in <2s, took {elapsed:.2f}s. "
        "Likely using an O(n) data structure."
    )
