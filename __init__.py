"""Hermes plugin entrypoint for memory runtime assets and dashboard hooks.

Agent-facing tools expose only the Active Memory actions that are meaningful in
conversation. Configuration and injection resolution remain dashboard/runtime
internals in ``control.py``; they are not a generic agent control router.

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


def _read_selected_note_handler(args: dict[str, Any], **_: Any) -> str:
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
        name="memory_read_selected_note",
        toolset="memory",
        schema={
            "name": "memory_read_selected_note",
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
        handler=_read_selected_note_handler,
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
