"""
Private tests — grader-only, never shown to the agent.
Test correctness under complex eviction sequences, large inputs, and O(1) performance.
"""

import time

from lru_cache import LRUCache


# ------------------------------------------------------------------
# Correctness: tricky eviction ordering
# ------------------------------------------------------------------

def test_eviction_order_after_multiple_gets():
    cache = LRUCache(3)
    cache.put(1, 1)
    cache.put(2, 2)
    cache.put(3, 3)
    cache.get(1)       # order (LRU→MRU): 2, 3, 1
    cache.get(2)       # order: 3, 1, 2
    cache.put(4, 4)    # evicts 3
    assert cache.get(3) == -1
    assert cache.get(1) == 1
    assert cache.get(2) == 2
    assert cache.get(4) == 4


def test_update_does_not_increase_size():
    cache = LRUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    cache.put(1, 100)  # update, not insert — should not evict key 2
    assert cache.get(2) == 2
    assert cache.get(1) == 100


def test_update_refreshes_recency():
    cache = LRUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    cache.put(1, 100)  # update makes key 1 MRU
    cache.put(3, 3)    # should evict key 2
    assert cache.get(2) == -1
    assert cache.get(1) == 100
    assert cache.get(3) == 3


def test_interleaved_puts_and_gets():
    """Simulate a realistic access pattern."""
    cache = LRUCache(3)
    ops = [
        ("put", 1, 1), ("put", 2, 2), ("put", 3, 3),
        ("get", 1, 1),                 # refreshes 1
        ("put", 4, 4),                 # evicts 2
        ("get", 2, -1),
        ("get", 3, 3),                 # refreshes 3
        ("put", 5, 5),                 # evicts 1
        ("get", 1, -1),
        ("get", 3, 3),
        ("get", 4, 4),
        ("get", 5, 5),
    ]
    for op in ops:
        if op[0] == "put":
            cache.put(op[1], op[2])
        else:
            assert cache.get(op[1]) == op[2], f"get({op[1]}) expected {op[2]}"


def test_large_capacity_sequential_fill():
    n = 1000
    cache = LRUCache(n)
    for i in range(n):
        cache.put(i, i * 2)
    for i in range(n):
        assert cache.get(i) == i * 2


def test_eviction_after_full_sequential_fill():
    n = 100
    cache = LRUCache(n)
    for i in range(n):
        cache.put(i, i)
    # Adding one more should evict key 0 (LRU)
    cache.put(n, n)
    assert cache.get(0) == -1
    assert cache.get(1) == 1
    assert cache.get(n) == n


def test_repeated_same_key():
    cache = LRUCache(3)
    for i in range(100):
        cache.put(42, i)
    assert cache.get(42) == 99


# ------------------------------------------------------------------
# Performance: both get and put must be O(1)
# A correct doubly-linked-list + hashmap implementation handles
# 200k ops in well under 1 second; O(n) implementations take ~10s+.
# ------------------------------------------------------------------

def test_performance_put_get_o1():
    n = 200_000
    cache = LRUCache(n // 2)

    start = time.perf_counter()
    for i in range(n):
        cache.put(i % (n // 2), i)
    for i in range(n):
        cache.get(i % (n // 2))
    elapsed = time.perf_counter() - start

    assert elapsed < 2.0, (
        f"Expected O(1) ops to complete 400k operations in <2s, took {elapsed:.2f}s. "
        "Likely using an O(n) data structure."
    )
