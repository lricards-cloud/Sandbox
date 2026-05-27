"""Position sizing and risk gates for copy execution.

This is the safety layer. Every copy signal passes through `evaluate`, which
either returns an approved USDC size or a reason the trade was blocked.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .models import Trade
from .store import Store


@dataclass
class RiskDecision:
    approved: bool
    usdc: float = 0.0
    reason: str = ""


def _start_of_day_ts() -> int:
    now = time.time()
    return int(now - (now % 86400))


class RiskManager:
    def __init__(self, copy_cfg: dict[str, Any], risk_cfg: dict[str, Any], store: Store):
        self.copy = copy_cfg
        self.risk = risk_cfg
        self.store = store

    def size_for(self, trade: Trade) -> float:
        """Raw target size in USDC before risk caps, per the sizing strategy."""
        if self.copy.get("sizing") == "fixed":
            usdc = float(self.copy.get("fixed_usdc", 25))
        else:
            usdc = trade.usdc_size * float(self.copy.get("scale", 0.1))
        lo = float(self.copy.get("min_trade_usdc", 0))
        hi = float(self.copy.get("max_trade_usdc", 1e9))
        return max(0.0, min(usdc, hi)) if usdc >= lo else 0.0

    def evaluate(self, trade: Trade) -> RiskDecision:
        # --- signal-level filters ------------------------------------------
        if trade.side == "BUY" and not self.copy.get("copy_buys", True):
            return RiskDecision(False, reason="buys disabled")
        if trade.side == "SELL" and not self.copy.get("copy_sells", True):
            return RiskDecision(False, reason="sells disabled")
        if trade.age_sec > float(self.copy.get("max_signal_age_sec", 120)):
            return RiskDecision(False, reason=f"stale ({trade.age_sec:.0f}s)")
        if not self._market_allowed(trade):
            return RiskDecision(False, reason="market filtered")

        usdc = self.size_for(trade)
        if usdc <= 0:
            return RiskDecision(False, reason="below min size")

        # --- portfolio-level gates -----------------------------------------
        if self.store.realized_pnl_since(_start_of_day_ts()) <= -abs(
            float(self.risk.get("daily_loss_limit_usdc", 1e12))
        ):
            return RiskDecision(False, reason="daily loss limit hit")

        exposure = self.store.open_exposure()
        if len([v for v in exposure.values() if abs(v) > 1e-6]) >= int(
            self.risk.get("max_open_positions", 1_000_000)
        ) and trade.condition_id not in exposure:
            return RiskDecision(False, reason="max open positions")

        total = sum(abs(v) for v in exposure.values())
        if trade.side == "BUY" and total + usdc > float(
            self.risk.get("max_total_exposure_usdc", 1e12)
        ):
            return RiskDecision(False, reason="max total exposure")

        per_market = abs(exposure.get(trade.condition_id, 0.0))
        cap = float(self.risk.get("max_position_per_market_usdc", 1e12))
        if trade.side == "BUY" and per_market + usdc > cap:
            usdc = max(0.0, cap - per_market)
            if usdc < float(self.copy.get("min_trade_usdc", 0)):
                return RiskDecision(False, reason="per-market cap")

        return RiskDecision(True, usdc=round(usdc, 2))

    def _market_allowed(self, trade: Trade) -> bool:
        allow = self.copy.get("market_allowlist") or []
        block = self.copy.get("market_blocklist") or []
        hay = f"{trade.condition_id} {trade.slug}".lower()
        if block and any(b.lower() in hay for b in block):
            return False
        if allow and not any(a.lower() in hay for a in allow):
            return False
        return True
