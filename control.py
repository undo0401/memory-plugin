"""Internal memory control implementation behind the registry tool surface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .dashboard import plugin_api as api


_ACTIVE_MEMORY_RESULT_MAX_CHARS = 12_000


def read_active_memory_result(path: str | None = None) -> dict[str, Any]:
    """Read a bounded note only when the latest active-memory retrieval selected it."""
    requested = api._safe_text(path)
    if not requested:
        return {"error": "path_required"}

    notes_root = api._active_memory_root("workspace/notes")
    candidate = Path(requested).expanduser()
    if notes_root is None or not candidate.is_absolute():
        return {"error": "path_outside_notes_root"}
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(notes_root)
    except (OSError, ValueError):
        return {"error": "path_outside_notes_root"}

    state = api.load_state()
    retrieval = state.get("last_active_memory_retrieval") or {}
    selected = retrieval.get("selected") if isinstance(retrieval, dict) else []
    if not isinstance(selected, list):
        selected = []
    allowed_paths = {
        str(Path(item.get("path") or "").resolve(strict=False))
        for item in selected
        if isinstance(item, dict) and api._safe_text(item.get("path"))
    }
    if str(resolved) not in allowed_paths:
        return {"error": "path_not_selected"}
    if not resolved.is_file():
        return {"error": "selected_path_missing"}
    try:
        content = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {"error": f"read_failed: {type(exc).__name__}"}
    return {
        "path": str(resolved),
        "content": content[:_ACTIVE_MEMORY_RESULT_MAX_CHARS],
        "chars": min(len(content), _ACTIVE_MEMORY_RESULT_MAX_CHARS),
        "truncated": len(content) > _ACTIVE_MEMORY_RESULT_MAX_CHARS,
    }


def get_config() -> dict[str, Any]:
    config = api.load_config()
    state = api.load_state()
    state["last_loaded_at"] = api.now_iso()
    api.save_state(state)
    lane_previews = {
        str(lane.get("name") or ""): api._load_lane_preview(lane)
        for lane in list(config.get("lanes") or [])
        if isinstance(lane, dict)
    }
    lane_runtime = api._memory_lane_runtime_summary(state)
    return {
        "plugin": api.PLUGIN_NAME,
        "kind": api.PLUGIN_KIND,
        "config_file": str(api.config_path()),
        "state_file": str(api.state_path()),
        "active_profile": api._active_profile_name(),
        "available_profiles": api._available_profiles(),
        "config": config,
        "runtime": state,
        "lane_runtime": lane_runtime,
        "lane_previews": lane_previews,
        "summary": api._memory_observability_summary(config, state, lane_runtime),
    }


def put_config(payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
    normalized = api._normalize_config(payload)
    api._write_json(api.config_path(), normalized)
    state = api.load_state()
    state["last_saved_at"] = api.now_iso()
    api.save_state(state)
    woken_watchers = api._wake_runtime_watchers(reason="dashboard-config-save")
    response = get_config()
    response["watcher"] = {
        "reason": "dashboard-config-save",
        "woken_watchers": woken_watchers,
    }
    return response


def resolve(payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
    request = api._coerce_json_dict(payload, context="resolve payload")
    source = request.get("source") or {}
    if not isinstance(source, dict):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="source must be an object")
    session_key = api._safe_text(request.get("session_key") or "")
    config = api.load_config()
    policy = api.resolve_memory_injection_policy(
        config,
        session_key,
        source,
        is_new_session=bool(request.get("is_new_session", False)),
        session_id=api._safe_text(request.get("session_id") or ""),
    )
    result = dict(policy.get("result") or {})
    mark_injected = bool(request.get("mark_injected", False)) and bool(policy.get("should_inject"))
    state = api.update_memory_resolution_state(policy, injected=mark_injected)
    return {
        "plugin": api.PLUGIN_NAME,
        "kind": api.PLUGIN_KIND,
        "config": config,
        "result": result,
        "decision": {
            "should_inject": bool(policy.get("should_inject")),
            "decision_reason": policy.get("decision_reason"),
            "reinject_interval_minutes": int(policy.get("reinject_interval_minutes") or 0),
            "matched_reinject_intervals": list(policy.get("matched_reinject_intervals") or []),
            "last_injected_at": policy.get("last_injected_at"),
            "elapsed_minutes": policy.get("elapsed_minutes"),
            "is_new_session": bool(policy.get("is_new_session")),
            "session_key": policy.get("session_key"),
            "session_id": policy.get("session_id"),
        },
        "runtime": state,
    }



def health() -> dict[str, Any]:
    """Return plugin-owned memory health for System Desk."""
    config = api.load_config()
    state = api.load_state()
    lane_runtime = api._memory_lane_runtime_summary(state)
    summary_counts = api._memory_observability_summary(config, state, lane_runtime)
    enabled = int(summary_counts.get("enabled_lanes") or 0)
    disabled = int(summary_counts.get("disabled_lanes") or 0)
    tracked = int(summary_counts.get("tracked_lanes") or 0)
    sessions = int(summary_counts.get("sessions") or 0)
    last_tick_at = state.get("last_tick_at")
    status = "ok" if last_tick_at else "unknown"
    summary = f"enabled {enabled} / disabled {disabled} / tracked {tracked} / sessions {sessions}"
    if not last_tick_at:
        summary += " / last tick missing"
    return {
        "plugin": api.PLUGIN_NAME,
        "status": status,
        "summary": summary,
        "generated_at": api.now_iso(),
        "details": {
            "config_file": str(api.config_path()),
            "state_file": str(api.state_path()),
            "summary": summary_counts,
            "lane_runtime": lane_runtime,
            "last_tick_at": last_tick_at,
        },
    }
