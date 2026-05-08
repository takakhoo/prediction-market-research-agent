from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional

from .config import DiscoverySettings
from .errors import TDLibAuthRequiredError, TDLibRequestError, WatchlistError
from .models import (
    ChannelResult,
    ExpandSimilarRequest,
    ExpandSimilarResponse,
    MessageResult,
    SearchResponse,
    SimilarEdgeResult,
    WatchlistCreateRequest,
    WatchlistItem,
    WatchlistPatchRequest,
)
from .repository import DiscoveryRepository
from .tdlib_client import TDLibDiscoveryClient


class DiscoveryService:
    def __init__(
        self,
        settings: DiscoverySettings,
        repository: DiscoveryRepository,
        tdlib_client: TDLibDiscoveryClient,
    ):
        self.settings = settings
        self.repository = repository
        self.tdlib_client = tdlib_client

    async def health(self) -> Dict[str, Any]:
        auth_state = self.tdlib_client.auth_state()
        if auth_state != "bootstrap_required":
            try:
                await self.tdlib_client.ensure_started()
                auth_state = self.tdlib_client.auth_state()
            except TDLibAuthRequiredError:
                auth_state = "bootstrap_required"
            except TDLibRequestError:
                auth_state = "error"

        return {
            "status": "ok",
            "auth_state": auth_state,
            "read_only_mode": self.settings.telegram_read_only_mode,
            "session_marker_exists": self.tdlib_client.session_marker_exists,
            "tdlib_started": self.tdlib_client.started,
            "db_path": str(self.settings.db_path),
        }

    async def search_channels(self, query: str, limit: Optional[int]) -> SearchResponse:
        effective_limit = limit or self.settings.discovery_search_limit
        effective_limit = max(1, min(effective_limit, self.settings.discovery_search_limit))

        channels = await self.tdlib_client.search_public_chats(query, effective_limit)
        await self.repository.upsert_channels(channels, source="search")
        run_id = await self.repository.create_discovery_run(query)

        return SearchResponse(
            run_id=run_id,
            query=query,
            channels=[ChannelResult(**channel, last_source="search") for channel in channels],
        )

    async def channel_messages(self, chat_id: int, limit: Optional[int]) -> List[MessageResult]:
        requested_limit = limit or self.settings.discovery_message_preview_limit
        effective_limit = max(1, min(requested_limit, self.settings.discovery_message_preview_limit, 100))

        result = await self.tdlib_client.get_chat_history(chat_id, effective_limit)
        channel = result["channel"]
        messages = result["messages"]

        await self.repository.upsert_channels([channel], source="history")
        await self.repository.upsert_messages(chat_id, messages)

        return [MessageResult(**message) for message in messages]

    async def expand_similar(
        self,
        chat_id: int,
        request: ExpandSimilarRequest,
    ) -> ExpandSimilarResponse:
        depth = request.depth or self.settings.discovery_similar_depth
        per_node = request.per_node or self.settings.discovery_similar_per_node
        max_nodes = request.max_nodes or self.settings.discovery_similar_max_nodes

        depth = max(1, min(depth, 4))
        per_node = max(1, min(per_node, 50))
        max_nodes = max(1, min(max_nodes, 500))

        root_channel = await self.tdlib_client.get_channel(chat_id)
        if root_channel is None:
            raise WatchlistError(f"Chat {chat_id} is not a public channel")

        queue = deque([(chat_id, 0)])
        visited = {chat_id}
        seen_channels: Dict[int, Dict[str, Any]] = {chat_id: root_channel}
        edges: List[Dict[str, int]] = []
        edge_keys = set()

        while queue:
            parent_chat_id, parent_depth = queue.popleft()
            if parent_depth >= depth:
                continue

            similar = await self.tdlib_client.get_chat_similar_chats(parent_chat_id)
            accepted = 0

            for channel in similar:
                child_chat_id = int(channel["chat_id"])
                if child_chat_id == parent_chat_id:
                    continue
                if accepted >= per_node:
                    break

                edge_key = (parent_chat_id, child_chat_id)
                if edge_key not in edge_keys:
                    edge_keys.add(edge_key)
                    edges.append(
                        {
                            "parent_chat_id": parent_chat_id,
                            "child_chat_id": child_chat_id,
                            "depth": parent_depth + 1,
                        }
                    )
                seen_channels[child_chat_id] = channel
                accepted += 1

                if child_chat_id not in visited and len(visited) < max_nodes:
                    visited.add(child_chat_id)
                    queue.append((child_chat_id, parent_depth + 1))

            if len(visited) >= max_nodes:
                break

        run_id = await self.repository.create_discovery_run(f"similar:{chat_id}")
        await self.repository.upsert_channels(seen_channels.values(), source="similar")
        await self.repository.save_similar_edges(run_id, edges)

        sorted_channels = sorted(seen_channels.values(), key=lambda item: item["chat_id"])

        return ExpandSimilarResponse(
            run_id=run_id,
            root_chat_id=chat_id,
            depth=depth,
            channels=[ChannelResult(**channel, last_source="similar") for channel in sorted_channels],
            edges=[SimilarEdgeResult(**edge) for edge in edges],
            node_count=len(visited),
        )

    async def get_watchlist(self) -> List[WatchlistItem]:
        items = await self.repository.get_watchlist()
        return [WatchlistItem(**item) for item in items]

    async def add_watchlist(self, request: WatchlistCreateRequest) -> WatchlistItem:
        channel = await self.repository.get_channel(request.chat_id)
        if channel is None:
            resolved = await self.tdlib_client.get_channel(request.chat_id)
            if resolved is None:
                raise WatchlistError(f"Chat {request.chat_id} is not a public channel")
            await self.repository.upsert_channels([resolved], source="watchlist")

        item = await self.repository.set_watchlist_item(
            chat_id=request.chat_id,
            trust_weight=request.trust_weight,
            tags=request.tags,
            notes=request.notes,
        )
        return WatchlistItem(**item)

    async def patch_watchlist(self, chat_id: int, request: WatchlistPatchRequest) -> WatchlistItem:
        item = await self.repository.patch_watchlist_item(
            chat_id=chat_id,
            trust_weight=request.trust_weight,
            tags=request.tags,
            notes=request.notes,
        )
        if item is None:
            raise WatchlistError(f"Watchlist entry {chat_id} not found")
        return WatchlistItem(**item)
