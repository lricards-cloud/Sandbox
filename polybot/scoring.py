"""Turn a wallet's raw activity/positions into stats and a single rank score.

Scoring is intentionally transparent: each component is normalised to ~[0,1]
and combined with configurable weights. No magic models — just math, which is
what a copy-trading strategy should be auditable against.
"""
from __future__ import annotations

import math
import time
from typing import Any

from .models import Trade, WalletStats


def build_stats(
    address: str,
    activity: list[dict[str, Any]],
    positions: list[dict[str, Any]],
) -> WalletStats:
    """Aggregate a wallet's history into a WalletStats."""
    stats = WalletStats(address=address.lower())

    for raw in activity:
        t = Trade.from_activity(raw, address)
        if t.activity_type != "TRADE":
            continue
        stats.num_trades += 1
        stats.volume += t.usdc_size
        stats.last_active = max(stats.last_active, t.timestamp)

    # PnL and win-rate come from closed/open positions, which carry per-market PnL.
    for pos in positions:
        realized = _pos_field(pos, ("realizedPnl", "realized_pnl"))
        unrealized = _pos_field(pos, ("cashPnl", "unrealizedPnl", "unrealized_pnl"))
        stats.realized_pnl += realized
        stats.unrealized_pnl += unrealized

        size = _pos_field(pos, ("size", "shares"))
        is_closed = (abs(size) < 1e-9) or bool(pos.get("redeemable")) or bool(pos.get("closed"))
        if is_closed and abs(realized) > 1e-9:
            stats.num_closed += 1
            if realized > 0:
                stats.num_wins += 1

    return stats


def score_wallet(stats: WalletStats, scoring_cfg: dict[str, Any]) -> float:
    """Compute a single comparable score from a wallet's stats."""
    w = scoring_cfg.get("weights", {})

    win_component = stats.win_rate  # already 0..1
    roi_component = _squash(stats.roi)  # ROI can be negative or large
    pnl_component = _log_scale(stats.total_pnl, pivot=1000.0)
    vol_component = _log_scale(stats.volume, pivot=10000.0)
    recency_component = _recency(stats.last_active, half_life_days=10.0)

    score = (
        w.get("win_rate", 1.0) * win_component
        + w.get("roi", 1.0) * roi_component
        + w.get("total_pnl", 1.0) * pnl_component
        + w.get("volume", 1.0) * vol_component
        + w.get("recency", 1.0) * recency_component
    )
    return round(score, 4)


def passes_filters(stats: WalletStats, scoring_cfg: dict[str, Any]) -> bool:
    """Hard gates a wallet must clear before it's eligible to be followed."""
    if stats.num_trades < scoring_cfg.get("min_trades", 0):
        return False
    if stats.volume < scoring_cfg.get("min_volume_usdc", 0):
        return False
    if stats.num_closed and stats.win_rate < scoring_cfg.get("min_win_rate", 0.0):
        return False
    if stats.total_pnl <= 0:
        return False
    if stats.idle_days > scoring_cfg.get("max_idle_days", 1e9):
        return False
    return True


# ----- normalisation helpers -------------------------------------------------
def _squash(x: float) -> float:
    """Map any real to (0,1) via a logistic centred at 0, gentle slope."""
    return 1.0 / (1.0 + math.exp(-4.0 * x))


def _log_scale(value: float, pivot: float) -> float:
    """0 at <=0, ~0.5 at `pivot`, saturating toward 1 for large values."""
    if value <= 0:
        return 0.0
    return math.log1p(value) / (math.log1p(value) + math.log1p(pivot))


def _recency(last_active: int, half_life_days: float) -> float:
    if not last_active:
        return 0.0
    age_days = max(0.0, (time.time() - last_active) / 86400.0)
    return 0.5 ** (age_days / half_life_days)


def _pos_field(pos: dict[str, Any], keys: tuple[str, ...]) -> float:
    for k in keys:
        if k in pos and pos[k] is not None:
            try:
                return float(pos[k])
            except (TypeError, ValueError):
                continue
    return 0.0
