from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "telegram_preflight.sh"


def test_preflight_tdlib_discovery_only_passes_without_bot_token(tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "\n".join(
            [
                "TELEGRAM_API_ID=123",
                "TELEGRAM_API_HASH=testhash",
                "TELEGRAM_PHONE_NUMBER=+10000000000",
                "TELEGRAM_SESSION_DIR=.runtime/telegram_session",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", str(SCRIPT), "tdlib_discovery_only", str(env_file)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Preflight OK for mode: tdlib_discovery_only" in result.stdout


def test_preflight_tdlib_discovery_only_reports_missing_values(tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "\n".join(
            [
                "TELEGRAM_API_ID=123",
                "TELEGRAM_PHONE_NUMBER=+10000000000",
                "TELEGRAM_SESSION_DIR=.runtime/telegram_session",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", str(SCRIPT), "tdlib_discovery_only", str(env_file)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "TELEGRAM_API_HASH" in result.stdout
