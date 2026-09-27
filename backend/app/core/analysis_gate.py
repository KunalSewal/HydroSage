"""Bounds how many analyses one process runs at once, with a short,
bounded wait queue in front.

One analysis peaks around 305-500 MB (docs/DECISIONS.md D-012, D-013) and
each lab container is capped at 512 MB, so two at once is an OOM kill that
loses both callers' answers. uvicorn runs sync endpoints on a thread pool
of ~40 threads, which would happily start forty. The gate makes the limit
explicit: extra requests wait briefly for a slot, and once the queue is
full they are refused straight away (the caller answers 503 + Retry-After)
rather than piling up until something is killed.
"""

import asyncio


class AnalysisGate:
    def __init__(self, limit: int = 1, max_waiting: int = 8) -> None:
        self._semaphore = asyncio.Semaphore(limit)
        self._limit = limit
        self._max_waiting = max_waiting
        self.in_flight = 0
        self.waiting = 0

    async def acquire(self, timeout: float) -> bool:
        """True once a slot is held (the caller must release() it); False
        if the queue was full or no slot freed up within `timeout`."""
        if self.in_flight >= self._limit and self.waiting >= self._max_waiting:
            return False
        self.waiting += 1
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout)
        except TimeoutError:
            return False
        finally:
            self.waiting -= 1
        self.in_flight += 1
        return True

    def release(self) -> None:
        self.in_flight -= 1
        self._semaphore.release()
