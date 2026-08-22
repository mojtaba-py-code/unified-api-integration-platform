"""FastAPI endpoint tests, driven fully in-process (no server, no network)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from app.api.app import API_KEY_HEADER, MAX_SELECTIONS, create_app, get_platform, get_secrets
from app.cache.ttl_cache import TTLCache
from app.connectors.base import BaseConnector
from app.core.config import Secrets
from app.core.metrics import Metrics
from app.normalize.schema import UnifiedRecord
from app.orchestrator import Orchestrator
from app.storage.repository import RecordRepository


class FakeConnector(BaseConnector):
    def __init__(self, name: str) -> None:
        self.name = name
        self.record_type = name

    async def fetch(self, params: dict[str, Any] | None = None) -> list[UnifiedRecord]:
        return [
            UnifiedRecord(
                source=self.name, record_type=self.name,
                external_id="1", title="one", payload={"v": 1},
            )
        ]

    async def aclose(self) -> None:
        return None


class StubPlatform:
    def __init__(
        self, orchestrator: Orchestrator, repository: RecordRepository, metrics: Metrics
    ) -> None:
        self.orchestrator = orchestrator
        self.repository = repository
        self.metrics = metrics


API_KEY = "test-collect-key"
AUTH = {API_KEY_HEADER: API_KEY}


@asynccontextmanager
async def _api_client(api_key: str | None) -> AsyncIterator[httpx.AsyncClient]:
    repo = RecordRepository(":memory:")
    await repo.init_db()
    metrics = Metrics()
    cache: TTLCache[list[UnifiedRecord]] = TTLCache(0.0)
    orch = Orchestrator({"weather": FakeConnector("weather")}, repo, cache, metrics)
    stub = StubPlatform(orch, repo, metrics)

    app = create_app()
    app.dependency_overrides[get_platform] = lambda: stub
    app.dependency_overrides[get_secrets] = lambda: Secrets(api_key=api_key)

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client
    finally:
        await repo.aclose()


@pytest.fixture
async def client() -> Any:
    async with _api_client(API_KEY) as http_client:
        yield http_client


@pytest.fixture
async def unkeyed_client() -> Any:
    """An instance started without UNIFIED_API_KEY in the environment."""
    async with _api_client(None) as http_client:
        yield http_client


async def test_health(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_list_connectors(client: httpx.AsyncClient) -> None:
    resp = await client.get("/connectors")
    assert resp.json() == {"connectors": ["weather"]}


async def test_collect_then_query_records(client: httpx.AsyncClient) -> None:
    collect = await client.post("/collect", json={}, headers=AUTH)
    assert collect.status_code == 200
    body = collect.json()
    assert body["stored"] == 1
    assert body["results"][0]["connector"] == "weather"

    records = await client.get("/records", params={"source": "weather"})
    assert records.json()["count"] == 1

    metrics = await client.get("/metrics")
    assert metrics.json()["records.stored"] == 1


async def test_collect_rejects_missing_api_key(client: httpx.AsyncClient) -> None:
    resp = await client.post("/collect", json={})
    assert resp.status_code == 401


async def test_collect_rejects_wrong_api_key(client: httpx.AsyncClient) -> None:
    resp = await client.post("/collect", json={}, headers={API_KEY_HEADER: "wrong"})
    assert resp.status_code == 401


async def test_collect_refused_when_no_key_is_configured(
    unkeyed_client: httpx.AsyncClient,
) -> None:
    """An unset key must close the endpoint, not open it."""
    resp = await unkeyed_client.post("/collect", json={}, headers=AUTH)
    assert resp.status_code == 503

    resp = await unkeyed_client.post("/collect", json={})
    assert resp.status_code == 503


async def test_collect_caps_the_number_of_selections(client: httpx.AsyncClient) -> None:
    selections = [{"connector": "weather"} for _ in range(MAX_SELECTIONS + 1)]
    resp = await client.post("/collect", json={"selections": selections}, headers=AUTH)
    assert resp.status_code == 422

    at_the_cap = [{"connector": "weather"} for _ in range(MAX_SELECTIONS)]
    resp = await client.post("/collect", json={"selections": at_the_cap}, headers=AUTH)
    assert resp.status_code == 200
