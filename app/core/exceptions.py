"""Domain-specific exceptions.

A small, explicit hierarchy lets callers (and tests) distinguish *why* a
collection failed without matching on strings.
"""

from __future__ import annotations


class PlatformError(Exception):
    """Base class for every error raised by the platform."""


class ConfigError(PlatformError):
    """Raised when configuration is missing or invalid."""


class ConnectorError(PlatformError):
    """Raised when a connector fails to fetch or map data."""

    def __init__(self, connector: str, message: str) -> None:
        self.connector = connector
        super().__init__(f"[{connector}] {message}")


class CircuitOpenError(PlatformError):
    """Raised when a request is short-circuited by an open circuit breaker."""


class RetryableHTTPError(PlatformError):
    """Internal marker: an HTTP response whose status is worth retrying."""

    def __init__(self, status_code: int, url: str) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(f"retryable HTTP {status_code} from {url}")
