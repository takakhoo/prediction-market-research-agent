from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class PolymarketConfig:
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    clob_base_url: str = "https://clob.polymarket.com"
    data_base_url: str = "https://data-api.polymarket.com"
    timeout_seconds: int = 20

    database_url: str = ""
    direct_url: str = ""

    chain_id: int = 137
    signature_type: int = 0

    likely_probability_threshold: float = 0.75
    unlikely_probability_threshold: float = 0.25
    high_competition_volume_usd: float = 5_000_000.0
    ingest_page_limit: int = 200
    ingest_max_pages: int = 10
    market_store_outcomes: bool = True
    market_store_snapshots: bool = False
    market_analysis_keep_history: bool = False
    telegram_min_channel_members: int = 1000
    telegram_min_channel_relevance_score: float = 0.18
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_http_referer: str = ""
    openai_app_name: str = ""
    openai_timeout_seconds: int = 30
    ai_runtime_mode: str = "prefer_ai"
    ai_market_classifier_model: str = "gpt-4o-mini"
    ai_telegram_query_planner_model: str = "gpt-4o-mini"
    ai_telegram_channel_relevance_model: str = "gpt-4o-mini"
    ai_telegram_message_matcher_model: str = "gpt-4o-mini"
    ai_enable_message_matcher: bool = False
    ai_message_matcher_api_key: str = ""
    ai_message_matcher_base_url: str = ""
    ai_message_matcher_http_referer: str = ""
    ai_message_matcher_app_name: str = ""
    serper_api_key: str = ""
    serpapi_api_key: str = ""
    serp_timeout_seconds: int = 15
    serp_results_per_query: int = 8

    private_key: str = ""
    funder_address: str = ""
    clob_api_key: str = ""
    clob_secret: str = ""
    clob_passphrase: str = ""

    @classmethod
    def from_env(cls) -> "PolymarketConfig":
        def _get(name: str, default: str = "") -> str:
            value = os.getenv(name, default)
            return value.strip() if isinstance(value, str) else value

        timeout_raw = _get("POLYMARKET_TIMEOUT_SECONDS", "20")
        chain_id_raw = _get("POLYMARKET_CHAIN_ID", "137")
        sig_type_raw = _get("POLYMARKET_SIGNATURE_TYPE", "0")
        likely_raw = _get("MARKET_PROB_LIKELY_THRESHOLD", "0.75")
        unlikely_raw = _get("MARKET_PROB_UNLIKELY_THRESHOLD", "0.25")
        high_comp_raw = _get("MARKET_HIGH_COMPETITION_VOLUME_USD", "5000000")
        page_limit_raw = _get("MARKET_INGEST_PAGE_LIMIT", "200")
        max_pages_raw = _get("MARKET_INGEST_MAX_PAGES", "10")
        store_outcomes_raw = _get("MARKET_STORE_OUTCOMES", "true")
        store_snapshots_raw = _get("MARKET_STORE_SNAPSHOTS", "false")
        analysis_keep_history_raw = _get("MARKET_ANALYSIS_KEEP_HISTORY", "false")
        min_members_raw = _get("MARKET_TELEGRAM_MIN_CHANNEL_MEMBERS", "1000")
        min_relevance_raw = _get("MARKET_TELEGRAM_MIN_RELEVANCE_SCORE", "0.18")
        openai_timeout_raw = _get("OPENAI_TIMEOUT_SECONDS", "30")
        serp_timeout_raw = _get("SERP_TIMEOUT_SECONDS", "15")
        serp_results_raw = _get("SERP_RESULTS_PER_QUERY", "8")
        ai_provider = _get("AI_PROVIDER", "").lower()
        openrouter_model = _get("OPENROUTER_MODEL", "")
        if ai_provider == "openrouter":
            primary_api_key = _get("OPENROUTER_API_KEY", "") or _get("OPENAI_API_KEY", "")
            primary_base_url = _get("OPENROUTER_BASE_URL", "") or _get("OPENAI_BASE_URL", "")
            primary_http_referer = _get("OPENROUTER_HTTP_REFERER", "") or _get("OPENAI_HTTP_REFERER", "")
            primary_app_name = (
                _get("OPENROUTER_APP_NAME", "")
                or _get("OPENROUTER_SITE_NAME", "")
                or _get("OPENAI_APP_NAME", "")
            )
        else:
            primary_api_key = _get("OPENAI_API_KEY", "") or _get("OPENROUTER_API_KEY", "")
            primary_base_url = _get("OPENAI_BASE_URL", "") or _get("OPENROUTER_BASE_URL", "")
            primary_http_referer = _get("OPENAI_HTTP_REFERER", "") or _get("OPENROUTER_HTTP_REFERER", "")
            primary_app_name = (
                _get("OPENAI_APP_NAME", "")
                or _get("OPENROUTER_APP_NAME", "")
                or _get("OPENROUTER_SITE_NAME", "")
            )

        return cls(
            gamma_base_url=_get("POLYMARKET_GAMMA_BASE_URL", "https://gamma-api.polymarket.com"),
            clob_base_url=_get("POLYMARKET_CLOB_BASE_URL", "https://clob.polymarket.com"),
            data_base_url=_get("POLYMARKET_DATA_BASE_URL", "https://data-api.polymarket.com"),
            timeout_seconds=_safe_int(timeout_raw, 20),
            database_url=(
                _get("SUPABASE_DB_URL")
                or _get("DATABASE_URL")
                or _get("SUPABASE_DIRECT_DB_URL")
                or _get("DIRECT_URL")
            ),
            direct_url=(
                _get("SUPABASE_DIRECT_DB_URL")
                or _get("DIRECT_URL")
                or _get("SUPABASE_DB_URL")
                or _get("DATABASE_URL")
            ),
            chain_id=_safe_int(chain_id_raw, 137),
            signature_type=_safe_int(sig_type_raw, 0),
            likely_probability_threshold=_safe_float(likely_raw, 0.75),
            unlikely_probability_threshold=_safe_float(unlikely_raw, 0.25),
            high_competition_volume_usd=_safe_float(high_comp_raw, 5_000_000.0),
            ingest_page_limit=max(1, min(_safe_int(page_limit_raw, 200), 500)),
            ingest_max_pages=max(1, min(_safe_int(max_pages_raw, 10), 1000)),
            market_store_outcomes=_safe_bool(store_outcomes_raw, True),
            market_store_snapshots=_safe_bool(store_snapshots_raw, False),
            market_analysis_keep_history=_safe_bool(analysis_keep_history_raw, False),
            telegram_min_channel_members=max(0, min(_safe_int(min_members_raw, 1000), 10_000_000)),
            telegram_min_channel_relevance_score=max(0.0, min(_safe_float(min_relevance_raw, 0.18), 1.0)),
            openai_api_key=primary_api_key,
            openai_base_url=primary_base_url,
            openai_http_referer=primary_http_referer,
            openai_app_name=primary_app_name,
            openai_timeout_seconds=max(5, min(_safe_int(openai_timeout_raw, 30), 300)),
            ai_runtime_mode=_get("AI_RUNTIME_MODE", "prefer_ai").lower() or "prefer_ai",
            ai_market_classifier_model=_get("AI_MARKET_CLASSIFIER_MODEL", "") or openrouter_model or "gpt-4o-mini",
            ai_telegram_query_planner_model=_get("AI_TELEGRAM_QUERY_PLANNER_MODEL", "") or openrouter_model or "gpt-4o-mini",
            ai_telegram_channel_relevance_model=(
                _get("AI_TELEGRAM_CHANNEL_RELEVANCE_MODEL", "") or openrouter_model or "gpt-4o-mini"
            ),
            ai_telegram_message_matcher_model=(
                _get("AI_TELEGRAM_MESSAGE_MATCHER_MODEL", "") or openrouter_model or "gpt-4o-mini"
            ),
            ai_enable_message_matcher=_safe_bool(_get("AI_ENABLE_MESSAGE_MATCHER", "false"), False),
            ai_message_matcher_api_key=_get("AI_MESSAGE_MATCHER_API_KEY", ""),
            ai_message_matcher_base_url=_get("AI_MESSAGE_MATCHER_BASE_URL", ""),
            ai_message_matcher_http_referer=_get("AI_MESSAGE_MATCHER_HTTP_REFERER", ""),
            ai_message_matcher_app_name=_get("AI_MESSAGE_MATCHER_APP_NAME", ""),
            serper_api_key=_get("SERPER_API_KEY", ""),
            serpapi_api_key=_get("SERPAPI_API_KEY", ""),
            serp_timeout_seconds=max(5, min(_safe_int(serp_timeout_raw, 15), 120)),
            serp_results_per_query=max(1, min(_safe_int(serp_results_raw, 8), 20)),
            private_key=_get("POLYMARKET_PRIVATE_KEY", ""),
            funder_address=_get("POLYMARKET_FUNDER_ADDRESS", ""),
            clob_api_key=_get("POLYMARKET_CLOB_API_KEY", ""),
            clob_secret=_get("POLYMARKET_CLOB_SECRET", ""),
            clob_passphrase=_get("POLYMARKET_CLOB_PASSPHRASE", ""),
        )


@dataclass(frozen=True)
class TradingReadiness:
    mode: str
    ready: bool
    missing: list[str]
    notes: list[str]


def evaluate_trading_readiness(config: PolymarketConfig) -> TradingReadiness:
    missing: list[str] = []
    notes: list[str] = []

    if not config.private_key:
        missing.append("POLYMARKET_PRIVATE_KEY")
    if not config.funder_address:
        missing.append("POLYMARKET_FUNDER_ADDRESS")

    has_l2 = bool(config.clob_api_key and config.clob_secret and config.clob_passphrase)
    if not has_l2:
        notes.append(
            "L2 CLOB API credentials are missing. You can derive/create them from private key (L1 auth) via official CLOB clients."
        )

    mode = "trading_ready" if not missing else "read_only"
    ready = len(missing) == 0
    return TradingReadiness(mode=mode, ready=ready, missing=missing, notes=notes)


def _safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: str, default: bool) -> bool:
    lowered = str(value or "").strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default
