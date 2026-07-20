from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

sys.path.insert(0, "/opt/hermes")


class _Router:
    def get(self, *_args, **_kwargs):
        return lambda func: func

    put = get
    post = get
    delete = get


fastapi = types.ModuleType("fastapi")
setattr(fastapi, "APIRouter", _Router)
setattr(fastapi, "HTTPException", RuntimeError)
sys.modules.setdefault("fastapi", fastapi)


MODULE_PATH = Path(__file__).parent / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("memory_plugin_api_test", MODULE_PATH)
assert spec and spec.loader
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

runtime_spec = importlib.util.spec_from_file_location("memory_runtime_tick_test", Path(__file__).parent / "runtime_tick.py")
assert runtime_spec and runtime_spec.loader
runtime_tick = importlib.util.module_from_spec(runtime_spec)
runtime_spec.loader.exec_module(runtime_tick)


def test_normalize_lane_replaces_pre_context_command_with_active_memory_directory():
    lane = api._normalize_lane({
        "name": "casual",
        "pre_context_command": "legacy-command",
        "pre_context_timeout_seconds": 9,
        "active_memory_directory": "workspace/notes/LIN",
    })

    assert lane["active_memory_directory"] == "workspace/notes/LIN"
    assert "pre_context_command" not in lane
    assert "pre_context_timeout_seconds" not in lane


def test_zero_interval_lane_injects_independently_of_a_throttled_lane():
    original_load_state = api.load_state
    now = api.now_iso()
    setattr(api, "load_state", lambda: {
        "session_runtime": {
            "dm": {
                "__pre_call_lanes__": {
                    "casual": {"last_injected_at": now},
                    "all": {"last_injected_at": now},
                },
            },
        },
    })
    try:
        policy = api.resolve_memory_injection_policy(
            {
                "lanes": [
                    {
                        "name": "casual",
                        "enabled": True,
                        "target_sessions": ["dm"],
                        "include_current_time": True,
                        "snapshot_files": ["state/STATUS.md"],
                        "reinject_interval_minutes": 30,
                    },
                    {
                        "name": "all",
                        "enabled": True,
                        "target_sessions": [],
                        "prompt": "all memory",
                        "reinject_interval_minutes": 0,
                    },
                ],
            },
            "dm",
            {"platform": "discord", "chat_id": "dm"},
        )
    finally:
        setattr(api, "load_state", original_load_state)

    assert policy["matched_reinject_intervals"] == [0, 30]
    assert policy["selected_lane_names"] == ["all"]
    assert policy["result"]["lane_names"] == ["all"]
    assert policy["result"]["snapshot_files"] == []
    assert policy["should_inject"] is True
    assert [
        {key: item[key] for key in ("lane_name", "should_inject", "decision_reason", "reinject_interval_minutes")}
        for item in policy["lane_decisions"]
    ] == [
        {"lane_name": "casual", "should_inject": False, "decision_reason": "interval_not_elapsed", "reinject_interval_minutes": 30},
        {"lane_name": "all", "should_inject": True, "decision_reason": "interval_zero_always", "reinject_interval_minutes": 0},
    ]


def test_update_resolution_state_records_only_lanes_injected_this_call():
    original_load_state = api.load_state
    original_save_state = api.save_state
    state = {"session_runtime": {"dm": {}}}
    setattr(api, "load_state", lambda: state)
    setattr(api, "save_state", lambda _state: None)
    try:
        api.update_memory_resolution_state(
            {
                "session_key": "dm",
                "should_inject": True,
                "decision_reason": "interval_zero_always",
                "lane_decisions": [
                    {"lane_name": "casual", "should_inject": False, "reinject_interval_minutes": 30},
                    {"lane_name": "all", "should_inject": True, "decision_reason": "interval_zero_always", "reinject_interval_minutes": 0},
                ],
                "result": {"matched": True, "session_key": "dm", "lane_names": ["all"]},
            },
            injected=True,
        )
    finally:
        setattr(api, "load_state", original_load_state)
        setattr(api, "save_state", original_save_state)

    lane_state = state["session_runtime"]["dm"]["__pre_call_lanes__"]
    assert set(lane_state) == {"all"}
    assert lane_state["all"]["reinject_interval_minutes"] == 0


