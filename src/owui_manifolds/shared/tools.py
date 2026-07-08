"""Shared Open WebUI tool registry and execution helpers."""

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal


@dataclass
class SharedToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class SharedToolResult:
    call_id: str
    name: str
    arguments: dict[str, Any]
    output_text: str
    response_payload: Any
    status: Literal["ok", "error", "timeout"]
    error_message: str | None = None
    files: list[Any] = field(default_factory=list)
    embeds: list[Any] = field(default_factory=list)


@dataclass
class SharedToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


def normalize_parameters(schema: object) -> dict[str, Any]:
    return schema if isinstance(schema, dict) else {"type": "object", "properties": {}}


def iter_tool_definitions(registry: dict[str, Any] | None) -> list[SharedToolDefinition]:
    definitions: list[SharedToolDefinition] = []
    for entry in (registry or {}).values():
        if not isinstance(entry, dict):
            continue
        spec = entry.get("spec") if isinstance(entry.get("spec"), dict) else {}
        name = spec.get("name")
        if not isinstance(name, str) or not name:
            continue
        definitions.append(
            SharedToolDefinition(
                name=name,
                description=str(spec.get("description") or ""),
                parameters=normalize_parameters(spec.get("parameters")),
            )
        )
    return definitions


def candidate_tool_names(name: str) -> list[str]:
    candidates = [name]
    for sep in (":", "."):
        if sep in name:
            candidates.append(name.rsplit(sep, 1)[-1])
    seen: set[str] = set()
    return [candidate for candidate in candidates if candidate and not (candidate in seen or seen.add(candidate))]


async def dispatch_direct_tool(
    *,
    name: str,
    arguments: dict[str, Any],
    entry: dict[str, Any],
    event_call: Any | None,
    metadata: dict[str, Any] | None = None,
    call_id: str = "",
) -> SharedToolResult:
    if not callable(event_call):
        error = (
            f"Tool '{name}' is a direct tool-server tool and requires "
            "__event_call__ (browser round-trip) context, which is not "
            "available for this request."
        )
        return SharedToolResult(
            call_id=call_id,
            name=name,
            arguments=arguments,
            output_text=json.dumps({"error": error}, ensure_ascii=False),
            response_payload={"error": error},
            status="error",
            error_message="__event_call__ not available",
        )

    try:
        value = await event_call(
            {
                "type": "execute:tool",
                "data": {
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "params": arguments,
                    "server": entry.get("server", {}),
                    "session_id": (metadata or {}).get("session_id"),
                },
            }
        )
    except Exception as exc:
        return SharedToolResult(
            call_id=call_id,
            name=name,
            arguments=arguments,
            output_text=f"Direct tool error: {exc}",
            response_payload={"error": str(exc)},
            status="error",
            error_message=str(exc),
        )

    output_text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    payload = value if isinstance(value, dict) else {"result": value}
    return SharedToolResult(
        call_id=call_id,
        name=name,
        arguments=arguments,
        output_text=output_text,
        response_payload=payload,
        status="ok",
    )


