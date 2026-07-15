"""Shared status-emission helper for context-compaction progress updates."""

from __future__ import annotations

import asyncio
from typing import Any, Optional


async def emit_status(event_emitter: Any, description: str, done: bool = False) -> None:
    if not event_emitter:
        return
    try:
        await event_emitter(
            {"type": "status", "data": {"description": description, "done": done}}
        )
    except Exception:
        pass


async def emit_status_durable(
    event_emitter: Any,
    chat_id: Optional[str],
    message_id: Optional[str],
    description: str,
    done: bool = False,
    attempts: int = 5,
    retry_delay: float = 0.05,
) -> None:
    """Emit a status and verify it actually landed in the persisted chat.

    Open WebUI's status persistence (Chats.add_message_status_to_chat_by_id_and_message_id)
    is an unlocked read-modify-write: concurrent status writers (e.g. the pipe's own
    scheduled 'Thinking...' updates) can race and silently clobber each other's entry.
    We can't fix that upstream race from here, but we can self-heal our own write by
    re-checking it landed and resending if it was lost.
    """
    if not event_emitter:
        return

    try:
        from open_webui.models.chats import Chats
    except Exception:
        Chats = None

    for attempt in range(attempts):
        try:
            await event_emitter(
                {"type": "status", "data": {"description": description, "done": done}}
            )
        except Exception:
            return

        if not Chats or not chat_id or not message_id:
            return

        try:
            chat = await Chats.get_chat_by_id(chat_id)
            history = (chat.chat or {}).get("history", {}) if chat else {}
            status_list = (
                history.get("messages", {}).get(message_id, {}).get("statusHistory", [])
            )
            if any(
                s.get("description") == description and s.get("done") == done
                for s in status_list
            ):
                return
        except Exception:
            return

        await asyncio.sleep(retry_delay * (attempt + 1))
