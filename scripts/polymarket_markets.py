#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.polymarket.actions import PolymarketActionAdvisor
from src.polymarket.config import PolymarketConfig
from src.polymarket.gamma_client import GammaMarketsClient


def load_env_file(path: str | None) -> None:
    if not path:
        return
    env_path = Path(path)
    if not env_path.is_absolute():
        env_path = ROOT / env_path
    if not env_path.exists():
        raise FileNotFoundError(f"Env file not found: {env_path}")

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def cmd_list(args: argparse.Namespace) -> int:
    config = PolymarketConfig.from_env()
    gamma = GammaMarketsClient(config)

    markets = gamma.list_markets(
        limit=args.limit,
        offset=args.offset,
        active=args.active,
        closed=args.closed,
        archived=args.archived,
        search=args.search,
        tag_id=args.tag_id,
    )
    summaries = gamma.summarize(markets)

    if args.json:
        print(json.dumps(markets, indent=2, ensure_ascii=True))
        return 0

    print(f"Retrieved {len(summaries)} markets")
    print("id | active | closed | end_date | question")
    print("-" * 120)
    for item in summaries:
        question = item.question.replace("\n", " ").strip()
        if len(question) > 90:
            question = question[:87] + "..."
        print(f"{item.market_id} | {item.active} | {item.closed} | {item.end_date_iso or '-'} | {question}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    config = PolymarketConfig.from_env()
    gamma = GammaMarketsClient(config)

    market = None
    if args.market_id:
        market = gamma.get_market_by_id(args.market_id)
    elif args.slug:
        market = gamma.get_market_by_slug(args.slug)

    if market is None:
        print("Market not found", file=sys.stderr)
        return 1

    outcomes, prices = gamma.parse_outcomes(market)

    if args.json:
        print(json.dumps(market, indent=2, ensure_ascii=True))
    else:
        print(f"Market ID: {market.get('id')}")
        print(f"Question: {market.get('question')}")
        print(f"Slug: {market.get('slug')}")
        print(f"Active: {market.get('active')} | Closed: {market.get('closed')}")
        print(f"End Date: {market.get('endDate')}")
        print(f"Condition ID: {market.get('conditionId')}")
        print(f"Volume: {market.get('volume')}")
        print(f"Liquidity: {market.get('liquidity')}")
        if outcomes:
            print("Outcomes:")
            for index, outcome in enumerate(outcomes):
                price = prices[index] if index < len(prices) else None
                print(f"  - {outcome}: {price}")

    return 0


def cmd_actions(_: argparse.Namespace) -> int:
    config = PolymarketConfig.from_env()
    advisor = PolymarketActionAdvisor(config)
    plan = advisor.summarize()

    print(f"Read-only market retrieval available: {plan.can_read_markets}")
    print(f"Trading-ready: {plan.can_trade}")
    if plan.required_for_trade:
        print("Missing for trading:")
        for item in plan.required_for_trade:
            print(f" - {item}")
    if plan.notes:
        print("Notes:")
        for note in plan.notes:
            print(f" - {note}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Polymarket market discovery helper")
    parser.add_argument(
        "--env-file",
        default=None,
        help="Optional env file path (e.g., configs/sources/polymarket_runtime.template.env)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List available markets")
    list_parser.add_argument("--limit", type=int, default=25)
    list_parser.add_argument("--offset", type=int, default=0)
    list_parser.add_argument("--active", type=_bool_or_none, default=None)
    list_parser.add_argument("--closed", type=_bool_or_none, default=None)
    list_parser.add_argument("--archived", type=_bool_or_none, default=None)
    list_parser.add_argument("--search", default=None)
    list_parser.add_argument("--tag-id", type=int, default=None)
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=cmd_list)

    show_parser = subparsers.add_parser("show", help="Show one market by id or slug")
    show_group = show_parser.add_mutually_exclusive_group(required=True)
    show_group.add_argument("--market-id")
    show_group.add_argument("--slug")
    show_parser.add_argument("--json", action="store_true")
    show_parser.set_defaults(func=cmd_show)

    actions_parser = subparsers.add_parser("actions", help="Explain action/trading readiness")
    actions_parser.set_defaults(func=cmd_actions)

    return parser


def _bool_or_none(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError("Expected true/false")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        load_env_file(args.env_file)
        return args.func(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
