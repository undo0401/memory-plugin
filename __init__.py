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
from pathlib import Path
from typing import Any

PLUGIN_DIR = Path(__file__).resolve().parent
SKILL_PATH = PLUGIN_DIR / "skills" / "memory-operations" / "SKILL.md"

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


def _compact_control_schema(schema: dict[str, Any]) -> dict[str, Any]:
    parameters = dict(schema.get("parameters") or {})
    parameters["properties"] = {
        key: {field: value for field, value in spec.items() if field != "description"}
        for key, spec in (parameters.get("properties") or {}).items()
    }
    return {**schema, "parameters": parameters}


def register(ctx) -> None:
    """Register the memory registry tool surface."""
    if SKILL_PATH.exists() and hasattr(ctx, "register_skill"):
        ctx.register_skill(
            "memory-operations",
            SKILL_PATH,
            "Operate Hermes memory runtime configuration and diagnostic resolution.",
        )
    ctx.register_tool(
        name="memory_control",
        toolset="memory",
        schema=_compact_control_schema({
            "name": "memory_control",
            "description": 'Before operating, load skill_view("memory:memory-operations").',
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
        }),
        handler=_control_handler,
        description='Before operating, load skill_view("memory:memory-operations").',
        emoji="🫧",
    )
