"""Execute copy trades from source signals, in paper or live mode."""
from __future__ import annotations

import logging
from typing import Callable

from .clients.clob import ClobClient
from .config import Config, Secrets
from .models import CopyOrder, Trade
from .risk import RiskManager
from .store import Store

log = logging.getLogger("polybot.copytrader")


class CopyTrader:
    def __init__(
        self,
        cfg: Config,
        store: Store,
        secrets: Secrets | None = None,
        clob: ClobClient | None = None,
        on_order: Callable[[CopyOrder], None] | None = None,
    ):
        self.cfg = cfg
        self.store = store
        self.secrets = secrets or Secrets()
        self.clob = clob or ClobClient(self.secrets)
        self.risk = RiskManager(cfg.copy, cfg.risk, store)
        self.on_order = on_order

    def handle(self, trade: Trade) -> CopyOrder | None:
        """Process one source trade: risk-check, price, execute, record."""
        decision = self.risk.evaluate(trade)
        if not decision.approved:
            log.debug("skip %s %s: %s", trade.side, trade.title[:40], decision.reason)
            return None

        exec_price = self._execution_price(trade)
        if exec_price is None:
            return self._record(trade, decision.usdc, trade.price, "rejected", "no market price")

        if not self._within_slippage(trade, exec_price):
            return self._record(
                trade, decision.usdc, exec_price, "rejected",
                f"slippage {abs(exec_price - trade.price):.3f} > max",
            )

        size_shares = round(decision.usdc / exec_price, 2) if exec_price > 0 else 0.0
        if size_shares <= 0:
            return self._record(trade, decision.usdc, exec_price, "rejected", "zero size")

        if self.cfg.mode == "live":
            return self._execute_live(trade, exec_price, size_shares, decision.usdc)
        return self._record(trade, decision.usdc, exec_price, "filled", "paper")

    # ----- pricing -----------------------------------------------------------
    def _execution_price(self, trade: Trade) -> float | None:
        price = self.clob.price(trade.asset, side=trade.side)
        if price is None:
            price = self.clob.midpoint(trade.asset)
        if price is None and 0.0 < trade.price < 1.0:
            # Fall back to the source's price (paper mode safety net).
            price = trade.price
        return price

    def _within_slippage(self, trade: Trade, exec_price: float) -> bool:
        if not (0.0 < trade.price < 1.0):
            return True  # no reliable reference price to compare against
        max_slip = float(self.cfg.copy.get("max_slippage", 0.02))
        # Buying worse = higher price; selling worse = lower price.
        if trade.side == "BUY":
            return exec_price <= trade.price * (1 + max_slip)
        return exec_price >= trade.price * (1 - max_slip)

    # ----- execution ---------------------------------------------------------
    def _execute_live(self, trade: Trade, price: float, shares: float, usdc: float) -> CopyOrder:
        try:
            resp = self.clob.place_limit_order(trade.asset, trade.side, price, shares)
            ok = bool(resp.get("success", True)) and not resp.get("error")
            status = "submitted" if ok else "rejected"
            detail = str(resp.get("orderID") or resp.get("error") or resp)[:200]
        except Exception as err:  # noqa: BLE001 - surface any live failure as a record
            status, detail = "error", str(err)[:200]
            log.error("live order failed for %s: %s", trade.title[:40], err)
        return self._record(trade, usdc, price, status, detail)

    def _record(self, trade: Trade, usdc: float, price: float, status: str, detail: str) -> CopyOrder:
        shares = round(usdc / price, 2) if price > 0 else 0.0
        order = CopyOrder(
            source_wallet=trade.wallet,
            source_trade_uid=trade.uid,
            asset=trade.asset,
            condition_id=trade.condition_id,
            side=trade.side,
            price=round(price, 4),
            size=shares,
            usdc=round(usdc, 2),
            title=trade.title,
            mode=self.cfg.mode,
            status=status,
            detail=detail,
        )
        self.store.record_copy(order)
        if self.on_order:
            self.on_order(order)
        log.info(
            "%s [%s] %s %s $%.2f @ %.3f (%s)",
            self.cfg.mode, status, trade.side, trade.title[:40], usdc, price, detail[:60],
        )
        return order
