"""Common content cleanup helpers for Open WebUI message history."""

from __future__ import annotations

import re
from collections.abc import Iterable

DETAILS_BLOCK_RE = re.compile(r"<details\b[^>]*>.*?</details>", re.DOTALL)
EMPTY_CONTEXT_RE = re.compile(r"<context>\s*</context>", flags=re.DOTALL)
SOURCE_TAGS_RE = re.compile(r"<source[^>]*>.*?</source>", flags=re.DOTALL)
RAG_MESSAGE_RE = re.compile(r"### Task:.*?<context>.*?</context>", re.DOTALL)
USER_CONTEXT_RE = re.compile(r"\nUser Context:\n(.*)$", flags=re.DOTALL)


def strip_details_blocks(text: str | None) -> str:
    return DETAILS_BLOCK_RE.sub("", text or "")


def render_system_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict) and "text" in content:
        return str(content.get("text", ""))
    if isinstance(content, Iterable) and not isinstance(content, (str, bytes, dict)):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "\n".join(part for part in parts if part)
    return str(content or "")


__all__ = [
    "DETAILS_BLOCK_RE",
    "EMPTY_CONTEXT_RE",
    "RAG_MESSAGE_RE",
    "SOURCE_TAGS_RE",
    "USER_CONTEXT_RE",
    "render_system_content",
    "strip_details_blocks",
]

