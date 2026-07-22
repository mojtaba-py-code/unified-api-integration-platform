"""In-memory metrics.

A tiny, dependency-free counter store. In production this would be swapped for
Prometheus, but the interface (`increment` / `snapshot`) stays the same, which
is the whole point of keeping observability behind a seam.
"""

from __future__ import annotations

import threading
from collections import defaultdict


class Metrics:
    """Thread-safe monotonic counters."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def get(self, name: str) -> int:
        with self._lock:
            return self._counters[name]

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
