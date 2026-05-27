"""Core data models shared across the bot."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class Trade:
    """A single on-chain trade emitted by a wallet (from the data API)."""

    wallet: str
    timestamp: int
    condition_id: str
    asset: str  # ERC-1155 token id; equals the CLOB token_id
    side: str  # BUY | SELL
    price: float
    size: float  # shares
    usdc_size: float
    outcome: str
    outcome_index: int
    title: str
    slug: str
    tx_hash: str
    activity_type: str  # TRADE | SPLIT | MERGE | REDEEM | ...

    @property
    def uid(self) -> str:
        """Stable identity for dedupe across polls."""
        return f"{self.tx_hash}:{self.asset}:{self.side}:{self.outcome_index}"

    @property
    def age_sec(self) -> float:
        return max(0.0, time.time() - self.timestamp)

    @classmethod
    def from_activity(cls, raw: dict[str, Any], wallet: str) -> "Trade":
        """Build from a data-api /activity record, tolerant of field naming."""
        return cls(
            wallet=(raw.get("proxyWallet") or raw.get("user") or wallet or "").lower(),
            timestamp=int(_f(raw.get("timestamp"))),
            condition_id=str(raw.get("conditionId") or raw.get("condition_id") or ""),
            asset=str(raw.get("asset") or raw.get("tokenId") or raw.get("token_id") or ""),
            side=str(raw.get("side") or "").upper(),
            price=_f(raw.get("price")),
            size=_f(raw.get("size")),
            usdc_size=_f(raw.get("usdcSize") or raw.get("usdc_size") or raw.get("value")),
            outcome=str(raw.get("outcome") or ""),
            outcome_index=int(_f(raw.get("outcomeIndex") or raw.get("outcome_index"))),
            title=str(raw.get("title") or raw.get("eventTitle") or ""),
            slug=str(raw.get("slug") or raw.get("eventSlug") or ""),
            tx_hash=str(raw.get("transactionHash") or raw.get("txHash") or raw.get("hash") or ""),
            activity_type=str(raw.get("type") or "TRADE").upper(),
        )


@dataclass
class WalletStats:
    """Aggregated performance of a wallet, used for ranking."""

    address: str
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    volume: float = 0.0
    num_trades: int = 0
    num_closed: int = 0
    num_wins: int = 0
    last_active: int = 0
    score: float = 0.0

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    @property
    def win_rate(self) -> float:
        return self.num_wins / self.num_closed if self.num_closed else 0.0

    @property
    def roi(self) -> float:
        return self.total_pnl / self.volume if self.volume else 0.0

    @property
    def idle_days(self) -> float:
        if not self.last_active:
            return 1e9
        return max(0.0, (time.time() - self.last_active) / 86400.0)


@dataclass
class CopyOrder:
    """A copy action the bot took (paper or live) in response to a Trade."""

    source_wallet: str
    source_trade_uid: str
    asset: str
    condition_id: str
    side: str
    price: float
    size: float
    usdc: float
    title: str
    mode: str  # paper | live
    status: str = "filled"  # filled | submitted | rejected | error
    detail: str = ""
    ts: int = field(default_factory=lambda: int(time.time()))
