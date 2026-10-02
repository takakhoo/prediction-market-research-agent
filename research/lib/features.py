"""Feature construction for the pricing model. Everything here is known at the snapshot time."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .stats import logit

CATS = ["sports", "crypto_updown", "crypto", "weather", "politics", "finance", "mentions", "culture", "economy",
        "geopolitics", "tech", "other"]

BASE = ["lp", "tte_log", "life_log", "frac_life", "age_log", "n_obs_log", "path_rv", "run_max", "run_min", "p_first",
        "d_1h", "d_6h", "d_1d", "d_3d", "d_7d", "cum_usd_log", "usd_1h_log", "flow_cum", "flow_1h", "yes_no",
        "neg_risk", "n_sib_log", "has_fee", "cat_code"]
WALLET = ["smart_flow", "dumb_flow", "roi_flow", "new_flow"]
SMOOTH = ["vwap_gap"]
FAIR = ["fair_lp", "fair_gap"]
QUOTE = ["mid_gap"]


def add_features(p: pd.DataFrame) -> pd.DataFrame:
    p = p.copy()
    p["lp"] = logit(p.p)
    p["tte_log"] = np.log1p(np.clip(p.tte, 0, None))
    p["life_log"] = np.log1p(p.life)
    p["age_log"] = np.log1p(np.clip(p.age, 0, None))
    p["n_obs_log"] = np.log1p(p.n_obs)
    for name in ("1h", "6h", "1d", "3d", "7d"):
        p[f"d_{name}"] = p.lp - logit(p[f"lag_{name}"].where(p[f"lag_{name}"].notna()))
        p.loc[p[f"lag_{name}"].isna(), f"d_{name}"] = np.nan
    p["cum_usd_log"] = np.log1p(p.cum_usd)
    p["usd_1h_log"] = np.log1p(p.usd_1h)
    p["flow_cum"] = p.cum_flow / np.maximum(p.cum_usd, 1.0)
    p["flow_1h"] = p.flow_1h / np.maximum(p.usd_1h, 1.0)
    p["n_sib_log"] = np.log1p(p.n_siblings)
    p["has_fee"] = p.fees_enabled.astype(float)
    p["yes_no"] = p.yes_no.astype(float)
    p["neg_risk"] = p.neg_risk.astype(float)
    if "c_smart" in p:
        den = np.maximum(p.cum_usd, 1.0)
        p["smart_flow"], p["dumb_flow"] = p.c_smart / den, p.c_dumb / den
        p["roi_flow"], p["new_flow"] = p.c_roi_flow / den, p.c_new / den
    if "vwap10" in p:
        p["vwap_gap"] = logit(p.vwap10) - p.lp
    p["cat_code"] = pd.Categorical(p.category, categories=CATS).codes.astype(float)
    return p


def add_fair(p: pd.DataFrame) -> pd.DataFrame:
    """Digital-option fair value at each snapshot for crypto and stock threshold contracts (NaN elsewhere)."""
    from research.experiments.crypto_obs import CONTRACT_COLS, attach_spot, restrict
    from research.experiments.e4_crypto_options import matched_vol
    from research.lib.stocks import model_prob
    from research.lib.vol import contract_prob

    p = p.copy()
    p["fair"] = np.nan
    key = p[["market_id", "t_snap"]].assign(row=np.arange(len(p)), t=p.t_snap.astype(np.int64), p=p.p.to_numpy())
    c = pd.read_parquet("research/data/derived/crypto_contracts.parquet")
    c = c[c.kind.isin(["above", "below", "between"])]
    o = key.merge(c[CONTRACT_COLS], on="market_id")
    if len(o):
        o = attach_spot(restrict(o))
        p.iloc[o.row.to_numpy(), p.columns.get_loc("fair")] = contract_prob(o, matched_vol(o))
    s = pd.read_parquet("research/data/derived/stock_contracts.parquet")
    s = s[~s.file.isin({"CL_F", "GSPC"})]
    o = key.merge(s[["market_id", "file", "kind", "k", "k2", "t_end"]], on="market_id")
    o = o[o.t < o.t_end - 60]
    if len(o):
        o = model_prob(o)
        p.iloc[o.row.to_numpy(), p.columns.get_loc("fair")] = o.pm.to_numpy()
    p["fair_lp"] = logit(p.fair.where(p.fair.notna()))
    p.loc[p.fair.isna(), "fair_lp"] = np.nan
    p["fair_gap"] = p.fair_lp - p.lp
    return p
