from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROMPTS_DIR = REPO_ROOT / "configs" / "prompts"


def resolve_prompts_dir() -> Path:
    raw = str(os.getenv("PROMPTS_DIR", "") or "").strip()
    if not raw:
        return DEFAULT_PROMPTS_DIR

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def load_prompt_template(relative_path: str, fallback: str) -> str:
    prompt_path = resolve_prompts_dir() / relative_path
    try:
        text = prompt_path.read_text(encoding="utf-8").strip()
    except OSError:
        return fallback
    return text or fallback


def render_prompt_template(template: str, values: Mapping[str, str]) -> str:
    # One pass: placeholders inside inserted, untrusted data stay literal.
    return re.sub(r"\{\{([^{}]+)\}\}", lambda m: str(values[m[1]]) if m[1] in values else m[0], str(template))
