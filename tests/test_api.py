"""FastAPI endpoint tests, driven fully in-process (no server, no network)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from app.api.app import create_app, get_platform
from app.cache.ttl_cache import TTLCache
from app.connectors.base import BaseConnector
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


@pytest.fixture
async def client() -> Any:
    repo = RecordRepository(":memory:")
    await repo.init_db()
    metrics = Metrics()
    cache: TTLCache[list[UnifiedRecord]] = TTLCache(0.0)
    orch = Orchestrator({"weather": FakeConnector("weather")}, repo, cache, metrics)
    stub = StubPlatform(orch, repo, metrics)

    app = create_app()
    app.dependency_overrides[get_platform] = lambda: stub

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client
    finally:
        await repo.aclose()


async def test_health(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_list_connectors(client: httpx.AsyncClient) -> None:
    resp = await client.get("/connectors")
    assert resp.json() == {"connectors": ["weather"]}


async def test_collect_then_query_records(client: httpx.AsyncClient) -> None:
    collect = await client.post("/collect", json={})
    assert collect.status_code == 200
    body = collect.json()
    assert body["stored"] == 1
    assert body["results"][0]["connector"] == "weather"

    records = await client.get("/records", params={"source": "weather"})
    assert records.json()["count"] == 1

    metrics = await client.get("/metrics")
    assert metrics.json()["records.stored"] == 1