def test_current_time_entry_marks_time_as_accurate():
    entry = api._current_time_entry()

    assert entry["kind"] == "current_time"
    assert "This is the accurate current time." in entry["content"]
    assert "Asia/Tokyo" in entry["content"]


def test_active_memory_retrieval_selects_relevant_markdown_and_ignores_unrelated(tmp_path: Path):
    notes = tmp_path / "workspace" / "notes"
    notes.mkdir(parents=True)
    original_home = api.get_hermes_home
    setattr(api, "get_hermes_home", lambda: tmp_path)
    (notes / "memory.md").write_text(
        "# Active Memory\n\n会話の話題に応じて必要なノートだけを返答前に思い出す仕組み。\n",
        encoding="utf-8",
    )
    (notes / "weather.md").write_text(
        "# Weather\n\n明日の天気と降水確率を記録する。\n",
        encoding="utf-8",
    )

    result = api.run_active_memory_retrieval(
        [{"name": "casual", "active_memory_directory": "workspace/notes"}],
        query="アクティブメモリーはどうやって必要なノートを思い出す？",
    )
    setattr(api, "get_hermes_home", original_home)

    assert result["selected"]
    assert result["selected"][0]["path"].endswith("memory.md")
    assert "Active Memory" in result["entries"][0]["content"]
    assert "read_active_memory(path=<shown path>)" in result["entries"][0]["content"]
    assert "weather.md" not in result["entries"][0]["content"]


def test_active_memory_retrieval_limits_each_lane_to_two_100_character_frontmatter_excerpts(tmp_path: Path):
    notes = tmp_path / "workspace" / "notes"
    notes.mkdir(parents=True)
    original_home = api.get_hermes_home
    setattr(api, "get_hermes_home", lambda: tmp_path)
    try:
        for name in ("a", "b", "c"):
            (notes / f"{name}.md").write_text(
                f"---\ntags: [needle]\n---\nneedle {name} " + ("x" * 180),
                encoding="utf-8",
            )
        result = api.run_active_memory_retrieval(
            [{"name": "active", "active_memory_directory": "workspace/notes"}],
            query="needle",
        )
    finally:
        setattr(api, "get_hermes_home", original_home)

    assert len(result["selected"]) == 2
    assert all(len(item["excerpt"]) == 100 for item in result["selected"])
    assert "excerpt=--- tags: [needle] --- needle a" in result["entries"][0]["content"]
    assert "c.md" not in result["entries"][0]["content"]


def test_active_memory_retrieval_is_empty_for_blank_query_or_missing_directory(tmp_path: Path):
    original_home = api.get_hermes_home
    setattr(api, "get_hermes_home", lambda: tmp_path)
    lane = {"name": "casual", "active_memory_directory": "workspace/notes/missing"}

    assert api.run_active_memory_retrieval([lane], query="")["entries"] == []
    result = api.run_active_memory_retrieval([lane], query="memory")
    setattr(api, "get_hermes_home", original_home)
    assert result["entries"] == []
    assert result["errors"][0]["error"] == "directory_missing"


def test_active_memory_ignores_generic_japanese_phrase_overlap(tmp_path: Path):
    notes = tmp_path / "workspace" / "notes"
    notes.mkdir(parents=True)
    original_home = api.get_hermes_home
    setattr(api, "get_hermes_home", lambda: tmp_path)
    (notes / "generic.md").write_text(
        "# 雑記\n\nこれは発動する感じではないでいいんだよね。\n",
        encoding="utf-8",
    )
    (notes / "restart.md").write_text("# 運用\n\n再起動手順。\n", encoding="utf-8")
    result = api.run_active_memory_retrieval(
        [{"name": "active", "active_memory_directory": "workspace/notes"}],
        query="再起動した。アクティブメモリーは発動する感じではないでいいんだよね",
    )
    setattr(api, "get_hermes_home", original_home)
    assert result["selected"] == []


def test_active_memory_retrieval_supports_hiragana_topic(tmp_path: Path):
    notes = tmp_path / "workspace" / "notes"
    notes.mkdir(parents=True)
    original_home = api.get_hermes_home
    setattr(api, "get_hermes_home", lambda: tmp_path)
    try:
        (notes / "sleep.md").write_text("# 眠り\n\nおやすみ前の静かな習慣。\n", encoding="utf-8")
        (notes / "noise.md").write_text("# 天気\n\n明日の降水確率。\n", encoding="utf-8")
        result = api.run_active_memory_retrieval(
            [{"name": "active", "active_memory_directory": "workspace/notes"}],
            query="おやすみ",
        )
    finally:
        setattr(api, "get_hermes_home", original_home)
    assert result["selected"]
    assert result["selected"][0]["path"].endswith("sleep.md")
    assert "noise.md" not in result["entries"][0]["content"]


