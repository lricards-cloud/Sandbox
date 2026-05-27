import time

from polybot.config import DEFAULTS
from polybot.models import Trade
from polybot.risk import RiskManager
from polybot.store import Store


def _trade(usdc=100.0, side="BUY", cid="cX", age=0):
    return Trade(
        wallet="0xsrc",
        timestamp=int(time.time()) - age,
        condition_id=cid,
        asset="tok1",
        side=side,
        price=0.5,
        size=usdc / 0.5,
        usdc_size=usdc,
        outcome="Yes",
        outcome_index=0,
        title="Test market",
        slug="test-market",
        tx_hash="0xabc",
        activity_type="TRADE",
    )


def _store(tmp_path):
    return Store(str(tmp_path / "t.db"))


def _copy_cfg(**over):
    cfg = dict(DEFAULTS["copy"])
    cfg.update(over)
    return cfg


def _risk_cfg(**over):
    cfg = dict(DEFAULTS["risk"])
    cfg.update(over)
    return cfg


def test_proportional_sizing_and_caps(tmp_path):
    rm = RiskManager(_copy_cfg(scale=0.1, max_trade_usdc=100), _risk_cfg(), _store(tmp_path))
    # 1000 * 0.1 = 100, at the cap.
    assert rm.size_for(_trade(usdc=1000)) == 100.0
    # 2000 * 0.1 = 200, clamped to 100.
    assert rm.size_for(_trade(usdc=2000)) == 100.0


def test_fixed_sizing(tmp_path):
    rm = RiskManager(_copy_cfg(sizing="fixed", fixed_usdc=25), _risk_cfg(), _store(tmp_path))
    assert rm.size_for(_trade(usdc=9999)) == 25.0


def test_below_min_size_rejected(tmp_path):
    rm = RiskManager(_copy_cfg(sizing="fixed", fixed_usdc=1, min_trade_usdc=5), _risk_cfg(), _store(tmp_path))
    assert rm.evaluate(_trade()).approved is False


def test_stale_signal_rejected(tmp_path):
    rm = RiskManager(_copy_cfg(max_signal_age_sec=60), _risk_cfg(), _store(tmp_path))
    d = rm.evaluate(_trade(age=120))
    assert d.approved is False
    assert "stale" in d.reason


def test_blocklist_filter(tmp_path):
    rm = RiskManager(_copy_cfg(market_blocklist=["test-market"]), _risk_cfg(), _store(tmp_path))
    assert rm.evaluate(_trade()).approved is False


def test_allowlist_filter(tmp_path):
    rm = RiskManager(_copy_cfg(market_allowlist=["other"]), _risk_cfg(), _store(tmp_path))
    assert rm.evaluate(_trade()).approved is False
    rm2 = RiskManager(_copy_cfg(market_allowlist=["test-market"]), _risk_cfg(), _store(tmp_path))
    assert rm2.evaluate(_trade()).approved is True


def test_per_market_cap_trims_size(tmp_path):
    store = _store(tmp_path)
    rm = RiskManager(
        _copy_cfg(scale=1.0, max_trade_usdc=1000, min_trade_usdc=5),
        _risk_cfg(max_position_per_market_usdc=120),
        store,
    )
    from polybot.models import CopyOrder
    store.record_copy(CopyOrder("0xsrc", "u1", "tok1", "cX", "BUY", 0.5, 200, 100, "Test", "paper", "filled"))
    d = rm.evaluate(_trade(usdc=100, cid="cX"))
    assert d.approved is True
    assert d.usdc == 20.0  # 120 cap - 100 existing


def test_max_total_exposure(tmp_path):
    store = _store(tmp_path)
    rm = RiskManager(
        _copy_cfg(scale=1.0, max_trade_usdc=10000, min_trade_usdc=5),
        _risk_cfg(max_total_exposure_usdc=150, max_position_per_market_usdc=100000),
        store,
    )
    from polybot.models import CopyOrder
    store.record_copy(CopyOrder("0xsrc", "u1", "tok9", "cZ", "BUY", 0.5, 200, 100, "Z", "paper", "filled"))
    d = rm.evaluate(_trade(usdc=100, cid="cNew"))
    assert d.approved is False
    assert "exposure" in d.reason
