#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.discovery.config import DiscoverySettings


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
            # Always override process env with env-file values to avoid stale shell exports
            # (for example TELEGRAM_API_ID=replace_me lingering from a previous session).
            os.environ[key] = value


async def _bootstrap(settings: DiscoverySettings) -> None:
    try:
        from aiotdlib import Client, ClientSettings, TDLibLogVerbosity
    except Exception as exc:
        raise RuntimeError(
            "aiotdlib is not installed. Install dependencies from pyproject.toml first."
        ) from exc

    settings.session_dir_path.mkdir(parents=True, exist_ok=True)
    client_settings = ClientSettings(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        phone_number=settings.telegram_phone_number,
        password=settings.telegram_2fa_password,
        files_directory=settings.session_dir_path,
        tdlib_verbosity=TDLibLogVerbosity.FATAL,
    )

    print("Starting TDLib login bootstrap. Telegram may prompt for SMS/app code in this terminal.")

    client = Client(settings=client_settings)
    me = None
    try:
        await client.start()
        me = await client.api.get_me(request_timeout=settings.telegram_request_timeout_seconds)
    finally:
        try:
            await client.stop()
        except asyncio.CancelledError:
            # aiotdlib may raise CancelledError while stopping update loop; safe to ignore here.
            pass
        except Exception:
            pass

    marker_path = settings.session_dir_path / ".authorized"
    marker_path.write_text(
        "\n".join(
            [
                f"authorized_at={datetime.now(timezone.utc).replace(microsecond=0).isoformat()}",
                f"user_id={int(getattr(me, 'id', 0))}",
                f"phone_number={settings.telegram_phone_number}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"TDLib session bootstrap complete. Marker written: {marker_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap TDLib discovery session")
    parser.add_argument(
        "--env-file",
        default="configs/sources/telegram_runtime.template.env",
        help="Path to env file with TELEGRAM_API_ID/TELEGRAM_API_HASH/TELEGRAM_PHONE_NUMBER",
    )
    args = parser.parse_args()

    env_file = (ROOT / args.env_file) if not Path(args.env_file).is_absolute() else Path(args.env_file)
    _load_env_file(env_file)

    try:
        settings = DiscoverySettings()
    except Exception as exc:
        print(f"Invalid Telegram env configuration: {exc}", file=sys.stderr)
        return 1

    missing = []
    if not settings.telegram_api_id or str(settings.telegram_api_id) == "replace_me":
        missing.append("TELEGRAM_API_ID")
    if not settings.telegram_api_hash or settings.telegram_api_hash == "replace_me":
        missing.append("TELEGRAM_API_HASH")
    if not settings.telegram_phone_number or settings.telegram_phone_number == "replace_me":
        missing.append("TELEGRAM_PHONE_NUMBER")
    if missing:
        print("Missing required values:", file=sys.stderr)
        for name in missing:
            print(f" - {name}", file=sys.stderr)
        return 1

    if settings.telegram_mode != "tdlib_discovery_only":
        print(
            "Warning: TELEGRAM_MODE is not tdlib_discovery_only. Continuing with TDLib bootstrap anyway.",
            file=sys.stderr,
        )

    try:
        asyncio.run(_bootstrap(settings))
    except KeyboardInterrupt:
        print("Bootstrap cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
