"""Tests for retry, rate limiting, circuit breaker, and the HTTP client."""

from __future__ import annotations

import httpx
import pytest
from app.core.config import CircuitBreakerConfig, RetryConfig
from app.core.exceptions import CircuitOpenError, RetryableHTTPError
from app.core.metrics import Metrics
from app.resilience.circuit_breaker import CircuitBreaker, CircuitState
from app.resilience.rate_limit import AsyncRateLimiter
from app.resilience.retry import retry_async

from tests.conftest import make_client


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def _noop_sleep(_seconds: float) -> None:
    return None


# --------------------------- retry ---------------------------

async def test_retry_succeeds_after_transient_failures() -> None:
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    result = await retry_async(
        flaky,
        config=RetryConfig(max_attempts=3, base_delay_seconds=0.0, max_delay_seconds=0.0),
        retry_on=(ValueError,),
        sleep=_noop_sleep,
    )
    assert result == "ok"
    assert calls["n"] == 3


async def test_retry_reraises_after_exhausting_attempts() -> None:
    async def always_fail() -> str:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await retry_async(
            always_fail,
            config=RetryConfig(max_attempts=2, base_delay_seconds=0.0, max_delay_seconds=0.0),
            retry_on=(ValueError,),
            sleep=_noop_sleep,
        )


async def test_retry_does_not_swallow_unlisted_exceptions() -> None:
    async def raise_type_error() -> str:
        raise TypeError("nope")

    with pytest.raises(TypeError):
        await retry_async(
            raise_type_error,
            config=RetryConfig(max_attempts=3),
            retry_on=(ValueError,),
            sleep=_noop_sleep,
        )


# ------------------------ rate limiter ------------------------

async def test_rate_limiter_sleeps_when_bucket_empty() -> None:
    clock = FakeClock()
    slept: list[float] = []

    async def record_sleep(seconds: float) -> None:
        slept.append(seconds)

    limiter = AsyncRateLimiter(2.0, clock=clock, sleep=record_sleep)
    # Bucket starts full with `rate` tokens (2). Drain them, then force a wait.
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()
    assert slept, "expected a throttling sleep once the bucket was empty"


# ----------------------- circuit breaker -----------------------

async def test_circuit_opens_after_threshold_and_recovers() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(
        CircuitBreakerConfig(failure_threshold=2, reset_timeout_seconds=5.0), clock=clock
    )
    assert breaker.allow() is True
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    assert breaker.allow() is False  # still within reset window

    clock.now += 6.0
    assert breaker.allow() is True  # half-open trial
    assert breaker.state is CircuitState.HALF_OPEN
    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED


# ---------------------- resilient client ----------------------

async def test_client_retries_on_503_then_succeeds(http_config, metrics: Metrics) -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    client = make_client(
        httpx.MockTransport(handler),
        base_url="https://api.test",
        config=http_config,
        metrics=metrics,
    )
    result = await client.get_json("/data")
    assert result == {"ok": True}
    assert attempts["n"] == 2
    assert metrics.get("http.retries") == 1
    await client.aclose()


async def test_client_opens_circuit_after_repeated_failures(
    http_config, metrics: Metrics
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = make_client(
        httpx.MockTransport(handler),
        base_url="https://api.test",
        config=http_config,
        metrics=metrics,
    )
    # threshold=3; each get_json exhausts retries -> one recorded failure each.
    for _ in range(3):
        with pytest.raises(RetryableHTTPError):
            await client.get_json("/data")

    with pytest.raises(CircuitOpenError):
        await client.get_json("/data")
    await client.aclose()
