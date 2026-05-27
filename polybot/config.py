"""Configuration loading and typed accessors.

Config is a plain dict loaded from YAML, merged over built-in defaults so a
sparse user file still produces a complete, valid configuration.
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "mode": "paper",
    "discovery": {
        "seed_wallets": [],
        "leaderboard_url": "https://lb-api.polymarket.com/leaderboard",
        "leaderboard_window": "30d",
        "leaderboard_metric": "pnl",
        "leaderboard_limit": 100,
        "scan_market_holders": True,
        "markets_to_scan": 20,
        "holders_per_market": 20,
        "activity_lookback": 500,
    },
    "scoring": {
        "weights": {
            "win_rate": 1.0,
            "roi": 1.0,
            "total_pnl": 1.2,
            "volume": 0.6,
            "recency": 0.8,
        },
        "min_trades": 20,
        "min_volume_usdc": 1000,
        "min_win_rate": 0.55,
        "max_idle_days": 14,
    },
    "copy": {
        "follow_top_n": 7,
        "sizing": "proportional",
        "scale": 0.10,
        "fixed_usdc": 25,
        "min_trade_usdc": 5,
        "max_trade_usdc": 100,
        "copy_buys": True,
        "copy_sells": True,
        "max_slippage": 0.02,
        "max_signal_age_sec": 120,
        "market_allowlist": [],
        "market_blocklist": [],
    },
    "risk": {
        "max_open_positions": 25,
        "max_total_exposure_usdc": 1500,
        "max_position_per_market_usdc": 150,
        "daily_loss_limit_usdc": 300,
    },
    "monitor": {
        "poll_interval_sec": 8,
        "jitter_sec": 2,
    },
    "database": "polybot.db",
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass
class Secrets:
    """Live-trading credentials, read from the environment only."""

    private_key: str | None = None
    funder_address: str | None = None
    clob_api_key: str | None = None
    clob_api_secret: str | None = None
    clob_api_passphrase: str | None = None

    @classmethod
    def from_env(cls) -> "Secrets":
        return cls(
            private_key=os.getenv("POLYMARKET_PRIVATE_KEY") or None,
            funder_address=os.getenv("POLYMARKET_FUNDER_ADDRESS") or None,
            clob_api_key=os.getenv("POLYMARKET_CLOB_API_KEY") or None,
            clob_api_secret=os.getenv("POLYMARKET_CLOB_API_SECRET") or None,
            clob_api_passphrase=os.getenv("POLYMARKET_CLOB_API_PASSPHRASE") or None,
        )

    @property
    def has_trading_key(self) -> bool:
        return bool(self.private_key)


class Config:
    """Dict-backed config with convenient dotted access and section helpers."""

    def __init__(self, data: dict[str, Any]):
        self.data = data

    @classmethod
    def load(cls, path: str | None) -> "Config":
        user: dict[str, Any] = {}
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                user = yaml.safe_load(fh) or {}
        return cls(_deep_merge(DEFAULTS, user))

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    # Section accessors keep callers terse and explicit.
    @property
    def mode(self) -> str:
        return self.data.get("mode", "paper")

    @mode.setter
    def mode(self, value: str) -> None:
        self.data["mode"] = value

    @property
    def discovery(self) -> dict[str, Any]:
        return self.data["discovery"]

    @property
    def scoring(self) -> dict[str, Any]:
        return self.data["scoring"]

    @property
    def copy(self) -> dict[str, Any]:
        return self.data["copy"]

    @property
    def risk(self) -> dict[str, Any]:
        return self.data["risk"]

    @property
    def monitor(self) -> dict[str, Any]:
        return self.data["monitor"]

    @property
    def database(self) -> str:
        return self.data.get("database", "polybot.db")
