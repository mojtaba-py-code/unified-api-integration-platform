"""The orchestrator — concurrent collection across connectors.

Given a set of (connector, params) selections it fetches from all of them
*concurrently* with ``asyncio.gather``, serving from cache when possible,
persisting the results, and returning a structured, per-connector summary. One
connector failing never aborts the others.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from app.cache.ttl_cache import TTLCache
from app.connectors.base import BaseConnector
from app.core.logging import get_logger
from app.core.metrics import Metrics
from app.normalize.schema import UnifiedRecord
from app.storage.repository import RecordRepository

logger = get_logger(__name__)


class CollectionSelection(BaseModel):
    connector: str
    params: dict[str, Any] | None = None


class ConnectorResult(BaseModel):
    connector: str
    status: str  # "ok" | "error"
    record_count: int = 0
    cached: bool = False
    error: str | None = None


class CollectionSummary(BaseModel):
    total_records: int
    stored: int
    results: list[ConnectorResult]


class Orchestrator:
    def __init__(
        self,
        connectors: dict[str, BaseConnector],
        repository: RecordRepository,
        cache: TTLCache[list[UnifiedRecord]],
        metrics: Metrics,
    ) -> None:
        self._connectors = connectors
        self._repository = repository
        self._cache = cache
        self._metrics = metrics

    def available(self) -> list[str]:
        return sorted(self._connectors)

    async def collect(
        self, selections: list[CollectionSelection] | None = None
    ) -> CollectionSummary:
        """Collect from the selected connectors (all enabled ones by default)."""
        if selections is None:
            selections = [CollectionSelection(connector=name) for name in self._connectors]

        results = await asyncio.gather(
            *(self._collect_one(sel) for sel in selections)
        )

        all_records: list[UnifiedRecord] = []
        connector_results: list[ConnectorResult] = []
        for result, records in results:
            connector_results.append(result)
            all_records.extend(records)

        stored = await self._repository.upsert_many(all_records)
        self._metrics.increment("records.stored", stored)

        return CollectionSummary(
            total_records=len(all_records),
            stored=stored,
            results=connector_results,
        )

    async def _collect_one(
        self, selection: CollectionSelection
    ) -> tuple[ConnectorResult, list[UnifiedRecord]]:
        name = selection.connector
        connector = self._connectors.get(name)
        if connector is None:
            return (
                ConnectorResult(connector=name, status="error", error="unknown connector"),
                [],
            )

        cache_key = TTLCache.make_key(name, selection.params)
        cached = await self._cache.get(cache_key)
        if cached is not None:
            self._metrics.increment("cache.hits")
            return (
                ConnectorResult(
                    connector=name, status="ok", record_count=len(cached), cached=True
                ),
                cached,
            )
        self._metrics.increment("cache.misses")

        try:
            records = await connector.fetch(selection.params)
        except Exception as exc:  # noqa: BLE001 — isolate connector failures
            self._metrics.increment("collect.errors")
            logger.error(
                "connector failed",
                extra={"context": {"connector": name, "error": str(exc)}},
            )
            return (
                ConnectorResult(connector=name, status="error", error=str(exc)),
                [],
            )

        await self._cache.set(cache_key, records)
        return (
            ConnectorResult(connector=name, status="ok", record_count=len(records)),
            records,
        )
