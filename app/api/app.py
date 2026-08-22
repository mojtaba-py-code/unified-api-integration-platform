"""FastAPI application.

Thin HTTP layer over the ``Platform`` facade. The platform is created once on
startup (lifespan) and shared via dependency injection, so requests reuse
connectors, the cache, and DB connections rather than rebuilding them.
"""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import Secrets
from app.orchestrator import CollectionSelection, CollectionSummary
from app.platform import Platform

_PLATFORM_KEY = "platform"

#: Header carrying the shared secret for /collect.
API_KEY_HEADER = "X-API-Key"

#: Upper bound on how many connector fetches one request may trigger. Each
#: selection becomes an outbound HTTP call, so an uncapped list turns the
#: endpoint into an amplifier.
MAX_SELECTIONS = 25


class CollectRequest(BaseModel):
    selections: list[CollectionSelection] | None = Field(
        default=None, max_length=MAX_SELECTIONS
    )


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


@lru_cache(maxsize=1)
def _cached_secrets() -> Secrets:
    return Secrets()


def get_secrets() -> Secrets:  # overridden via dependency_overrides in tests
    return _cached_secrets()


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
    secrets: Secrets = Depends(get_secrets),
) -> None:
    """Gate an endpoint behind ``UNIFIED_API_KEY``.

    A missing key is a refusal, never a bypass: the guarded endpoint drives
    outbound requests on the caller's behalf, so shipping it open by default
    is precisely the failure this guard exists to prevent.
    """
    expected = secrets.api_key
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="endpoint disabled: UNIFIED_API_KEY is not configured",
        )
    # Compare on bytes: a header may legitimately carry non-ASCII, which the
    # str form of compare_digest rejects with a TypeError.
    supplied = (x_api_key or "").encode("utf-8")
    if not x_api_key or not hmac.compare_digest(supplied, expected.encode("utf-8")):
        raise HTTPException(
            status_code=401, detail=f"missing or invalid {API_KEY_HEADER}"
        )


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

    @app.post(
        "/collect",
        response_model=CollectionSummary,
        dependencies=[Depends(require_api_key)],
    )
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
