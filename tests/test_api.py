from __future__ import annotations

from typing import Any, Dict, List

from fastapi.testclient import TestClient

from src.discovery.api import create_app
from src.discovery.config import DiscoverySettings
from src.discovery.repository import DiscoveryRepository


class FakeTDLibClient:
    def __init__(self):
        self.started = False
        self.session_marker_exists = True

    def auth_state(self) -> str:
        return "ready" if self.started else "session_marker_present"

    async def ensure_started(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.started = False

    async def search_public_chats(self, query: str, limit: int) -> List[Dict[str, Any]]:
        await self.ensure_started()
        return [
            {
                "chat_id": 1,
                "title": f"{query} Channel",
                "username": "query_channel",
                "description": "search hit",
                "member_count": 100,
            }
        ][:limit]

    async def get_channel(self, chat_id: int) -> Dict[str, Any] | None:
        await self.ensure_started()
        if chat_id <= 0:
            return None
        return {
            "chat_id": chat_id,
            "title": f"Channel {chat_id}",
            "username": f"channel_{chat_id}",
            "description": "desc",
            "member_count": 50,
        }

    async def get_chat_history(self, chat_id: int, limit: int) -> Dict[str, Any]:
        await self.ensure_started()
        if chat_id == 999:
            return {
                "channel": await self.get_channel(chat_id),
                "messages": [],
            }
        return {
            "channel": await self.get_channel(chat_id),
            "messages": [
                {
                    "chat_id": chat_id,
                    "message_id": 10,
                    "posted_at": "2026-02-28T12:00:00+00:00",
                    "text": "hello",
                    "url": f"https://t.me/channel_{chat_id}/10",
                }
            ][:limit],
        }

    async def get_chat_similar_chats(self, chat_id: int) -> List[Dict[str, Any]]:
        await self.ensure_started()
        if chat_id == 1:
            return [
                {
                    "chat_id": 2,
                    "title": "Channel 2",
                    "username": "channel_2",
                    "description": "second",
                    "member_count": 20,
                },
                {
                    "chat_id": 3,
                    "title": "Channel 3",
                    "username": "channel_3",
                    "description": "third",
                    "member_count": 30,
                },
                {
                    "chat_id": 2,
                    "title": "Channel 2",
                    "username": "channel_2",
                    "description": "second",
                    "member_count": 20,
                },
            ]
        return []


def _build_client(tmp_path) -> TestClient:
    settings = DiscoverySettings(
        telegram_api_id=1,
        telegram_api_hash="hash",
        telegram_phone_number="+10000000000",
        discovery_db_path=tmp_path / "discovery.db",
        telegram_session_dir=tmp_path / "session",
    )
    app = create_app(
        settings=settings,
        repository=DiscoveryRepository(settings.db_path),
        tdlib_client=FakeTDLibClient(),
    )
    return TestClient(app)


def test_api_search_returns_normalized_channels(tmp_path):
    with _build_client(tmp_path) as client:
        resp = client.post("/api/search", json={"query": "Lebanon", "limit": 10})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["query"] == "Lebanon"
        assert payload["channels"][0]["title"] == "Lebanon Channel"


def test_api_messages_handles_empty_result(tmp_path):
    with _build_client(tmp_path) as client:
        resp = client.get("/api/channels/999/messages?limit=30")
        assert resp.status_code == 200
        assert resp.json() == []


def test_api_expand_similar_respects_caps_and_dedupes(tmp_path):
    with _build_client(tmp_path) as client:
        resp = client.post(
            "/api/channels/1/expand-similar",
            json={"depth": 2, "per_node": 1, "max_nodes": 3},
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["depth"] == 2
        assert payload["node_count"] <= 3
        assert len(payload["edges"]) == 1
        assert payload["edges"][0]["child_chat_id"] == 2


def test_ui_probe_renders_visual_probe_panel(tmp_path):
    with _build_client(tmp_path) as client:
        resp = client.get("/ui/probe?query=Lebanon&limit=5&messages_limit=2&similar_limit=2")
        assert resp.status_code == 200
        body = resp.text
        assert "Raw probe JSON" in body
        assert "Selected channel" in body