def test_active_memory_retrieval_allows_single_specific_term(tmp_path: Path):
    notes = tmp_path / "workspace" / "notes"
    notes.mkdir(parents=True)
    original_home = api.get_hermes_home
    setattr(api, "get_hermes_home", lambda: tmp_path)
    try:
        (notes / "restart.md").write_text("# 運用\n\nHermes の再起動手順。\n", encoding="utf-8")
        result = api.run_active_memory_retrieval(
            [{"name": "active", "active_memory_directory": "workspace/notes"}],
            query="再起動",
        )
    finally:
        setattr(api, "get_hermes_home", original_home)
    assert result["selected"]
    assert result["selected"][0]["path"].endswith("restart.md")


def test_active_memory_cache_refreshes_after_note_edit(tmp_path: Path):
    notes = tmp_path / "workspace" / "notes"
    notes.mkdir(parents=True)
    note = notes / "cache.md"
    original_home = api.get_hermes_home
    setattr(api, "get_hermes_home", lambda: tmp_path)
    try:
        note.write_text("# Cache\n\nAlphaTopic のメモ。\n", encoding="utf-8")
        lane = {"name": "active", "active_memory_directory": "workspace/notes"}
        assert api.run_active_memory_retrieval([lane], query="AlphaTopic")["selected"]
        note.write_text("# Cache\n\nBetaTopic の更新済みメモです。\n", encoding="utf-8")
        assert api.run_active_memory_retrieval([lane], query="BetaTopic")["selected"]
        assert api.run_active_memory_retrieval([lane], query="AlphaTopic")["selected"] == []
    finally:
        setattr(api, "get_hermes_home", original_home)


def test_active_memory_directory_rejects_absolute_and_escape_paths():
    for directory in ("/tmp", "workspace/notes/../../secrets"):
        result = api.run_active_memory_retrieval(
            [{"name": "casual", "active_memory_directory": directory}],
            query="secret memory",
        )
        assert result["entries"] == []
        assert result["errors"][0]["error"] == "directory_outside_notes_root"


def test_record_active_memory_retrieval_keeps_only_notes_paths(tmp_path: Path):
    notes = tmp_path / "workspace" / "notes"
    notes.mkdir(parents=True)
    selected = notes / "selected.md"
    selected.write_text("selected", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    original_home = api.get_hermes_home
    api.get_hermes_home = lambda: tmp_path
    try:
        api.record_active_memory_retrieval("session", {
            "selected": [{"path": str(selected)}, {"path": str(outside)}],
        })
        state = api.load_state()
        first_retrieval = state["last_active_memory_retrieval"]
        api.record_active_memory_retrieval("session", {"selected": []})
        cleared_retrieval = api.load_state()["last_active_memory_retrieval"]
    finally:
        api.get_hermes_home = original_home

    retrieval = first_retrieval
    assert retrieval["session_key"] == "session"
    assert retrieval["selected"] == [{"path": str(selected)}]
    assert cleared_retrieval["selected"] == []


def test_read_active_memory_result_reads_only_a_last_selected_note(tmp_path: Path):
    import json
    import types

    package = types.ModuleType("hermes_plugins")
    package.__path__ = []
    sys.modules.setdefault("hermes_plugins", package)
    package_spec = importlib.util.spec_from_file_location(
        "hermes_plugins.memory",
        Path(__file__).parent / "__init__.py",
        submodule_search_locations=[str(Path(__file__).parent)],
    )
    assert package_spec and package_spec.loader
    memory_package = importlib.util.module_from_spec(package_spec)
    sys.modules["hermes_plugins.memory"] = memory_package
    package_spec.loader.exec_module(memory_package)
    from hermes_plugins.memory import control

    notes = tmp_path / "workspace" / "notes"
    notes.mkdir(parents=True)
    selected = notes / "selected.md"
    selected.write_text("# Selected\n\n" + ("x" * 12_001), encoding="utf-8")
    ignored = notes / "ignored.md"
    ignored.write_text("# Ignored\n\nshould not be readable", encoding="utf-8")

    original_home = control.api.get_hermes_home
    control.api.get_hermes_home = lambda: tmp_path
    try:
        state_path = control.api.state_path()
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps({
            "last_active_memory_retrieval": {
                "selected": [{"path": str(selected)}],
            },
        }), encoding="utf-8")

        original_read_text = control.Path.read_text

        def reject_full_selected_read(path, *args, **kwargs):
            if path.resolve(strict=False) == selected.resolve(strict=False):
                raise AssertionError("selected note must be read with a bounded stream")
            return original_read_text(path, *args, **kwargs)

        control.Path.read_text = reject_full_selected_read
        try:
            result = control.read_active_memory_result(str(selected))
        finally:
            control.Path.read_text = original_read_text
        rejected = control.read_active_memory_result(str(ignored))
    finally:
        control.api.get_hermes_home = original_home

    assert result["path"] == str(selected)
    assert result["content"] == "# Selected\n\n" + ("x" * 11_988)
    assert result["chars"] == 12_000
    assert result["truncated"] is True
    assert rejected["error"] == "path_not_selected"


