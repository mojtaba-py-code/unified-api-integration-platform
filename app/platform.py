"""Platform facade — wires the whole system together.

Constructs config, metrics, connectors, cache, repository and orchestrator, and
manages their lifecycle. Both the FastAPI app and the CLI use this single entry
point, so wiring lives in exactly one place.
"""

from __future__ import annotations

from types import TracebackType

from app.cache.ttl_cache import TTLCache
from app.connectors.registry import build_connectors
from app.core.config import Config, Secrets, load_config
from app.core.logging import configure_logging
from app.core.metrics import Metrics
from app.normalize.schema import UnifiedRecord
from app.orchestrator import Orchestrator
from app.storage.repository import RecordRepository


class Platform:
    def __init__(self, config: Config, secrets: Secrets | None = None) -> None:
        self.config = config
        self.secrets = secrets or Secrets()
        self.metrics = Metrics()
        self._repository = RecordRepository(config.app.database_path)
        self._connectors = build_connectors(config, self.metrics, self.secrets)
        cache: TTLCache[list[UnifiedRecord]] = TTLCache(config.app.cache_ttl_seconds)
        self.orchestrator = Orchestrator(
            connectors=self._connectors,
            repository=self._repository,
            cache=cache,
            metrics=self.metrics,
        )

    @property
    def repository(self) -> RecordRepository:
        return self._repository

    @classmethod
    def from_config_file(cls, path: str | None = None) -> Platform:
        configure_logging()
        return cls(load_config(path))

    async def startup(self) -> None:
        await self._repository.init_db()

    async def shutdown(self) -> None:
        for connector in self._connectors.values():
            await connector.aclose()
        await self._repository.aclose()

    async def __aenter__(self) -> Platform:
        await self.startup()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.shutdown()
