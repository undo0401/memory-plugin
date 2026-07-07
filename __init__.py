"""Hermes plugin entrypoint for memory runtime assets and dashboard hooks.

Configuration and resolve operations are exposed through the Hermes tool
registry as `memory_control`. Dashboard HTTP endpoints route through that tool;
operational implementation lives in `control.py` behind the registry surface.

Diary/daily-memory authoring and snapshot production are intentionally outside
this plugin.  Memory consumes configured snapshots; it does not register diary
skills or run diary producers.
"""

from __future__ import annotations

import json
from typing import Any


def _control_handler(args: dict[str, Any], **_: Any) -> str:
    from hermes_plugins.memory import control

    action = str((args or {}).get("action") or "get_config").strip()
    try:
        if action == "get_config":
            result = control.get_config()
        elif action == "put_config":
            result = control.put_config((args or {}).get("config"))
        elif action == "resolve":
            result = control.resolve((args or {}).get("payload"))
        elif action == "health":
            result = control.health()
        else:
            result = {"error": f"unknown memory_control action: {action}"}
    except Exception as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"}
    return json.dumps(result, ensure_ascii=False)


def _memory_search_handler(args: dict[str, Any], **_: Any) -> str:
    from hermes_plugins.memory import control

    try:
        result = control.memory_search(args or {})
    except Exception as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"}
    return json.dumps(result, ensure_ascii=False)


def _memory_get_handler(args: dict[str, Any], **_: Any) -> str:
    from hermes_plugins.memory import control

    try:
        result = control.memory_get(args or {})
    except Exception as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"}
    return json.dumps(result, ensure_ascii=False)


def register(ctx) -> None:
    """Register the memory registry tool surface."""
    ctx.register_tool(
        name="memory_control",
        toolset="memory",
        schema={
            "name": "memory_control",
            "description": "Internal control surface for the memory plugin. Reads/saves memory lane config and resolves memory injection policy via the tool registry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get_config", "put_config", "resolve", "health"],
                        "description": "Operation to perform.",
                    },
                    "config": {
                        "anyOf": [{"type": "object"}, {"type": "string"}, {"type": "null"}],
                        "description": "Full memory config payload for put_config.",
                    },
                    "payload": {
                        "anyOf": [{"type": "object"}, {"type": "string"}, {"type": "null"}],
                        "description": "Resolve payload for action=resolve.",
                    },
                },
                "additionalProperties": False,
            },
        },
        handler=_control_handler,
        description="Memory plugin control surface.",
        emoji="🫧",
    )

    ctx.register_tool(
        name="memory_search",
        toolset="memory",
        schema={
            "name": "memory_search",
            "description": "Search configured daily memory Markdown files before answering questions about prior work, decisions, dates, people, preferences, todos, or diary context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "maxResults": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Maximum result rows."},
                    "minScore": {"type": "number", "description": "Accepted for OpenClaw compatibility; currently informational."},
                    "corpus": {"type": "string", "enum": ["memory", "wiki", "all", "sessions"], "description": "Corpus selector. This plugin currently searches daily memory for memory/all."},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        handler=_memory_search_handler,
        description="Search daily memory.",
        emoji="🫧",
    )

    ctx.register_tool(
        name="memory_get",
        toolset="memory",
        schema={
            "name": "memory_get",
            "description": "Read a small excerpt from a memory_search result path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path or relative_path returned by memory_search."},
                    "from": {"type": "integer", "minimum": 1, "description": "1-based start line."},
                    "lines": {"type": "integer", "minimum": 1, "maximum": 500, "description": "Number of lines to read."},
                    "corpus": {"type": "string", "enum": ["memory", "wiki", "all"], "description": "Accepted for OpenClaw compatibility."},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
        handler=_memory_get_handler,
        description="Read memory excerpt.",
        emoji="🫧",
    )

    ctx.register_tool(
        name="memory_health",
        toolset="memory",
        schema={
            "name": "memory_health",
            "description": "Return Memory plugin-owned health status for System Desk.",
            "parameters": {"type": "object", "properties": {}},
        },
        handler=lambda args, **kwargs: _control_handler({"action": "health"}, **kwargs),
        description="Memory health surface.",
        emoji="🫧",
    )
