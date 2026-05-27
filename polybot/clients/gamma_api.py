"""Client for Polymarket's Gamma API (markets & events metadata).

Base: https://gamma-api.polymarket.com

Used by discovery to pick active, liquid markets whose holders are worth
scanning, and to resolve market metadata for display.
"""
from __future__ import annotations

from typing import Any

from .http import HttpClient

GAMMA_API = "https://gamma-api.polymarket.com"


class GammaAPI:
    def __init__(self, base_url: str = GAMMA_API):
        self.http = HttpClient(base_url)

    def active_markets(self, limit: int = 50) -> list[dict[str, Any]]:
        """Active, non-closed markets ordered by 24h volume."""
        data = self.http.get(
            "/markets",
            params={
                "active": "true",
                "closed": "false",
                "limit": limit,
                "order": "volume24hr",
                "ascending": "false",
            },
        )
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        return []

    def condition_ids(self, limit: int = 50) -> list[str]:
        ids: list[str] = []
        for m in self.active_markets(limit=limit):
            cid = m.get("conditionId") or m.get("condition_id")
            if cid:
                ids.append(str(cid))
        return ids
