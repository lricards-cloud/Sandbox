"""Poll followed wallets for new trades and feed them to the copy trader."""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Callable

from .clients.data_api import DataAPI
from .config import Config
from .copytrader import CopyTrader
from .models import Trade
from .store import Store

log = logging.getLogger("polybot.monitor")


class Monitor:
    def __init__(
        self,
        cfg: Config,
        store: Store,
        copytrader: CopyTrader,
        data_api: DataAPI | None = None,
        on_trade: Callable[[Trade], None] | None = None,
    ):
        self.cfg = cfg
        self.store = store
        self.copytrader = copytrader
        self.data = data_api or DataAPI()
        self.on_trade = on_trade
        self._stop = threading.Event()
        # Per-wallet high-water timestamp so we only react to genuinely new trades.
        self._watermark: dict[str, int] = {}

    def stop(self) -> None:
        self._stop.set()

    def prime(self, wallets: list[str]) -> None:
        """Record current latest-trade timestamps so we don't replay history."""
        for w in wallets:
            acts = self.data.activity(w, limit=1)
            if acts:
                t = Trade.from_activity(acts[0], w)
                self._watermark[w] = t.timestamp
            else:
                self._watermark[w] = int(time.time())

    def poll_once(self, wallet: str) -> list[Trade]:
        """Return new, unseen TRADE events for a wallet (newest last)."""
        new: list[Trade] = []
        mark = self._watermark.get(wallet, 0)
        highest = mark
        for raw in self.data.activity(wallet, limit=50):
            t = Trade.from_activity(raw, wallet)
            if t.activity_type != "TRADE" or not t.asset:
                continue
            if t.timestamp < mark:
                continue
            if self.store.is_seen(t.uid):
                continue
            new.append(t)
            highest = max(highest, t.timestamp)
        if highest > mark:
            self._watermark[wallet] = highest
        new.sort(key=lambda x: x.timestamp)
        return new

    def run(self) -> None:
        """Blocking loop. Call stop() from another thread (or Ctrl-C) to end."""
        interval = float(self.cfg.monitor.get("poll_interval_sec", 8))
        jitter = float(self.cfg.monitor.get("jitter_sec", 2))
        wallets = self.store.followed_wallets()
        if not wallets:
            log.warning("no followed wallets; run discovery first")
            return
        self.prime(wallets)
        log.info("monitoring %d wallets in %s mode", len(wallets), self.cfg.mode)

        while not self._stop.is_set():
            wallets = self.store.followed_wallets()
            for wallet in wallets:
                if self._stop.is_set():
                    break
                try:
                    for trade in self.poll_once(wallet):
                        self.store.mark_seen(trade.uid, wallet)
                        if self.on_trade:
                            self.on_trade(trade)
                        self.copytrader.handle(trade)
                except Exception as err:  # noqa: BLE001 - keep the loop alive
                    log.error("poll failed for %s: %s", wallet, err)
            self._stop.wait(interval + random.uniform(-jitter, jitter))