def test_patch_lane_updates_only_requested_active_memory_fields(tmp_path: Path):
    import json
    import types

    package = types.ModuleType("hermes_plugins")
    package.__path__ = []
    sys.modules.setdefault("hermes_plugins", package)
    package_spec = importlib.util.spec_from_file_location(
        "hermes_plugins.memory",
        Path(__file__).parent / "__init__.py",
        submodule_search_locations=[str(Path(__file__).parent)],
    )
    assert package_spec and package_spec.loader
    memory_package = importlib.util.module_from_spec(package_spec)
    sys.modules["hermes_plugins.memory"] = memory_package
    package_spec.loader.exec_module(memory_package)
    from hermes_plugins.memory import control

    original_home = control.api.get_hermes_home
    control.api.get_hermes_home = lambda: tmp_path
    try:
        control.api.config_path().parent.mkdir(parents=True)
        control.api.config_path().write_text(json.dumps({"lanes": [
            {"name": "all", "enabled": True, "active_memory_directory": "workspace/notes", "snapshot_files": ["state/STATUS.md"]},
            {"name": "casual", "enabled": True, "active_memory_directory": "", "target_sessions": ["session-a"]},
        ]}), encoding="utf-8")

        result = control.patch_lane("all", {
            "active_memory_directory": "workspace/notes/research",
            "enabled": False,
        })
        config = control.api.load_config()
    finally:
        control.api.get_hermes_home = original_home

    updated = next(lane for lane in config["lanes"] if lane["name"] == "all")
    untouched = next(lane for lane in config["lanes"] if lane["name"] == "casual")
    assert result["updated_lane"] == "all"
    assert updated["active_memory_directory"] == "workspace/notes/research"
    assert updated["enabled"] is False
    assert updated["snapshot_files"] == ["state/STATUS.md"]
    assert untouched["target_sessions"] == ["session-a"]


def test_patch_lane_rejects_unknown_lanes_and_fields(tmp_path: Path):
    import json
    import types

    package = types.ModuleType("hermes_plugins")
    package.__path__ = []
    sys.modules.setdefault("hermes_plugins", package)
    package_spec = importlib.util.spec_from_file_location(
        "hermes_plugins.memory",
        Path(__file__).parent / "__init__.py",
        submodule_search_locations=[str(Path(__file__).parent)],
    )
    assert package_spec and package_spec.loader
    memory_package = importlib.util.module_from_spec(package_spec)
    sys.modules["hermes_plugins.memory"] = memory_package
    package_spec.loader.exec_module(memory_package)
    from hermes_plugins.memory import control

    original_home = control.api.get_hermes_home
    control.api.get_hermes_home = lambda: tmp_path
    try:
        control.api.config_path().parent.mkdir(parents=True)
        control.api.config_path().write_text(json.dumps({"lanes": [{"name": "all"}]}), encoding="utf-8")
        missing = control.patch_lane("missing", {"enabled": False})
        invalid = control.patch_lane("all", {"unknown": "nope"})
        unsafe_directory = control.patch_lane("all", {"active_memory_directory": "/tmp"})
        config = control.api.load_config()
    finally:
        control.api.get_hermes_home = original_home

    assert missing == {"error": "lane_not_found"}
    assert invalid == {"error": "unsupported_lane_fields", "fields": ["unknown"]}
    assert unsafe_directory == {"error": "active_memory_directory_invalid"}
    assert config["lanes"][0]["enabled"] is True


