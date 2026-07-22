"""A minimal async-safe TTL cache.

Avoids re-hitting an upstream API for identical requests within the TTL window.
Keyed by (connector, params) at the orchestrator layer.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

V = TypeVar("V")


@dataclass
class _Entry(Generic[V]):
    value: V
    expires_at: float


class TTLCache(Generic[V]):
    def __init__(
        self,
        ttl_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._store: dict[str, _Entry[V]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> V | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if self._clock() >= entry.expires_at:
                del self._store[key]
                return None
            return entry.value

    async def set(self, key: str, value: V) -> None:
        if self._ttl <= 0:
            return  # caching disabled
        async with self._lock:
            self._store[key] = _Entry(value=value, expires_at=self._clock() + self._ttl)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    @staticmethod
    def make_key(connector: str, params: dict[str, Any] | None) -> str:
        import json

        normalized = json.dumps(params or {}, sort_keys=True, default=str)
        return f"{connector}:{normalized}"
