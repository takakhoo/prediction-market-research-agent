#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


MONTH_TOKENS = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
}
STOP_TOKENS = MONTH_TOKENS | {
    "a",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "before",
    "between",
    "by",
    "end",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "there",
    "this",
    "to",
    "week",
    "will",
    "with",
    "year",
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Env file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve handpicked market names against grouped Polymarket markets.")
    parser.add_argument("input_path", help="Text file containing one requested market per line.")
    parser.add_argument("--env-file", default=".env", help="Path to runtime env file.")
    parser.add_argument("--apply-migration", action="store_true", help="Apply sql/003_handpicked_market_targets.sql before import.")
    parser.add_argument(
        "--replace-source",
        action="store_true",
        help="Delete existing rows for the same source_file before importing.",
    )
    parser.add_argument(
        "--match-threshold",
        type=float,
        default=0.72,
        help="Score needed for an automatic match.",
    )
    parser.add_argument(
        "--review-threshold",
        type=float,
        default=0.58,
        help="Score needed to store as low_confidence instead of unmatched.",
    )
    parser.add_argument(
        "--margin-threshold",
        type=float,
        default=0.07,
        help="Minimum lead over the second-best candidate for an automatic match.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="How many candidates to persist for each request.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write to the database.",
    )
    return parser


@dataclass(frozen=True)
class ParsedRequest:
    line_number: int
    raw_line: str
    requested_name: str
    requested_bucket: str | None
    requested_locator: str | None


def parse_request_lines(path: Path) -> list[ParsedRequest]:
    requests: list[ParsedRequest] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        requested_name = parts[0]
        requested_bucket = parts[1] if len(parts) >= 2 and parts[1] else None
        requested_locator = parts[2] if len(parts) >= 3 and parts[2] else None
        requests.append(
            ParsedRequest(
                line_number=line_number,
                raw_line=raw_line.rstrip("\n"),
                requested_name=requested_name,
                requested_bucket=requested_bucket,
                requested_locator=requested_locator,
            )
        )
    return requests


def normalize_text(value: str | None) -> str:
    text = str(value or "").lower().strip()
    text = text.replace("&", " and ")
    text = re.sub(r"\bu\.s\.\b", "us", text)
    text = re.sub(r"\bx\b", " ", text)
    text = text.replace("/", " ")
    text = text.replace("-", " ")
    text = text.replace("_", " ")
    text = text.replace("…", " ")
    text = text.replace("...", " ")
    text = re.sub(r"\b(20\d{2}|19\d{2})\b", " ", text)
    text = re.sub(r"\b\d+(st|nd|rd|th)?\b", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def informative_tokens(value: str | None) -> set[str]:
    tokens = set()
    for token in normalize_text(value).split():
        if not token or token in STOP_TOKENS:
            continue
        if len(token) == 1:
            continue
        tokens.add(token)
    return tokens


def score_text_pair(query: str, candidate: str) -> float:
    query_norm = normalize_text(query)
    candidate_norm = normalize_text(candidate)
    if not query_norm or not candidate_norm:
        return 0.0
    if query_norm == candidate_norm:
        return 1.0
    query_tokens = informative_tokens(query_norm)
    candidate_tokens = informative_tokens(candidate_norm)
    overlap = len(query_tokens & candidate_tokens)
    query_cover = overlap / len(query_tokens) if query_tokens else 0.0
    candidate_cover = overlap / len(candidate_tokens) if candidate_tokens else 0.0
    contains_bonus = 1.0 if query_norm in candidate_norm or candidate_norm in query_norm else 0.0
    ratio = SequenceMatcher(None, query_norm, candidate_norm).ratio()
    compact_ratio = SequenceMatcher(None, query_norm.replace(" ", ""), candidate_norm.replace(" ", "")).ratio()
    return max(
        ratio,
        compact_ratio,
        (0.35 * ratio) + (0.35 * compact_ratio) + (0.2 * query_cover) + (0.1 * contains_bonus),
        (0.45 * query_cover) + (0.2 * candidate_cover) + (0.25 * ratio) + (0.1 * contains_bonus),
    )


def bucket_bonus(requested_bucket: str | None, scope_label: str | None) -> float:
    requested_tokens = informative_tokens(requested_bucket)
    scope_tokens = informative_tokens(scope_label)
    if not requested_tokens or not scope_tokens:
        return 0.0
    overlap = len(requested_tokens & scope_tokens)
    if overlap == 0:
        return 0.0
    return min(0.12, 0.04 * overlap)


def extract_slug_from_locator(locator: str | None) -> str | None:
    value = str(locator or "").strip()
    if not value:
        return None
    if re.fullmatch(r"[a-z0-9-]+", value.lower()):
        return value.lower()
    parsed = urlparse(value)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0].lower() == "event":
        slug = parts[1].strip().lower()
        if re.fullmatch(r"[a-z0-9-]+", slug):
            return slug
    return None


def fetch_group_records(conn: psycopg.Connection[Any]) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              mg.group_slug,
              mg.group_title,
              mg.scope_label,
              mg.representative_market_id,
              mg.market_count,
              mg.tradable_market_count,
              mg.sample_questions,
              COALESCE(m.question, '') AS representative_question
            FROM market_groups mg
            LEFT JOIN markets m
              ON m.market_id = mg.representative_market_id
            ORDER BY mg.scope_label ASC, mg.market_count DESC, mg.group_slug ASC;
            """
        )
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row["sample_questions"] = list(row.get("sample_questions") or [])
    return rows


def score_group_candidates(
    request: ParsedRequest,
    groups: list[dict[str, Any]],
    *,
    top_k: int,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    locator_slug = extract_slug_from_locator(request.requested_locator)
    if locator_slug:
        for group in groups:
            if str(group.get("group_slug") or "").strip().lower() == locator_slug:
                candidate = {
                    "group_slug": group["group_slug"],
                    "group_title": group["group_title"],
                    "scope_label": group["scope_label"],
                    "representative_market_id": group["representative_market_id"],
                    "market_count": int(group.get("market_count") or 0),
                    "score": 1.0,
                    "match_method": "direct_locator",
                    "matched_field": "group_slug",
                    "matched_text": group["group_slug"],
                }
                return candidate, [candidate]

    scored_candidates: list[dict[str, Any]] = []
    for group in groups:
        candidate_texts = [
            ("group_title", str(group.get("group_title") or "")),
            ("group_slug", str(group.get("group_slug") or "")),
            ("representative_question", str(group.get("representative_question") or "")),
        ]
        for sample_question in list(group.get("sample_questions") or []):
            candidate_texts.append(("sample_question", str(sample_question or "")))
        best_score = 0.0
        best_field = ""
        best_text = ""
        for field_name, candidate_text in candidate_texts:
            score = score_text_pair(request.requested_name, candidate_text)
            score += bucket_bonus(request.requested_bucket, str(group.get("scope_label") or ""))
            if score > best_score:
                best_score = score
                best_field = field_name
                best_text = candidate_text
        if best_score <= 0:
            continue
        scored_candidates.append(
            {
                "group_slug": group["group_slug"],
                "group_title": group["group_title"],
                "scope_label": group["scope_label"],
                "representative_market_id": group["representative_market_id"],
                "market_count": int(group.get("market_count") or 0),
                "score": round(min(best_score, 1.0), 4),
                "match_method": "scored_text",
                "matched_field": best_field,
                "matched_text": best_text,
            }
        )

    scored_candidates.sort(
        key=lambda item: (
            -float(item.get("score") or 0.0),
            -int(item.get("market_count") or 0),
            str(item.get("group_slug") or ""),
        )
    )
    top_candidates = scored_candidates[: max(1, top_k)]
    top_candidate = top_candidates[0] if top_candidates else None
    return top_candidate, top_candidates


def derive_match_status(
    top_candidate: dict[str, Any] | None,
    top_candidates: list[dict[str, Any]],
    *,
    match_threshold: float,
    review_threshold: float,
    margin_threshold: float,
) -> tuple[str, str | None]:
    if not top_candidate:
        return "unmatched", "No viable market group candidate."
    top_score = float(top_candidate.get("score") or 0.0)
    second_score = float(top_candidates[1].get("score") or 0.0) if len(top_candidates) >= 2 else 0.0
    margin = top_score - second_score
    if top_candidate.get("match_method") == "direct_locator":
        return "matched", "Resolved directly from provided locator."
    if top_score >= match_threshold and (margin >= margin_threshold or top_score >= 0.9):
        return "matched", f"Top candidate cleared match threshold with margin {margin:.3f}."
    if top_score >= review_threshold:
        return "low_confidence", f"Top candidate score {top_score:.3f} needs review; margin {margin:.3f}."
    return "unmatched", f"No candidate cleared review threshold; top score {top_score:.3f}."


def apply_migration(conn: psycopg.Connection[Any]) -> None:
    migration_path = ROOT / "sql" / "003_handpicked_market_targets.sql"
    with conn.cursor() as cur:
        cur.execute(migration_path.read_text(encoding="utf-8"))
    conn.commit()


def build_rows(
    requests: list[ParsedRequest],
    groups: list[dict[str, Any]],
    *,
    source_file: str,
    top_k: int,
    match_threshold: float,
    review_threshold: float,
    margin_threshold: float,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    summary = {"matched": 0, "low_confidence": 0, "unmatched": 0}
    for request in requests:
        top_candidate, top_candidates = score_group_candidates(request, groups, top_k=top_k)
        match_status, notes = derive_match_status(
            top_candidate,
            top_candidates,
            match_threshold=match_threshold,
            review_threshold=review_threshold,
            margin_threshold=margin_threshold,
        )
        summary[match_status] += 1
        chosen = top_candidate if match_status in {"matched", "low_confidence"} else None
        rows.append(
            {
                "source_file": source_file,
                "source_line_number": request.line_number,
                "raw_line": request.raw_line,
                "requested_name": request.requested_name,
                "requested_bucket": request.requested_bucket,
                "requested_locator": request.requested_locator,
                "match_status": match_status,
                "matched_group_slug": chosen.get("group_slug") if chosen else None,
                "matched_group_title": chosen.get("group_title") if chosen else None,
                "matched_scope_label": chosen.get("scope_label") if chosen else None,
                "representative_market_id": chosen.get("representative_market_id") if chosen else None,
                "matched_market_count": chosen.get("market_count") if chosen else None,
                "match_score": float(chosen.get("score")) if chosen else None,
                "match_method": chosen.get("match_method") if chosen else None,
                "candidate_payload": Jsonb(top_candidates),
                "notes": notes,
            }
        )
    return rows, summary


def persist_rows(
    conn: psycopg.Connection[Any],
    *,
    source_file: str,
    rows: list[dict[str, Any]],
    replace_source: bool,
) -> None:
    with conn.cursor() as cur:
        if replace_source:
            cur.execute("DELETE FROM handpicked_market_targets WHERE source_file = %s;", (source_file,))
        cur.executemany(
            """
            INSERT INTO handpicked_market_targets (
              source_file,
              source_line_number,
              raw_line,
              requested_name,
              requested_bucket,
              requested_locator,
              match_status,
              matched_group_slug,
              matched_group_title,
              matched_scope_label,
              representative_market_id,
              matched_market_count,
              match_score,
              match_method,
              candidate_payload,
              notes,
              imported_at,
              updated_at
            ) VALUES (
              %(source_file)s,
              %(source_line_number)s,
              %(raw_line)s,
              %(requested_name)s,
              %(requested_bucket)s,
              %(requested_locator)s,
              %(match_status)s,
              %(matched_group_slug)s,
              %(matched_group_title)s,
              %(matched_scope_label)s,
              %(representative_market_id)s,
              %(matched_market_count)s,
              %(match_score)s,
              %(match_method)s,
              %(candidate_payload)s,
              %(notes)s,
              NOW(),
              NOW()
            )
            ON CONFLICT (source_file, source_line_number) DO UPDATE
            SET
              raw_line = EXCLUDED.raw_line,
              requested_name = EXCLUDED.requested_name,
              requested_bucket = EXCLUDED.requested_bucket,
              requested_locator = EXCLUDED.requested_locator,
              match_status = EXCLUDED.match_status,
              matched_group_slug = EXCLUDED.matched_group_slug,
              matched_group_title = EXCLUDED.matched_group_title,
              matched_scope_label = EXCLUDED.matched_scope_label,
              representative_market_id = EXCLUDED.representative_market_id,
              matched_market_count = EXCLUDED.matched_market_count,
              match_score = EXCLUDED.match_score,
              match_method = EXCLUDED.match_method,
              candidate_payload = EXCLUDED.candidate_payload,
              notes = EXCLUDED.notes,
              updated_at = NOW();
            """,
            rows,
        )
    conn.commit()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    input_path = Path(args.input_path).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    load_env_file(Path(args.env_file))
    db_url = os.environ.get("SUPABASE_DIRECT_DB_URL") or os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("No database URL configured. Set SUPABASE_DIRECT_DB_URL or SUPABASE_DB_URL in the env file.")

    requests = parse_request_lines(input_path)
    if not requests:
        raise RuntimeError(f"No importable lines found in {input_path}")

    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        if args.apply_migration:
            apply_migration(conn)
        groups = fetch_group_records(conn)
        if not groups:
            raise RuntimeError("No market_groups rows found. Build grouped markets first.")
        rows, summary = build_rows(
            requests,
            groups,
            source_file=str(input_path),
            top_k=max(1, min(int(args.top_k), 10)),
            match_threshold=float(args.match_threshold),
            review_threshold=float(args.review_threshold),
            margin_threshold=float(args.margin_threshold),
        )
        if not args.dry_run:
            persist_rows(
                conn,
                source_file=str(input_path),
                rows=rows,
                replace_source=bool(args.replace_source),
            )

    preview_rows = []
    for row in rows[:10]:
        preview_rows.append(
            {
                "line": row["source_line_number"],
                "requested_name": row["requested_name"],
                "status": row["match_status"],
                "matched_group_slug": row["matched_group_slug"],
                "match_score": row["match_score"],
            }
        )
    result = {
        "input_path": str(input_path),
        "requests": len(requests),
        "summary": summary,
        "stored": not bool(args.dry_run),
        "preview": preview_rows,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
