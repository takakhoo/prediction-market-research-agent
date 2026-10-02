"""Assemble the two analysis tables every experiment reads.

tape.parquet   : one row per taker fill, with market metadata, fees, and the taker's realized result
panel.parquet  : clock-sampled last-trade snapshots with path and flow features (see research/lib/panel.py)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.lib.panel import build, prepare_markets
from research.lib.trades import load_trades, taker_fee

MCOLS = ["market_id", "y", "category", "yes_no", "fee_rate", "t_end", "t0", "t_close", "event_id", "volume", "neg_risk", "n_siblings"]


def add_wallet_skill(t: pd.DataFrame) -> pd.DataFrame:
    """Per fill, the taker wallet's record on markets that had already resolved when the fill happened.

    A wallet's result on a market becomes public at that market's close, so the lookup joins each
    fill at time t to the wallet's cumulative result over fills whose market closed strictly before t.
    """
    t = t.sort_values(["market_id", "t"]).reset_index(drop=True)
    sh = t["size"].to_numpy(dtype=np.float64)
    hist = pd.DataFrame({"wallet": t.wallet.to_numpy(), "t_known": t.t_close.to_numpy(dtype=np.float64),
                         "pnl": sh * (t.win.to_numpy() - t.cost.to_numpy() - t.fee.to_numpy()),
                         "stake": sh * t.cost.to_numpy()}).sort_values(["wallet", "t_known"])
    hist["w_pnl"] = hist.groupby("wallet").pnl.cumsum()
    hist["w_stake"] = hist.groupby("wallet").stake.cumsum()
    hist["w_n"] = hist.groupby("wallet").cumcount() + 1
    q = pd.DataFrame({"wallet": t.wallet.to_numpy(), "t": t.t.to_numpy(dtype=np.float64), "row": np.arange(len(t))})
    j = pd.merge_asof(q.sort_values("t"), hist[["wallet", "t_known", "w_pnl", "w_stake", "w_n"]].sort_values("t_known"),
                      left_on="t", right_on="t_known", by="wallet", allow_exact_matches=False).sort_values("row")
    t["w_pnl"] = j.w_pnl.fillna(0.0).to_numpy(dtype=np.float32)
    t["w_stake"] = j.w_stake.fillna(0.0).to_numpy(dtype=np.float32)
    t["w_n"] = j.w_n.fillna(0).to_numpy(dtype=np.int32)
    roi = t.w_pnl / (t.w_stake + 1000.0)  # shrink thin records toward zero
    usd_signed = (t.usd * t.d).to_numpy(dtype=np.float64)
    seasoned = (t.w_n >= 20).to_numpy()
    t["c_smart"] = np.where(seasoned & (roi > 0.05).to_numpy(), usd_signed, 0.0)
    t["c_dumb"] = np.where(seasoned & (roi < -0.05).to_numpy(), usd_signed, 0.0)
    t["c_roi_flow"] = usd_signed * np.clip(roi.to_numpy(), -0.5, 0.5)
    t["c_new"] = np.where(t.w_n.to_numpy() == 0, usd_signed, 0.0)
    return t


def main():
    m = prepare_markets(pd.read_parquet("research/data/derived/markets.parquet"))
    t = load_trades().merge(m[MCOLS], on="market_id")
    t = t[(t.t < t.t_close) & (t.p > 0) & (t.p < 1) & (t["size"] > 0)].copy()
    t["win"] = np.where(t.d == 1, t.y, 1 - t.y).astype(np.int8)
    t["fee"] = taker_fee(t.cost, t.fee_rate).astype(np.float32)
    t["tte"] = (t.t_end - t.t).astype(np.float32)
    t["ttc"] = (t.t_close - t.t).astype(np.float32)
    t = add_wallet_skill(t)
    t.to_parquet("research/data/derived/tape.parquet", index=False)
    print(len(t), "fills,", t.market_id.nunique(), "markets,", f"${t.usd.sum()/1e6:.0f}M")
    cols = ["market_id", "t", "p", "usd", "d", "size"] + [c for c in t.columns if c.startswith("c_")]
    panel = build(m, t[cols])
    panel.to_parquet("research/data/derived/panel.parquet", index=False)
    print(len(panel), "snapshots,", panel.market_id.nunique(), "markets")
    print(panel.groupby("category").market_id.nunique().to_string())


if __name__ == "__main__":
    main()
