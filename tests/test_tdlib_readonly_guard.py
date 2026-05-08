from __future__ import annotations

import pytest

from src.discovery.config import DiscoverySettings
from src.discovery.errors import TDLibRequestError
from src.discovery.tdlib_client import TDLibDiscoveryClient


def test_read_only_guard_allows_get_and_search_ops(tmp_path):
    settings = DiscoverySettings(
        telegram_read_only_mode=True,
        discovery_db_path=tmp_path / "db.sqlite3",
        telegram_session_dir=tmp_path / "session",
    )
    client = TDLibDiscoveryClient(settings)
    client._assert_read_only_operation("get_chat_history")
    client._assert_read_only_operation("search_public_chats")


def test_read_only_guard_blocks_non_allowlisted_ops(tmp_path):
    settings = DiscoverySettings(
        telegram_read_only_mode=True,
        discovery_db_path=tmp_path / "db.sqlite3",
        telegram_session_dir=tmp_path / "session",
    )
    client = TDLibDiscoveryClient(settings)

    with pytest.raises(TDLibRequestError, match="blocked by TELEGRAM_READ_ONLY_MODE"):
        client._assert_read_only_operation("send_message")


def test_read_only_guard_can_be_disabled(tmp_path):
    settings = DiscoverySettings(
        telegram_read_only_mode=False,
        discovery_db_path=tmp_path / "db.sqlite3",
        telegram_session_dir=tmp_path / "session",
    )
    client = TDLibDiscoveryClient(settings)
    client._assert_read_only_operation("send_message")
