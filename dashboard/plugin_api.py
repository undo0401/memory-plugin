from __future__ import annotations

import fnmatch
import importlib
import json
import logging
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

try:
    from hermes_constants import get_hermes_home
except ImportError:
    import os as _os

    def get_hermes_home() -> Path:  # type: ignore[misc]
        val = (_os.environ.get("HERMES_HOME") or "").strip()
        return Path(val) if val else Path.home() / ".hermes"


router = APIRouter()
logger = logging.getLogger(__name__)
PLUGIN_NAME = "memory"
CONFIG_DIRNAME = "config"
STATE_DIRNAME = "state"
CONFIG_FILENAME = "memory.json"
STATE_FILENAME = "memory-runtime.json"
PLUGIN_KIND = "memory"
BUILD_MEMORY_CONTEXT_SCRIPT = Path("/opt/data/scripts/diaries/build-memory-context.py")
JST = ZoneInfo("Asia/Tokyo")
MANAGED_SNAPSHOT_PATHS = {
    "/opt/data/state/MEMORY_EVENT_CONTEXT.md",
    "/opt/data/state/MEMORY_EMOTIONS_CONTEXT.md",
}
DEFAULT_LANE = {
    "name": "memory-1",
    "enabled": True,
    "prompt": "",
    "idle_seconds": 0,
    "max_session_age_seconds": 86400,
    "reinject_interval_minutes": 0,
    "target_sessions": [],
    "target_channels": [],
    "exclude_sessions": [],
    "exclude_channels": [],
    "include_current_time": False,
    "snapshot_files": [
        "/opt/data/state/MEMORY_EVENT_CONTEXT.md",
        "/opt/data/state/MEMORY_EMOTIONS_CONTEXT.md",
    ],
}
DEFAULT_CONFIG = {
    "schema_version": 1,
    "description": "memory dashboard v3 config",
    "lanes": [],
}
DEFAULT_STATE = {
    "last_loaded_at": None,
    "last_saved_at": None,
    "last_resolved_at": None,
    "last_injected_at": None,
    "last_tick_at": None,
    "last_tick_summary": None,
    "last_resolution": None,
    "session_runtime": {},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def plugin_root() -> Path:
    return get_hermes_home() / "plugins" / PLUGIN_NAME


def config_path() -> Path:
    return plugin_root() / CONFIG_DIRNAME / CONFIG_FILENAME


def state_path() -> Path:
    return plugin_root() / STATE_DIRNAME / STATE_FILENAME


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return _json_clone(default)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail=f"JSON object expected: {path}")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_lines(values: list[str]) -> list[str]:
    normalized = []
    for item in values:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _coerce_json_dict(payload: Any, *, context: str) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return {}
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"{context} must be valid JSON") from exc
        if isinstance(decoded, dict):
            return decoded
        raise HTTPException(status_code=400, detail=f"{context} must decode to a JSON object")
    if payload is None:
        return {}
    raise HTTPException(status_code=400, detail=f"{context} must be a JSON object")


