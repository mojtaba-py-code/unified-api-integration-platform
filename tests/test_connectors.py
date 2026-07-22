"""Connector tests — each maps a mocked upstream payload to UnifiedRecords."""

from __future__ import annotations

from collections.abc import Callable

import httpx
from app.connectors.crypto import CryptoConnector
from app.connectors.github import GitHubConnector
from app.connectors.weather import WeatherConnector
from app.core.config import HttpConfig
from app.core.metrics import Metrics

from tests.conftest import make_client

Handler = Callable[[httpx.Request], httpx.Response]


def _client(
    handler: Handler, base_url: str, name: str, config: HttpConfig, metrics: Metrics
):
    return make_client(
        httpx.MockTransport(handler),
        base_url=base_url,
        config=config,
        metrics=metrics,
        name=name,
    )


async def test_weather_connector_maps_current_weather(http_config, metrics: Metrics) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/forecast"
        return httpx.Response(
            200,
            json={
                "current": {
                    "temperature_2m": 21.5,
                    "wind_speed_10m": 3.2,
                    "relative_humidity_2m": 55,
                    "time": "2026-07-21T12:00",
                }
            },
        )

    connector = WeatherConnector(
        _client(handler, "https://weather.test", "weather", http_config, metrics)
    )
    records = await connector.fetch(
        {"locations": [{"name": "Tehran", "latitude": 35.7, "longitude": 51.4}]}
    )

    assert len(records) == 1
    rec = records[0]
    assert rec.source == "weather"
    assert rec.record_type == "weather"
    assert rec.payload["temperature_c"] == 21.5
    assert rec.payload["location"] == "Tehran"
    await connector.aclose()


async def test_crypto_connector_maps_prices(http_config, metrics: Metrics) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "bitcoin": {"usd": 65000, "usd_24h_change": 1.2},
                "ethereum": {"usd": 3200, "usd_24h_change": -0.8},
            },
        )

    connector = CryptoConnector(
        _client(handler, "https://crypto.test", "crypto", http_config, metrics)
    )
    records = await connector.fetch({"ids": ["bitcoin", "ethereum"], "vs_currency": "usd"})

    assert {r.payload["coin"] for r in records} == {"bitcoin", "ethereum"}
    btc = next(r for r in records if r.payload["coin"] == "bitcoin")
    assert btc.payload["price"] == 65000
    assert btc.external_id == "bitcoin:usd"
    await connector.aclose()


async def test_crypto_connector_skips_missing_coin(http_config, metrics: Metrics) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"bitcoin": {"usd": 65000}})

    connector = CryptoConnector(
        _client(handler, "https://crypto.test", "crypto", http_config, metrics)
    )
    records = await connector.fetch({"ids": ["bitcoin", "dogecoin"], "vs_currency": "usd"})
    assert len(records) == 1  # dogecoin absent -> skipped, not fatal
    await connector.aclose()


async def test_github_connector_maps_repo(http_config, metrics: Metrics) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/python/cpython"
        return httpx.Response(
            200,
            json={
                "id": 81598961,
                "full_name": "python/cpython",
                "stargazers_count": 60000,
                "forks_count": 29000,
                "open_issues_count": 1500,
                "language": "Python",
                "description": "The Python programming language",
            },
        )

    connector = GitHubConnector(
        _client(handler, "https://github.test", "github", http_config, metrics)
    )
    records = await connector.fetch({"repos": ["python/cpython"]})

    assert len(records) == 1
    rec = records[0]
    assert rec.external_id == "81598961"
    assert rec.payload["stars"] == 60000
    assert rec.payload["language"] == "Python"
    await connector.aclose()
