"""The unified record — the heart of "Unified" in the platform's name.

Every connector, no matter how different its upstream payload, maps its data
into this single shape. Downstream code (storage, API, CLI) only ever deals
with ``UnifiedRecord`` and stays completely ignorant of any specific API.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UnifiedRecord(BaseModel):
    """A single normalized datum from any source."""

    source: str = Field(description="Connector name, e.g. 'weather'.")
    record_type: str = Field(description="Kind of record, e.g. 'crypto_price'.")
    external_id: str = Field(description="Stable id, unique within the source.")
    title: str = Field(description="Human-readable label.")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Normalized, source-agnostic fields."
    )
    fetched_at: datetime = Field(default_factory=_utcnow)

    def dedupe_key(self) -> tuple[str, str]:
        """Identity used for upserts: one row per (source, external_id)."""
        return (self.source, self.external_id)
