"""Internal memory control implementation behind the registry tool surface."""

from __future__ import annotations

from typing import Any

from .dashboard import plugin_api as api


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
