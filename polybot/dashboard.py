"""A live terminal dashboard (the 'monitoring terminal') built on rich.

Runs the monitor in a background thread and renders followed wallets, recent
copy orders, and running totals.
"""
from __future__ import annotations

import threading
import time
from collections import deque

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import Config
from .copytrader import CopyTrader
from .models import CopyOrder, Trade
from .monitor import Monitor
from .store import Store


class Dashboard:
    def __init__(self, cfg: Config, store: Store, copytrader: CopyTrader, monitor: Monitor):
        self.cfg = cfg
        self.store = store
        self.copytrader = copytrader
        self.monitor = monitor
        self._recent_orders: deque[CopyOrder] = deque(maxlen=12)
        self._recent_signals: deque[Trade] = deque(maxlen=12)
        self._lock = threading.Lock()
        self._started = time.time()

        copytrader.on_order = self._on_order
        monitor.on_trade = self._on_signal

    def _on_order(self, order: CopyOrder) -> None:
        with self._lock:
            self._recent_orders.appendleft(order)

    def _on_signal(self, trade: Trade) -> None:
        with self._lock:
            self._recent_signals.appendleft(trade)

    def _header(self) -> Panel:
        mode = self.cfg.mode.upper()
        color = "green" if mode == "PAPER" else "bold red"
        followed = len(self.store.followed_wallets())
        uptime = int(time.time() - self._started)
        text = Text.assemble(
            ("POLYBOT  ", "bold cyan"),
            ("monitoring terminal\n", "cyan"),
            ("mode: ", "dim"), (f"{mode}", color),
            ("   following: ", "dim"), (f"{followed} wallets", "white"),
            ("   uptime: ", "dim"), (f"{uptime}s", "white"),
        )
        return Panel(text, border_style=color)

    def _wallets_table(self) -> Table:
        t = Table(title="Followed wallets", expand=True, border_style="blue")
        for col in ("#", "wallet", "score", "win%", "PnL $", "vol $", "trades", "idle d"):
            t.add_column(col, overflow="fold")
        for i, w in enumerate(self.store.top_wallets(limit=10), 1):
            if not w["followed"]:
                continue
            closed = w["num_closed"] or 0
            wins = w["num_wins"] or 0
            winr = (wins / closed * 100) if closed else 0.0
            pnl = (w["realized_pnl"] or 0) + (w["unrealized_pnl"] or 0)
            idle = (time.time() - (w["last_active"] or 0)) / 86400 if w["last_active"] else 0
            t.add_row(
                str(i),
                _short(w["address"]),
                f"{(w['score'] or 0):.2f}",
                f"{winr:.0f}",
                _money(pnl),
                f"{(w['volume'] or 0):,.0f}",
                str(w["num_trades"] or 0),
                f"{idle:.1f}",
            )
        return t

    def _orders_table(self) -> Table:
        t = Table(title="Recent copy orders", expand=True, border_style="magenta")
        for col in ("time", "status", "side", "market", "$", "@price", "from"):
            t.add_column(col, overflow="fold")
        with self._lock:
            orders = list(self._recent_orders)
        for o in orders:
            status_color = {"filled": "green", "submitted": "green", "rejected": "yellow"}.get(
                o.status, "red"
            )
            t.add_row(
                time.strftime("%H:%M:%S", time.localtime(o.ts)),
                Text(o.status, style=status_color),
                Text(o.side, style="green" if o.side == "BUY" else "red"),
                (o.title or o.condition_id)[:32],
                f"{o.usdc:.0f}",
                f"{o.price:.3f}",
                _short(o.source_wallet),
            )
        return t

    def render(self) -> Group:
        return Group(self._header(), self._wallets_table(), self._orders_table())

    def run(self) -> None:
        thread = threading.Thread(target=self.monitor.run, daemon=True)
        thread.start()
        try:
            with Live(self.render(), refresh_per_second=2, screen=True) as live:
                while thread.is_alive():
                    live.update(self.render())
                    time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.monitor.stop()


def _short(addr: str) -> str:
    return f"{addr[:6]}…{addr[-4:]}" if addr and len(addr) > 12 else (addr or "?")


def _money(v: float) -> Text:
    return Text(f"{v:,.0f}", style="green" if v >= 0 else "red")
