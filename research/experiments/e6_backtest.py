"""E6. A capital-constrained replay of the option-model rule on real fills.

Rule: whenever a taker fill happened on a price-linked contract and the digital-option model, fed
with spot data at least `lag` old, says that side was worth at least `theta` more than the price
paid plus the taker fee, take the same side at the same price for at most `cap` dollars. Hold to
settlement. The rule has no fitted parameters; theta was fixed at 0.10 after looking only at fills
that expired before the confirmation period, and the confirmation period is reported separately.

P&L is booked on the expiry day. Daily returns are P&L divided by the largest stake outstanding on
any day, which is the capital the rule would have needed. Sharpe is annualized from daily returns;
the deflated Sharpe ratio (Bailey and Lopez de Prado) discounts for the number of variants tried.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

from research.experiments import e4_crypto_options as e4
from research.experiments import e9_stock_options as e9

CONFIRM_FROM = pd.Timestamp("2026-04-01", tz="UTC").timestamp()
TRIALS = 24  # thresholds x spot ages x sides examined in E4


def deflated_sharpe(sr_daily, n, sk, ku, trials):
    """Probability the true Sharpe exceeds the expected maximum of `trials` zero-skill strategies."""
    emc = 0.5772156649
    sr0 = np.sqrt(1.0 / n) * ((1 - emc) * norm.ppf(1 - 1.0 / trials) + emc * norm.ppf(1 - 1.0 / (trials * np.e)))
    den = np.sqrt((1 - sk * sr_daily + (ku - 1) / 4.0 * sr_daily ** 2) / (n - 1))
    return float(norm.cdf((sr_daily - sr0) / den))


def replay(g: pd.DataFrame, theta=0.10, cap=200.0):
    edge = g.d.to_numpy() * (g.pm.to_numpy() - g.p.to_numpy()) - g.fee.to_numpy()
    s = g[edge > theta].copy()
    stake_full = s["size"].to_numpy(float) * s.cost.to_numpy()
    scale = np.minimum(1.0, cap / np.maximum(stake_full, 1e-9))
    s["stake"] = stake_full * scale
    s["pnl"] = s["size"].to_numpy(float) * scale * (s.win.to_numpy() - s.cost.to_numpy() - s.fee.to_numpy())
    s["open_day"] = (s.t // 86400).astype(int)
    return s


def summarize(s: pd.DataFrame, label: str) -> dict:
    if s.empty:
        return {}
    days = np.arange(s.open_day.min(), s.day.max() + 1)
    pnl = s.groupby("day").pnl.sum().reindex(days, fill_value=0.0)
    opened = s.groupby("open_day").stake.sum().reindex(days, fill_value=0.0).cumsum()
    closed = s.groupby("day").stake.sum().reindex(days, fill_value=0.0).cumsum().shift(1, fill_value=0.0)
    capital = float((opened - closed).max())
    r = pnl / capital
    sr_d = r.mean() / r.std()
    out = {"fills": int(len(s)), "markets": int(s.market_id.nunique()), "days": int(len(days)), "active_days": int((pnl != 0).sum()),
           "stake": float(s.stake.sum()), "pnl": float(s.pnl.sum()), "return_on_stake": float(s.pnl.sum() / s.stake.sum()),
           "peak_capital": capital, "win_rate": float(np.average(s.win, weights=s.stake)), "mean_cost": float(np.average(s.cost, weights=s.stake)),
           "sharpe_annual": float(sr_d * np.sqrt(365)), "t_stat": float(sr_d * np.sqrt(len(days))),
           "deflated_sharpe_prob": deflated_sharpe(sr_d, len(days), float(skew(r)), float(kurtosis(r, fisher=False)), TRIALS),
           "max_drawdown_pct_of_capital": float((pnl.cumsum().cummax() - pnl.cumsum()).max() / capital),
           "curve": {"day": [int(d) for d in days], "cum_pnl": [float(x) for x in pnl.cumsum()]}}
    print(f"  {label:34s} fills {out['fills']:6d} mkts {out['markets']:5d} stake ${out['stake']/1e3:8.0f}k pnl ${out['pnl']/1e3:+8.1f}k ({100*out['return_on_stake']:+.1f}%)"
          f" capital ${capital/1e3:6.0f}k Sharpe {out['sharpe_annual']:.2f} t {out['t_stat']:.2f} DSR {out['deflated_sharpe_prob']:.3f} maxDD {100*out['max_drawdown_pct_of_capital']:.0f}%")
    return out


def main():
    res = {}
    for name, loader, lags in (("crypto", lambda lag: e4.load(lag)[lambda x: x.kind.isin(["above", "below", "between"])], (0, 240, 840)),
                               ("stocks", e9.load, (0, 3600))):
        for lag in lags:
            g = loader(lag)
            s = replay(g)
            tag = f"{name}_lag{lag}"
            print(tag)
            res[tag] = {"all": summarize(s, "all fills"), "selection": summarize(s[s.t_end < CONFIRM_FROM], "selection period"),
                        "confirmation": summarize(s[s.t_end >= CONFIRM_FROM], "confirmation period (from 2026-04)")}
    json.dump(res, open("results/tables/e6_backtest.json", "w"), indent=1)


if __name__ == "__main__":
    main()
