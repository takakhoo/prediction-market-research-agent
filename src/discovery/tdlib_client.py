from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config import DiscoverySettings
from .errors import TDLibAuthRequiredError, TDLibRequestError

try:
    from aiotdlib import Client, ClientSettings, TDLibLogVerbosity
    from aiotdlib.api import AioTDLibError
except Exception as import_error:  # pragma: no cover - tested by runtime import path
    Client = None
    ClientSettings = None
    TDLibLogVerbosity = None
    AioTDLibError = Exception
    _AIOTDLIB_IMPORT_ERROR = import_error
else:
    _AIOTDLIB_IMPORT_ERROR = None

_READ_ONLY_ALLOWED_OPERATIONS = {
    "search_public_chats",
    "search_public_chat",
    "get_chat_history",
    "get_chat_similar_chats",
    "get_chat",
    "get_supergroup",
    "get_supergroup_full_info",
}


class TDLibDiscoveryClient:
    def __init__(self, settings: DiscoverySettings):
        self.settings = settings
        self._client: Optional[Client] = None
        self._started = False
        self._start_lock = asyncio.Lock()
        # TDLib/aiotdlib can fail if receive is triggered from concurrent call paths.
        # Serialize all request calls through one lock.
        self._api_lock = asyncio.Lock()

    @property
    def started(self) -> bool:
        return self._started

    @property
    def session_marker_path(self) -> Path:
        return self.settings.session_dir_path / ".authorized"

    @property
    def session_marker_exists(self) -> bool:
        return self.session_marker_path.exists()

    def auth_state(self) -> str:
        if self._started:
            return "ready"
        if self.session_marker_exists:
            return "session_marker_present"
        return "bootstrap_required"

    async def ensure_started(self) -> None:
        if self._started:
            return

        async with self._start_lock:
            if self._started:
                return

            if Client is None or ClientSettings is None or TDLibLogVerbosity is None:
                raise TDLibRequestError(
                    "aiotdlib is not available. Install dependencies from pyproject.toml."
                ) from _AIOTDLIB_IMPORT_ERROR

            if not self.session_marker_exists:
                raise TDLibAuthRequiredError(
                    "TDLib session is not bootstrapped. Run scripts/telegram_session_bootstrap.py first."
                )
            if (
                not self.settings.telegram_api_id
                or not self.settings.telegram_api_hash
                or not self.settings.telegram_phone_number
                or self.settings.telegram_api_hash == "replace_me"
                or self.settings.telegram_phone_number == "replace_me"
            ):
                raise TDLibRequestError(
                    "Telegram credentials are missing. Set TELEGRAM_API_ID/TELEGRAM_API_HASH/TELEGRAM_PHONE_NUMBER."
                )

            self.settings.session_dir_path.mkdir(parents=True, exist_ok=True)

            client_settings = ClientSettings(
                api_id=self.settings.telegram_api_id,
                api_hash=self.settings.telegram_api_hash,
                phone_number=self.settings.telegram_phone_number,
                password=self.settings.telegram_2fa_password,
                files_directory=self.settings.session_dir_path,
                tdlib_verbosity=TDLibLogVerbosity.FATAL,
            )
            self._client = Client(settings=client_settings)

            try:
                timeout_seconds = max(8, self.settings.telegram_request_timeout_seconds)
                await asyncio.wait_for(self._client.start(), timeout=timeout_seconds)
            except asyncio.TimeoutError as exc:
                await self._safe_stop()
                raise TDLibAuthRequiredError(
                    "Timed out while opening TDLib session. Run session bootstrap again."
                ) from exc
            except Exception as exc:  # pragma: no cover - network/runtime dependent
                await self._safe_stop()
                raise TDLibRequestError(f"Failed to start TDLib client: {exc}") from exc

            self._started = True

    async def close(self) -> None:
        await self._safe_stop()

    async def _safe_stop(self) -> None:
        if self._client is None:
            self._started = False
            return

        try:
            await self._client.stop()
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            self._client = None
            self._started = False

    async def search_public_chats(self, query: str, limit: int) -> List[Dict[str, Any]]:
        await self.ensure_started()
        response = await self._call_with_retry(
            self._client.api.search_public_chats,
            operation="search_public_chats",
            query=query,
        )
        chat_ids = list(getattr(response, "chat_ids", []) or [])
        results: List[Dict[str, Any]] = []

        for chat_id in chat_ids:
            channel = await self._build_channel_payload(chat_id)
            if channel is None:
                continue
            results.append(channel)
            if len(results) >= limit:
                break

        return results

    async def search_public_chat(self, username: str) -> Optional[Dict[str, Any]]:
        await self.ensure_started()
        handle = username.strip().lstrip("@")
        if not handle:
            return None

        chat = await self._call_with_retry(
            self._client.api.search_public_chat,
            operation="search_public_chat",
            username=handle,
        )
        chat_id = int(getattr(chat, "id"))
        return await self._build_channel_payload(chat_id)

    async def get_channel(self, chat_id: int) -> Optional[Dict[str, Any]]:
        await self.ensure_started()
        return await self._build_channel_payload(chat_id)

    async def get_chat_history(self, chat_id: int, limit: int) -> Dict[str, Any]:
        await self.ensure_started()
        channel = await self._build_channel_payload(chat_id)
        if channel is None:
            raise TDLibRequestError(f"chat_id {chat_id} is not a public channel")

        message_limit = max(1, min(100, limit))
        response = await self._call_with_retry(
            self._client.api.get_chat_history,
            operation="get_chat_history",
            chat_id=chat_id,
            from_message_id=0,
            offset=0,
            limit=message_limit,
            only_local=False,
        )

        messages = []
        for message in list(getattr(response, "messages", []) or []):
            if message is None:
                continue
            text = _extract_message_text(message)
            posted_at = _timestamp_to_iso(getattr(message, "date", 0))
            url = None
            if channel.get("username"):
                url = f"https://t.me/{channel['username']}/{int(getattr(message, 'id'))}"

            messages.append(
                {
                    "chat_id": chat_id,
                    "message_id": int(getattr(message, "id")),
                    "posted_at": posted_at,
                    "text": text,
                    "url": url,
                }
            )

        return {"channel": channel, "messages": messages}

    async def get_chat_similar_chats(self, chat_id: int) -> List[Dict[str, Any]]:
        await self.ensure_started()
        response = await self._call_with_retry(
            self._client.api.get_chat_similar_chats,
            operation="get_chat_similar_chats",
            chat_id=chat_id,
        )
        chat_ids = list(getattr(response, "chat_ids", []) or [])

        channels: List[Dict[str, Any]] = []
        for candidate_chat_id in chat_ids:
            channel = await self._build_channel_payload(int(candidate_chat_id))
            if channel is not None:
                channels.append(channel)

        return channels

    async def add_update_handler(
        self,
        handler: Callable[[Any, Any], Any],
        *,
        update_type: str = "*",
        filters: Any = None,
    ) -> Any:
        await self.ensure_started()
        return self._client.add_event_handler(handler, update_type, filters=filters)

    async def remove_update_handler(self, handler: Any, *, update_type: str = "*") -> None:
        if self._client is None:
            return
        self._client.remove_event_handler(handler, update_type)

    async def idle(self) -> None:
        await self.ensure_started()
        await self._client.idle()

    async def _build_channel_payload(self, chat_id: int) -> Optional[Dict[str, Any]]:
        chat = await self._call_with_retry(
            self._client.api.get_chat,
            operation="get_chat",
            chat_id=chat_id,
        )
        chat_type = getattr(chat, "type_", None)
        if chat_type is None or getattr(chat_type, "ID", "") != "chatTypeSupergroup":
            return None

        supergroup = await self._call_with_retry(
            self._client.api.get_supergroup,
            operation="get_supergroup",
            supergroup_id=int(getattr(chat_type, "supergroup_id")),
        )

        if not bool(getattr(supergroup, "is_channel", False)):
            return None

        usernames = getattr(supergroup, "usernames", None)
        active_usernames = list(getattr(usernames, "active_usernames", []) or [])
        username = active_usernames[0] if active_usernames else None

        description = None
        member_count = _clean_member_count(getattr(supergroup, "member_count", None))

        try:
            full_info = await self._call_with_retry(
                self._client.api.get_supergroup_full_info,
                operation="get_supergroup_full_info",
                supergroup_id=int(getattr(supergroup, "id")),
            )
        except TDLibRequestError:
            full_info = None

        if full_info is not None:
            description = (getattr(full_info, "description", "") or "").strip() or None
            if member_count is None:
                member_count = _clean_member_count(getattr(full_info, "member_count", None))

        return {
            "chat_id": int(getattr(chat, "id")),
            "title": (getattr(chat, "title", "") or "").strip() or str(chat_id),
            "username": username,
            "public_link": f"https://t.me/{username}" if username else None,
            "description": description,
            "member_count": member_count,
            "is_verified": bool(getattr(supergroup, "is_verified", False)),
            "is_scam": bool(getattr(supergroup, "is_scam", False)),
            "is_fake": bool(getattr(supergroup, "is_fake", False)),
        }

    async def _call_with_retry(self, method: Any, *, operation: str, **kwargs: Any) -> Any:
        self._assert_read_only_operation(operation)
        async with self._api_lock:
            retries = 2
            for attempt in range(retries + 1):
                try:
                    return await method(
                        request_timeout=self.settings.telegram_request_timeout_seconds,
                        **kwargs,
                    )
                except (asyncio.TimeoutError, TimeoutError) as exc:
                    if attempt >= retries:
                        raise TDLibRequestError(f"{operation} timed out") from exc
                    await asyncio.sleep(0.4 * (attempt + 1))
                except AioTDLibError as exc:
                    code = getattr(exc, "code", None)
                    message = getattr(exc, "message", str(exc))
                    if code in {401, 403}:
                        raise TDLibAuthRequiredError(
                            f"TDLib authorization is invalid: {message}"
                        ) from exc
                    if code in {420, 429} and attempt < retries:
                        await asyncio.sleep(0.7 * (attempt + 1))
                        continue
                    raise TDLibRequestError(f"{operation} failed: {message}") from exc
                except TDLibAuthRequiredError:
                    raise
                except Exception as exc:
                    raise TDLibRequestError(f"{operation} failed: {exc}") from exc

    def _assert_read_only_operation(self, operation: str) -> None:
        if not self.settings.telegram_read_only_mode:
            return
        if operation in _READ_ONLY_ALLOWED_OPERATIONS:
            return
        raise TDLibRequestError(
            f"Operation '{operation}' is blocked by TELEGRAM_READ_ONLY_MODE=true"
        )



def _extract_message_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if content is None:
        return ""

    content_type = getattr(content, "ID", "")
    if content_type == "messageText":
        formatted = getattr(content, "text", None)
        return (getattr(formatted, "text", "") or "").strip()

    caption = getattr(content, "caption", None)
    if caption is not None:
        return (getattr(caption, "text", "") or "").strip()

    formatted = getattr(content, "text", None)
    if formatted is not None:
        return (getattr(formatted, "text", "") or "").strip()

    if content_type:
        return f"[{content_type}]"
    return ""



def _clean_member_count(value: Any) -> Optional[int]:
    if value in (None, 0):
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    return count if count > 0 else None



def _timestamp_to_iso(timestamp: int) -> Optional[str]:
    if not timestamp:
        return None
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).replace(microsecond=0).isoformat()


def extract_td_message_text(message: Any) -> str:
    return _extract_message_text(message)


def td_timestamp_to_iso(timestamp: int) -> Optional[str]:
    return _timestamp_to_iso(timestamp)


def td_message_content_type(message: Any) -> str:
    content = getattr(message, "content", None)
    if content is None:
        return ""
    return str(getattr(content, "ID", "") or "")
