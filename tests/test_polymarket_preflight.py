from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "polymarket_preflight.sh"


def test_polymarket_preflight_read_only_passes_without_keys(tmp_path):
    env_file = tmp_path / "pm.env"
    env_file.write_text("POLYMARKET_GAMMA_BASE_URL=https://gamma-api.polymarket.com\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(SCRIPT), "read_only", str(env_file)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Preflight OK for mode: read_only" in result.stdout


def test_polymarket_preflight_trading_requires_key_and_funder(tmp_path):
    env_file = tmp_path / "pm.env"
    env_file.write_text("POLYMARKET_GAMMA_BASE_URL=https://gamma-api.polymarket.com\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(SCRIPT), "trading", str(env_file)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "POLYMARKET_PRIVATE_KEY" in result.stdout
    assert "POLYMARKET_FUNDER_ADDRESS" in result.stdout
