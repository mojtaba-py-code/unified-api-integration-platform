"""Shared fixtures. Every test runs fully offline — no real network calls."""

from __future__ import annotations

import httpx
import pytest
from app.core.config import (
    CircuitBreakerConfig,
    Config,
    ConnectorConfig,
    HttpConfig,
    RateLimitConfig,
    RetryConfig,
)
from app.core.metrics import Metrics
from app.resilience.http_client import ResilientHttpClient


@pytest.fixture
def http_config() -> HttpConfig:
    # Fast, deterministic settings for tests.
    return HttpConfig(
        timeout_seconds=1.0,
        retry=RetryConfig(max_attempts=3, base_delay_seconds=0.0, max_delay_seconds=0.0),
        rate_limit=RateLimitConfig(requests_per_second=1000.0),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=3, reset_timeout_seconds=0.01),
    )


@pytest.fixture
def metrics() -> Metrics:
    return Metrics()


@pytest.fixture
def test_config(tmp_path) -> Config:  # type: ignore[no-untyped-def]
    db = tmp_path / "test.db"
    return Config(
        app={"database_path": str(db), "cache_ttl_seconds": 0},  # type: ignore[arg-type]
        http=HttpConfig(),
        connectors={
            "weather": ConnectorConfig(enabled=True, base_url="https://weather.test"),
            "crypto": ConnectorConfig(enabled=True, base_url="https://crypto.test"),
            "github": ConnectorConfig(enabled=True, base_url="https://github.test"),
        },
    )


def make_client(
    handler: httpx.MockTransport,
    *,
    base_url: str,
    config: HttpConfig,
    metrics: Metrics,
    name: str = "test",
) -> ResilientHttpClient:
    """Build a ResilientHttpClient backed by an in-memory mock transport."""
    mock_client = httpx.AsyncClient(base_url=base_url, transport=handler)
    return ResilientHttpClient(
        name=name, base_url=base_url, config=config, metrics=metrics, client=mock_client
    )
