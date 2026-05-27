"""Discover candidate wallets and rank them by profitability.

Candidates come from three sources, unioned together:
  1. Seed wallets from config.
  2. A best-effort leaderboard fetch.
  3. Top holders of the most active markets.

Each candidate is then scored from its real activity/positions history.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from .clients.data_api import DataAPI
from .clients.gamma_api import GammaAPI
from .clients.http import HttpClient
from .config import Config
from .models import WalletStats
from .scoring import build_stats, passes_filters, score_wallet

log = logging.getLogger("polybot.discovery")


class Discovery:
    def __init__(self, cfg: Config, data_api: DataAPI | None = None, gamma: GammaAPI | None = None):
        self.cfg = cfg
        self.data = data_api or DataAPI()
        self.gamma = gamma or GammaAPI()

    def candidate_addresses(self) -> list[str]:
        d = self.cfg.discovery
        found: set[str] = set()

        for addr in d.get("seed_wallets", []) or []:
            if addr:
                found.add(str(addr).lower())

        if d.get("leaderboard_url"):
            for addr in self._leaderboard(d):
                found.add(addr)

        if d.get("scan_market_holders", True):
            for addr in self._holders(d):
                found.add(addr)

        log.info("discovery collected %d candidate wallets", len(found))
        return sorted(found)

    def rank(self, progress: Callable[[str], None] | None = None) -> list[WalletStats]:
        """Score every candidate and return them sorted best-first."""
        scoring_cfg = self.cfg.scoring
        lookback = self.cfg.discovery.get("activity_lookback", 500)
        ranked: list[WalletStats] = []

        for addr in self.candidate_addresses():
            if progress:
                progress(addr)
            activity = self.data.activity_paged(addr, total=lookback)
            positions = self.data.positions(addr)
            if not activity and not positions:
                continue
            stats = build_stats(addr, activity, positions)
            stats.score = score_wallet(stats, scoring_cfg)
            ranked.append(stats)

        ranked.sort(key=lambda s: s.score, reverse=True)
        return ranked

    def eligible(self, ranked: list[WalletStats]) -> list[WalletStats]:
        return [s for s in ranked if passes_filters(s, self.cfg.scoring)]

    # ----- candidate sources -------------------------------------------------
    def _leaderboard(self, d: dict[str, Any]) -> list[str]:
        http = HttpClient()
        data = http.get(
            d["leaderboard_url"],
            params={
                "window": d.get("leaderboard_window", "30d"),
                "type": d.get("leaderboard_metric", "pnl"),
                "limit": d.get("leaderboard_limit", 100),
            },
        )
        rows = data if isinstance(data, list) else (data or {}).get("data", []) if isinstance(data, dict) else []
        out: list[str] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            addr = row.get("proxyWallet") or row.get("wallet") or row.get("user") or row.get("address")
            if addr:
                out.append(str(addr).lower())
        log.info("leaderboard returned %d wallets", len(out))
        return out

    def _holders(self, d: dict[str, Any]) -> list[str]:
        out: set[str] = set()
        cids = self.gamma.condition_ids(limit=d.get("markets_to_scan", 20))
        for cid in cids:
            for addr in self.data.holders(cid, limit=d.get("holders_per_market", 20)):
                out.add(addr)
        log.info("market-holder scan returned %d wallets", len(out))
        return list(out)
