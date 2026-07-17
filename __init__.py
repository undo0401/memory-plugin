"""Hermes plugin entrypoint for memory runtime assets and dashboard hooks.

Agent-facing tools expose selected Active Memory reads and an explicit Memory
control surface. ``memory_control`` is for configuration inspection, edits, and
injection diagnostics; selected note reads stay separate so their path gate is
clear.

Diary/daily-memory authoring and snapshot production are intentionally outside
this plugin. Memory consumes configured snapshots; it does not register diary
skills or run diary producers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PLUGIN_DIR = Path(__file__).resolve().parent
SKILL_PATH = PLUGIN_DIR / "skills" / "registry" / "SKILL.md"


def _control_handler(args: dict[str, Any], **_: Any) -> str:
    """Inspect or edit Memory config, or inspect an injection decision."""
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


def _read_active_memory_handler(args: dict[str, Any], **_: Any) -> str:
    """Read one note that Active Memory selected for the current retrieval."""
    from hermes_plugins.memory import control

    try:
        result = control.read_active_memory_result((args or {}).get("path"))
    except Exception as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"}
    return json.dumps(result, ensure_ascii=False)


def _status_handler(_args: dict[str, Any], **_: Any) -> str:
    """Return compact plugin-owned health for an explicit status check."""
    from hermes_plugins.memory import control

    try:
        result = control.health()
    except Exception as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"}
    return json.dumps(result, ensure_ascii=False)


def register(ctx) -> None:
    """Register the memory registry tool surface."""
    ctx.register_skill(
        "registry",
        SKILL_PATH,
        "Memory plugin technical registry: tool, snapshot, and runtime boundaries.",
    )
    ctx.register_tool(
        name="memory_control",
        toolset="memory",
        schema={
            "name": "memory_control",
            "description": "Inspect or edit Memory configuration and inspect an injection decision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get_config", "put_config", "resolve", "health"],
                        "description": "get_config confirms configuration; put_config replaces it; resolve previews a session injection; health checks runtime state.",
                    },
                    "config": {
                        "anyOf": [{"type": "object"}, {"type": "string"}, {"type": "null"}],
                        "description": "Full Memory configuration payload for action=put_config.",
                    },
                    "payload": {
                        "anyOf": [{"type": "object"}, {"type": "string"}, {"type": "null"}],
                        "description": "Session/source payload for action=resolve.",
                    },
                },
                "additionalProperties": False,
            },
        },
        handler=_control_handler,
        description="Inspect or edit Memory configuration.",
        emoji="🫧",
    )
    ctx.register_tool(
        name="read_active_memory",
        toolset="memory",
        schema={
            "name": "read_active_memory",
            "description": "Read a note selected by the latest Active Memory retrieval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path returned by the latest active-memory selection.",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
        handler=_read_active_memory_handler,
        description="Read a note selected by Active Memory.",
        emoji="🫧",
    )
    ctx.register_tool(
        name="memory_status",
        toolset="memory",
        schema={
            "name": "memory_status",
            "description": "Check Active Memory health and lane status.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        handler=_status_handler,
        description="Check Active Memory health and lane status.",
        emoji="🫧",
    )
