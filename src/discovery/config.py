from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class DiscoverySettings(BaseSettings):
    """Runtime settings for the Telegram discovery dashboard."""

    telegram_mode: str = Field(default="tdlib_discovery_only", validation_alias="TELEGRAM_MODE")
    telegram_api_id: int = Field(default=0, validation_alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(default="", validation_alias="TELEGRAM_API_HASH")
    telegram_phone_number: str = Field(default="", validation_alias="TELEGRAM_PHONE_NUMBER")
    telegram_2fa_password: Optional[str] = Field(default=None, validation_alias="TELEGRAM_2FA_PASSWORD")
    telegram_read_only_mode: bool = Field(default=True, validation_alias="TELEGRAM_READ_ONLY_MODE")
    telegram_session_dir: Path = Field(
        default=Path(".runtime/telegram_session"),
        validation_alias="TELEGRAM_SESSION_DIR",
    )
    telegram_request_timeout_seconds: int = Field(
        default=20,
        validation_alias="TELEGRAM_REQUEST_TIMEOUT_SECONDS",
    )

    discovery_db_path: Path = Field(
        default=Path("data/derived/discovery.db"),
        validation_alias="DISCOVERY_DB_PATH",
    )
    discovery_search_limit: int = Field(default=50, validation_alias="DISCOVERY_SEARCH_LIMIT")
    discovery_similar_depth: int = Field(default=2, validation_alias="DISCOVERY_SIMILAR_DEPTH")
    discovery_similar_per_node: int = Field(default=20, validation_alias="DISCOVERY_SIMILAR_PER_NODE")
    discovery_similar_max_nodes: int = Field(default=120, validation_alias="DISCOVERY_SIMILAR_MAX_NODES")
    discovery_message_preview_limit: int = Field(default=30, validation_alias="DISCOVERY_MESSAGE_PREVIEW_LIMIT")

    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    @property
    def session_dir_path(self) -> Path:
        return _resolve_repo_path(self.telegram_session_dir)

    @property
    def db_path(self) -> Path:
        return _resolve_repo_path(self.discovery_db_path)



def _resolve_repo_path(path_value: Path) -> Path:
    if path_value.is_absolute():
        return path_value
    return REPO_ROOT / path_value
