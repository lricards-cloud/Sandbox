import time

from polybot.config import Config
from polybot.copytrader import CopyTrader
from polybot.models import Trade
from polybot.store import Store


class FakeClob:
    """Stand-in CLOB that returns a fixed price and never trades for real."""

    def __init__(self, price=0.5):
        self._price = price
        self.orders = []

    def price(self, token_id, side="BUY"):
        return self._price

    def midpoint(self, token_id):
        return self._price

    def place_limit_order(self, token_id, side, price, size_shares):
        self.orders.append((token_id, side, price, size_shares))
        return {"success": True, "orderID": "fake-1"}


def _trade(**over):
    base = dict(
        wallet="0xsrc", timestamp=int(time.time()), condition_id="cX", asset="tok1",
        side="BUY", price=0.5, size=200, usdc_size=100, outcome="Yes", outcome_index=0,
        title="Test market", slug="test-market", tx_hash="0xabc", activity_type="TRADE",
    )
    base.update(over)
    return Trade(**base)


def _cfg(mode="paper"):
    c = Config.load(None)
    c.mode = mode
    c.copy["scale"] = 0.1
    return c


def test_paper_fill_recorded(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    ct = CopyTrader(_cfg("paper"), store, clob=FakeClob(0.5))
    order = ct.handle(_trade(usdc_size=1000))  # -> 100 usdc copy
    assert order is not None
    assert order.status == "filled"
    assert order.mode == "paper"
    assert order.usdc == 100.0
    assert order.size == 200.0  # 100 / 0.5
    assert len(store.recent_copies()) == 1


def test_slippage_rejects(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    cfg = _cfg("paper")
    cfg.copy["max_slippage"] = 0.01
    # Source bought at 0.50 but market now wants 0.60 -> too much slippage.
    ct = CopyTrader(cfg, store, clob=FakeClob(0.60))
    order = ct.handle(_trade(usdc_size=1000, price=0.50))
    assert order.status == "rejected"
    assert "slippage" in order.detail


def test_live_mode_places_order(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "t.db"))
    cfg = _cfg("live")
    fake = FakeClob(0.5)
    ct = CopyTrader(cfg, store, clob=fake)
    order = ct.handle(_trade(usdc_size=1000))
    assert order.status == "submitted"
    assert len(fake.orders) == 1
    assert fake.orders[0][1] == "BUY"
