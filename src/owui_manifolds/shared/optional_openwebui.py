"""Import-guarded Open WebUI integrations."""

from __future__ import annotations

from typing import Any


def import_chats() -> Any | None:
    try:
        from open_webui.models.chats import Chats

        return Chats
    except Exception:
        return None


def import_process_tool_result() -> Any | None:
    try:
        from open_webui.utils.middleware import process_tool_result

        return process_tool_result
    except Exception:
        return None


__all__ = ["import_chats", "import_process_tool_result"]

