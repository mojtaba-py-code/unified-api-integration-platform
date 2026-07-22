"""Exponential-backoff retry with jitter.

Transient failures (a dropped connection, a 503) are the *normal* case when
talking to real APIs, so retrying is a first-class concern rather than an
afterthought. Jitter spreads retries out so a fleet of clients doesn't
stampede a recovering server.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.config import RetryConfig

T = TypeVar("T")


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    config: RetryConfig,
    retry_on: tuple[type[BaseException], ...],
    on_retry: Callable[[int, BaseException], None] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: random.Random | None = None,
) -> T:
    """Run ``operation``, retrying on the given exception types.

    ``sleep`` and ``rng`` are injectable so tests stay fast and deterministic.
    """
    randomizer = rng or random.Random()
    last_exc: BaseException | None = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            return await operation()
        except retry_on as exc:
            last_exc = exc
            if attempt >= config.max_attempts:
                break
            if on_retry is not None:
                on_retry(attempt, exc)
            # Full-jitter backoff: uniform(0, min(cap, base * 2**(attempt-1))).
            ceiling = min(
                config.max_delay_seconds,
                config.base_delay_seconds * (2 ** (attempt - 1)),
            )
            await sleep(randomizer.uniform(0, ceiling))

    assert last_exc is not None  # unreachable: loop only breaks after an exception
    raise last_exc
