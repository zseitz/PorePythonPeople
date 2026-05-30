import importlib.util
import sys
import queue
from pathlib import Path
from types import SimpleNamespace

from nanoporethon.operator_assistant_gui import (
    OperatorAssistantGUI,
    _assistant_ui_palette,
    _render_markdown_to_text_widget,
    _activity_indicator_text,
    _activity_status_label,
    _classifier_health_check,
    _intent_badge_style,
    _style_assistant_button,
    _runtime_preflight_check,
    _resolve_repo_root,
)


def test_intent_badge_style_for_feature_request_is_explicit_and_green():
    text, color = _intent_badge_style("feature_request", 0.85)
    assert "Feature Request" in text
    assert "0.85" in text
    assert color == "#0a7d33"


def test_intent_badge_style_defaults_for_unknown_intent():
    text, color = _intent_badge_style("", 0.0)
    assert "Unknown" in text
    assert color == "#555555"


def test_intent_badge_style_for_nanopore_science_is_distinct():
    text, color = _intent_badge_style("nanopore_science_explanation", 0.77)
    assert "Nanopore Science Explanation" in text
    assert color == "#0b7285"


def test_classifier_health_check_healthy():
    policy = {
        "assistant_scope": {
            "domain_anchors": ["runtime", "nanoporethon"],
            "grounding_files": ["Docs/components.md"],
            "sensitive_domains": ["medical advice"],
        }
    }
    result = _classifier_health_check(policy)
    assert result["ok"] == "true"
    assert result["status"] == "healthy"


def test_classifier_health_check_missing_anchors():
    policy = {
        "assistant_scope": {
            "domain_anchors": [],
            "grounding_files": ["Docs/components.md"],
            "sensitive_domains": ["medical advice"],
        }
    }
    result = _classifier_health_check(policy)
    assert result["ok"] == "false"
    assert result["status"] == "config_error"


def test_classifier_health_check_missing_grounding_files():
    policy = {
        "assistant_scope": {
            "domain_anchors": ["runtime"],
            "grounding_files": [],
            "sensitive_domains": ["medical advice"],
        }
    }
    result = _classifier_health_check(policy)
    assert result["ok"] == "false"
    assert result["status"] == "config_error"


def test_classifier_health_check_missing_sensitive_domains():
    policy = {
        "assistant_scope": {
            "domain_anchors": ["runtime"],
            "grounding_files": ["Docs/components.md"],
            "sensitive_domains": [],
        }
    }
    result = _classifier_health_check(policy)
    assert result["ok"] == "false"
    assert result["status"] == "config_error"


def test_activity_indicator_runtime_cycles_dots():
    text_1, color_1 = _activity_indicator_text(runtime_running=True, assistant_processing=False, dot_phase=0)
    text_2, color_2 = _activity_indicator_text(runtime_running=True, assistant_processing=False, dot_phase=1)
    text_3, color_3 = _activity_indicator_text(runtime_running=True, assistant_processing=False, dot_phase=2)

    assert text_1.endswith(".")
    assert text_2.endswith("..")
    assert text_3.endswith("...")
    assert color_1 == "#1f4aa8"
    assert color_2 == "#1f4aa8"
    assert color_3 == "#1f4aa8"


def test_activity_indicator_assistant_processing_and_idle():
    processing_text, processing_color = _activity_indicator_text(
        runtime_running=False,
        assistant_processing=True,
        dot_phase=1,
    )
    idle_text, idle_color = _activity_indicator_text(
        runtime_running=False,
        assistant_processing=False,
        dot_phase=2,
    )

    assert "assistant is processing" in processing_text
    assert processing_text.endswith("..")
    assert processing_color == "#6a3dad"
    assert idle_text == "Activity: idle"
    assert idle_color == "#666666"


def test_activity_status_label_includes_last_ui_tick():
    label = _activity_status_label("Activity: runtime execution in progress..", "13:47:22")
    assert label == "Activity: runtime execution in progress.. (last UI tick: 13:47:22)"


