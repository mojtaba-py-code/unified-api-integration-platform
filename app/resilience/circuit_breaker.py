"""Circuit breaker.

Stops hammering an upstream that is already failing. After
``failure_threshold`` consecutive failures the circuit *opens* and requests are
rejected immediately for ``reset_timeout`` seconds; then it goes *half-open* and
allows a single trial. A success closes it; a failure re-opens it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum

from app.core.config import CircuitBreakerConfig


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        config: CircuitBreakerConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = config.failure_threshold
        self._reset_timeout = config.reset_timeout_seconds
        self._clock = clock
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = 0.0

    @property
    def state(self) -> CircuitState:
        return self._state

    def allow(self) -> bool:
        """Return whether a request may proceed, advancing state if needed."""
        if self._state is CircuitState.OPEN:
            if self._clock() - self._opened_at >= self._reset_timeout:
                self._state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failures += 1
        if self._state is CircuitState.HALF_OPEN or self._failures >= self._threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
