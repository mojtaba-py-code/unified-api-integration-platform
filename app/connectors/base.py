"""The connector contract.

Adding a new API to the platform means writing one subclass of
``BaseConnector`` — nothing in the core (orchestrator, storage, API, CLI) ever
changes. That single fact is what makes this a *platform* and not a bag of
scripts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.normalize.schema import UnifiedRecord
from app.resilience.http_client import ResilientHttpClient


class BaseConnector(ABC):
    #: Unique connector name; also the ``source`` on emitted records.
    name: str = ""
    #: Default ``record_type`` for emitted records.
    record_type: str = ""

    def __init__(self, http: ResilientHttpClient) -> None:
        self._http = http

    @abstractmethod
    async def fetch(self, params: dict[str, Any] | None = None) -> list[UnifiedRecord]:
        """Fetch from the upstream API and return normalized records."""

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        """Sensible parameters so ``fetch()`` works out-of-the-box for demos."""
        return {}

    async def aclose(self) -> None:
        await self._http.aclose()
