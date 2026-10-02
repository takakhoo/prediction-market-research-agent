"""Download every closed Polymarket market above a volume floor from the public Gamma API.

One partition per scheduled-end month, each walked with keyset cursors. Resumable:
a finished partition leaves a .done marker next to its .jsonl.gz.
"""
from __future__ import annotations

import argparse
import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .http import get_json

URL = "https://gamma-api.polymarket.com/markets/keyset"
DROP = {"image", "icon", "clobRewards", "seriesColor", "twitterCardImage", "imageOptimized", "iconOptimized"}
EVENT_KEEP = ("id", "slug", "title", "startDate", "endDate", "volume", "negRisk", "commentCount")


def month_edges(start: str, end: str):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        yield f"{y:04d}-{m:02d}", f"{y:04d}-{m:02d}-01T00:00:00Z", f"{ny:04d}-{nm:02d}-01T00:00:00Z"
        y, m = ny, nm


def slim(m: dict) -> dict:
    out = {k: v for k, v in m.items() if k not in DROP}
    out["events"] = [{k: e.get(k) for k in EVENT_KEEP} for e in m.get("events") or []]
    out["tags"] = [t.get("label", "").strip() for t in m.get("tags") or []]
    return out


def pull_partition(args) -> tuple[str, int]:
    name, lo, hi, out_dir, min_volume = args
    target = out_dir / f"markets_{name}.jsonl.gz"
    done = out_dir / f"markets_{name}.done"
    if done.exists():
        return name, -1
    n = 0
    cursor = None
    with gzip.open(target, "wt") as fh:
        while True:
            params = {
                "closed": "true", "limit": 100, "include_tag": "true",
                "end_date_min": lo, "end_date_max": hi, "volume_num_min": min_volume,
            }
            if cursor:
                params["after_cursor"] = cursor
            page = get_json(URL, params)
            if "_error" in page:
                raise RuntimeError(f"{name}: {page}")
            for m in page.get("markets", []):
                fh.write(json.dumps(slim(m)) + "\n")
                n += 1
            cursor = page.get("next_cursor")
            if not cursor or not page.get("markets"):
                break
    done.write_text(datetime.now(timezone.utc).isoformat())
    return name, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="research/data/raw/markets")
    ap.add_argument("--start", default="2020-01")
    ap.add_argument("--end", default="2026-10")
    ap.add_argument("--min-volume", type=float, default=1000)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(n, lo, hi, out, a.min_volume) for n, lo, hi in month_edges(a.start, a.end)]
    with ThreadPoolExecutor(a.workers) as ex:
        for name, n in ex.map(pull_partition, jobs):
            print(name, "cached" if n < 0 else n, flush=True)


if __name__ == "__main__":
    main()
