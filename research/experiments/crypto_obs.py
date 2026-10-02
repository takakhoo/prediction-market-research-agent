"""Join Polymarket price paths for crypto contracts with spot and volatility at each observation.

Every model input at time t uses spot candles that closed before t. Output: one row per
(contract, price observation) with the market price and the inputs every pricing model needs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.lib.contracts import Spot, load_spot
from research.lib.panel import load_prices
from research.lib.vol import MinuteVol

RV_WINDOWS = {"rv_15m": 900, "rv_1h": 3600, "rv_6h": 6 * 3600, "rv_1d": 86400, "rv_7d": 7 * 86400, "rv_30d": 30 * 86400}
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


def load_dvol(cur):
    d = pd.read_parquet(f"research/data/raw/crypto/dvol_{cur}.parquet").sort_values("t")
    return d.t.to_numpy(), d.close.to_numpy() / 100.0


CONTRACT_COLS = ["market_id", "symbol", "kind", "k", "k2", "window", "source", "t_end", "t0", "y", "fee_rate"]


def attach_spot(obs: pd.DataFrame, lag: int = 0) -> pd.DataFrame:
    """Add spot, time to expiry, strike reference, and trailing volatility as known just before each row's time `t`.

    `lag` (seconds) makes the spot and volatility inputs older than the row, to test how much of an
    edge depends on reacting quickly.
    """
    parts = []
    for sym, g in obs.groupby("symbol"):
        sp = Spot(load_spot(sym))
        mv = MinuteVol(sp.t0, pd.Series(sp.close).ffill().to_numpy())
        g = g.copy()
        t = g.t.to_numpy() - lag
        g["s"] = sp.last_close(t)
        g["tau"] = g.t_end.to_numpy() - g.t.to_numpy()
        w_start = (g.t_end - g.window).fillna(0).to_numpy().astype(np.int64)
        g["s_open"] = np.where(g.kind == "updown", sp.at("open", w_start), np.nan)
        for name, w in RV_WINDOWS.items():
            g[name] = mv.rv(t, w)
        cur = sym[:3]
        if cur in ("BTC", "ETH"):
            dt, dv = load_dvol(cur)
            i = np.searchsorted(dt, t - 3600, side="right") - 1
            g["dvol"] = np.where(i >= 0, dv[np.clip(i, 0, None)], np.nan)
        else:
            g["dvol"] = np.nan
        g["run_hi"], g["run_lo"] = np.nan, np.nan
        touch = g.kind.isin(["reach", "dip"]).to_numpy()
        if touch.any():
            for mid, h in g[touch].groupby("market_id"):
                a = int(sp._i(int(h.t_end.iloc[0] - h.window.iloc[0])))
                b = np.clip(sp._i(h.t.to_numpy()), a + 1, sp.n)
                g.loc[h.index, "run_hi"] = [np.nanmax(sp.high[a:x]) for x in b]
                g.loc[h.index, "run_lo"] = [np.nanmin(sp.low[a:x]) for x in b]
        parts.append(g)
    out = pd.concat(parts, ignore_index=True)
    return out[np.isfinite(out.s)]


def restrict(obs: pd.DataFrame) -> pd.DataFrame:
    obs = obs[(obs.t < obs.t_end - 30) & (obs.p > 0) & (obs.p < 1)]
    # up/down and touch contracts are only priced inside their window, where the strike is known
    windowed = obs.kind.isin(["updown", "reach", "dip"])
    return obs[~windowed | (obs.t >= obs.t_end - obs.window + 60)].copy()


def main():
    c = pd.read_parquet("research/data/derived/crypto_contracts.parquet")
    c = c[c.symbol.isin(SYMS)]
    px = load_prices()
    px = px[px.market_id.isin(c.market_id)]
    out = attach_spot(restrict(px.merge(c[CONTRACT_COLS], on="market_id")))
    out.to_parquet("research/data/derived/crypto_obs.parquet", index=False)
    print(len(out), "quote observations,", out.market_id.nunique(), "contracts")
    from research.lib.trades import load_trades
    tr = load_trades()
    tr = tr[tr.market_id.isin(c.market_id)]
    out = attach_spot(restrict(tr.merge(c[CONTRACT_COLS], on="market_id")))
    out.to_parquet("research/data/derived/crypto_trades.parquet", index=False)
    print(len(out), "trades,", out.market_id.nunique(), "contracts")
    print(out.groupby(["kind", "source"]).market_id.nunique())


if __name__ == "__main__":
    main()
