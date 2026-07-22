"""Connector registry.

Maps connector names to classes and builds live, resilient instances from
config. This is the *only* place that knows the full set of connectors, so
registering a new one is a single-line change here.
"""

from __future__ import annotations

from app.connectors.base import BaseConnector
from app.connectors.crypto import CryptoConnector
from app.connectors.github import GitHubConnector
from app.connectors.weather import WeatherConnector
from app.core.config import Config, Secrets
from app.core.metrics import Metrics
from app.resilience.http_client import ResilientHttpClient

# name -> connector class. Add a new API by adding a line here.
CONNECTOR_TYPES: dict[str, type[BaseConnector]] = {
    WeatherConnector.name: WeatherConnector,
    CryptoConnector.name: CryptoConnector,
    GitHubConnector.name: GitHubConnector,
}


def build_connectors(
    config: Config, metrics: Metrics, secrets: Secrets | None = None
) -> dict[str, BaseConnector]:
    """Instantiate every *enabled* connector with its own resilient client."""
    secrets = secrets or Secrets()
    connectors: dict[str, BaseConnector] = {}

    for name, conn_config in config.connectors.items():
        if not conn_config.enabled:
            continue
        connector_cls = CONNECTOR_TYPES.get(name)
        if connector_cls is None:
            raise ValueError(f"unknown connector in config: {name!r}")

        headers = _headers_for(name, secrets)
        http = ResilientHttpClient(
            name=name,
            base_url=conn_config.base_url,
            config=config.http,
            metrics=metrics,
            headers=headers,
        )
        connectors[name] = connector_cls(http)

    return connectors


def _headers_for(name: str, secrets: Secrets) -> dict[str, str]:
    """Inject per-connector auth headers from secrets (never from config)."""
    headers = {"Accept": "application/json"}
    if name == GitHubConnector.name:
        headers["Accept"] = "application/vnd.github+json"
        if secrets.github_token:
            headers["Authorization"] = f"Bearer {secrets.github_token}"
    return headers
