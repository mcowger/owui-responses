"""
Regression tests for Open WebUI 'direct' tool-server dispatch
(anthropic_function.py Pipe._execute_tool / _execute_direct_tool /
_client_tool_names).

Background: Open Terminal (and other OWUI tool-server integrations) register
tools like run_command/list_files/glob_search with no local 'callable' —
instead each entry carries {'direct': True, 'server': {...}}. Open WebUI's own
native middleware (utils/middleware.py: tool_call_handler) executes these via
a WebSocket round-trip: __event_call__({'type': 'execute:tool', 'data': {...}}).

The 2026-07-02 SDK-lean rewrite of anthropic_function.py dropped this
dispatch path entirely: pipe() never declared/accepted __event_call__, and
_client_tool_names() only recognized entries with a truthy 'callable' — so a
direct tool's tool_use block was mistaken for a server-side tool
(web_search/web_fetch) and silently dropped instead of executed, even though
the tool was still correctly advertised in the outgoing Anthropic tools
payload (_build_tools does not filter on callable/direct).

Run:
    uv run --with anthropic --with pydantic --with pytest \\
        pytest tests/test_direct_tool_dispatch.py -v
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))
MODULE_PATH = SRC_ROOT / "owui_manifolds/providers/anthropic/pipe.py"

_spec = importlib.util.spec_from_file_location("anthropic_function", MODULE_PATH)
anthropic_function = importlib.util.module_from_spec(_spec)
sys.modules["anthropic_function"] = anthropic_function
_spec.loader.exec_module(anthropic_function)

Pipe = anthropic_function.Pipe


def _make_pipe() -> Pipe:
    return Pipe()


# A direct tool-server entry shaped exactly like Open Terminal's registration
# in __tools__ (no 'callable' key at all — see middleware.py
# direct_tool_servers handling: {'spec': tool, 'direct': True, 'server': tool_server}).
DIRECT_TOOL_ENTRY = {
    "spec": {
        "name": "list_files",
        "description": "Return a structured listing of files and directories.",
        "parameters": {
            "type": "object",
            "properties": {"directory": {"type": "string"}},
            "required": [],
        },
    },
    "direct": True,
    "server": {"url": "http://192.168.0.2:8889", "openapi": {"openapi": "3.1.0"}},
}


def test_client_tool_names_includes_direct_entries():
    """Direct tool-server entries must be recognized as client tools, or
    their tool_use blocks get mistaken for server-side tools (web_search/
    web_fetch) and silently dropped in _tool_calls_from_message."""
    pipe = _make_pipe()
    names = pipe._client_tool_names({"list_files": DIRECT_TOOL_ENTRY})
    assert names == {"list_files"}


def test_direct_tool_dispatches_via_event_call():
    """A 'direct' tool entry with no callable is executed via __event_call__,
    not misrouted into the 'Tool not found' fallback."""
    pipe = _make_pipe()
    captured_events: list[dict] = []

    async def fake_event_call(event: dict) -> dict:
        captured_events.append(event)
        return {"entries": ["a.txt", "b.txt"]}

    call = {"id": "toolu_1", "name": "list_files", "input": {"directory": "/"}}

    async def run():
        return await pipe._execute_tool(
            call,
            {"list_files": DIRECT_TOOL_ENTRY},
            request=None,
            metadata={"session_id": "sess-123"},
            user={},
            event_call=fake_event_call,
        )

    block, output, files, embeds, is_error = asyncio.run(run())

    assert len(captured_events) == 1
    event = captured_events[0]
    assert event["type"] == "execute:tool"
    assert event["data"]["name"] == "list_files"
    assert event["data"]["params"] == {"directory": "/"}
    assert event["data"]["server"] == DIRECT_TOOL_ENTRY["server"]
    assert event["data"]["session_id"] == "sess-123"

    assert is_error is False
    assert "entries" in output
    assert "not found" not in output.lower()
    assert block["tool_use_id"] == "toolu_1"
    assert block.get("is_error") is not True


def test_direct_tool_without_event_call_reports_clear_error():
    """When __event_call__ isn't available (e.g. API-key callers without a
    live browser session), the direct tool fails with an explicit, honest
    error instead of silently doing nothing or leaking raw JSON."""
    pipe = _make_pipe()
    call = {"id": "toolu_2", "name": "list_files", "input": {"directory": "/"}}

    async def run():
        return await pipe._execute_tool(
            call,
            {"list_files": DIRECT_TOOL_ENTRY},
            request=None,
            metadata={},
            user={},
            event_call=None,
        )

    block, output, files, embeds, is_error = asyncio.run(run())
    assert is_error is True
    assert "requires __event_call__" in output
    assert block["is_error"] is True


def test_non_direct_tool_still_uses_callable_path():
    """Sanity check: a normal callable user tool (no 'direct' flag) is
    unaffected by the new direct-dispatch branch."""
    pipe = _make_pipe()

    async def fake_callable(**kwargs):
        return {"ok": True, "kwargs": kwargs}

    tools = {
        "search_memories": {
            "callable": fake_callable,
            "spec": {"name": "search_memories"},
        }
    }
    call = {"id": "toolu_3", "name": "search_memories", "input": {"query": "x"}}

    async def run():
        return await pipe._execute_tool(
            call, tools, request=None, metadata={}, user={}, event_call=None
        )

    block, output, files, embeds, is_error = asyncio.run(run())
    assert is_error is False
    assert "ok" in output


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