class SharedOpenWebUIToolExecutor:
    def __init__(
        self,
        registry: dict[str, Any] | None,
        *,
        parallel: bool = True,
        event_call: Any | None = None,
        metadata: dict[str, Any] | None = None,
        timeout: float | None = None,
        process_tool_result: Any | None = None,
        request: Any | None = None,
        user: dict[str, Any] | None = None,
        namespace_resolution: bool = True,
    ):
        self._parallel = parallel
        self._event_call = event_call
        self._metadata = metadata or {}
        self._timeout = timeout
        self._process_tool_result = process_tool_result
        self._request = request
        self._user = user or {}
        self._namespace_resolution = namespace_resolution
        self._callables: dict[str, Any] = {}
        self._direct_entries: dict[str, dict[str, Any]] = {}
        for entry in (registry or {}).values():
            if not isinstance(entry, dict):
                continue
            spec = entry.get("spec") if isinstance(entry.get("spec"), dict) else {}
            name = spec.get("name")
            if not isinstance(name, str) or not name:
                continue
            fn = entry.get("callable")
            if fn is not None:
                self._callables[name] = fn
            elif entry.get("direct"):
                self._direct_entries[name] = entry

    def names(self) -> set[str]:
        return set(self._callables) | set(self._direct_entries)

    def iter_definitions(self) -> Iterable[SharedToolDefinition]:
        return iter_tool_definitions(
            {
                name: {"spec": {"name": name}}
                for name in sorted(self.names())
            }
        )

    def _names_for_lookup(self, name: str) -> list[str]:
        return candidate_tool_names(name) if self._namespace_resolution else [name]

    def _resolve(self, name: str) -> tuple[str, Any | None, dict[str, Any] | None]:
        for candidate in self._names_for_lookup(name):
            fn = self._callables.get(candidate)
            if fn is not None:
                return candidate, fn, None
            entry = self._direct_entries.get(candidate)
            if entry is not None:
                return candidate, None, entry
        return name, None, None

    async def execute(self, calls: list[SharedToolCall]) -> list[SharedToolResult]:
        if not self._parallel or len(calls) <= 1:
            return [await self._execute_one(call) for call in calls]

        seen: set[str] = set()
        has_duplicates = any((call.name in seen) or (seen.add(call.name) or False) for call in calls)
        if has_duplicates:
            return [await self._execute_one(call) for call in calls]

        return list(await asyncio.gather(*(self._execute_one(call) for call in calls)))

    async def _execute_callable(self, fn: Any, call: SharedToolCall) -> tuple[Any, list[Any], list[Any]]:
        async def invoke() -> Any:
            if inspect.iscoroutinefunction(fn):
                return await fn(**call.arguments)
            return await asyncio.to_thread(fn, **call.arguments)

        value = await asyncio.wait_for(invoke(), timeout=self._timeout) if self._timeout else await invoke()
        files: list[Any] = []
        embeds: list[Any] = []
        if self._process_tool_result and self._request:
            value, files, embeds = await self._process_tool_result(
                self._request,
                call.name,
                value,
                "pipe",
                metadata=self._metadata,
                user=self._user,
            )
        return value, files, embeds

    async def _execute_one(self, call: SharedToolCall) -> SharedToolResult:
        resolved_name, fn, direct_entry = self._resolve(call.name)
        if fn is None:
            if direct_entry is not None:
                return await dispatch_direct_tool(
                    name=resolved_name,
                    arguments=call.arguments,
                    entry=direct_entry,
                    event_call=self._event_call,
                    metadata=self._metadata,
                    call_id=call.call_id,
                )
            return SharedToolResult(
                call_id=call.call_id,
                name=call.name,
                arguments=call.arguments,
                output_text="Tool not found",
                response_payload={"error": "Tool not found"},
                status="error",
                error_message="Tool not found",
            )

        try:
            value, files, embeds = await self._execute_callable(fn, call)
            output_text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
            payload = value if isinstance(value, dict) else {"result": value}
            return SharedToolResult(
                call_id=call.call_id,
                name=call.name,
                arguments=call.arguments,
                output_text=output_text,
                response_payload=payload,
                status="ok",
                files=files,
                embeds=embeds,
            )
        except asyncio.TimeoutError:
            error = f"Tool '{call.name}' timed out"
            return SharedToolResult(
                call_id=call.call_id,
                name=call.name,
                arguments=call.arguments,
                output_text=error,
                response_payload={"error": error},
                status="timeout",
                error_message=error,
            )
        except Exception as exc:
            return SharedToolResult(
                call_id=call.call_id,
                name=call.name,
                arguments=call.arguments,
                output_text=f"Tool error: {exc}",
                response_payload={"error": str(exc)},
                status="error",
                error_message=str(exc),
            )


__all__ = [
    "SharedOpenWebUIToolExecutor",
    "SharedToolCall",
    "SharedToolDefinition",
    "SharedToolResult",
    "candidate_tool_names",
    "dispatch_direct_tool",
    "iter_tool_definitions",
    "normalize_parameters",
]

