"""FastAPI application.

Thin HTTP layer over the ``Platform`` facade. The platform is created once on
startup (lifespan) and shared via dependency injection, so requests reuse
connectors, the cache, and DB connections rather than rebuilding them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from app.orchestrator import CollectionSelection, CollectionSummary
from app.platform import Platform

_PLATFORM_KEY = "platform"


class CollectRequest(BaseModel):
    selections: list[CollectionSelection] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    platform = Platform.from_config_file()
    await platform.startup()
    app.state.platform = platform
    try:
        yield
    finally:
        await platform.shutdown()


def get_platform() -> Platform:  # overridden via dependency_overrides in tests
    raise RuntimeError("platform dependency not configured")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Unified API Integration Platform",
        version="1.0.0",
        description="Integrate multiple external APIs behind one unified interface.",
        lifespan=lifespan,
    )

    def _platform_from_state() -> Platform:
        platform: Platform | None = getattr(app.state, _PLATFORM_KEY, None)
        if platform is None:
            raise HTTPException(status_code=503, detail="platform not ready")
        return platform

    app.dependency_overrides.setdefault(get_platform, _platform_from_state)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/connectors")
    async def connectors(platform: Platform = Depends(get_platform)) -> dict[str, list[str]]:
        return {"connectors": platform.orchestrator.available()}

    @app.post("/collect", response_model=CollectionSummary)
    async def collect(
        platform: Platform = Depends(get_platform),
        request: CollectRequest = Body(default_factory=CollectRequest),
    ) -> CollectionSummary:
        return await platform.orchestrator.collect(request.selections)

    @app.get("/records")
    async def records(
        source: str | None = Query(default=None),
        record_type: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
        platform: Platform = Depends(get_platform),
    ) -> dict[str, Any]:
        rows = await platform.repository.list_records(
            source=source, record_type=record_type, limit=limit
        )
        return {"count": len(rows), "records": rows}

    @app.get("/metrics")
    async def metrics(platform: Platform = Depends(get_platform)) -> dict[str, int]:
        return platform.metrics.snapshot()

    return app


app = create_app()