def _source_get(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _platform_text(source: Any) -> str:
    platform = _source_get(source, "platform", "")
    value = getattr(platform, "value", platform)
    return str(value or "").strip()


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled"}:
            return True
        if text in {"0", "false", "no", "off", "disabled"}:
            return False
    if value is None:
        return default
    return bool(value)


def _normalize_reinject_interval_minutes(value: Any) -> int:
    try:
        minutes = int(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, minutes)


def _normalize_nonnegative_seconds(value: Any, default: int = 0) -> int:
    try:
        seconds = int(round(float(value)))
    except (TypeError, ValueError):
        return max(0, int(default))
    return max(0, seconds)


def _normalize_idle_seconds(source: dict[str, Any]) -> int:
    explicit = source.get("idle_seconds")
    if explicit is not None and str(explicit).strip() != "":
        return _normalize_nonnegative_seconds(explicit, 0)
    legacy_minutes = _normalize_reinject_interval_minutes(source.get("reinject_interval_minutes"))
    return legacy_minutes * 60


def _normalize_lane(data: dict[str, Any], index: int = 0) -> dict[str, Any]:
    source = dict(data or {})
    normalized = _json_clone(DEFAULT_LANE)
    fallback_name = f"memory-{index + 1}"
    normalized["name"] = str(source.get("name") or source.get("id") or fallback_name)
    normalized["enabled"] = bool(source.get("enabled", True))
    normalized["prompt"] = str(source.get("prompt") or "").strip()
    normalized["include_current_time"] = _normalize_bool(
        source.get("include_current_time"),
        False,
    )
    idle_seconds = _normalize_idle_seconds(source)
    normalized["idle_seconds"] = idle_seconds
    normalized["reinject_interval_minutes"] = _normalize_reinject_interval_minutes(
        source.get("reinject_interval_minutes") if source.get("reinject_interval_minutes") is not None else idle_seconds / 60
    )
    normalized["max_session_age_seconds"] = _normalize_nonnegative_seconds(
        source.get("max_session_age_seconds"),
        DEFAULT_LANE.get("max_session_age_seconds", 86400),
    )
    target_sessions = _normalize_lines(list(source.get("target_sessions") or []))
    target_channels = _normalize_lines(list(source.get("target_channels") or []))
    exclude_sessions = _normalize_lines(list(source.get("exclude_sessions") or []))
    exclude_channels = _normalize_lines(list(source.get("exclude_channels") or []))
    if target_channels or exclude_channels:
        normalized["target_sessions"] = []
        normalized["target_channels"] = target_channels
        normalized["exclude_sessions"] = []
        normalized["exclude_channels"] = exclude_channels
    else:
        normalized["target_sessions"] = target_sessions
        normalized["target_channels"] = []
        normalized["exclude_sessions"] = exclude_sessions
        normalized["exclude_channels"] = []
    normalized["snapshot_files"] = _normalize_lines(list(source.get("snapshot_files") or []))
    return normalized


def _normalize_config(data: dict[str, Any] | str | None) -> dict[str, Any]:
    source = _coerce_json_dict(data, context="config payload")
    config = _json_clone(DEFAULT_CONFIG)
    raw_lanes = source.get("lanes")
    if isinstance(raw_lanes, list):
        lanes = [_normalize_lane(item if isinstance(item, dict) else {}, index=i) for i, item in enumerate(raw_lanes)]
    else:
        lanes = [_normalize_lane(source, index=0)]
    if not lanes:
        lanes = []
    config["schema_version"] = 1
    config["description"] = str(source.get("description") or "memory dashboard v3 config")
    config["lanes"] = lanes
    return config


def load_config() -> dict[str, Any]:
    data = _read_json(config_path(), DEFAULT_CONFIG)
    return _normalize_config(data)


def load_state() -> dict[str, Any]:
    state = _read_json(state_path(), DEFAULT_STATE)
    for key, value in DEFAULT_STATE.items():
        state.setdefault(key, _json_clone(value))
    if not isinstance(state.get("session_runtime"), dict):
        state["session_runtime"] = {}
    return state


def save_state(state: dict[str, Any]) -> dict[str, Any]:
    _write_json(state_path(), state)
    return state


def _load_runtime_module() -> Any | None:
    try:
        return importlib.import_module("hermes_plugins.memory.runtime_tick")
    except Exception:
        logger.info("memory plugin: runtime module not available for watcher wake", exc_info=True)
        return None


def _wake_runtime_watchers(reason: str = "dashboard-config-save") -> int:
    module = _load_runtime_module()
    if module is None:
        return 0
    wake = getattr(module, "wake_all_memory_tick_watchers", None)
    if not callable(wake):
        return 0
    try:
        return int(wake(reason=reason) or 0)
    except Exception:
        logger.warning("memory plugin: failed to wake runtime watchers", exc_info=True)
        return 0


def _definition_target_patterns(lane: dict[str, Any]) -> list[str]:
    target_channels = list(lane.get("target_channels") or [])
    if target_channels:
        return target_channels
    return list(lane.get("target_sessions") or [])


def _definition_exclude_patterns(lane: dict[str, Any]) -> list[str]:
    exclude_channels = list(lane.get("exclude_channels") or [])
    if exclude_channels:
        return exclude_channels
    return list(lane.get("exclude_sessions") or [])


def _build_session_key_from_source(source: Any) -> str:
    try:
        from gateway.session import SessionSource, build_session_key

        if isinstance(source, SessionSource):
            return build_session_key(source)
        if isinstance(source, dict) and source.get("platform") and source.get("chat_id"):
            return build_session_key(SessionSource.from_dict(source))
    except Exception:
        return ""
    return ""


def _session_selector_aliases(session_key: str, source: Any) -> set[str]:
    aliases = set()
    normalized_session_key = _safe_text(session_key)
    if normalized_session_key:
        aliases.add(normalized_session_key)
    platform = _platform_text(source)
    chat_id = _safe_text(_source_get(source, "chat_id", ""))
    thread_id = _safe_text(_source_get(source, "thread_id", ""))
    parent_chat_id = _safe_text(_source_get(source, "parent_chat_id", ""))
    chat_type = _safe_text(_source_get(source, "chat_type", ""))
    if chat_id:
        aliases.add(chat_id)
    if thread_id:
        aliases.add(thread_id)
    if parent_chat_id:
        aliases.add(parent_chat_id)
    if platform and chat_type and chat_id:
        aliases.add(f"{platform}:{chat_type}:{chat_id}")
    if platform and thread_id:
        aliases.add(f"{platform}:thread:{thread_id}")
        if chat_id:
            aliases.add(f"{platform}:{chat_id}:{thread_id}")
    if platform and parent_chat_id:
        aliases.add(f"{platform}:parent:{parent_chat_id}")
    return aliases


def _channel_name_aliases(chat_name: str) -> set[str]:
    aliases = set()
    normalized = _safe_text(chat_name)
    if not normalized:
        return aliases
    aliases.add(normalized)
    for part in normalized.split(" / "):
        part_text = _safe_text(part)
        if not part_text:
            continue
        aliases.add(part_text)
        if "#" in part_text:
            aliases.add(part_text[part_text.index("#"):])
    return aliases


def _channel_selector_aliases(source: Any) -> set[str]:
    aliases = set()
    platform = _platform_text(source)
    chat_id = _safe_text(_source_get(source, "chat_id", ""))
    thread_id = _safe_text(_source_get(source, "thread_id", ""))
    parent_chat_id = _safe_text(_source_get(source, "parent_chat_id", ""))
    chat_name = _safe_text(_source_get(source, "chat_name", ""))
    if chat_id:
        aliases.add(chat_id)
    if thread_id:
        aliases.add(thread_id)
    if parent_chat_id:
        aliases.add(parent_chat_id)
    if platform and chat_id:
        aliases.add(f"{platform}:{chat_id}")
    if platform and thread_id:
        aliases.add(f"{platform}:{thread_id}")
    if platform and parent_chat_id:
        aliases.add(f"{platform}:{parent_chat_id}")
    if platform and chat_id and thread_id:
        aliases.add(f"{platform}:{chat_id}:{thread_id}")
    for name_alias in _channel_name_aliases(chat_name):
        aliases.add(name_alias)
        if platform:
            aliases.add(f"{platform}:{name_alias}")
    return aliases


def _patterns_match(aliases: set[str], patterns: list[str]) -> bool:
    normalized_patterns = _normalize_lines(patterns)
    if not normalized_patterns:
        return True
    if any(pattern in {"*", "all", "origin"} for pattern in normalized_patterns):
        return True
    for pattern in normalized_patterns:
        for alias in aliases:
            if fnmatch.fnmatchcase(alias, pattern):
                return True
    return False


def _lane_selector_kind(lane: dict[str, Any]) -> str:
    if lane.get("target_channels") or lane.get("exclude_channels"):
        return "channel"
    return "session"


def _select_matching_lanes(config: dict[str, Any], session_key: str, source: Any) -> list[dict[str, Any]]:
    session_aliases = _session_selector_aliases(session_key, source)
    channel_aliases = _channel_selector_aliases(source)
    matched = []
    for lane in list(config.get("lanes") or []):
        if not isinstance(lane, dict):
            continue
        normalized_lane = _normalize_lane(lane)
        if not normalized_lane.get("enabled", True):
            continue
        selector_kind = _lane_selector_kind(normalized_lane)
        aliases = channel_aliases if selector_kind == "channel" else session_aliases
        target_patterns = _definition_target_patterns(normalized_lane)
        exclude_patterns = _definition_exclude_patterns(normalized_lane)
        if not _patterns_match(aliases, target_patterns):
            continue
        if exclude_patterns and _patterns_match(aliases, exclude_patterns):
            continue
        matched.append(normalized_lane)
    return matched


def _read_snapshot_text(raw_path: str) -> dict[str, Any]:
    path = Path(raw_path)
    if not path.is_absolute():
        path = (plugin_root() / path).resolve()
    result = {"path": str(path), "exists": path.exists(), "content": "", "error": None}
    if not path.exists():
        result["error"] = "missing"
        return result
    try:
        result["content"] = path.read_text(encoding="utf-8").strip()
    except Exception as exc:  # pragma: no cover - defensive logging path
        result["error"] = str(exc)
    return result


def _maybe_refresh_managed_snapshots(paths: list[str]) -> None:
    normalized_paths = {_safe_text(path) for path in paths if _safe_text(path)}
    if not normalized_paths.intersection(MANAGED_SNAPSHOT_PATHS):
        return
    if not BUILD_MEMORY_CONTEXT_SCRIPT.exists():
        logger.warning("memory plugin: build script missing: %s", BUILD_MEMORY_CONTEXT_SCRIPT)
        return
    try:
        subprocess.run(
            ["python3", str(BUILD_MEMORY_CONTEXT_SCRIPT)],
            cwd="/opt/data",
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except Exception:
        logger.warning("memory plugin: failed to refresh managed snapshots before resolve", exc_info=True)


def _current_time_entry() -> dict[str, Any]:
    now = datetime.now(JST)
    content = "\n".join(
        [
            f"current_time: {now.isoformat(timespec='seconds')}",
            "timezone: Asia/Tokyo",
        ]
    )
    return {
        "path": "__current_time__",
        "content": content,
        "kind": "current_time",
        "label": "now",
        "date": now.date().isoformat(),
    }


def _render_injection_text(matched_lanes: list[dict[str, Any]], loaded_files: list[dict[str, Any]]) -> str:
    if not matched_lanes:
        return ""
    lane_names = ", ".join(str(lane.get("name") or "unknown") for lane in matched_lanes)
    sections = [
        "[IMPORTANT: The following MEMORY context was auto-injected for this session. Treat it as background context. Use it when relevant, and avoid quoting it unless it materially helps the user.]",
        f"[Memory lanes: {lane_names}]",
    ]
    for lane in matched_lanes:
        prompt_text = str(lane.get("prompt") or "").strip()
        if not prompt_text:
            continue
        lane_name = str(lane.get("name") or "unknown")
        sections.append(f"[Memory behavior prompt: {lane_name}]\n{prompt_text}")
    for item in loaded_files:
        content = str(item.get("content") or "")
        if not content.strip():
            continue
        if item.get("kind") == "current_time":
            sections.append(f"[Current time: {item.get('label') or 'now'} · {item.get('date') or ''}]\n{content}")
        else:
            sections.append(f"[Memory snapshot: {item['path']}]\n{content}")
    if len(sections) <= 2:
        return ""
    return "\n\n".join(sections)


def _truncate_preview_text(value: Any, *, limit: int = 400) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _load_lane_preview(lane: dict[str, Any]) -> dict[str, Any]:
    normalized_lane = _normalize_lane(lane)
    ordered_paths: list[str] = []
    seen_paths: set[str] = set()
    for raw_path in list(normalized_lane.get("snapshot_files") or []):
        path_text = _safe_text(raw_path)
        if not path_text or path_text in seen_paths:
            continue
        ordered_paths.append(path_text)
        seen_paths.add(path_text)
    _maybe_refresh_managed_snapshots(ordered_paths)
    file_results = [_read_snapshot_text(path_text) for path_text in ordered_paths]
    loaded_files = [item for item in file_results if item.get("content")]
    include_current_time = _normalize_bool(normalized_lane.get("include_current_time"), False)
    current_time_files = [_current_time_entry()] if include_current_time else []
    loaded_entries = current_time_files + loaded_files
    missing_files = [item for item in file_results if item.get("error")]
    text = _render_injection_text([normalized_lane], loaded_entries)
    return {
        "lane_name": str(normalized_lane.get("name") or ""),
        "text": text,
        "excerpt": _truncate_preview_text(text),
        "has_preview": bool(text),
        "include_current_time": include_current_time,
        "snapshot_files": ordered_paths,
        "loaded_files": [
            {
                "path": item["path"],
                "chars": len(str(item.get("content") or "")),
                "kind": str(item.get("kind") or "snapshot"),
                "label": item.get("label"),
                "date": item.get("date"),
            }
            for item in loaded_entries
        ],
        "missing_files": [{"path": item["path"], "error": item.get("error")} for item in missing_files],
    }


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = _safe_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _session_runtime_entry(state: dict[str, Any], session_key: str) -> dict[str, Any]:
    runtime = state.setdefault("session_runtime", {})
    if not isinstance(runtime, dict):
        runtime = {}
        state["session_runtime"] = runtime
    entry = runtime.get(session_key)
    if not isinstance(entry, dict):
        entry = {}
        runtime[session_key] = entry
    return entry


def resolve_memory_injection_policy(
    config: dict[str, Any],
    session_key: str,
    source: Any,
    *,
    is_new_session: bool = False,
    session_id: str | None = None,
) -> dict[str, Any]:
    result = resolve_memory_injection(config, session_key, source)
    effective_session_key = _safe_text(result.get("session_key") or session_key)
    matched_lanes = list(result.get("lanes") or [])
    positive_intervals = sorted(
        {
            _normalize_reinject_interval_minutes(lane.get("reinject_interval_minutes"))
            for lane in matched_lanes
            if _normalize_reinject_interval_minutes(lane.get("reinject_interval_minutes")) > 0
        }
    )
    reinject_interval_minutes = positive_intervals[0] if positive_intervals else 0
    state = load_state()
    session_runtime = _session_runtime_entry(state, effective_session_key) if effective_session_key else {}
    last_injected_at = _safe_text(session_runtime.get("last_injected_at") or "")
    last_injected_dt = _parse_iso_datetime(last_injected_at)
    now_dt = datetime.now(timezone.utc).astimezone()
    elapsed_minutes = None
    if last_injected_dt is not None:
        elapsed_minutes = max(0.0, (now_dt - last_injected_dt).total_seconds() / 60.0)

    should_inject = False
    decision_reason = "no_match"
    if result.get("matched"):
        if is_new_session:
            should_inject = True
            decision_reason = "new_session"
        elif reinject_interval_minutes <= 0:
            decision_reason = "interval_disabled"
        elif not effective_session_key:
            decision_reason = "missing_session_key"
        elif not last_injected_at:
            decision_reason = "awaiting_initial_injection"
        elif elapsed_minutes is not None and elapsed_minutes >= float(reinject_interval_minutes):
            should_inject = True
            decision_reason = "interval_elapsed"
        else:
            decision_reason = "interval_not_elapsed"

    return {
        "result": result,
        "session_key": effective_session_key,
        "session_id": _safe_text(session_id or ""),
        "is_new_session": bool(is_new_session),
        "should_inject": should_inject,
        "decision_reason": decision_reason,
        "reinject_interval_minutes": reinject_interval_minutes,
        "matched_reinject_intervals": positive_intervals,
        "last_injected_at": last_injected_at or None,
        "elapsed_minutes": elapsed_minutes,
    }


def resolve_memory_injection(config: dict[str, Any], session_key: str, source: Any) -> dict[str, Any]:
    normalized_config = _normalize_config(config)
    effective_session_key = _safe_text(session_key) or _build_session_key_from_source(source)
    matched_lanes = _select_matching_lanes(normalized_config, effective_session_key, source)
    ordered_paths: list[str] = []
    seen_paths: set[str] = set()
    for lane in matched_lanes:
        for raw_path in list(lane.get("snapshot_files") or []):
            path_text = _safe_text(raw_path)
            if not path_text or path_text in seen_paths:
                continue
            ordered_paths.append(path_text)
            seen_paths.add(path_text)
    _maybe_refresh_managed_snapshots(ordered_paths)
    file_results = [_read_snapshot_text(path_text) for path_text in ordered_paths]
    loaded_files = [item for item in file_results if item.get("content")]
    include_current_time = any(
        _normalize_bool(lane.get("include_current_time"), False) for lane in matched_lanes
    )
    current_time_files = [_current_time_entry()] if include_current_time else []
    loaded_entries = current_time_files + loaded_files
    missing_files = [item for item in file_results if item.get("error")]
    text = _render_injection_text(matched_lanes, loaded_entries)
    session_aliases = sorted(_session_selector_aliases(effective_session_key, source))
    channel_aliases = sorted(_channel_selector_aliases(source))
    return {
        "matched": bool(text),
        "session_key": effective_session_key,
        "lane_names": [str(lane.get("name") or "") for lane in matched_lanes],
        "lane_prompts": [
            {
                "name": str(lane.get("name") or ""),
                "prompt": str(lane.get("prompt") or ""),
            }
            for lane in matched_lanes
            if str(lane.get("prompt") or "").strip()
        ],
        "lanes": matched_lanes,
        "selector_aliases": {
            "session": session_aliases,
            "channel": channel_aliases,
        },
        "include_current_time": include_current_time,
        "snapshot_files": ordered_paths,
        "loaded_files": [
            {
                "path": item["path"],
                "chars": len(str(item.get("content") or "")),
                "kind": str(item.get("kind") or "snapshot"),
                "label": item.get("label"),
                "date": item.get("date"),
            }
            for item in loaded_entries
        ],
        "missing_files": [{"path": item["path"], "error": item.get("error")} for item in missing_files],
        "text": text,
    }


def update_memory_resolution_state(policy: dict[str, Any], *, injected: bool) -> dict[str, Any]:
    result = dict(policy.get("result") or {})
    state = load_state()
    now = now_iso()
    state["last_resolved_at"] = now
    if injected and result.get("matched"):
        state["last_injected_at"] = now
    session_key = _safe_text(policy.get("session_key") or result.get("session_key") or "")
    if session_key:
        session_runtime = _session_runtime_entry(state, session_key)
        session_runtime["last_seen_at"] = now
        session_runtime["last_resolved_at"] = now
        session_runtime["last_decision_reason"] = policy.get("decision_reason")
        session_runtime["lane_names"] = list(result.get("lane_names") or [])
        session_runtime["reinject_interval_minutes"] = int(policy.get("reinject_interval_minutes") or 0)
        if policy.get("session_id"):
            session_runtime["session_id"] = policy.get("session_id")
        if injected and result.get("matched"):
            session_runtime["last_injected_at"] = now
            if policy.get("decision_reason") == "pre_call_memory":
                session_runtime["last_injected_mode"] = "pre_call_memory"
            elif policy.get("decision_reason") == "pre_call_current_time":
                session_runtime["last_injected_mode"] = "pre_call_current_time"
            else:
                session_runtime["last_injected_mode"] = "session_open" if policy.get("is_new_session") else "interval"
    state["last_resolution"] = {
        "matched": bool(result.get("matched")),
        "session_key": result.get("session_key"),
        "lane_names": list(result.get("lane_names") or []),
        "lane_prompts": list(result.get("lane_prompts") or []),
        "include_current_time": bool(result.get("include_current_time")),
        "snapshot_files": list(result.get("snapshot_files") or []),
        "loaded_files": list(result.get("loaded_files") or []),
        "missing_files": list(result.get("missing_files") or []),
        "decision_reason": policy.get("decision_reason"),
        "should_inject": bool(policy.get("should_inject")),
        "reinject_interval_minutes": int(policy.get("reinject_interval_minutes") or 0),
        "elapsed_minutes": policy.get("elapsed_minutes"),
    }
    save_state(state)
    return state


def _memory_lane_runtime_summary(state: dict[str, Any]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    runtime = state.get("session_runtime")
    if not isinstance(runtime, dict):
        return summaries
    for session_key, session_state in runtime.items():
        if not isinstance(session_key, str) or not isinstance(session_state, dict):
            continue
        lanes = session_state.get("__lanes__")
        if not isinstance(lanes, dict):
            continue
        for lane_name, lane_state in lanes.items():
            if not isinstance(lane_name, str) or not isinstance(lane_state, dict):
                continue
            summary = summaries.setdefault(
                lane_name,
                {
                    "lane_name": lane_name,
                    "matched_session_count": 0,
                    "last_applied_at": None,
                    "last_attempt_at": None,
                    "last_decision_reason": None,
                    "last_session_key": None,
                    "last_session_id": None,
                    "last_source": None,
                },
            )
            summary["matched_session_count"] = int(summary.get("matched_session_count") or 0) + 1
            applied_dt = _parse_iso_datetime(lane_state.get("last_applied_at"))
            current_best = _parse_iso_datetime(summary.get("last_applied_at"))
            if applied_dt is not None and (current_best is None or applied_dt >= current_best):
                summary["last_applied_at"] = lane_state.get("last_applied_at")
                summary["last_attempt_at"] = lane_state.get("last_attempt_at")
                summary["last_decision_reason"] = lane_state.get("last_decision_reason")
                summary["last_session_key"] = session_key
                summary["last_session_id"] = session_state.get("session_id")
                summary["last_source"] = {
                    "platform": lane_state.get("platform"),
                    "chat_id": lane_state.get("chat_id"),
                    "thread_id": lane_state.get("thread_id"),
                }
    return summaries


@router.get("/config")
async def get_config() -> dict[str, Any]:
    config = load_config()
    state = load_state()
    state["last_loaded_at"] = now_iso()
    save_state(state)
    lane_previews = {
        str(lane.get("name") or ""): _load_lane_preview(lane)
        for lane in list(config.get("lanes") or [])
        if isinstance(lane, dict)
    }
    return {
        "plugin": PLUGIN_NAME,
        "kind": PLUGIN_KIND,
        "config_file": str(config_path()),
        "state_file": str(state_path()),
        "config": config,
        "runtime": state,
        "lane_runtime": _memory_lane_runtime_summary(state),
        "lane_previews": lane_previews,
    }


@router.put("/config")
async def put_config(payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
    normalized = _normalize_config(payload)
    _write_json(config_path(), normalized)
    state = load_state()
    state["last_saved_at"] = now_iso()
    save_state(state)
    woken_watchers = _wake_runtime_watchers(reason="dashboard-config-save")
    response = await get_config()
    response["watcher"] = {
        "reason": "dashboard-config-save",
        "woken_watchers": woken_watchers,
    }
    return response


@router.post("/resolve")
async def resolve_configured_memory(payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
    request = _coerce_json_dict(payload, context="resolve payload")
    source = request.get("source") or {}
    if not isinstance(source, dict):
        raise HTTPException(status_code=400, detail="source must be an object")
    session_key = _safe_text(request.get("session_key") or "")
    config = load_config()
    policy = resolve_memory_injection_policy(
        config,
        session_key,
        source,
        is_new_session=bool(request.get("is_new_session", False)),
        session_id=_safe_text(request.get("session_id") or ""),
    )
    result = dict(policy.get("result") or {})
    mark_injected = bool(request.get("mark_injected", False)) and bool(policy.get("should_inject"))
    state = update_memory_resolution_state(policy, injected=mark_injected)
    return {
        "plugin": PLUGIN_NAME,
        "kind": PLUGIN_KIND,
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
