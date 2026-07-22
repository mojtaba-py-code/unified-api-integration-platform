"""A resilient HTTP client.

Composes the three resilience primitives — rate limiting, retry with backoff,
and a circuit breaker — around a single ``httpx.AsyncClient``. Connectors talk
only to this client and never worry about transient failures themselves.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import HttpConfig
from app.core.exceptions import CircuitOpenError, RetryableHTTPError
from app.core.logging import get_logger
from app.core.metrics import Metrics
from app.resilience.circuit_breaker import CircuitBreaker
from app.resilience.rate_limit import AsyncRateLimiter
from app.resilience.retry import retry_async

logger = get_logger(__name__)

# Status codes that represent a transient condition worth retrying.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class ResilientHttpClient:
    """Per-connector HTTP client with isolated rate limiter and breaker."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        config: HttpConfig,
        metrics: Metrics,
        headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._name = name
        self._config = config
        self._metrics = metrics
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=config.timeout_seconds,
            headers=headers or {},
        )
        self._rate_limiter = AsyncRateLimiter(config.rate_limit.requests_per_second)
        self._breaker = CircuitBreaker(config.circuit_breaker)

    async def get_json(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        """GET ``path`` and return parsed JSON, applying all resilience policies."""
        if not self._breaker.allow():
            self._metrics.increment("http.circuit_open")
            raise CircuitOpenError(f"circuit open for connector '{self._name}'")

        async def _attempt() -> Any:
            await self._rate_limiter.acquire()
            self._metrics.increment("http.requests")
            response = await self._client.get(path, params=params)
            if response.status_code in RETRYABLE_STATUS:
                raise RetryableHTTPError(response.status_code, str(response.url))
            response.raise_for_status()
            return response.json()

        def _log_retry(attempt: int, exc: BaseException) -> None:
            self._metrics.increment("http.retries")
            logger.warning(
                "retrying request",
                extra={"context": {"connector": self._name, "attempt": attempt, "error": str(exc)}},
            )

        try:
            result = await retry_async(
                _attempt,
                config=self._config.retry,
                retry_on=(httpx.TransportError, RetryableHTTPError),
                on_retry=_log_retry,
            )
        except Exception:
            self._metrics.increment("http.errors")
            self._breaker.record_failure()
            raise
        else:
            self._breaker.record_success()
            return result

    async def aclose(self) -> None:
        await self._client.aclose()