def test_gui_chrome_palette_uses_clear_button_hierarchy():
    palette = _assistant_ui_palette(False)
    button = _FakeWidget()

    _style_assistant_button(button, palette, primary=True)

    assert button.kwargs["bg"] == palette["button_primary_bg"]
    assert button.kwargs["fg"] == palette["button_primary_fg"]
    assert button.kwargs["font"] == ("TkDefaultFont", 10, "bold")


def test_operator_assistant_gui_direct_file_import_succeeds_without_repo_root_on_syspath():
    module_path = Path(__file__).resolve().parents[1] / "src" / "nanoporethon" / "operator_assistant_gui.py"
    module_name = "_tmp_operator_assistant_gui_direct_import"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None

    original_syspath = list(sys.path)
    try:
        repo_root = str(Path(__file__).resolve().parents[1])
        sys.path = [p for p in sys.path if p and p != repo_root]
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path = original_syspath
        sys.modules.pop(module_name, None)

    assert hasattr(module, "run_gui")


def test_resolve_repo_root_finds_policy_from_non_repo_cwd(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    resolved = _resolve_repo_root(tmp_path, module_file=repo_root / "src" / "nanoporethon" / "operator_assistant_gui.py")
    assert resolved == repo_root


class _FakeVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class _FakeText:
    def __init__(self):
        self.state = None
        self.content = ""
        self.fg = None
        self.bg = None
        self.relief = None
        self.bd = None

    def config(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]
        if "fg" in kwargs:
            self.fg = kwargs["fg"]
        if "bg" in kwargs:
            self.bg = kwargs["bg"]
        if "relief" in kwargs:
            self.relief = kwargs["relief"]
        if "bd" in kwargs:
            self.bd = kwargs["bd"]

    def insert(self, _where, text):
        self.content += text

    def see(self, _where):
        return None

    def delete(self, _start, _end):
        self.content = ""


class _FakeEntry:
    def __init__(self, value="", **kwargs):
        self.value = value
        self.kwargs = dict(kwargs)
        self.bind_calls = []
        self.config_calls = []

    def get(self, *args):
        return self.value

    def delete(self, *args):
        self.value = ""

    def insert(self, _index, text):
        self.value += text

    def bind(self, *args, **kwargs):
        self.bind_calls.append((args, kwargs))

    def config(self, **kwargs):
        self.config_calls.append(kwargs)
        self.kwargs.update(kwargs)

    def set(self, value):
        self.value = value


class _FakeButton:
    def __init__(self):
        self.state = None
        self.kwargs = {}

    def config(self, **kwargs):
        self.kwargs.update(kwargs)
        if "state" in kwargs:
            self.state = kwargs["state"]


class _FakeWidget:
    def __init__(self):
        self.kwargs = {}

    def config(self, **kwargs):
        self.kwargs.update(kwargs)


class _FakeRoot:
    def __init__(self):
        self.after_calls = []

    def update_idletasks(self):
        return None

    def after(self, interval, callback):
        self.after_calls.append((interval, callback))


def _build_gui_stub():
    gui = OperatorAssistantGUI.__new__(OperatorAssistantGUI)
    gui.root = _FakeRoot()
    gui.chat_output = _FakeText()
    gui.followup_output = _FakeText()
    gui.preview_output = _FakeText()
    gui.timeline_output = _FakeText()
    gui.intent_badge_var = _FakeVar("Intent: Waiting for message")
    gui.intent_badge = _FakeText()
    gui.readiness_var = _FakeVar("Status: waiting")
    gui.activity_var = _FakeVar("Activity: idle")
    gui.activity_label = _FakeText()
    gui.chat_input = _FakeEntry("", height=4, wrap="word")
    gui.send_button = _FakeButton()
    gui.run_button = _FakeButton()
    gui.assistant = None
    gui.runtime_running = False
    gui.assistant_processing = False
    gui.activity_dot_phase = 0
    gui.activity_last_tick = 0.0
    gui.activity_last_ui_tick = "00:00:00"
    gui.runtime_queue = queue.Queue()
    gui.current_run_dir = None
    gui.current_run_id = None
    gui.run_watch_started_at = None
    gui.existing_runs = set()
    gui.events_line_cursor = 0
    gui.policy = {"runtime": {"run_root": ".nanopore-runtime/runs"}}
    gui.repo_root = Path(__file__).resolve().parents[1]
    gui.session_state = {}
    gui.latest_runtime_request = None
    gui.latest_ready_to_run = False
    return gui


class _CleanFeatureBranchManager:
    def __init__(self, repo_root, sandbox_root):
        self.repo_root = repo_root
        self.sandbox_root = sandbox_root

    def inspect_start_state(self, require_clean=True, recommend_feature_branch=False):
        return {
            "is_git_repo": True,
            "base_branch": "feature/test",
            "working_tree_clean": True,
            "warnings": [],
        }


class _MainBranchManager:
    def __init__(self, repo_root, sandbox_root):
        self.repo_root = repo_root
        self.sandbox_root = sandbox_root

    def inspect_start_state(self, require_clean=True, recommend_feature_branch=False):
        return {
            "is_git_repo": True,
            "base_branch": "main",
            "working_tree_clean": True,
            "warnings": [],
        }


class _DirtyRepoManager:
    def __init__(self, repo_root, sandbox_root):
        self.repo_root = repo_root
        self.sandbox_root = sandbox_root

    def inspect_start_state(self, require_clean=True, recommend_feature_branch=False):
        raise RuntimeError("working tree is not clean")


def test_runtime_preflight_check_passes_for_clean_feature_branch():
    policy = {
        "assistant_scope": {
            "runtime_preflight": {
                "require_clean_worktree": True,
                "require_feature_branch": True,
            }
        }
    }
    result = _runtime_preflight_check(
        policy,
        Path(__file__).resolve().parents[1],
        workspace_manager_factory=_CleanFeatureBranchManager,
    )
    assert result["ok"] == "true"
    assert result["status"] == "ready"


def test_runtime_preflight_check_blocks_main_branch_when_required():
    policy = {
        "assistant_scope": {
            "runtime_preflight": {
                "require_clean_worktree": True,
                "require_feature_branch": True,
            }
        }
    }
    result = _runtime_preflight_check(
        policy,
        Path(__file__).resolve().parents[1],
        workspace_manager_factory=_MainBranchManager,
    )
    assert result["ok"] == "false"
    assert result["status"] == "feature_branch_required"


def test_runtime_preflight_check_blocks_dirty_worktree_when_required():
    policy = {
        "assistant_scope": {
            "runtime_preflight": {
                "require_clean_worktree": True,
                "require_feature_branch": False,
            }
        }
    }
    result = _runtime_preflight_check(
        policy,
        Path(__file__).resolve().parents[1],
        workspace_manager_factory=_DirtyRepoManager,
    )
    assert result["ok"] == "false"
    assert result["status"] == "dirty_worktree"


def test_gui_logging_and_preview_helpers_update_widgets():
    gui = _build_gui_stub()
    gui._log_chat("assistant", "hello")
    assert "Assistant" in gui.chat_output.content
    assert "hello" in gui.chat_output.content

    gui._set_preview_text("request preview")
    assert "review my plan before hitting Run Latest Request" in gui.chat_output.content
    assert "request preview" in gui.chat_output.content

    gui._set_followups(["Q1", "Q2"])
    assert "I need to know these things first" in gui.chat_output.content
    assert "1. Q1" in gui.chat_output.content
    assert "2. Q2" in gui.chat_output.content

    gui._set_followups([])
    assert "No follow-up questions pending." not in gui.chat_output.content


def test_gui_chat_input_wraps_and_keeps_long_text_visible():
    gui = _build_gui_stub()
    assert gui.chat_input.kwargs["wrap"] == "word"
    assert gui.chat_input.kwargs.get("height") == 4

    long_text = "This is a long request that should wrap instead of disappearing off the edge of the chat box."
    gui.assistant = SimpleNamespace(
        handle_message=lambda _text, session=None: SimpleNamespace(
            intent="repo_question",
            confidence=0.5,
            message="ok",
            followup_questions=[],
            ready_to_run=False,
            runtime_request=None,
            session_updates={"history": []},
        )
    )
    gui.chat_input.set(long_text)
    gui._on_send_chat()

    assert long_text in gui.chat_output.content
    assert gui.chat_input.value == ""


def test_gui_chat_input_shift_enter_inserts_newline():
    gui = _build_gui_stub()
    gui.chat_input.set("hello")

    result = gui._insert_chat_newline()

    assert gui.chat_input.value == "hello\n"
    assert result == "break"


def test_gui_places_runtime_timeline_below_runtime_controls(monkeypatch):
    created = []

    class FakeWidget:
        def __init__(self, master=None, **kwargs):
            self.master = master
            self.kwargs = kwargs
            self.children = []
            self.pack_calls = []
            self.config_calls = []
            self.bind_calls = []
            self.content = ""
            if master is not None and hasattr(master, "children"):
                master.children.append(self)
            created.append(self)

        def pack(self, **kwargs):
            self.pack_calls.append(kwargs)

        def config(self, **kwargs):
            self.config_calls.append(kwargs)

        def bind(self, *args, **kwargs):
            self.bind_calls.append((args, kwargs))

        def cget(self, key):
            return self.kwargs.get(key, "#f8fafc")

        def see(self, _where):
            return None

        def delete(self, *_args, **_kwargs):
            self.content = ""

        def insert(self, _where, text):
            self.content += text

    class FakeRoot(FakeWidget):
        def __init__(self):
            super().__init__(None)
            self.after_calls = []

        def title(self, *_args, **_kwargs):
            return None

        def geometry(self, *_args, **_kwargs):
            return None

        def update_idletasks(self):
            return None

        def after(self, interval, callback):
            self.after_calls.append((interval, callback))

    class FakeVar:
        def __init__(self, value=None):
            self.value = value

        def set(self, value):
            self.value = value

        def get(self):
            return self.value

    monkeypatch.setattr("nanoporethon.operator_assistant_gui.tk.Frame", lambda master=None, **kwargs: FakeWidget(master, **kwargs))
    monkeypatch.setattr("nanoporethon.operator_assistant_gui.tk.LabelFrame", lambda master=None, **kwargs: FakeWidget(master, **kwargs))
    monkeypatch.setattr("nanoporethon.operator_assistant_gui.tk.Label", lambda master=None, **kwargs: FakeWidget(master, **kwargs))
    monkeypatch.setattr("nanoporethon.operator_assistant_gui.tk.Button", lambda master=None, **kwargs: FakeWidget(master, **kwargs))
    monkeypatch.setattr("nanoporethon.operator_assistant_gui.tk.Entry", lambda master=None, **kwargs: FakeWidget(master, **kwargs))
    monkeypatch.setattr("nanoporethon.operator_assistant_gui.tk.StringVar", lambda value=None: FakeVar(value))
    monkeypatch.setattr("nanoporethon.operator_assistant_gui.scrolledtext.ScrolledText", lambda master=None, **kwargs: FakeWidget(master, **kwargs))
    monkeypatch.setattr(OperatorAssistantGUI, "_log_chat", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(OperatorAssistantGUI, "_refresh_activity_indicator", lambda self, *args, **kwargs: None)

    gui = OperatorAssistantGUI.__new__(OperatorAssistantGUI)
    gui.root = FakeRoot()
    gui.assistant_startup_error = None
    gui._build_gui()

    top_frames = [child for child in gui.root.children if not child.kwargs.get("text")]
    assert top_frames, "Top container frame was not created"
    top = top_frames[0]

    right_frames = [child for child in top.children if child.kwargs.get("text") == "Runtime Controls"]
    assert right_frames, "Runtime Controls frame was not created"
    right = right_frames[0]

    timeline_frames = [child for child in right.children if child.kwargs.get("text") == "Runtime Timeline (events)"]
    assert timeline_frames, "Runtime Timeline frame should be nested under Runtime Controls"
    timeline = timeline_frames[0]

    assert timeline.master is right
    assert timeline.pack_calls and timeline.pack_calls[0]["side"] == "top"
    assert timeline.pack_calls[0]["fill"] == "both"
    assert timeline.pack_calls[0]["expand"] is True
    assert right.children[-1] is timeline


def test_markdown_renderer_formats_basic_markdown_in_text_widgets():
    text = _FakeText()
    _render_markdown_to_text_widget(
        text,
        "# Title\n- bullet item\n1. first\nUse `code` and **bold** text.",
        append=False,
    )
    assert "Title" in text.content
    assert "# Title" not in text.content
    assert "• bullet item" in text.content
    assert "1. first" in text.content
    assert "`code`" not in text.content
    assert "**bold**" not in text.content


def test_markdown_renderer_formats_chat_and_timeline_headers_as_headings():
    gui = _build_gui_stub()
    gui._log_chat("assistant", "Body text")
    gui._log_timeline("Runtime line")

    assert "##" not in gui.chat_output.content
    assert "###" not in gui.timeline_output.content
    assert "Assistant" in gui.chat_output.content
    assert "Body text" in gui.chat_output.content
    assert "Runtime line" in gui.timeline_output.content
    assert "─" * 10 in gui.chat_output.content
    assert "─" * 10 in gui.timeline_output.content


def test_gui_new_session_resets_runtime_request_state():
    gui = _build_gui_stub()
    gui.assistant = SimpleNamespace(init_session=lambda: {"history": []})
    gui.latest_runtime_request = "old"
    gui.latest_ready_to_run = True

    gui._new_session()

    assert gui.latest_runtime_request is None
    assert gui.latest_ready_to_run is False
    assert gui.run_button.state == "disabled"
    assert "Started a new chat session" in gui.chat_output.content


def test_gui_on_send_chat_handles_missing_assistant_and_runtime_error():
    gui = _build_gui_stub()
    gui.assistant = None
    gui.chat_input.set("hello")
    gui._on_send_chat()
    assert "assistant is unavailable due to startup error" in gui.chat_output.content

    class _BadAssistant:
        def handle_message(self, _text, session=None):
            raise RuntimeError("bad json")

    gui = _build_gui_stub()
    gui.assistant = _BadAssistant()
    gui.chat_input.set("feature request")
    gui._on_send_chat()
    assert "Routing error" in gui.chat_output.content
    assert gui.run_button.state == "disabled"


def test_gui_on_send_chat_updates_badge_followups_and_run_state():
    response = SimpleNamespace(
        intent="feature_request",
        confidence=0.91,
        message="ready",
        followup_questions=[],
        ready_to_run=True,
        runtime_request="run this",
        session_updates={"history": ["x"]},
    )

    class _GoodAssistant:
        def handle_message(self, _text, session=None):
            return response

    gui = _build_gui_stub()
    gui.assistant = _GoodAssistant()
    gui.chat_input.set("please implement")

    gui._on_send_chat()

    assert gui.latest_runtime_request == "run this"
    assert gui.latest_ready_to_run is True
    assert gui.run_button.state == "normal"
    assert "Intent: Feature Request" in gui.intent_badge_var.get()
    assert "ready to run" in gui.readiness_var.get().lower()


def test_gui_on_send_chat_shows_consulting_notice_before_assistant_runs():
    response = SimpleNamespace(
        intent="repo_question",
        confidence=0.8,
        message="done",
        followup_questions=[],
        ready_to_run=False,
        runtime_request=None,
        session_updates={"history": []},
    )

    class _NoticeCheckingAssistant:
        def __init__(self, gui):
            self.gui = gui
            self.checked = False

        def handle_message(self, _text, session=None):
            assert "consulting agents" in self.gui.intent_badge_var.get().lower()
            assert "consulting agents" in self.gui.readiness_var.get().lower()
            assert "consulting agents" in self.gui.chat_output.content.lower()
            self.checked = True
            return response

    gui = _build_gui_stub()
    checker = _NoticeCheckingAssistant(gui)
    gui.assistant = checker
    gui.chat_input.set("what models are running?")

    gui._on_send_chat()

    assert checker.checked is True
    assert "Message received, consulting agents" in gui.chat_output.content
    assert "Intent: Repo Question" in gui.intent_badge_var.get()
    assert gui.intent_badge.bg is not None
    assert gui.activity_label.fg is not None


def test_gui_event_format_discovery_and_polling(tmp_path):
    gui = _build_gui_stub()
    run_root = tmp_path / "runs"
    run_root.mkdir()
    gui.policy = {"runtime": {"run_root": str(run_root)}}
    gui.run_watch_started_at = 0

    run_dir = run_root / "run_123"
    run_dir.mkdir()
    events_file = run_dir / "events.jsonl"
    events_file.write_text(
        "\n".join(
            [
                '{"type":"stage_result","stage_id":"implement","status":"success"}',
                '{"type":"gate_result","stage_id":"verify","passed":true}',
                '{"type":"approval_requested","from_stage":"a","to_stage":"b"}',
                '{"type":"promotion_blocked","reason":"drift"}',
            ]
        ),
        encoding="utf-8",
    )

    discovered = gui._discover_run_dir()
    assert discovered == run_dir

    gui._read_new_events()
    text = gui.timeline_output.content
    assert "stage_result: implement -> success" in text
    assert "gate_result: verify -> PASS" in text
    assert "approval_requested: a -> b" in text
    assert "promotion_blocked: drift" in text

    gui.runtime_running = True
    gui.runtime_queue.put({"type": "complete", "run_state": {"status": "completed", "run_id": "run_123"}})
    gui._poll_runtime_state()
    assert "Run completed: run_123 status=completed" in gui.timeline_output.content
    assert gui.runtime_running is False
    assert len(gui.root.after_calls) >= 1


def test_gui_does_not_replay_old_events_before_a_new_run_starts(tmp_path):
    gui = _build_gui_stub()
    run_root = tmp_path / "runs"
    run_root.mkdir()
    run_dir = run_root / "run_old"
    run_dir.mkdir()
    (run_dir / "events.jsonl").write_text('{"type":"stage_result","stage_id":"implement","status":"success"}\n', encoding="utf-8")
    gui.policy = {"runtime": {"run_root": str(run_root)}}
    gui.run_watch_started_at = None
    gui.current_run_dir = None
    gui.runtime_running = False

    gui._read_new_events()

    assert gui.timeline_output.content == ""


def test_gui_health_check_logs_success_and_failure(monkeypatch):
    gui = _build_gui_stub()
    gui.policy = {"assistant_scope": {"intent_classifier": {"enabled": True}}}

    monkeypatch.setattr(
        "nanoporethon.operator_assistant_gui._classifier_health_check",
        lambda _policy: {"ok": "true", "status": "healthy", "message": "ok"},
    )
    gui._run_health_check()
    assert "Health check passed" in gui.chat_output.content

    monkeypatch.setattr(
        "nanoporethon.operator_assistant_gui._classifier_health_check",
        lambda _policy: {"ok": "false", "status": "chat_error", "message": "bad"},
    )
    gui._run_health_check()
    assert "Health check failed" in gui.chat_output.content


def test_start_runtime_blocks_when_preflight_fails(monkeypatch):
    gui = _build_gui_stub()
    gui.latest_runtime_request = "run this request"
    gui.latest_ready_to_run = True
    gui.runtime_running = False

    monkeypatch.setattr(
        "nanoporethon.operator_assistant_gui._runtime_preflight_check",
        lambda _policy, _repo_root: {
            "ok": "false",
            "status": "feature_branch_required",
            "message": "must use feature branch",
            "warnings": [],
        },
    )

    gui._start_runtime()

    assert gui.runtime_running is False
    assert "Runtime launch blocked" in gui.chat_output.content
    assert "must use feature branch" in gui.timeline_output.content
