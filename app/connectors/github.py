"""GitHub connector — public repository metadata.

Works anonymously (60 req/h). Pass a token via ``UNIFIED_GITHUB_TOKEN`` to lift
the limit to 5000 req/h; the token is injected as an auth header by the
registry, so this connector never sees the secret directly.

https://docs.github.com/en/rest/repos/repos#get-a-repository
"""

from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector
from app.core.exceptions import ConnectorError
from app.normalize.schema import UnifiedRecord


class GitHubConnector(BaseConnector):
    name = "github"
    record_type = "repository"

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {"repos": ["python/cpython", "encode/httpx"]}

    async def fetch(self, params: dict[str, Any] | None = None) -> list[UnifiedRecord]:
        params = params or self.default_params()
        repos = params.get("repos") or self.default_params()["repos"]

        records: list[UnifiedRecord] = []
        for full_name in repos:
            if "/" not in full_name:
                raise ConnectorError(
                    self.name, f"repo must be 'owner/name', got {full_name!r}"
                )
            data = await self._http.get_json(f"/repos/{full_name}")
            if not isinstance(data, dict) or "id" not in data:
                raise ConnectorError(self.name, f"unexpected response for {full_name!r}")

            records.append(
                UnifiedRecord(
                    source=self.name,
                    record_type=self.record_type,
                    external_id=str(data["id"]),
                    title=data.get("full_name", full_name),
                    payload={
                        "full_name": data.get("full_name"),
                        "stars": data.get("stargazers_count"),
                        "forks": data.get("forks_count"),
                        "open_issues": data.get("open_issues_count"),
                        "language": data.get("language"),
                        "description": data.get("description"),
                    },
                )
            )
        return records
