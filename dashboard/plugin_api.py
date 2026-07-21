from __future__ import annotations

import fnmatch
import importlib
import json
import logging
import math
import re

from collections import Counter

from datetime import datetime, timedelta, timezone
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
JST = ZoneInfo("Asia/Tokyo")
DEFAULT_LANE = {
    "name": "memory-1",
    "enabled": True,
    "prompt": "",
    "idle_seconds": 0,
    "max_session_age_seconds": 86400,
    "reinject_interval_minutes": 0,
    "target_sessions": [],
    "target_profiles": ["default"],
    "exclude_sessions": [],
    "exclude_profiles": [],
    "skills": [],

    "active_memory_directory": "",
    "snapshot_files": [
        "state/MEMORY_EVENT_CONTEXT.md",
        "state/MEMORY_EMOTIONS_CONTEXT.md",
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
    "last_active_memory_retrieval": None,
    "session_runtime": {},
}
_ACTIVE_MEMORY_CACHE: dict[str, dict[str, Any]] = {}
SNAPSHOT_PATH_ROOT = Path("/opt/data")
_DATE_TOKEN_RE = re.compile(
    r"\{(?P<name>TODAY|TOMORROW|YESTERDAY|YESTADAY)(?P<offset>[+-]\d+)?\}", re.IGNORECASE
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def plugin_root() -> Path:
    plugins_root = get_hermes_home() / "plugins"
    renamed_root = plugins_root / "memory"
    if renamed_root.exists():
        return renamed_root
    return plugins_root / PLUGIN_NAME


def config_path() -> Path:
    return plugin_root() / CONFIG_DIRNAME / CONFIG_FILENAME


def state_path() -> Path:
    return plugin_root() / STATE_DIRNAME / STATE_FILENAME


def _snapshot_path_root() -> Path:
    return SNAPSHOT_PATH_ROOT


def _expand_snapshot_path_tokens(raw_path: str, *, now: datetime | None = None) -> str:
    base_date = (now or datetime.now(JST)).date()

    def replace(match: re.Match[str]) -> str:
        name = match.group("name").upper()
        offset_text = match.group("offset") or ""
        offset = int(offset_text) if offset_text else 0
        if name == "TOMORROW":
            offset += 1
        if name in {"YESTERDAY", "YESTADAY"}:
            offset -= 1
        return (base_date + timedelta(days=offset)).isoformat()

    return _DATE_TOKEN_RE.sub(replace, _safe_text(raw_path))


def _resolve_snapshot_path(raw_path: str) -> Path:
    expanded = _expand_snapshot_path_tokens(raw_path)
    path = Path(expanded)
    if not path.is_absolute():
        path = (_snapshot_path_root() / path).resolve()
    return path


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


_DISCORD_CHANNEL_MENTION_RE = re.compile(r"^(?:(?P<platform>[A-Za-z][\w-]*):)?<#(?P<id>\d+)>$")


def _selector_pattern_aliases(pattern: str) -> set[str]:
    text = _safe_text(pattern)
    if not text:
        return set()
    aliases = {text}
    match = _DISCORD_CHANNEL_MENTION_RE.match(text)
    if match:
        channel_id = match.group("id")
        platform = (match.group("platform") or "discord").lower()
        aliases.update({channel_id, f"<#{channel_id}>", f"{platform}:<#{channel_id}>"})
    return aliases


def _active_profile_name() -> str:
    try:
        from hermes_cli.profiles import get_active_profile_name

        return str(get_active_profile_name() or "default").strip() or "default"
    except Exception:
        return "default"


def _available_profiles() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        value = str(name or "").strip()
        if not value or value in seen:
            return
        seen.add(value)
        rows.append({"value": value, "label": value})

    add("default")
    try:
        from hermes_cli.profiles import list_profiles

        for info in list_profiles():
            add(str(getattr(info, "name", "") or ""))
    except Exception:
        pass

    candidate_roots = [
        get_hermes_home() / "profiles",
        Path("/opt/data/profiles"),
    ]
    for root in candidate_roots:
        try:
            if not root.is_dir():
                continue
            for entry in sorted(root.iterdir()):
                if entry.is_dir() and entry.name != "default":
                    add(entry.name)
        except Exception:
            continue
    return rows


def _profile_patterns_match(profile: str, patterns: list[str]) -> bool:
    normalized_patterns = _normalize_lines(patterns)
    if not normalized_patterns:
        normalized_patterns = ["default"]
    profile_text = _safe_text(profile) or "default"
    aliases = {profile_text, profile_text.lower()}
    if profile_text == "default":
        aliases.add("root")
    for pattern in normalized_patterns:
        pattern_text = _safe_text(pattern)
        if pattern_text in {"*", "all", "any"}:
            continue
        pattern_lower = pattern_text.lower()
        for alias in aliases:
            if fnmatch.fnmatchcase(alias, pattern_text) or fnmatch.fnmatchcase(alias.lower(), pattern_lower):
                return True
    return False


def _lane_matches_active_profile(lane: dict[str, Any], active_profile: str | None = None) -> bool:
    profile = _safe_text(active_profile) or _active_profile_name()
    if not _profile_patterns_match(profile, list(lane.get("target_profiles") or [])):
        return False
    exclude_profiles = _normalize_lines(list(lane.get("exclude_profiles") or []))
    if exclude_profiles and _profile_patterns_match(profile, exclude_profiles):
        return False
    return True


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


def _normalize_positive_seconds(value: Any, default: int = 8) -> int:
    try:
        seconds = int(round(float(value)))
    except (TypeError, ValueError):
        return max(1, int(default))
    return max(1, seconds)


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

    idle_seconds = _normalize_idle_seconds(source)
    normalized["idle_seconds"] = idle_seconds
    if idle_seconds > 0:
        normalized["reinject_interval_minutes"] = _normalize_reinject_interval_minutes(idle_seconds / 60)
    else:
        normalized["reinject_interval_minutes"] = _normalize_reinject_interval_minutes(source.get("reinject_interval_minutes"))
    normalized["max_session_age_seconds"] = _normalize_nonnegative_seconds(
        source.get("max_session_age_seconds"),
        DEFAULT_LANE.get("max_session_age_seconds", 86400),
    )
    normalized["target_sessions"] = _normalize_lines(list(source.get("target_sessions") or []))
    normalized["target_profiles"] = _normalize_lines(list(source.get("target_profiles") or [])) or ["default"]
    normalized["exclude_sessions"] = _normalize_lines(list(source.get("exclude_sessions") or []))
    normalized["exclude_profiles"] = _normalize_lines(list(source.get("exclude_profiles") or []))
    normalized["skills"] = _normalize_lines(list(source.get("skills") or []))
    normalized["active_memory_directory"] = str(source.get("active_memory_directory") or "").strip()
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
    return list(lane.get("target_sessions") or [])


def _definition_exclude_patterns(lane: dict[str, Any]) -> list[str]:
    return list(lane.get("exclude_sessions") or [])


def _lane_selector_kind(lane: dict[str, Any]) -> str:
    targets = [item for item in _definition_target_patterns(lane) if item != "*"]
    excludes = _definition_exclude_patterns(lane)
    if targets:
        return "target"
    if excludes:
        return "exclude"
    return "all"


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



def _patterns_match(aliases: set[str], patterns: list[str]) -> bool:
    normalized_patterns = _normalize_lines(patterns)
    if not normalized_patterns:
        return True
    normalized_aliases = {_safe_text(alias) for alias in aliases if _safe_text(alias)}
    if not normalized_aliases:
        return False
    lower_aliases = {alias.lower() for alias in normalized_aliases}
    for pattern in normalized_patterns:
        pattern_text = _safe_text(pattern)
        pattern_lower = pattern_text.lower()
        if pattern_lower in {"*", "all", "any"}:
            return True
        for pattern_alias in _selector_pattern_aliases(pattern_text):
            pattern_alias_lower = pattern_alias.lower()
            for alias in normalized_aliases:
                if fnmatch.fnmatchcase(alias, pattern_alias):
                    return True
            for alias_lower in lower_aliases:
                if fnmatch.fnmatchcase(alias_lower, pattern_alias_lower):
                    return True
    return False



def _select_matching_lanes(config: dict[str, Any], session_key: str, source: Any) -> list[dict[str, Any]]:
    session_aliases = _session_selector_aliases(session_key, source)
    matched = []
    for lane in list(config.get("lanes") or []):
        if not isinstance(lane, dict):
            continue
        normalized_lane = _normalize_lane(lane)
        if not normalized_lane.get("enabled", True):
            continue
        if not _lane_matches_active_profile(normalized_lane):
            continue
        target_patterns = _definition_target_patterns(normalized_lane)
        exclude_patterns = _definition_exclude_patterns(normalized_lane)
        if not _patterns_match(session_aliases, target_patterns):
            continue
        if exclude_patterns and _patterns_match(session_aliases, exclude_patterns):
            continue
        matched.append(normalized_lane)
    return matched


def _read_snapshot_text(raw_path: str) -> dict[str, Any]:
    path = _resolve_snapshot_path(raw_path)
    result = {"path": str(path), "exists": path.exists(), "content": "", "error": None}
    if not path.exists():
        result["error"] = "missing"
        return result
    try:
        result["content"] = path.read_text(encoding="utf-8").strip()
    except Exception as exc:  # pragma: no cover - defensive logging path
        result["error"] = str(exc)
    return result



_HIRAGANA_STOPWORDS = frozenset({
    "ある", "いる", "する", "した", "して", "です", "ます", "ない", "なる", "ので", "から", "まで", "より",
    "ここ", "これ", "それ", "あれ", "この", "その", "あの", "もの", "こと", "ため", "よう", "ほう",
})


def _active_memory_terms(text: str, *, expand_kanji: bool = False) -> list[str]:
    normalized = str(text or "").casefold()
    terms: list[str] = []
    for match in re.finditer(r"[0-9a-z][0-9a-z._+-]{2,}|[\u30a0-\u30ffー]{2,}|[\u3400-\u9fff]{2,}|[\u3040-\u309f]{2,}", normalized):
        term = match.group(0)
        if "\u3040" <= term[0] <= "\u309f" and (len(term) > 6 or term in _HIRAGANA_STOPWORDS):
            continue
        terms.append(term)
        if expand_kanji and "\u3400" <= term[0] <= "\u9fff":
            for width in range(2, min(4, len(term)) + 1):
                terms.extend(term[index:index + width] for index in range(len(term) - width + 1))
    return terms


def _active_memory_root(value: str) -> Path | None:
    notes_root = (get_hermes_home() / "workspace" / "notes").resolve()
    path = Path(value).expanduser()
    if path.is_absolute():
        return None
    candidate = (get_hermes_home() / path).resolve()
    if candidate != notes_root and notes_root not in candidate.parents:
        return None
    return candidate


def _active_memory_records(root: Path) -> list[dict[str, Any]]:
    paths = sorted([*root.rglob("*.md"), *root.rglob("*.txt")], key=lambda item: str(item))[:500]
    signature: list[tuple[str, int, int]] = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        signature.append((str(path), stat.st_mtime_ns, stat.st_size))
    cache_key = str(root.resolve())
    cached = _ACTIVE_MEMORY_CACHE.get(cache_key)
    if cached and cached.get("signature") == signature:
        return list(cached.get("records") or [])
    records: list[dict[str, Any]] = []
    for path_text, _mtime_ns, _size in signature:
        path = Path(path_text)
        try:
            text = path.read_text(encoding="utf-8")[:120000]
        except (OSError, UnicodeError):
            continue
        records.append({
            "title": path.stem,
            "path": path_text,
            "terms": Counter(_active_memory_terms(f"{path.stem}\n{text}", expand_kanji=True)),
            "excerpt": re.sub(r"\s+", " ", text).strip()[:100],
        })
    _ACTIVE_MEMORY_CACHE[cache_key] = {"signature": signature, "records": records}
    return records


def run_active_memory_retrieval(lanes: list[dict[str, Any]], *, query: str) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    query_terms = set(_active_memory_terms(query))
    if not query_terms:
        return {"entries": [], "selected": [], "errors": []}
    for lane in lanes:
        directory = _safe_text(lane.get("active_memory_directory"))
        if not directory:
            continue
        lane_name = str(lane.get("name") or "unknown")
        root = _active_memory_root(directory)
        if root is None:
            errors.append({"lane_name": lane_name, "directory": directory, "error": "directory_outside_notes_root"})
            continue
        if not root.exists() or not root.is_dir():
            errors.append({"lane_name": lane_name, "directory": str(root), "error": "directory_missing"})
            continue
        records = _active_memory_records(root)
        document_frequency: Counter[str] = Counter()
        for record in records:
            document_frequency.update(set(record.get("terms") or {}))
        average_length = sum(sum((record.get("terms") or {}).values()) for record in records) / max(1, len(records))
        candidates: list[dict[str, Any]] = []
        for record in records:
            term_counts: Counter[str] = record.get("terms") or Counter()
            matched_terms = query_terms & set(term_counts)
            if not matched_terms:
                continue
            if len(matched_terms) < 2 and len(query_terms) > 1:
                continue
            document_length = sum(term_counts.values())
            score = 0.0
            for term in matched_terms:
                frequency = term_counts[term]
                inverse_frequency = math.log(1 + (len(records) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
                denominator = frequency + 1.2 * (1 - 0.75 + 0.75 * document_length / max(1, average_length))
                score += inverse_frequency * frequency * 2.2 / denominator
            candidates.append({"title": record["title"], "path": record["path"], "score": round(score, 4), "excerpt": record["excerpt"]})
        lane_selected = sorted(candidates, key=lambda item: (-float(item["score"]), str(item["path"])))[:2]
        if not lane_selected:
            continue
        selected.extend({**item, "lane_name": lane_name} for item in lane_selected)
        lines = [
            "[Active memory]",
            "Use as soft context, not source of truth.",
            "If surrounding context is necessary, use read_active_memory(path=<shown path>) only for a path listed below.",
        ]
        for item in lane_selected:
            lines.extend([f"- {item['title']} ({item['path']})", f"  relevance={item['score']}", f"  excerpt={item['excerpt']}"])
        lines.append("[/Active memory]")
        context = "\n".join(lines)
        entries.append({
            "path": f"__active_memory__:{lane_name}",
            "content": context,
            "kind": "active_memory",
            "label": f"Active memory: {lane_name}",
            "date": None,
            "directory": str(root),
        })
    return {"entries": entries, "selected": selected, "errors": errors}


def record_active_memory_retrieval(session_key: str, retrieval: dict[str, Any]) -> dict[str, Any]:
    """Persist only the paths selected by the most recent active-memory retrieval."""
    notes_root = _active_memory_root("workspace/notes")
    selected_paths: list[dict[str, str]] = []
    for item in list(retrieval.get("selected") or []):
        if not isinstance(item, dict):
            continue
        raw_path = _safe_text(item.get("path"))
        if not raw_path or notes_root is None:
            continue
        try:
            path = Path(raw_path).resolve(strict=False)
            path.relative_to(notes_root)
        except (OSError, ValueError):
            continue
        selected_paths.append({"path": str(path)})
    state = load_state()
    state["last_active_memory_retrieval"] = {
        "recorded_at": now_iso(),
        "session_key": _safe_text(session_key),
        "selected": selected_paths,
    }
    save_state(state)
    return state


def append_active_memory_results(result: dict[str, Any], retrieval: dict[str, Any]) -> dict[str, Any]:
    next_result = dict(result or {})
    entries = list(retrieval.get("entries") or [])
    errors = list(retrieval.get("errors") or [])
    if entries:
        addition = "\n\n".join(_safe_text(item.get("content")) for item in entries if _safe_text(item.get("content")))
        if addition:
            base = _safe_text(next_result.get("text"))
            next_result["text"] = (base + "\n\n" + addition).strip() if base else addition
        loaded = list(next_result.get("loaded_files") or [])
        loaded.extend(
            {
                "path": item.get("path"),
                "chars": len(str(item.get("content") or "")),
                "kind": str(item.get("kind") or "active_memory"),
                "label": item.get("label"),
                "date": item.get("date"),
            }
            for item in entries
        )
        next_result["loaded_files"] = loaded
    next_result["active_memory_results"] = {
        "selected_count": len(list(retrieval.get("selected") or [])),
        "selected": list(retrieval.get("selected") or []),
        "errors": errors,
    }
    if errors:
        missing = list(next_result.get("missing_files") or [])
        missing.extend({"path": f"__active_memory__:{err.get('lane_name')}", "error": err.get("error")} for err in errors)
        next_result["missing_files"] = missing
    next_result["matched"] = bool(_safe_text(next_result.get("text")) or next_result.get("lane_names"))
    return next_result


def _format_elapsed_text(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs and not parts:
        parts.append(f"{secs}s")
    return " ".join(parts) if parts else "0s"


def _load_skills_prompt(skill_names: list[str], *, task_id: str | None = None) -> tuple[str, list[str], list[str]]:
    normalized_names = _normalize_lines(skill_names)
    if not normalized_names:
        return "", [], []
    try:
        from agent.skill_commands import build_preloaded_skills_prompt

        return build_preloaded_skills_prompt(normalized_names, task_id=task_id)
    except Exception:
        logger.warning("memory plugin: failed to load configured skills", exc_info=True)
        return "", [], normalized_names


def _render_injection_text(
    matched_lanes: list[dict[str, Any]],
    loaded_files: list[dict[str, Any]],
    *,
    session_id: str | None = None,
    include_skills: bool = True,
) -> str:
    if not matched_lanes:
        return ""
    sections: list[str] = []
    for lane in matched_lanes:
        prompt_text = str(lane.get("prompt") or "").strip()
        if not prompt_text:
            continue
        lane_name = str(lane.get("name") or "unknown")
        sections.append(f"[Memory behavior prompt: {lane_name}]\n{prompt_text}")
    if include_skills:
        for lane in matched_lanes:
            skill_names = _normalize_lines(list(lane.get("skills") or []))
            if not skill_names:
                continue
            lane_name = str(lane.get("name") or "unknown")
            skills_prompt, loaded_skills, missing_skills = _load_skills_prompt(skill_names, task_id=session_id)
            if loaded_skills:
                sections.append(f"[Memory lane skills: {lane_name} · {', '.join(loaded_skills)}]\n{skills_prompt}")
            if missing_skills:
                sections.append(f"[Memory lane missing skills: {lane_name}]\n{', '.join(missing_skills)}")
    for item in loaded_files:
        content = str(item.get("content") or "")
        if not content.strip():
            continue
        if item.get("kind") == "current_time":
            sections.append(content)
        elif item.get("kind") == "current_source":
            sections.append(content)
        else:
            sections.append(f"[Memory snapshot: {item['path']}]\n{content}")
    return "\n\n".join(sections).strip()


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
    file_results = [_read_snapshot_text(path_text) for path_text in ordered_paths]
    loaded_files = [item for item in file_results if item.get("content")]
    loaded_entries = loaded_files
    missing_files = [item for item in file_results if item.get("error")]
    text = _render_injection_text([normalized_lane], loaded_entries, include_skills=False)
    active_memory_directory = _safe_text(normalized_lane.get("active_memory_directory"))
    return {
        "lane_name": str(normalized_lane.get("name") or ""),
        "text": text,
        "excerpt": _truncate_preview_text(text),
        "has_preview": bool(text),
        "snapshot_files": ordered_paths,
        "active_memory_directory": active_memory_directory,
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
    matched_result = resolve_memory_injection(config, session_key, source)
    effective_session_key = _safe_text(matched_result.get("session_key") or session_key)
    matched_lanes = list(matched_result.get("lanes") or [])
    matched_intervals = sorted(
        {
            _normalize_reinject_interval_minutes(lane.get("reinject_interval_minutes"))
            for lane in matched_lanes
        }
    )
    state = load_state()
    session_runtime = _session_runtime_entry(state, effective_session_key) if effective_session_key else {}
    lane_runtime = session_runtime.get("__pre_call_lanes__") if isinstance(session_runtime, dict) else {}
    if not isinstance(lane_runtime, dict):
        lane_runtime = {}
    now_dt = datetime.now(timezone.utc).astimezone()
    lane_decisions: list[dict[str, Any]] = []
    selected_lanes: list[dict[str, Any]] = []

    for index, lane in enumerate(matched_lanes):
        lane_name = _safe_text(lane.get("name") or "") or f"lane-{index}"
        interval = _normalize_reinject_interval_minutes(lane.get("reinject_interval_minutes"))
        lane_result = resolve_memory_injection({"lanes": [lane]}, effective_session_key, source)
        previous = lane_runtime.get(lane_name)
        previous = previous if isinstance(previous, dict) else {}
        last_injected_at = _safe_text(previous.get("last_injected_at") or "")
        last_injected_dt = _parse_iso_datetime(last_injected_at)
        elapsed_minutes = None
        if last_injected_dt is not None:
            elapsed_minutes = max(0.0, (now_dt - last_injected_dt).total_seconds() / 60.0)

        lane_should_inject = False
        decision_reason = "no_context"
        if lane_result.get("matched"):
            if is_new_session:
                lane_should_inject = True
                decision_reason = "new_session"
            elif interval <= 0:
                lane_should_inject = True
                decision_reason = "interval_zero_always"
            elif not effective_session_key:
                decision_reason = "missing_session_key"
            elif not last_injected_at:
                lane_should_inject = True
                decision_reason = "initial_lane"
            elif elapsed_minutes is not None and elapsed_minutes >= float(interval):
                lane_should_inject = True
                decision_reason = "interval_elapsed"
            else:
                decision_reason = "interval_not_elapsed"
        lane_decisions.append({
            "lane_name": lane_name,
            "should_inject": lane_should_inject,
            "decision_reason": decision_reason,
            "reinject_interval_minutes": interval,
            "last_injected_at": last_injected_at or None,
            "elapsed_minutes": elapsed_minutes,
        })
        if lane_should_inject:
            selected_lanes.append(lane)

    selected_result = (
        resolve_memory_injection({"lanes": selected_lanes}, effective_session_key, source)
        if selected_lanes
        else matched_result
    )
    selected_decisions = [item for item in lane_decisions if item["should_inject"]]
    should_inject = bool(selected_decisions and selected_result.get("matched"))
    if not matched_lanes:
        decision_reason = "no_match"
    elif not selected_decisions:
        decision_reason = "no_lane_due"
    elif len(selected_decisions) == 1:
        decision_reason = str(selected_decisions[0]["decision_reason"])
    else:
        decision_reason = "per_lane_due"
    selected_lane_names = [str(item["lane_name"]) for item in selected_decisions]
    selected_intervals = [int(item["reinject_interval_minutes"]) for item in selected_decisions]

    return {
        "result": selected_result,
        "matched_result": matched_result,
        "session_key": effective_session_key,
        "session_id": _safe_text(session_id or ""),
        "is_new_session": bool(is_new_session),
        "should_inject": should_inject,
        "decision_reason": decision_reason,
        "reinject_interval_minutes": min(selected_intervals) if selected_intervals else None,
        "matched_reinject_intervals": matched_intervals,
        "selected_lane_names": selected_lane_names,
        "lane_decisions": lane_decisions,
        "last_injected_at": _safe_text(session_runtime.get("last_injected_at") or "") or None,
        "elapsed_minutes": None,
    }


def resolve_memory_injection(config: dict[str, Any], session_key: str, source: Any, *, session_gap: dict[str, Any] | None = None) -> dict[str, Any]:
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
    file_results = [_read_snapshot_text(path_text) for path_text in ordered_paths]
    loaded_files = [item for item in file_results if item.get("content")]
    loaded_entries = loaded_files
    missing_files = [item for item in file_results if item.get("error")]
    text = _render_injection_text(matched_lanes, loaded_entries, session_id=None)
    active_memory_directories = [
        {"lane_name": str(lane.get("name") or ""), "directory": _safe_text(lane.get("active_memory_directory"))}
        for lane in matched_lanes
        if _safe_text(lane.get("active_memory_directory"))
    ]
    session_aliases = sorted(_session_selector_aliases(effective_session_key, source))
    active_profile = _active_profile_name()
    return {
        "matched": bool(text or active_memory_directories),
        "session_key": effective_session_key,
        "active_profile": active_profile,
        "lane_names": [str(lane.get("name") or "") for lane in matched_lanes],
        "lane_prompts": [
            {
                "name": str(lane.get("name") or ""),
                "prompt": str(lane.get("prompt") or ""),
            }
            for lane in matched_lanes
            if str(lane.get("prompt") or "").strip()
        ],
        "lane_skills": [
            {
                "name": str(lane.get("name") or ""),
                "skills": list(lane.get("skills") or []),
            }
            for lane in matched_lanes
            if list(lane.get("skills") or [])
        ],
        "lanes": matched_lanes,
        "selector_aliases": {
            "session": session_aliases,
        },
        "snapshot_files": ordered_paths,
        "active_memory_directories": active_memory_directories,
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
            pre_call_lanes = session_runtime.get("__pre_call_lanes__")
            if not isinstance(pre_call_lanes, dict):
                pre_call_lanes = {}
                session_runtime["__pre_call_lanes__"] = pre_call_lanes
            for lane_decision in list(policy.get("lane_decisions") or []):
                if not isinstance(lane_decision, dict) or not lane_decision.get("should_inject"):
                    continue
                lane_name = _safe_text(lane_decision.get("lane_name") or "")
                if not lane_name:
                    continue
                lane_state = pre_call_lanes.get(lane_name)
                if not isinstance(lane_state, dict):
                    lane_state = {}
                    pre_call_lanes[lane_name] = lane_state
                lane_state["last_injected_at"] = now
                lane_state["last_decision_reason"] = lane_decision.get("decision_reason")
                lane_state["reinject_interval_minutes"] = int(lane_decision.get("reinject_interval_minutes") or 0)
            if policy.get("decision_reason") == "pre_call_memory":
                session_runtime["last_injected_mode"] = "pre_call_memory"
            else:
                session_runtime["last_injected_mode"] = "session_open" if policy.get("is_new_session") else "interval"
    state["last_resolution"] = {
        "matched": bool(result.get("matched")),
        "session_key": result.get("session_key"),
        "active_profile": result.get("active_profile"),
        "lane_names": list(result.get("lane_names") or []),
        "selected_lane_names": list(policy.get("selected_lane_names") or []),
        "lane_decisions": list(policy.get("lane_decisions") or []),
        "lane_prompts": list(result.get("lane_prompts") or []),
        "lane_skills": list(result.get("lane_skills") or []),
        "snapshot_files": list(result.get("snapshot_files") or []),
        "active_memory_directories": list(result.get("active_memory_directories") or []),
        "active_memory_results": dict(result.get("active_memory_results") or {}),
        "loaded_files": list(result.get("loaded_files") or []),
        "missing_files": list(result.get("missing_files") or []),
        "decision_reason": policy.get("decision_reason"),
        "should_inject": bool(policy.get("should_inject")),
        "reinject_interval_minutes": int(policy.get("reinject_interval_minutes") or 0),
        "elapsed_minutes": policy.get("elapsed_minutes"),
    }
    save_state(state)
    return state


def _memory_observability_summary(config: dict[str, Any], state: dict[str, Any], lane_runtime: dict[str, Any] | None = None) -> dict[str, int]:
    lanes = [lane for lane in list(config.get("lanes") or []) if isinstance(lane, dict)]
    runtime = state.get("session_runtime")
    session_count = len([key for key, value in runtime.items() if isinstance(key, str) and isinstance(value, dict)]) if isinstance(runtime, dict) else 0
    tracked_lanes = set(str(name) for name in (lane_runtime or {}).keys() if str(name))
    return {
        "enabled_lanes": sum(1 for lane in lanes if bool(lane.get("enabled", True))),
        "tracked": len(tracked_lanes),
        "sessions": session_count,
        "disabled": sum(1 for lane in lanes if not bool(lane.get("enabled", True))),
    }


def _memory_lane_runtime_summary(state: dict[str, Any]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    runtime = state.get("session_runtime")
    if not isinstance(runtime, dict):
        return summaries
    now_dt = datetime.now(timezone.utc)

    def ensure_summary(lane_name: str) -> dict[str, Any]:
        return summaries.setdefault(
            lane_name,
            {
                "lane_name": lane_name,
                "matched_session_count": 0,
                "last_applied_at": None,
                "last_injected_at": None,
                "last_applied_minutes_ago": None,
                "last_attempt_at": None,
                "last_decision_reason": None,
                "last_session_key": None,
                "last_session_id": None,
                "last_source": None,
            },
        )

    def maybe_update_latest(summary: dict[str, Any], *, applied_at: Any, session_key: str, session_state: dict[str, Any], lane_state: dict[str, Any] | None = None) -> None:
        applied_dt = _parse_iso_datetime(applied_at)
        current_best = _parse_iso_datetime(summary.get("last_applied_at"))
        if applied_dt is None or (current_best is not None and applied_dt < current_best):
            return
        summary["last_applied_at"] = _safe_text(applied_at) or None
        summary["last_injected_at"] = _safe_text(applied_at) or None
        summary["last_applied_minutes_ago"] = max(0, int((now_dt - applied_dt.astimezone(timezone.utc)).total_seconds() // 60))
        summary["last_session_key"] = session_key
        summary["last_session_id"] = session_state.get("session_id")
        if lane_state is not None:
            summary["last_attempt_at"] = lane_state.get("last_attempt_at") or applied_at
            summary["last_decision_reason"] = lane_state.get("last_decision_reason") or session_state.get("last_decision_reason")
            summary["last_source"] = {
                "platform": lane_state.get("platform"),
                "chat_id": lane_state.get("chat_id"),
                "thread_id": lane_state.get("thread_id"),
            }
        else:
            summary["last_attempt_at"] = session_state.get("last_resolved_at") or applied_at
            summary["last_decision_reason"] = session_state.get("last_decision_reason")
            summary["last_source"] = None

    for session_key, session_state in runtime.items():
        if not isinstance(session_key, str) or not isinstance(session_state, dict):
            continue

        # Pre-call injection records lane names directly on the session state.
        # This is the common path for memory, so surface it in the dashboard list.
        injected_at = session_state.get("last_injected_at")
        for raw_lane_name in list(session_state.get("lane_names") or []):
            lane_name = _safe_text(raw_lane_name)
            if not lane_name:
                continue
            summary = ensure_summary(lane_name)
            summary["matched_session_count"] = int(summary.get("matched_session_count") or 0) + 1
            maybe_update_latest(summary, applied_at=injected_at, session_key=session_key, session_state=session_state)

        # Legacy/tick lane state still carries richer per-lane details.
        lanes = session_state.get("__lanes__")
        if not isinstance(lanes, dict):
            continue
        for lane_name, lane_state in lanes.items():
            if not isinstance(lane_name, str) or not isinstance(lane_state, dict):
                continue
            summary = ensure_summary(lane_name)
            if lane_name not in list(session_state.get("lane_names") or []):
                summary["matched_session_count"] = int(summary.get("matched_session_count") or 0) + 1
            maybe_update_latest(
                summary,
                applied_at=lane_state.get("last_applied_at"),
                session_key=session_key,
                session_state=session_state,
                lane_state=lane_state,
            )
    return summaries



def _dispatch_internal_control(args: dict[str, Any]) -> dict[str, Any]:
    """Route dashboard-only operations to Memory's internal control module."""
    from hermes_plugins.memory import control

    action = _safe_text(args.get("action"))
    if action == "get_config":
        return control.get_config()
    if action == "put_config":
        return control.put_config(args.get("config"))
    if action == "patch_lane":
        return control.patch_lane(args.get("lane_name"), args.get("changes"))
    if action == "resolve":
        return control.resolve(args.get("payload"))
    raise HTTPException(status_code=400, detail=f"unknown internal memory action: {action}")


@router.get("/config")
async def get_config() -> dict[str, Any]:
    return _dispatch_internal_control({"action": "get_config"})


@router.put("/config")
async def put_config(payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
    return _dispatch_internal_control({"action": "put_config", "config": payload})


@router.post("/resolve")
async def resolve_configured_memory(payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
    return _dispatch_internal_control({"action": "resolve", "payload": payload})
