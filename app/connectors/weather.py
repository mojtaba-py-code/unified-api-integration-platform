"""Weather connector — Open-Meteo (no API key required).

https://open-meteo.com/en/docs
"""

from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector
from app.core.exceptions import ConnectorError
from app.normalize.schema import UnifiedRecord


class WeatherConnector(BaseConnector):
    name = "weather"
    record_type = "weather"

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        # A few well-known cities so `collect` works with zero arguments.
        return {
            "locations": [
                {"name": "Tehran", "latitude": 35.6892, "longitude": 51.3890},
                {"name": "London", "latitude": 51.5074, "longitude": -0.1278},
            ]
        }

    async def fetch(self, params: dict[str, Any] | None = None) -> list[UnifiedRecord]:
        params = params or self.default_params()
        locations = params.get("locations") or self.default_params()["locations"]

        records: list[UnifiedRecord] = []
        for loc in locations:
            try:
                lat = float(loc["latitude"])
                lon = float(loc["longitude"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ConnectorError(self.name, f"invalid location {loc!r}: {exc}") from exc

            data = await self._http.get_json(
                "/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,wind_speed_10m,relative_humidity_2m",
                },
            )
            current = data.get("current")
            if not isinstance(current, dict):
                raise ConnectorError(self.name, f"unexpected response shape: {data!r}")

            label = loc.get("name") or f"{lat},{lon}"
            records.append(
                UnifiedRecord(
                    source=self.name,
                    record_type=self.record_type,
                    external_id=f"{lat},{lon}",
                    title=f"Weather for {label}",
                    payload={
                        "location": label,
                        "latitude": lat,
                        "longitude": lon,
                        "temperature_c": current.get("temperature_2m"),
                        "wind_speed": current.get("wind_speed_10m"),
                        "humidity": current.get("relative_humidity_2m"),
                        "observed_at": current.get("time"),
                    },
                )
            )
        return records
