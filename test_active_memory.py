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
    assert "weather.md" not in result["entries"][0]["content"]


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
    assert "base context" in rendered
    assert "[Active memory]" in rendered


if __name__ == "__main__":
    import tempfile

    test_normalize_lane_replaces_pre_context_command_with_active_memory_directory()
    with tempfile.TemporaryDirectory() as temp:
        test_active_memory_retrieval_selects_relevant_markdown_and_ignores_unrelated(Path(temp))
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
    test_append_active_memory_results_adds_soft_context()
    test_pre_call_hook_uses_current_message_as_query()
    print("memory active-memory tests ok")
