from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import logging
import sys
import weakref
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hermes_cli.config import get_hermes_home

logger = logging.getLogger("gateway.memory_tick")
_PLUGIN_NAME = "memory"
_DEFAULT_CHECK_SECONDS = 60.0
_DEFAULT_MAX_SESSION_AGE_SECONDS = 86400.0
_ACTIVE_MEMORY_TICK_RUNNERS: list[weakref.ReferenceType[Any]] = []
_PLUGIN_API_MODULE_NAME = "hermes_plugins.memory.dashboard.plugin_api"


def _plugin_root() -> Path:
    plugins_root = get_hermes_home() / "plugins"
    renamed_root = plugins_root / "memory"
    if renamed_root.exists():
        return renamed_root
    return plugins_root / _PLUGIN_NAME


def _plugin_api_path() -> Path:
    return _plugin_root() / "dashboard" / "plugin_api.py"


def _load_plugin_api_module():
    module = sys.modules.get(_PLUGIN_API_MODULE_NAME)
    if module is not None:
        return module
    path = _plugin_api_path()
    spec = importlib.util.spec_from_file_location(_PLUGIN_API_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load memory plugin_api from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PLUGIN_API_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _register_active_runner(runner: Any) -> None:
    alive: list[weakref.ReferenceType[Any]] = []
    already_registered = False
    for ref in _ACTIVE_MEMORY_TICK_RUNNERS:
        existing = ref()
        if existing is None:
            continue
        alive.append(ref)
        if existing is runner:
            already_registered = True
    if not already_registered:
        try:
            alive.append(weakref.ref(runner))
        except TypeError:
            logger.debug("memory tick: runner does not support weakref registration: %r", runner)
            return
    _ACTIVE_MEMORY_TICK_RUNNERS[:] = alive


def wake_all_memory_tick_watchers(reason: str = "external-wake") -> int:
    woken = 0
    alive: list[weakref.ReferenceType[Any]] = []
    for ref in _ACTIVE_MEMORY_TICK_RUNNERS:
        runner = ref()
        if runner is None:
            continue
        alive.append(ref)
        starter = getattr(runner, "_ensure_memory_tick_watcher_started", None)
        waker = getattr(runner, "_memory_tick_hook_wake", None)
        try:
            if callable(starter):
                starter(reason)
                woken += 1
            elif callable(waker):
                waker()
                woken += 1
        except Exception:
            logger.warning("memory tick: failed to wake watcher reason=%s", reason, exc_info=True)
    _ACTIVE_MEMORY_TICK_RUNNERS[:] = alive
    if woken:
        logger.info("memory tick: woke %d watcher(s) reason=%s", woken, reason)
    else:
        logger.info("memory tick: no active watchers to wake reason=%s", reason)
    return woken


def _normalize_float(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return _parse_dt(value)


def _lane_runtime_entry(api: Any, state: dict[str, Any], session_key: str, lane_name: str) -> dict[str, Any]:
    session_runtime = api._session_runtime_entry(state, session_key)
    lanes = session_runtime.setdefault("__lanes__", {})
    if not isinstance(lanes, dict):
        lanes = {}
        session_runtime["__lanes__"] = lanes
    lane_state = lanes.get(lane_name)
    if not isinstance(lane_state, dict):
        lane_state = {}
        lanes[lane_name] = lane_state
    return lane_state


def _candidate_source_rows(api: Any, lane: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    ordered_paths: list[str] = []
    seen: set[str] = set()
    for raw_path in list(lane.get("snapshot_files") or []):
        path_text = api._safe_text(raw_path)
        if not path_text or path_text in seen:
            continue
        ordered_paths.append(path_text)
        seen.add(path_text)
    file_rows = [api._read_snapshot_text(path_text) for path_text in ordered_paths]
    loaded_rows = [item for item in file_rows if item.get("content")]
    return ordered_paths, file_rows, loaded_rows


def _content_hash(file_rows: list[dict[str, Any]]) -> str:
    serializable = []
    for item in list(file_rows):
        serializable.append(
            {
                "path": str(item.get("path") or ""),
                "content": str(item.get("content") or ""),
                "error": item.get("error"),
                "kind": str(item.get("kind") or "snapshot"),
                "label": item.get("label"),
                "date": item.get("date"),
            }
        )
    blob = json.dumps(serializable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _source_mtimes(api: Any, paths: list[str]) -> dict[str, str]:
    results: dict[str, str] = {}
    for raw_path in list(paths):
        text = str(raw_path or "").strip()
        if not text:
            continue
        path = api._resolve_snapshot_path(text)
        if not path.exists():
            continue
        try:
            results[str(path)] = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        except Exception:
            continue
    return results


def _matching_lanes(api: Any, config: dict[str, Any], session_key: str, source: Any) -> set[str]:
    return {str(lane.get("name") or "") for lane in api._select_matching_lanes(config, session_key, source)}


def _resolve_pre_call_memory_policy(
    api: Any,
    *,
    session_key: str | None,
    session_id: str | None,
    source: Any,
) -> dict[str, Any]:
    """Return the configured memory policy for the pre-call injection path.

    The dashboard resolver owns lane matching and text rendering. The policy
    layer decides whether to inject now: first matched session, every call when
    the interval is 0m, or after the configured interval has elapsed.
    """
    config = api.load_config()
    effective_session_key = api._safe_text(session_key) or api._build_session_key_from_source(source)
    return api.resolve_memory_injection_policy(
        config,
        effective_session_key,
        source,
        is_new_session=False,
        session_id=session_id or "",
    )


def _with_pre_call_memory_context(api: Any, *, runner: Any, message: Any, context_prompt: Any, session_key: str | None, session_id: str | None, source: Any) -> str:
    base = str(context_prompt or "")
    try:
        policy = _resolve_pre_call_memory_policy(api, session_key=session_key, session_id=session_id, source=source)
    except Exception:
        logger.debug("memory tick: failed to resolve pre-call memory policy", exc_info=True)
        return base
    result = dict(policy.get("result") or {})
    should_inject = bool(policy.get("should_inject")) and bool(result.get("matched"))
    if should_inject:
        try:
            active_memory_result = api.run_active_memory_retrieval(
                list(result.get("lanes") or []),
                query=str(message or ""),
            )
            result = api.append_active_memory_results(result, active_memory_result)
            policy = dict(policy)
            policy["result"] = result
        except Exception:
            logger.debug("memory tick: failed to retrieve active memory", exc_info=True)
    text = str(result.get("text") or "").strip()
    should_inject = should_inject and bool(text)
    try:
        api.update_memory_resolution_state(policy, injected=should_inject)
    except Exception:
        logger.debug("memory tick: failed to update pre-call memory state", exc_info=True)
    if not should_inject:
        logger.debug(
            "memory tick: pre-call memory skipped session=%s lanes=%s reason=%s",
            result.get("session_key") or session_key or "",
            result.get("lane_names"),
            policy.get("decision_reason"),
        )
        return base
    logger.debug(
        "memory tick: pre-call memory context injected session=%s lanes=%s reason=%s chars=%d",
        result.get("session_key") or session_key or "",
        result.get("lane_names"),
        policy.get("decision_reason"),
        len(text),
    )
    return (base + "\n\n" + text).strip()


async def _apply_memory_tick_for_lane(self, api: Any, state: dict[str, Any], session_key: str, entry: Any, lane: dict[str, Any]) -> bool:
    lane_name = str(lane.get("name") or "")
    if not lane_name:
        return False
    lane_state = _lane_runtime_entry(api, state, session_key, lane_name)
    now = api.now_iso()
    ordered_paths, file_rows, loaded_rows = _candidate_source_rows(api, lane)
    missing_rows = [item for item in file_rows if item.get("error")]
    source_hash = _content_hash(file_rows)
    source_mtimes = _source_mtimes(api, ordered_paths)
    previous_hash = str(lane_state.get("last_source_hash") or "")
    decision_reason = "source_changed" if source_hash != previous_hash else "source_unchanged"
    source = getattr(entry, "origin", None)
    session_runtime = api._session_runtime_entry(state, session_key)
    session_runtime["last_seen_at"] = now
    session_runtime["last_tick_at"] = now
    if getattr(entry, "session_id", None):
        session_runtime["session_id"] = getattr(entry, "session_id")
    lane_state["enabled"] = bool(lane.get("enabled", True))
    lane_state["last_attempt_at"] = now
    lane_state["last_applied_at"] = now
    lane_state["last_decision_reason"] = decision_reason
    lane_state["idle_seconds"] = _normalize_float(lane.get("idle_seconds"), 0.0)
    lane_state["reinject_interval_minutes"] = int(api._normalize_reinject_interval_minutes(lane.get("reinject_interval_minutes")))
    lane_state["include_current_time"] = bool(api._normalize_bool(lane.get("include_current_time"), False))
    lane_state["include_current_source"] = bool(api._normalize_bool(lane.get("include_current_source"), False))
    lane_state["active_profile"] = api._active_profile_name()
    lane_state["target_profiles"] = list(lane.get("target_profiles") or [])
    lane_state["exclude_profiles"] = list(lane.get("exclude_profiles") or [])
    lane_state["target_kind"] = api._lane_selector_kind(lane)
    lane_state["source_files"] = ordered_paths
    lane_state["loaded_files"] = [
        {
            "path": item.get("path"),
            "chars": len(str(item.get("content") or "")),
            "kind": item.get("kind") or "snapshot",
            "label": item.get("label"),
            "date": item.get("date"),
        }
        for item in loaded_rows
    ]

    lane_state["missing_files"] = [{"path": item.get("path"), "error": item.get("error")} for item in missing_rows]
    lane_state["last_source_hash"] = source_hash
    lane_state["last_source_mtimes"] = source_mtimes
    lane_state["platform"] = api._platform_text(source)
    lane_state["chat_id"] = api._safe_text(api._source_get(source, "chat_id", ""))
    lane_state["thread_id"] = api._safe_text(api._source_get(source, "thread_id", ""))
    return True


async def _memory_tick(self) -> float | None:
    api = _load_plugin_api_module()
    config = api.load_config()
    state = api.load_state()
    enabled_lanes = [lane for lane in list(config.get("lanes") or []) if isinstance(lane, dict) and lane.get("enabled", True)]
    now_dt = datetime.now(timezone.utc)
    next_delay_seconds: float | None = None
    applied = 0
    dirty = False

    try:
        self.session_store._ensure_loaded()
    except Exception:
        logger.debug("memory tick: session store not ready", exc_info=True)
        state["last_tick_at"] = api.now_iso()
        state["last_tick_summary"] = {"applied": 0, "enabled_lanes": len(enabled_lanes), "reason": "session_store_not_ready"}
        api.save_state(state)
        return _DEFAULT_CHECK_SECONDS

    with self.session_store._lock:
        self.session_store._ensure_loaded_locked()
        entries = {key: entry for key, entry in self.session_store._entries.items()}

    runtime = state.setdefault("session_runtime", {})
    if not isinstance(runtime, dict):
        runtime = {}
        state["session_runtime"] = runtime
        dirty = True

    stale_session_keys = set(runtime) - set(entries)
    for session_key in stale_session_keys:
        runtime.pop(session_key, None)
        dirty = True

    valid_lane_names = {str(lane.get("name") or "") for lane in enabled_lanes}
    for session_key, session_runtime in list(runtime.items()):
        if not isinstance(session_runtime, dict):
            runtime[session_key] = {}
            dirty = True
            continue
        lanes_state = session_runtime.get("__lanes__")
        if not isinstance(lanes_state, dict):
            continue
        stale_lane_names = set(lanes_state) - valid_lane_names
        for lane_name in stale_lane_names:
            lanes_state.pop(lane_name, None)
            dirty = True

    if not enabled_lanes:
        state["last_tick_at"] = api.now_iso()
        state["last_tick_summary"] = {"applied": 0, "enabled_lanes": 0, "reason": "no_enabled_lanes"}
        api.save_state(state)
        return _DEFAULT_CHECK_SECONDS

    matched_cache: dict[str, set[str]] = {}
    for session_key, entry in entries.items():
        source = getattr(entry, "origin", None)
        if source is None or not getattr(source, "chat_id", None):
            continue
        if getattr(entry, "suspended", False) or getattr(entry, "resume_pending", False):
            continue
        if session_key in getattr(self, "_running_agents", {}):
            continue
        adapter = self.adapters.get(source.platform)
        if adapter is None:
            continue
        updated_at = _coerce_dt(getattr(entry, "updated_at", None))
        if updated_at is None:
            continue
        matched_cache[session_key] = _matching_lanes(api, config, session_key, source)
        if not matched_cache[session_key]:
            continue
        for lane in enabled_lanes:
            lane_name = str(lane.get("name") or "")
            if not lane_name or lane_name not in matched_cache[session_key]:
                continue
            idle_seconds = _normalize_float(lane.get("idle_seconds"), 0.0)
            if idle_seconds <= 0:
                continue
            max_session_age_seconds = _normalize_float(lane.get("max_session_age_seconds"), _DEFAULT_MAX_SESSION_AGE_SECONDS)
            if max_session_age_seconds > 0 and (now_dt - updated_at).total_seconds() > max_session_age_seconds:
                continue
            lane_state = _lane_runtime_entry(api, state, session_key, lane_name)
            last_attempt_at = _parse_dt(lane_state.get("last_attempt_at"))
            last_applied_at = _parse_dt(lane_state.get("last_applied_at"))
            anchor_candidates = [dt for dt in (last_applied_at, last_attempt_at, updated_at) if dt is not None]
            if not anchor_candidates:
                continue
            anchor = max(anchor_candidates)
            due_at = anchor + timedelta(seconds=idle_seconds)
            if due_at > now_dt:
                due_delay = max(0.0, (due_at - now_dt).total_seconds())
                next_delay_seconds = due_delay if next_delay_seconds is None else min(next_delay_seconds, due_delay)
                continue
            changed = await _apply_memory_tick_for_lane(self, api, state, session_key, entry, lane)
            if changed:
                dirty = True
                applied += 1

    state["last_tick_at"] = api.now_iso()
    state["last_tick_summary"] = {
        "applied": applied,
        "enabled_lanes": len(enabled_lanes),
        "known_sessions": len(entries),
        "next_delay_seconds": next_delay_seconds,
    }
    dirty = True
    if dirty:
        api.save_state(state)
    if applied:
        return 0.0
    if next_delay_seconds is not None:
        return next_delay_seconds
    return _DEFAULT_CHECK_SECONDS


def _memory_tick_hook_wake(self) -> None:
    wake_event = getattr(self, "_memory_tick_hook_wake_event", None)
    if wake_event is None:
        wake_event = asyncio.Event()
        self._memory_tick_hook_wake_event = wake_event
    wake_event.set()


def _ensure_memory_tick_watcher_started(self, reason: str) -> None:
    _register_active_runner(self)
    existing = getattr(self, "_memory_tick_hook_task", None)
    if existing and not existing.done():
        _memory_tick_hook_wake(self)
        return
    wake_event = asyncio.Event()
    wake_event.set()
    self._memory_tick_hook_wake_event = wake_event
    task = asyncio.create_task(_memory_tick_hook_watcher(self))
    self._memory_tick_hook_task = task
    logger.info("memory tick watcher started (%s)", reason)


async def _memory_tick_hook_watcher(self) -> None:
    while self._running:
        try:
            next_delay = await _memory_tick(self)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("memory tick watcher tick failed")
            next_delay = _DEFAULT_CHECK_SECONDS
        wake_event = getattr(self, "_memory_tick_hook_wake_event", None)
        if wake_event is None:
            wake_event = asyncio.Event()
            self._memory_tick_hook_wake_event = wake_event
        if next_delay is None:
            next_delay = _DEFAULT_CHECK_SECONDS
        next_delay = max(0.0, float(next_delay))
        if next_delay == 0:
            await asyncio.sleep(0)
            continue
        try:
            await asyncio.wait_for(wake_event.wait(), timeout=next_delay)
        except asyncio.TimeoutError:
            pass
        finally:
            wake_event.clear()


def patch_gateway_runner() -> None:
    try:
        from gateway.run import GatewayRunner
    except Exception:
        logger.warning("memory tick: failed to import GatewayRunner", exc_info=True)
        return

    if getattr(GatewayRunner, "_memory_tick_hook_patched", False):
        return

    original_start = GatewayRunner.start
    original_schedule_resume_pending_sessions = GatewayRunner._schedule_resume_pending_sessions
    original_handle_message = GatewayRunner._handle_message
    original_run_agent_inner = GatewayRunner._run_agent_inner

    async def patched_start(self, *args, **kwargs):
        result = await original_start(self, *args, **kwargs)
        _ensure_memory_tick_watcher_started(self, "post-start")
        return result

    def patched_schedule_resume_pending_sessions(self, *args, **kwargs):
        _ensure_memory_tick_watcher_started(self, "startup-tail")
        return original_schedule_resume_pending_sessions(self, *args, **kwargs)

    async def patched_handle_message(self, event, *args, **kwargs):
        _ensure_memory_tick_watcher_started(self, "message")
        response = await original_handle_message(self, event, *args, **kwargs)
        if not bool(getattr(event, "internal", False)):
            _memory_tick_hook_wake(self)
        return response

    async def patched_run_agent_inner(self, *args, **kwargs):
        try:
            api = _load_plugin_api_module()
            if len(args) >= 5:
                next_args = list(args)
                source = next_args[3]
                session_id = str(next_args[4] or "")
                session_key = kwargs.get("session_key")
                if session_key is None and len(next_args) >= 6:
                    session_key = next_args[5]
                next_args[1] = _with_pre_call_memory_context(
                    api,
                    runner=self,
                    message=next_args[0],
                    context_prompt=next_args[1],
                    session_key=str(session_key or ""),
                    session_id=session_id,
                    source=source,
                )
                args = tuple(next_args)
            else:
                source = kwargs.get("source")
                if source is not None:
                    kwargs["context_prompt"] = _with_pre_call_memory_context(
                        api,
                        runner=self,
                        message=kwargs.get("message") or kwargs.get("prompt") or "",
                        context_prompt=kwargs.get("context_prompt"),
                        session_key=str(kwargs.get("session_key") or ""),
                        session_id=str(kwargs.get("session_id") or ""),
                        source=source,
                    )
        except Exception:
            logger.debug("memory tick: pre-call current-time patch skipped", exc_info=True)
        return await original_run_agent_inner(self, *args, **kwargs)

    GatewayRunner.start = patched_start
    GatewayRunner._schedule_resume_pending_sessions = patched_schedule_resume_pending_sessions
    GatewayRunner._handle_message = patched_handle_message
    GatewayRunner._run_agent_inner = patched_run_agent_inner
    GatewayRunner._memory_tick_hook_wake = _memory_tick_hook_wake
    GatewayRunner._ensure_memory_tick_watcher_started = _ensure_memory_tick_watcher_started
    GatewayRunner._memory_tick_hook_patched = True
    logger.info("memory tick: GatewayRunner patched")


async def handle_hook_event(event_type: str, context: dict[str, Any]) -> None:
    if event_type == "gateway:startup":
        logger.info("memory tick runtime received gateway:startup")
    return None
