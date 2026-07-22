"""Orchestrator tests — concurrency, caching, failure isolation."""

from __future__ import annotations

from typing import Any

from app.cache.ttl_cache import TTLCache
from app.connectors.base import BaseConnector
from app.core.metrics import Metrics
from app.normalize.schema import UnifiedRecord
from app.orchestrator import CollectionSelection, Orchestrator
from app.storage.repository import RecordRepository


class FakeConnector(BaseConnector):
    def __init__(
        self, name: str, records: list[UnifiedRecord] | None = None, fail: bool = False
    ) -> None:
        self.name = name
        self.record_type = name
        self._records = records or []
        self._fail = fail
        self.calls = 0

    async def fetch(self, params: dict[str, Any] | None = None) -> list[UnifiedRecord]:
        self.calls += 1
        if self._fail:
            raise RuntimeError("connector down")
        return self._records

    async def aclose(self) -> None:
        return None


def _rec(source: str, ext: str) -> UnifiedRecord:
    return UnifiedRecord(source=source, record_type=source, external_id=ext, title=ext, payload={})


async def _make_orchestrator(
    connectors: dict[str, BaseConnector], ttl: float = 0.0
) -> tuple[Orchestrator, RecordRepository, Metrics]:
    repo = RecordRepository(":memory:")
    await repo.init_db()
    metrics = Metrics()
    cache: TTLCache[list[UnifiedRecord]] = TTLCache(ttl)
    return Orchestrator(connectors, repo, cache, metrics), repo, metrics


async def test_collects_from_all_connectors_and_stores() -> None:
    connectors: dict[str, BaseConnector] = {
        "weather": FakeConnector("weather", [_rec("weather", "tehran")]),
        "crypto": FakeConnector("crypto", [_rec("crypto", "btc"), _rec("crypto", "eth")]),
    }
    orch, repo, _ = await _make_orchestrator(connectors)

    summary = await orch.collect()
    assert summary.total_records == 3
    assert summary.stored == 3
    assert {r.connector: r.status for r in summary.results} == {"weather": "ok", "crypto": "ok"}
    assert await repo.count() == 3


async def test_one_connector_failure_does_not_abort_others() -> None:
    connectors: dict[str, BaseConnector] = {
        "good": FakeConnector("good", [_rec("good", "1")]),
        "bad": FakeConnector("bad", fail=True),
    }
    orch, repo, metrics = await _make_orchestrator(connectors)

    summary = await orch.collect()
    statuses = {r.connector: r.status for r in summary.results}
    assert statuses == {"good": "ok", "bad": "error"}
    assert summary.stored == 1  # only the good connector's record persisted
    assert metrics.get("collect.errors") == 1


async def test_cache_prevents_second_fetch() -> None:
    fake = FakeConnector("weather", [_rec("weather", "tehran")])
    orch, _, metrics = await _make_orchestrator({"weather": fake}, ttl=60.0)

    sel = [CollectionSelection(connector="weather")]
    await orch.collect(sel)
    await orch.collect(sel)

    assert fake.calls == 1  # second collect served from cache
    assert metrics.get("cache.hits") == 1
    assert metrics.get("cache.misses") == 1


async def test_unknown_connector_reported_as_error() -> None:
    orch, _, _ = await _make_orchestrator({})
    summary = await orch.collect([CollectionSelection(connector="ghost")])
    assert summary.results[0].status == "error"
    assert "unknown" in (summary.results[0].error or "")
