from app.core import ttl_cache
from app.core.ttl_cache import TTLCache


def test_returns_what_was_stored():
    cache = TTLCache(ttl_seconds=60, max_entries=10)
    cache.set("k", 42)
    assert cache.get("k") == 42


def test_expires_entries_after_the_ttl(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(ttl_cache.time, "monotonic", lambda: now[0])
    cache = TTLCache(ttl_seconds=60, max_entries=10)
    cache.set("k", 1)
    now[0] += 61
    assert cache.get("k") is None


def test_evicts_the_least_recently_used_past_its_bound():
    cache = TTLCache(ttl_seconds=60, max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # a is now more recent than b
    cache.set("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1 and cache.get("c") == 3


def test_clear_empties_it():
    cache = TTLCache(ttl_seconds=60, max_entries=10)
    cache.set("a", 1)
    cache.clear()
    assert cache.get("a") is None
