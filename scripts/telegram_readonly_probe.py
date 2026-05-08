#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.discovery.config import DiscoverySettings
from src.discovery.errors import TDLibAuthRequiredError, TDLibRequestError
from src.discovery.tdlib_client import TDLibDiscoveryClient


def _load_env_file(env_path: Path) -> None:
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
        if key:
            os.environ[key] = value


async def _run_probe(args: argparse.Namespace, settings: DiscoverySettings) -> int:
    client = TDLibDiscoveryClient(settings)
    try:
        channels = await client.search_public_chats(args.query, args.limit)

        selected = None
        if args.username:
            selected = await client.search_public_chat(args.username)
        elif args.chat_id:
            selected = await client.get_channel(args.chat_id)
        elif channels:
            selected = channels[0]

        result: dict[str, Any] = {
            "query": args.query,
            "read_only_mode": settings.telegram_read_only_mode,
            "search_count": len(channels),
            "search_channels": channels,
            "selected_channel": selected,
        }

        if selected is not None:
            chat_id = int(selected["chat_id"])
            history = await client.get_chat_history(chat_id, args.messages_limit)
            similar = await client.get_chat_similar_chats(chat_id)
            result["selected_chat_messages_count"] = len(history.get("messages", []))
            result["selected_chat_messages"] = history.get("messages", [])
            result["selected_chat_similar_count"] = len(similar)
            result["selected_chat_similar"] = similar[: args.similar_limit]

        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except TDLibAuthRequiredError as exc:
        print(f"Auth required: {exc}", file=sys.stderr)
        return 2
    except TDLibRequestError as exc:
        print(f"TDLib request error: {exc}", file=sys.stderr)
        return 3
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Telegram discovery probe (search + history + similar)."
    )
    parser.add_argument(
        "--env-file",
        default="configs/sources/telegram_runtime.template.env",
        help="Path to Telegram runtime env file.",
    )
    parser.add_argument(
        "--query",
        default="israel lebanon",
        help="Keyword query for public channel search.",
    )
    parser.add_argument("--limit", type=int, default=5, help="Max search results to load.")
    parser.add_argument(
        "--messages-limit",
        type=int,
        default=5,
        help="Recent messages to fetch for selected channel.",
    )
    parser.add_argument(
        "--similar-limit",
        type=int,
        default=10,
        help="How many similar channels to print in output.",
    )
    parser.add_argument("--username", default=None, help="Optional @username to resolve directly.")
    parser.add_argument("--chat-id", type=int, default=None, help="Optional chat_id to resolve directly.")
    args = parser.parse_args()

    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = ROOT / env_file

    _load_env_file(env_file)
    settings = DiscoverySettings()
    if not settings.telegram_read_only_mode:
        print(
            "Warning: TELEGRAM_READ_ONLY_MODE is false. Set it to true for safe testing.",
            file=sys.stderr,
        )

    return asyncio.run(_run_probe(args, settings))


if __name__ == "__main__":
    raise SystemExit(main())
