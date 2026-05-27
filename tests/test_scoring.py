import time

from polybot.config import DEFAULTS
from polybot.models import Trade
from polybot.scoring import build_stats, passes_filters, score_wallet


def _activity(n, usdc=100.0, ts=None):
    ts = ts or int(time.time())
    return [
        {
            "type": "TRADE",
            "side": "BUY",
            "price": 0.5,
            "size": usdc / 0.5,
            "usdcSize": usdc,
            "timestamp": ts - i * 60,
            "asset": f"tok{i}",
            "conditionId": f"c{i}",
            "transactionHash": f"0x{i:064x}",
        }
        for i in range(n)
    ]


def _positions(wins, losses):
    pos = []
    for i in range(wins):
        pos.append({"realizedPnl": 50.0, "size": 0})
    for i in range(losses):
        pos.append({"realizedPnl": -30.0, "size": 0})
    return pos


def test_build_stats_aggregates_volume_and_winrate():
    stats = build_stats("0xABC", _activity(10, usdc=200), _positions(6, 4))
    assert stats.num_trades == 10
    assert stats.volume == 2000.0
    assert stats.num_closed == 10
    assert stats.num_wins == 6
    assert abs(stats.win_rate - 0.6) < 1e-9
    assert stats.address == "0xabc"  # normalised lowercase


def test_trade_from_activity_alt_field_names():
    raw = {
        "type": "TRADE",
        "side": "sell",
        "price": "0.42",
        "size": "10",
        "value": "4.2",
        "outcomeIndex": "1",
        "tokenId": "999",
        "txHash": "0xdead",
    }
    t = Trade.from_activity(raw, "0xWallet")
    assert t.side == "SELL"
    assert t.price == 0.42
    assert t.usdc_size == 4.2
    assert t.asset == "999"
    assert t.outcome_index == 1
    assert t.tx_hash == "0xdead"


def test_higher_pnl_scores_higher():
    good = build_stats("0x1", _activity(30, usdc=500), _positions(20, 5))
    bad = build_stats("0x2", _activity(30, usdc=500), _positions(8, 17))
    sg = score_wallet(good, DEFAULTS["scoring"])
    sb = score_wallet(bad, DEFAULTS["scoring"])
    assert sg > sb


def test_filters_reject_unprofitable_and_idle():
    cfg = DEFAULTS["scoring"]
    losing = build_stats("0x3", _activity(30, usdc=500), _positions(2, 20))
    assert not passes_filters(losing, cfg)

    old_ts = int(time.time()) - 60 * 86400
    idle = build_stats("0x4", _activity(30, usdc=500, ts=old_ts), _positions(20, 2))
    assert not passes_filters(idle, cfg)

    good = build_stats("0x5", _activity(30, usdc=500), _positions(20, 2))
    assert passes_filters(good, cfg)
