"""Crypto connector — CoinGecko simple price (no API key required).

https://docs.coingecko.com/reference/simple-price
"""

from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector
from app.core.exceptions import ConnectorError
from app.normalize.schema import UnifiedRecord


class CryptoConnector(BaseConnector):
    name = "crypto"
    record_type = "crypto_price"

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {"ids": ["bitcoin", "ethereum"], "vs_currency": "usd"}

    async def fetch(self, params: dict[str, Any] | None = None) -> list[UnifiedRecord]:
        params = params or self.default_params()
        ids = params.get("ids") or self.default_params()["ids"]
        vs_currency = params.get("vs_currency", "usd")

        data = await self._http.get_json(
            "/simple/price",
            params={
                "ids": ",".join(ids),
                "vs_currencies": vs_currency,
                "include_24hr_change": "true",
            },
        )
        if not isinstance(data, dict):
            raise ConnectorError(self.name, f"unexpected response shape: {data!r}")

        records: list[UnifiedRecord] = []
        for coin_id in ids:
            quote = data.get(coin_id)
            if not isinstance(quote, dict):
                # A missing coin is not fatal — skip it and keep the rest.
                continue
            records.append(
                UnifiedRecord(
                    source=self.name,
                    record_type=self.record_type,
                    external_id=f"{coin_id}:{vs_currency}",
                    title=f"{coin_id} price in {vs_currency.upper()}",
                    payload={
                        "coin": coin_id,
                        "vs_currency": vs_currency,
                        "price": quote.get(vs_currency),
                        "change_24h_pct": quote.get(f"{vs_currency}_24h_change"),
                    },
                )
            )
        return records
