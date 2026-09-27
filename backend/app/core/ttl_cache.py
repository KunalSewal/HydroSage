"""A small thread-safe, bounded, expiring in-process cache.

For slow external lookups whose answers don't change within hours
(long-term rainfall, land use around an area). Per process by design:
each API instance warms its own copy after one lookup, and the gateway's
affinity routing sends a repeated area back to the same instance
(app/gateway.py). Nothing depends on it being populated.
"""

import threading
import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: float, max_entries: int) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._entries: OrderedDict[Any, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()  # sync endpoints run in a thread pool

    def get(self, key: Any) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            if time.monotonic() - stored_at >= self._ttl:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return value

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._entries[key] = (time.monotonic(), value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
