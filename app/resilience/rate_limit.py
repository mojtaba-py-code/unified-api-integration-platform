"""Async token-bucket rate limiter.

Keeps us a good citizen of the upstream API: never exceed N requests/second,
regardless of how many coroutines call ``acquire`` concurrently.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable


class AsyncRateLimiter:
    """A token bucket refilled continuously at ``rate`` tokens per second."""

    def __init__(
        self,
        rate: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self._rate = rate
        self._capacity = rate
        self._tokens = rate
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._updated = now

    async def acquire(self) -> None:
        """Block until a token is available, then consume it."""
        async with self._lock:
            self._refill()
            if self._tokens < 1:
                deficit = 1 - self._tokens
                await self._sleep(deficit / self._rate)
                self._refill()
            self._tokens -= 1
