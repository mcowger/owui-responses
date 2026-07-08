"""Visible Open WebUI rendering helpers."""

from __future__ import annotations

import html
import json
import re
from typing import Any

TOOL_CALLS_DETAILS_RE = re.compile(
    r'\n?<details type="tool_calls"[^>]*>.*?</details>\n?',
    flags=re.DOTALL,
)
TOOL_CALLS_BLOCK_RE = re.compile(
    r'\n?<details type="tool_calls"([^>]*)>.*?</details>\n?',
    flags=re.DOTALL,
)
TOOL_CALLS_ATTRS_RE = re.compile(r'(\w+)="([^"]*)"')
REASONING_BLOCK_RE = re.compile(
    r'\n?<details type="reasoning"[^>]*>.*?</details>\n?',
    flags=re.DOTALL,
)


def format_reasoning_details(content: str, *, summary: str = "Thought") -> str:
    escaped = "\n".join(
        f"> {html.escape(line)}" if not line.startswith(">") else html.escape(line)
        for line in (content or "").splitlines()
    )
    return (
        '<details type="reasoning" done="true">\n'
        f"<summary>{html.escape(summary)}</summary>\n"
        f"{escaped}\n"
        "</details>\n"
    )


def format_tool_call_details(
    *,
    tool_id: str,
    name: str,
    args: dict[str, Any] | None,
    output: Any,
    is_error: bool = False,
    max_chars: int = 4000,
    ref: str = "",
) -> str:
    raw_result = output if isinstance(output, str) else str(output)
    truncated = len(raw_result) > max_chars
    preview = raw_result[:max_chars] if truncated else raw_result
    if truncated:
        preview += f"\n... (truncated, {len(raw_result) - max_chars} more chars)"
    escaped_args = html.escape(json.dumps(args or {}, ensure_ascii=False)) if args else ""
    escaped_result = html.escape(preview)
    error_attr = ' error="true"' if is_error else ""
    ref_attr = f' ref="{html.escape(ref)}"' if ref else ""
    return (
        f'<details type="tool_calls" done="true" id="{html.escape(tool_id)}" '
        f'name="{html.escape(name)}" arguments="{escaped_args}" '
        f'result="{escaped_result}" files="" embeds=""{error_attr}{ref_attr}>\n'
        "<summary>Tool Executed</summary>\n"
        "</details>\n"
    )


def parse_tool_call_attrs(raw_attrs: str) -> dict[str, str]:
    return {key: html.unescape(value) for key, value in TOOL_CALLS_ATTRS_RE.findall(raw_attrs or "")}


__all__ = [
    "REASONING_BLOCK_RE",
    "TOOL_CALLS_ATTRS_RE",
    "TOOL_CALLS_BLOCK_RE",
    "TOOL_CALLS_DETAILS_RE",
    "format_reasoning_details",
    "format_tool_call_details",
    "parse_tool_call_attrs",
]

