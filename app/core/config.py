"""Typed configuration.

Two sources, kept deliberately separate:

* ``config.yaml`` — non-secret, version-controlled runtime settings, validated
  into pydantic models so a typo fails fast at startup instead of at runtime.
* environment / ``.env`` — secrets and per-environment overrides, via
  ``pydantic-settings``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.exceptions import ConfigError


class RetryConfig(BaseModel):
    max_attempts: int = Field(default=3, ge=1)
    base_delay_seconds: float = Field(default=0.5, ge=0)
    max_delay_seconds: float = Field(default=5.0, ge=0)


class RateLimitConfig(BaseModel):
    requests_per_second: float = Field(default=5.0, gt=0)


class CircuitBreakerConfig(BaseModel):
    failure_threshold: int = Field(default=5, ge=1)
    reset_timeout_seconds: float = Field(default=30.0, gt=0)


class HttpConfig(BaseModel):
    timeout_seconds: float = Field(default=10.0, gt=0)
    retry: RetryConfig = RetryConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()


class AppConfig(BaseModel):
    name: str = "Unified API Integration Platform"
    database_path: str = "data/unified.db"
    cache_ttl_seconds: int = Field(default=300, ge=0)


class ConnectorConfig(BaseModel):
    enabled: bool = True
    base_url: str


class Config(BaseModel):
    app: AppConfig = AppConfig()
    http: HttpConfig = HttpConfig()
    connectors: dict[str, ConnectorConfig] = {}


class Secrets(BaseSettings):
    """Secrets and overrides pulled from the environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="UNIFIED_", env_file=".env", extra="ignore"
    )

    github_token: str | None = None
    config_path: str = "config.yaml"
    database_path: str | None = None


def load_config(path: str | Path | None = None, secrets: Secrets | None = None) -> Config:
    """Load and validate configuration from YAML, applying env overrides."""
    secrets = secrets or Secrets()
    config_path = Path(path) if path is not None else Path(secrets.config_path)
    if not config_path.exists():
        raise ConfigError(f"config file not found: {config_path}")

    try:
        raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc

    try:
        config = Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid configuration: {exc}") from exc

    # Environment override wins over the YAML value for the DB path.
    if secrets.database_path:
        config.app.database_path = secrets.database_path

    return config
