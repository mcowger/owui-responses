"""Async-safe Open WebUI chat item persistence."""

from __future__ import annotations

import inspect
import time
from typing import Any

from owui_manifolds.shared.ids import generate_ulid
from owui_manifolds.shared.optional_openwebui import import_chats


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class OpenWebUIItemStore:
    def __init__(
        self,
        *,
        root_key: str,
        version: int = 1,
        chats_model: Any | None = None,
    ):
        self.root_key = root_key
        self.version = version
        self._Chats = chats_model if chats_model is not None else import_chats()

    async def save_item(
        self,
        chat_id: str | None,
        payload: dict[str, Any],
        *,
        model_id: str | None = None,
        message_id: str | None = None,
        ulid: str | None = None,
    ) -> str | None:
        if not self._Chats or not chat_id:
            return None
        chat = await maybe_await(self._Chats.get_chat_by_id(chat_id))
        if not chat:
            return None
        item_id = ulid or generate_ulid()
        root = chat.chat.setdefault(self.root_key, {"__v": self.version})
        items = root.setdefault("items", {})
        stored: dict[str, Any] = {
            "created_at": int(time.time()),
            "payload": payload,
        }
        if model_id is not None:
            stored["model"] = model_id
        if message_id is not None:
            stored["message_id"] = message_id
            bucket = root.setdefault("messages_index", {}).setdefault(
                message_id,
                {"role": "assistant", "done": True, "item_ids": []},
            )
            bucket.setdefault("item_ids", []).append(item_id)
        items[item_id] = stored
        await maybe_await(self._Chats.update_chat_by_id(chat_id, chat.chat))
        return item_id

    async def save_items(
        self,
        chat_id: str | None,
        payloads: list[dict[str, Any]],
        *,
        model_id: str | None = None,
        message_id: str | None = None,
    ) -> list[str]:
        created: list[str] = []
        for payload in payloads:
            item_id = await self.save_item(
                chat_id,
                payload,
                model_id=model_id,
                message_id=message_id,
            )
            if item_id:
                created.append(item_id)
        return created

    async def load_item(
        self,
        chat_id: str | None,
        ulid: str,
        *,
        model_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not self._Chats or not chat_id or not ulid:
            return None
        chat = await maybe_await(self._Chats.get_chat_by_id(chat_id))
        if not chat:
            return None
        item = chat.chat.get(self.root_key, {}).get("items", {}).get(ulid)
        if not isinstance(item, dict):
            return None
        if model_id is not None and item.get("model") != model_id:
            return None
        payload = item.get("payload")
        return payload if isinstance(payload, dict) else None

    async def load_items(
        self,
        chat_id: str | None,
        item_ids: list[str],
        *,
        model_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        loaded: dict[str, dict[str, Any]] = {}
        for item_id in item_ids:
            payload = await self.load_item(chat_id, item_id, model_id=model_id)
            if payload is not None:
                loaded[item_id] = payload
        return loaded


__all__ = ["OpenWebUIItemStore", "maybe_await"]