def test_dashboard_internal_control_dispatches_patch_lane():
    import types

    package = types.ModuleType("hermes_plugins")
    package.__path__ = []
    sys.modules.setdefault("hermes_plugins", package)
    package_spec = importlib.util.spec_from_file_location(
        "hermes_plugins.memory",
        Path(__file__).parent / "__init__.py",
        submodule_search_locations=[str(Path(__file__).parent)],
    )
    assert package_spec and package_spec.loader
    memory_package = importlib.util.module_from_spec(package_spec)
    sys.modules["hermes_plugins.memory"] = memory_package
    package_spec.loader.exec_module(memory_package)
    from hermes_plugins.memory import control

    original_patch_lane = control.patch_lane
    captured = {}
    control.patch_lane = lambda lane_name, changes: captured.update({
        "lane_name": lane_name,
        "changes": changes,
    }) or {"updated_lane": lane_name}
    try:
        result = api._dispatch_internal_control({
            "action": "patch_lane",
            "lane_name": "all",
            "changes": {"active_memory_directory": "workspace/notes"},
        })
    finally:
        control.patch_lane = original_patch_lane

    assert captured == {
        "lane_name": "all",
        "changes": {"active_memory_directory": "workspace/notes"},
    }
    assert result == {"updated_lane": "all"}


