import time

from polybot.config import Config
from polybot.copytrader import CopyTrader
from polybot.monitor import Monitor
from polybot.store import Store


class FakeData:
    """Returns a scripted list of activity records."""

    def __init__(self, records):
        self.records = records

    def activity(self, wallet, limit=50, offset=0):
        return self.records[:limit]


class FakeClob:
    def price(self, token_id, side="BUY"):
        return 0.5

    def midpoint(self, token_id):
        return 0.5


def _rec(i, ts):
    return {
        "type": "TRADE", "side": "BUY", "price": 0.5, "size": 200, "usdcSize": 100,
        "timestamp": ts, "asset": f"tok{i}", "conditionId": f"c{i}",
        "transactionHash": f"0x{i:064x}", "title": f"Market {i}",
    }


def _monitor(tmp_path, records):
    cfg = Config.load(None)
    store = Store(str(tmp_path / "t.db"))
    ct = CopyTrader(cfg, store, clob=FakeClob())
    mon = Monitor(cfg, store, ct, data_api=FakeData(records))
    return mon, store


def test_poll_returns_only_new_trades(tmp_path):
    now = int(time.time())
    records = [_rec(2, now), _rec(1, now - 100)]
    mon, store = _monitor(tmp_path, records)
    mon._watermark["0xw"] = now - 50  # only the newest record is "new"

    new = mon.poll_once("0xw")
    assert [t.asset for t in new] == ["tok2"]
    # Watermark advanced to newest.
    assert mon._watermark["0xw"] == now


def test_seen_trades_not_replayed(tmp_path):
    now = int(time.time())
    records = [_rec(1, now)]
    mon, store = _monitor(tmp_path, records)
    mon._watermark["0xw"] = now - 10

    first = mon.poll_once("0xw")
    assert len(first) == 1
    store.mark_seen(first[0].uid, "0xw")
    # Same record again should be filtered by the seen-set even within watermark.
    mon._watermark["0xw"] = now - 10
    assert mon.poll_once("0xw") == []


def test_non_trade_activity_ignored(tmp_path):
    now = int(time.time())
    redeem = {**_rec(1, now), "type": "REDEEM"}
    mon, _ = _monitor(tmp_path, [redeem])
    mon._watermark["0xw"] = now - 10
    assert mon.poll_once("0xw") == []
