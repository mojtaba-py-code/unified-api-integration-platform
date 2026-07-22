"""Tests for the unified schema, TTL cache, and SQLite repository."""

from __future__ import annotations

from app.cache.ttl_cache import TTLCache
from app.normalize.schema import UnifiedRecord
from app.storage.repository import RecordRepository


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _record(external_id: str = "x", title: str = "t") -> UnifiedRecord:
    return UnifiedRecord(
        source="weather", record_type="weather", external_id=external_id,
        title=title, payload={"temperature_c": 20},
    )


# --------------------------- schema ---------------------------

def test_unified_record_dedupe_key() -> None:
    rec = _record("berlin")
    assert rec.dedupe_key() == ("weather", "berlin")


def test_unified_record_sets_fetched_at() -> None:
    assert _record().fetched_at is not None


# ---------------------------- cache ----------------------------

async def test_cache_hit_then_expiry() -> None:
    clock = FakeClock()
    cache: TTLCache[str] = TTLCache(10.0, clock=clock)
    await cache.set("k", "v")
    assert await cache.get("k") == "v"

    clock.now = 11.0
    assert await cache.get("k") is None  # expired


async def test_cache_disabled_when_ttl_zero() -> None:
    cache: TTLCache[str] = TTLCache(0.0)
    await cache.set("k", "v")
    assert await cache.get("k") is None


def test_cache_key_is_order_independent() -> None:
    a = TTLCache.make_key("crypto", {"ids": ["btc"], "vs": "usd"})
    b = TTLCache.make_key("crypto", {"vs": "usd", "ids": ["btc"]})
    assert a == b


# -------------------------- repository --------------------------

async def test_repository_upsert_and_list() -> None:
    repo = RecordRepository(":memory:")
    await repo.init_db()

    written = await repo.upsert_many([_record("a", "first"), _record("b", "second")])
    assert written == 2
    assert await repo.count() == 2

    rows = await repo.list_records(source="weather", limit=10)
    assert len(rows) == 2
    assert {r["external_id"] for r in rows} == {"a", "b"}


async def test_repository_upsert_is_idempotent() -> None:
    repo = RecordRepository(":memory:")
    await repo.init_db()

    await repo.upsert_many([_record("a", "old title")])
    await repo.upsert_many([_record("a", "new title")])  # same (source, external_id)

    assert await repo.count() == 1  # updated, not duplicated
    rows = await repo.list_records(limit=10)
    assert rows[0]["title"] == "new title"


async def test_repository_filters_by_type() -> None:
    repo = RecordRepository(":memory:")
    await repo.init_db()
    await repo.upsert_many([
        UnifiedRecord(
            source="crypto", record_type="crypto_price",
            external_id="btc", title="btc", payload={},
        ),
        _record("berlin"),
    ])
    rows = await repo.list_records(record_type="crypto_price", limit=10)
    assert len(rows) == 1
    assert rows[0]["source"] == "crypto"
