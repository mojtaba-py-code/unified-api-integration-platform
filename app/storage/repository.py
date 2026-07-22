"""SQLite persistence for unified records.

Uses ``aiosqlite`` so storage never blocks the event loop. A single connection
is held open for the repository's lifetime — this is required for ``:memory:``
databases (a fresh connection would see an empty schema) and is more efficient
for file databases too. Records are upserted on (source, external_id):
re-collecting the same entity updates the existing row rather than duplicating.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from app.core.exceptions import PlatformError
from app.normalize.schema import UnifiedRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT    NOT NULL,
    record_type  TEXT    NOT NULL,
    external_id  TEXT    NOT NULL,
    title        TEXT    NOT NULL,
    payload      TEXT    NOT NULL,
    fetched_at   TEXT    NOT NULL,
    UNIQUE(source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_records_source ON records(source);
CREATE INDEX IF NOT EXISTS idx_records_type ON records(record_type);
"""


class RecordRepository:
    def __init__(self, database_path: str) -> None:
        self._path = database_path
        self._db: aiosqlite.Connection | None = None

    async def init_db(self) -> None:
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    @property
    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise PlatformError("repository not initialized; call init_db() first")
        return self._db

    async def upsert_many(self, records: list[UnifiedRecord]) -> int:
        """Insert or update records; returns the number written."""
        if not records:
            return 0
        rows = [
            (
                r.source,
                r.record_type,
                r.external_id,
                r.title,
                json.dumps(r.payload, ensure_ascii=False, default=str),
                r.fetched_at.isoformat(),
            )
            for r in records
        ]
        await self._conn.executemany(
            """
            INSERT INTO records (source, record_type, external_id, title, payload, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, external_id) DO UPDATE SET
                record_type = excluded.record_type,
                title       = excluded.title,
                payload     = excluded.payload,
                fetched_at  = excluded.fetched_at
            """,
            rows,
        )
        await self._conn.commit()
        return len(rows)

    async def list_records(
        self,
        *,
        source: str | None = None,
        record_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        if source:
            clauses.append("source = ?")
            args.append(source)
        if record_type:
            clauses.append("record_type = ?")
            args.append(record_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        args.append(limit)

        cursor = await self._conn.execute(
            f"SELECT * FROM records {where} ORDER BY fetched_at DESC, id DESC LIMIT ?", args
        )
        rows = await cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    async def count(self) -> int:
        cursor = await self._conn.execute("SELECT COUNT(*) FROM records")
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def aclose(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @staticmethod
    def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "source": row["source"],
            "record_type": row["record_type"],
            "external_id": row["external_id"],
            "title": row["title"],
            "payload": json.loads(row["payload"]),
            "fetched_at": row["fetched_at"],
        }
