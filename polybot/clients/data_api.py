"""Client for Polymarket's public data API (positions, activity, holders).

Base: https://data-api.polymarket.com

These endpoints are read-only and require no auth. Response shapes are handled
defensively in the models layer because Polymarket has changed field names over
time.
"""
from __future__ import annotations

from typing import Any

from .http import HttpClient

DATA_API = "https://data-api.polymarket.com"


class DataAPI:
    def __init__(self, base_url: str = DATA_API):
        self.http = HttpClient(base_url)

    def activity(self, wallet: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Recent on-chain activity (trades, splits, merges, redeems) for a wallet."""
        data = self.http.get(
            "/activity",
            params={"user": wallet, "limit": limit, "offset": offset},
        )
        return _as_list(data)

    def activity_paged(self, wallet: str, total: int, page: int = 100) -> list[dict[str, Any]]:
        """Page through /activity up to `total` records."""
        out: list[dict[str, Any]] = []
        offset = 0
        while len(out) < total:
            batch = self.activity(wallet, limit=min(page, total - len(out)), offset=offset)
            if not batch:
                break
            out.extend(batch)
            if len(batch) < page:
                break
            offset += len(batch)
        return out

    def positions(self, wallet: str, limit: int = 500) -> list[dict[str, Any]]:
        """Current/closed positions for a wallet, including per-position PnL."""
        data = self.http.get("/positions", params={"user": wallet, "limit": limit})
        return _as_list(data)

    def value(self, wallet: str) -> float:
        """Total portfolio value in USDC."""
        data = self.http.get("/value", params={"user": wallet})
        if isinstance(data, list) and data:
            data = data[0]
        if isinstance(data, dict):
            for key in ("value", "totalValue", "balance"):
                if key in data:
                    try:
                        return float(data[key])
                    except (TypeError, ValueError):
                        return 0.0
        return 0.0

    def holders(self, condition_id: str, limit: int = 20) -> list[str]:
        """Addresses holding the most of a market's tokens."""
        data = self.http.get(
            "/holders", params={"market": condition_id, "limit": limit}
        )
        out: list[str] = []
        for row in _as_list(data):
            addr = row.get("proxyWallet") or row.get("user") or row.get("address")
            if addr:
                out.append(str(addr).lower())
        return out


def _as_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for key in ("data", "activity", "positions", "holders", "results"):
            if isinstance(data.get(key), list):
                return [d for d in data[key] if isinstance(d, dict)]
    return []
