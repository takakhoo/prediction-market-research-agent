"""Offline checks for the research library: pricing identities, fee math, and look-ahead guards."""
import numpy as np
import pandas as pd
import pytest

from research.lib import vol
from research.lib.boot import ratio_ci
from research.lib.contracts import Spot, parse, settle
from research.lib.panel import build
from research.lib.stats import fit_logistic, logit, murphy
from research.lib.trades import taker_fee


def test_digital_is_half_at_the_money_and_monotone_in_spot():
    p = vol.digital_above(np.array([90.0, 100.0, 110.0]), 100.0, 0.5, 86400.0)
    assert p[0] < p[1] < p[2]
    assert abs(p[1] - 0.5) < 0.01


def test_digital_converges_to_indicator_at_expiry():
    assert vol.digital_above(101.0, 100.0, 0.5, 1.0) > 0.99
    assert vol.digital_above(99.0, 100.0, 0.5, 1.0) < 0.01


def test_touch_probability_is_at_least_the_digital_and_one_once_touched():
    s, k, sig, tau = 100.0, 105.0, 0.6, 86400.0
    assert vol.touch_up(s, k, sig, tau) >= vol.digital_above(s, k, sig, tau)
    assert vol.touch_up(s, k, sig, tau, running_max=106.0) == 1.0


def test_implied_vol_round_trips():
    s, k, tau = 100.0, 104.0, 3 * 86400.0
    p = vol.digital_above(s, k, 0.7, tau)
    assert abs(vol.implied_vol(np.array([p]), s, k, tau)[0] - 0.7) < 1e-3


def test_taker_fee_matches_the_published_formula():
    assert taker_fee(0.5, 0.05) == pytest.approx(0.0125)
    assert taker_fee(0.9, 0.07) == pytest.approx(0.07 * 0.9 * 0.1)
    assert taker_fee(0.5, np.nan) == 0.0


def test_logistic_fit_recovers_slope_and_murphy_adds_up():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.05, 0.95, 20000)
    y = (rng.uniform(size=p.size) < 1 / (1 + np.exp(-1.3 * logit(p)))).astype(float)
    a, b = fit_logistic(logit(p), y)
    assert abs(b - 1.3) < 0.08 and abs(a) < 0.08
    m = murphy(p, y, bins=10)
    assert m["brier"] == pytest.approx(m["reliability"] - m["resolution"] + m["uncertainty"], abs=5e-3)


def test_ratio_ci_brackets_the_point_estimate():
    rng = np.random.default_rng(1)
    num, den, cl = rng.normal(0.02, 1, 5000), np.ones(5000), rng.integers(0, 400, 5000)
    pt, lo, hi = ratio_ci(num, den, cl, n_boot=300)
    assert lo < pt < hi


def _spot(prices, t0=1_700_000_040):
    t = t0 + 60 * np.arange(len(prices))
    return Spot(pd.DataFrame({"t": t, "open": prices, "high": prices, "low": prices, "close": prices}))


def test_settlement_replay_and_parser_agree_on_a_threshold_contract():
    prices = np.linspace(100, 110, 30)
    sp = _spot(prices)
    T = sp.t0 + 60 * 20
    m = pd.DataFrame({"market_id": [1], "question": ["Will the price of Bitcoin be above $105 on March 1?"],
                      "description": ["Binance 1 minute candle"], "t_end": [float(T)], "t0": [float(sp.t0)], "t_close": [float(T + 600)],
                      "y": [1], "volume": [1.0], "fee_rate": [np.nan]})
    c = parse(m)
    assert c.kind.iloc[0] == "above" and c.k.iloc[0] == 105.0
    assert settle(c, {"BTCUSDT": sp}).iloc[0] == float(prices[20] > 105)


def test_last_close_never_uses_the_current_minute():
    sp = _spot(np.arange(100.0, 110.0))
    t = sp.t0 + 60 * 5 + 30  # halfway through candle 5
    assert sp.last_close(t) == 104.0


def test_panel_features_ignore_everything_after_the_snapshot():
    markets = pd.DataFrame({"market_id": [7], "t0": [0.0], "t_end": [1000.0], "t_close": [1200.0], "y": [1], "category": ["x"],
                            "neg_risk": [False], "event_id": ["e"], "volume": [1.0], "yes_no": [True], "fees_enabled": [False],
                            "n_siblings": [1]})
    t = np.arange(10, 1000, 10)
    base = pd.DataFrame({"market_id": 7, "t": t, "p": np.linspace(0.3, 0.6, len(t))})
    shocked = base.copy()
    shocked.loc[shocked.t > 500, "p"] = 0.99  # rewrite the future
    a = build(markets, base)
    b = build(markets, shocked)
    early = a.t_snap <= 500
    cols = ["p", "run_max", "run_min", "path_rv", "lag_1h"]
    pd.testing.assert_frame_equal(a.loc[early, cols].reset_index(drop=True), b.loc[b.t_snap <= 500, cols].reset_index(drop=True))


def test_rule_expiry_reads_the_settlement_time_from_the_rules():
    from datetime import datetime, timezone

    from research.lib.contracts import rule_expiry

    api_end = datetime(2025, 6, 10, 0, 0, tzinfo=timezone.utc).timestamp()  # date-only end, 16 hours early
    q = "Will the price of Bitcoin be greater than $109K on June 10?"
    d = "the Binance 1 minute candle for BTCUSDT 10 June '25 12:00 in the ET timezone (noon)"
    assert rule_expiry(q, d, api_end) == datetime(2025, 6, 10, 16, 0, tzinfo=timezone.utc).timestamp()
    assert rule_expiry("Bitcoin above 71,600 on April 12, 1PM ET?", "the 1 hour candle", api_end) == api_end


def test_walkthrough_reproduces_the_pipeline_values_from_the_committed_sample():
    from research import walkthrough as w

    c, t0, close, mv = w.load()
    gaps = [abs(w.price(c, t0, close, mv, f["t"])["value"] - f["pm"]) for f in c["fills"][::50]]
    assert max(gaps) < 1e-3
