"""E8. Language-model forecasters against the market on questions opened after their training cutoff.

Condition A: the model sees the question and rules only. Condition B: it also sees the market price.
Every forecast is scored against the market price at the same snapshot (30% of scheduled life).
CIs resample questions; each question comes from a distinct event.
"""
from __future__ import annotations

import glob
import json
import re

import numpy as np
import pandas as pd

from research.lib.stats import fit_logistic, logit


def load() -> pd.DataFrame:
    q = pd.read_parquet("research/data/llm/questions.parquet").set_index("qid")
    for f in sorted(glob.glob("research/data/llm/forecasts/batch*_*.json")):
        mt = re.search(r"batch(\d)_([AB])_(\w+)\.json", f)
        d = pd.DataFrame(json.load(open(f))).drop_duplicates("qid").set_index("qid")
        col = f"{mt[3]}_{mt[2]}"
        if col not in q:
            q[col] = np.nan
        q.loc[d.index.intersection(q.index), col] = d.p.clip(0.01, 0.99)
    return q


def boot(fn, n, n_boot=4000, seed=0):
    rng = np.random.default_rng(seed)
    draws = np.array([fn(rng.integers(0, n, n)) for _ in range(n_boot)])
    return np.percentile(draws, [2.5, 97.5]), draws


def main():
    q = load()
    cols = [c for c in q.columns if re.fullmatch(r"\w+_[AB]", c) and c not in ("p_mkt",)]
    q = q.dropna(subset=cols)
    y, pm = q.y.to_numpy(float), q.p_mkt.to_numpy(float)
    n = len(q)
    res = {"n_questions": n, "base_rate": float(y.mean()), "market_brier": float(((pm - y) ** 2).mean()),
           "always_base_rate_brier": float(y.mean() * (1 - y.mean())), "models": {}}
    print(f"{n} questions, base rate {y.mean():.3f}, market Brier {res['market_brier']:.4f}")
    for c in sorted(cols):
        p = q[c].to_numpy(float)
        d = (p - y) ** 2 - (pm - y) ** 2
        ci, draws = boot(lambda i: d[i].mean(), n)
        # does the forecast add information to the market price? y ~ a + b logit(p_mkt) + c logit(p_llm)
        from scipy import optimize, special
        X = np.column_stack([np.ones(n), logit(pm), logit(p)])
        nll = lambda th, idx: np.sum(np.logaddexp(0, X[idx] @ th) - y[idx] * (X[idx] @ th))
        fit = lambda idx: optimize.minimize(nll, np.array([0, 1.0, 0]), args=(idx,), method="BFGS").x
        th = fit(np.arange(n))
        rng = np.random.default_rng(1)
        cs = np.array([fit(rng.integers(0, n, n))[2] for _ in range(500)])
        res["models"][c] = {"brier": float(((p - y) ** 2).mean()), "brier_minus_market": float(d.mean()),
                            "ci": [float(ci[0]), float(ci[1])], "p_worse_than_market": float((draws > 0).mean()),
                            "corr_with_market": float(np.corrcoef(p, pm)[0, 1]),
                            "mean_abs_move_from_market": float(np.abs(p - pm).mean()),
                            "weight_on_llm_given_market": float(th[2]), "weight_ci": [float(np.percentile(cs, 2.5)), float(np.percentile(cs, 97.5))]}
        r = res["models"][c]
        print(f"  {c:10s} Brier {r['brier']:.4f}  vs market {r['brier_minus_market']:+.4f} [{ci[0]:+.4f}, {ci[1]:+.4f}]  corr {r['corr_with_market']:.2f}  LLM weight {th[2]:+.2f} [{r['weight_ci'][0]:+.2f}, {r['weight_ci'][1]:+.2f}]")
    json.dump(res, open("results/tables/e8_llm.json", "w"), indent=1)
    q.reset_index().to_parquet("research/data/llm/scored.parquet", index=False)


if __name__ == "__main__":
    main()