def test_memory_registers_control_and_active_memory_tools():
    import types

    package = types.ModuleType("hermes_plugins")
    package.__path__ = []
    sys.modules.setdefault("hermes_plugins", package)
    package_spec = importlib.util.spec_from_file_location(
        "hermes_plugins.memory",
        Path(__file__).parent / "__init__.py",
        submodule_search_locations=[str(Path(__file__).parent)],
    )
    assert package_spec and package_spec.loader
    memory_package = importlib.util.module_from_spec(package_spec)
    sys.modules["hermes_plugins.memory"] = memory_package
    package_spec.loader.exec_module(memory_package)

    class FakeContext:
        tools = []

        def register_skill(self, *_args, **_kwargs):
            return None

        def register_tool(self, **kwargs):
            self.tools.append(kwargs)

    context = FakeContext()
    memory_package.register(context)
    tools = {tool["name"]: tool for tool in context.tools}

    assert set(tools) == {"memory_control", "read_active_memory", "memory_status"}
    assert tools["memory_control"]["schema"]["parameters"] == {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get_config", "put_config", "patch_lane", "resolve", "health"],
                "description": "get_config confirms configuration; put_config replaces it; patch_lane safely updates fields on one existing lane; resolve previews a session injection; health checks runtime state.",
            },
            "config": {
                "anyOf": [{"type": "object"}, {"type": "string"}, {"type": "null"}],
                "description": "Full Memory configuration payload for action=put_config.",
            },
            "lane_name": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "Existing lane name for action=patch_lane.",
            },
            "changes": {
                "anyOf": [{"type": "object"}, {"type": "string"}, {"type": "null"}],
                "description": "Partial allowed lane fields for action=patch_lane, such as active_memory_directory, enabled, selectors, or snapshot_files.",
            },
            "payload": {
                "anyOf": [{"type": "object"}, {"type": "string"}, {"type": "null"}],
                "description": "Session/source payload for action=resolve.",
            },
        },
        "additionalProperties": False,
    }
    assert tools["read_active_memory"]["schema"]["parameters"] == {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path returned by the latest active-memory selection.",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    }
    assert tools["memory_status"]["schema"]["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_append_active_memory_results_adds_soft_context():
    base = {"text": "Current time: now", "loaded_files": [], "missing_files": []}
    retrieval = {
        "entries": [{
            "path": "__active_memory__:casual",
            "content": "[Active memory]\n- Note\n[/Active memory]",
            "kind": "active_memory",
            "label": "Active memory: casual",
            "date": None,
        }],
        "selected": [{"path": "/tmp/Note.md", "score": 0.8}],
        "errors": [],
    }

    result = api.append_active_memory_results(base, retrieval)

    assert "[Active memory]" in result["text"]
    assert result["active_memory_results"]["selected_count"] == 1
    assert result["loaded_files"][0]["kind"] == "active_memory"


def test_pre_call_hook_uses_current_message_as_query():
    class FakeApi:
        captured_query = None
        recorded_retrieval = None

        @staticmethod
        def load_config():
            return {"lanes": []}

        @staticmethod
        def _safe_text(value):
            return str(value or "").strip()

        @staticmethod
        def _build_session_key_from_source(_source):
            return "session"

        @staticmethod
        def resolve_memory_injection_policy(*_args, **_kwargs):
            return {
                "should_inject": True,
                "session_key": "session",
                "result": {
                    "matched": True,
                    "lane_names": ["active-memory"],
                    "lanes": [{"name": "active-memory", "active_memory_directory": "notes"}],
                    "text": "",
                },
            }

        @classmethod
        def run_active_memory_retrieval(cls, _lanes, *, query):
            cls.captured_query = query
            return {
                "entries": [{"path": "__active_memory__:active-memory", "content": "[Active memory]\nalpha\n[/Active memory]", "kind": "active_memory"}],
                "selected": [{"path": "alpha.md"}],
                "errors": [],
            }

        @classmethod
        def record_active_memory_retrieval(cls, session_key, retrieval):
            cls.recorded_retrieval = (session_key, retrieval)

        append_active_memory_results = staticmethod(api.append_active_memory_results)

        @staticmethod
        def update_memory_resolution_state(_policy, *, injected):
            assert injected is True

    rendered = runtime_tick._with_pre_call_memory_context(
        FakeApi,
        runner=object(),
        message="alphaを思い出して",
        context_prompt="base context",
        session_key="session",
        session_id="id",
        source=None,
    )
    assert FakeApi.captured_query == "alphaを思い出して"
    assert FakeApi.recorded_retrieval == ("session", {"entries": [{"path": "__active_memory__:active-memory", "content": "[Active memory]\nalpha\n[/Active memory]", "kind": "active_memory"}], "selected": [{"path": "alpha.md"}], "errors": []})
    assert "base context" in rendered
    assert "[Active memory]" in rendered


if __name__ == "__main__":
    import tempfile

    test_normalize_lane_replaces_pre_context_command_with_active_memory_directory()
    test_zero_interval_lane_injects_independently_of_a_throttled_lane()
    test_update_resolution_state_records_only_lanes_injected_this_call()
    test_current_time_entry_marks_time_as_accurate()
    with tempfile.TemporaryDirectory() as temp:
        test_active_memory_retrieval_selects_relevant_markdown_and_ignores_unrelated(Path(temp))
    with tempfile.TemporaryDirectory() as temp:
        test_active_memory_retrieval_limits_each_lane_to_two_100_character_frontmatter_excerpts(Path(temp))
    with tempfile.TemporaryDirectory() as temp:
        test_active_memory_retrieval_is_empty_for_blank_query_or_missing_directory(Path(temp))
    with tempfile.TemporaryDirectory() as temp:
        test_active_memory_ignores_generic_japanese_phrase_overlap(Path(temp))
    with tempfile.TemporaryDirectory() as temp:
        test_active_memory_retrieval_supports_hiragana_topic(Path(temp))
    with tempfile.TemporaryDirectory() as temp:
        test_active_memory_retrieval_allows_single_specific_term(Path(temp))
    with tempfile.TemporaryDirectory() as temp:
        test_active_memory_cache_refreshes_after_note_edit(Path(temp))
    test_active_memory_directory_rejects_absolute_and_escape_paths()
    with tempfile.TemporaryDirectory() as temp:
        test_record_active_memory_retrieval_keeps_only_notes_paths(Path(temp))
    with tempfile.TemporaryDirectory() as temp:
        test_read_active_memory_result_reads_only_a_last_selected_note(Path(temp))
    with tempfile.TemporaryDirectory() as temp:
        test_patch_lane_updates_only_requested_active_memory_fields(Path(temp))
    with tempfile.TemporaryDirectory() as temp:
        test_patch_lane_rejects_unknown_lanes_and_fields(Path(temp))
    test_dashboard_internal_control_dispatches_patch_lane()
    test_memory_registers_control_and_active_memory_tools()
    test_append_active_memory_results_adds_soft_context()
    test_pre_call_hook_uses_current_message_as_query()
    print("memory active-memory tests ok")
