"""Hermes plugin entrypoint for memory runtime assets and dashboard hooks.

The canonical bare lane stays local `memory` plus plugin bare `daily-memory`.
We also register the plugin-paired SKILL.md for explicit namespaced loads
without colliding with the local bare `memory` skill.
"""

from __future__ import annotations

from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parent
SKILL_PATH = PLUGIN_DIR / "skills" / "daily-memory" / "SKILL.md"


def register(ctx) -> None:
    """Register the plugin-paired daily-memory skill for namespaced loads."""
    ctx.register_skill(
        "daily-memory",
        SKILL_PATH,
        "Daily-memory companion skill for the memory plugin.",
    )
