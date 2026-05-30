"""Operator Assistant GUI (Option B).

Local-only attended runtime interface with:
- strict-guardrail chat assistant
- chat-first request drafting (dynamic clarifications when needed)
- runtime execution with live event timeline updates
"""

from __future__ import annotations

import json
import queue
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set, Tuple

import tkinter as tk
from tkinter import scrolledtext

try:
    from runtime.adapters.ollama import OllamaAdapter
    from runtime.repo_ops import RepoWorkspaceManager
    from runtime.operator_assistant import AssistantStartupError, LocalOperatorAssistant, _chat_json_response
    from runtime.orchestrator import run_milestone1
except ModuleNotFoundError:
    # Support direct-file launch, e.g. `python src/nanoporethon/operator_assistant_gui.py`,
    # where the repository root may not be on sys.path.
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from runtime.adapters.ollama import OllamaAdapter
    from runtime.repo_ops import RepoWorkspaceManager
    from runtime.operator_assistant import AssistantStartupError, LocalOperatorAssistant, _chat_json_response
    from runtime.orchestrator import run_milestone1


def _intent_badge_style(intent: str, confidence: float) -> Tuple[str, str]:
    normalized = (intent or "unknown").strip().lower() or "unknown"
    pretty = normalized.replace("_", " ").title()
    text = f"Intent: {pretty} ({confidence:.2f})"

    color_map = {
        "feature_request": "#0a7d33",
        "runtime_help": "#1f4aa8",
        "code_explanation": "#6a3dad",
        "nanopore_science_explanation": "#0b7285",
        "repo_question": "#444444",
        "out_of_scope": "#b42318",
        "unknown": "#555555",
    }
    return text, color_map.get(normalized, "#555555")


def _activity_indicator_text(runtime_running: bool, assistant_processing: bool, dot_phase: int) -> Tuple[str, str]:
    dots = "." * (max(0, int(dot_phase)) % 3 + 1)
    if runtime_running:
        return f"Activity: runtime execution in progress{dots}", "#1f4aa8"
    if assistant_processing:
        return f"Activity: assistant is processing{dots}", "#6a3dad"
    return "Activity: idle", "#666666"


def _activity_status_label(activity_text: str, last_ui_tick: str) -> str:
    return f"{activity_text} (last UI tick: {last_ui_tick})"


def _load_policy(path: Path) -> Dict[str, object]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}

    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _resolve_repo_root(start_dir: Path, module_file: Optional[Path] = None) -> Path:
    """Find repository root by locating runtime/policies.yaml.

    This allows GUI startup to succeed when launched from outside the repo root.
    """
    start = start_dir.resolve()
    search_roots = [start, *start.parents]

    if module_file is not None:
        module_parent = module_file.resolve().parent
        if module_parent not in search_roots:
            search_roots.extend([module_parent, *module_parent.parents])

    for candidate in search_roots:
        if (candidate / "runtime" / "policies.yaml").exists():
            return candidate

    return start


def _classifier_health_check(
    policy: Dict[str, object],
    adapter_factory: Callable[..., Any] = OllamaAdapter,
) -> Dict[str, str]:
    del adapter_factory  # retained for backwards-compatible signature in tests/callers.

    assistant_scope = policy.get("assistant_scope", {}) if isinstance(policy, dict) else {}
    if not isinstance(assistant_scope, dict):
        return {
            "ok": "false",
            "status": "config_error",
            "message": "assistant_scope policy block is missing or invalid.",
        }

    domain_anchors = assistant_scope.get("domain_anchors", [])
    grounding_files = assistant_scope.get("grounding_files", [])
    sensitive_domains = assistant_scope.get("sensitive_domains", [])

    if not isinstance(domain_anchors, list) or len(domain_anchors) == 0:
        return {
            "ok": "false",
            "status": "config_error",
            "message": "assistant_scope.domain_anchors must be a non-empty list.",
        }
    if not isinstance(grounding_files, list) or len(grounding_files) == 0:
        return {
            "ok": "false",
            "status": "config_error",
            "message": "assistant_scope.grounding_files must be a non-empty list.",
        }
    if not isinstance(sensitive_domains, list) or len(sensitive_domains) == 0:
        return {
            "ok": "false",
            "status": "config_error",
            "message": "assistant_scope.sensitive_domains must be a non-empty list.",
        }

    return {
        "ok": "true",
        "status": "healthy",
        "message": "Scope-gate policy is healthy (anchors + grounding files + sensitive domains configured).",
    }


def _runtime_preflight_check(
    policy: Dict[str, object],
    repo_root: Path,
    workspace_manager_factory: Callable[..., Any] = RepoWorkspaceManager,
) -> Dict[str, object]:
    assistant_scope = policy.get("assistant_scope", {}) if isinstance(policy, dict) else {}
    preflight_cfg = assistant_scope.get("runtime_preflight", {}) if isinstance(assistant_scope, dict) else {}

    require_clean = True
    require_feature_branch = True
    if isinstance(preflight_cfg, dict):
        require_clean = bool(preflight_cfg.get("require_clean_worktree", True))
        require_feature_branch = bool(preflight_cfg.get("require_feature_branch", True))

    manager = workspace_manager_factory(repo_root=repo_root, sandbox_root=repo_root / ".nanopore-runtime" / "preflight")
    try:
        state = manager.inspect_start_state(require_clean=require_clean, recommend_feature_branch=False)
    except RuntimeError as exc:
        return {
            "ok": "false",
            "status": "dirty_worktree",
            "message": str(exc),
            "warnings": [],
        }

    if require_feature_branch and bool(state.get("is_git_repo", False)):
        branch = str(state.get("base_branch", ""))
        if branch in {"main", "master"}:
            return {
                "ok": "false",
                "status": "feature_branch_required",
                "message": (
                    f"Operator assistant runtime launch blocked on branch '{branch}'. "
                    "Please create/switch to a dedicated feature branch before running assistant-managed executions."
                ),
                "warnings": state.get("warnings", []),
            }
        if not branch:
            return {
                "ok": "false",
                "status": "feature_branch_required",
                "message": (
                    "Operator assistant runtime launch blocked in detached HEAD state. "
                    "Please switch to a dedicated feature branch before running assistant-managed executions."
                ),
                "warnings": state.get("warnings", []),
            }

    return {
        "ok": "true",
        "status": "ready",
        "message": "Runtime preflight checks passed.",
        "warnings": state.get("warnings", []),
    }


def _init_markdown_tags(widget: Any) -> None:
    theme = getattr(widget, "_pane_theme", "light")
    if getattr(widget, "_markdown_tags_ready", False) and getattr(widget, "_markdown_theme", "light") == theme:
        return
    if not hasattr(widget, "tag_configure"):
        return

    light = {
        "body": "#1f2937",
        "h1": "#1d4ed8",
        "h2": "#1e40af",
        "h3": "#1e3a8a",
        "bold": "#111827",
        "italic": "#334155",
        "code_fg": "#7c2d12",
        "code_bg": "#fff7ed",
        "quote": "#475467",
    }
    dark = {
        "body": "#e5e7eb",
        "h1": "#93c5fd",
        "h2": "#bfdbfe",
        "h3": "#dbeafe",
        "bold": "#f9fafb",
        "italic": "#cbd5e1",
        "code_fg": "#fed7aa",
        "code_bg": "#3f2b1d",
        "quote": "#cbd5e1",
    }
    colors = dark if theme == "dark" else light

    widget.tag_configure("md_body", foreground=colors["body"], spacing1=1, spacing3=2)
    widget.tag_configure("md_h1", font=("TkDefaultFont", 16, "bold"), foreground=colors["h1"], spacing1=11, spacing3=6)
    widget.tag_configure("md_h2", font=("TkDefaultFont", 14, "bold"), foreground=colors["h2"], spacing1=9, spacing3=5)
    widget.tag_configure("md_h3", font=("TkDefaultFont", 12, "bold"), foreground=colors["h3"], spacing1=7, spacing3=4)
    widget.tag_configure("md_bold", font=("TkDefaultFont", 11, "bold"), foreground=colors["bold"])
    widget.tag_configure("md_italic", font=("TkDefaultFont", 11, "italic"), foreground=colors["italic"])
    widget.tag_configure("md_code", font=("Courier", 10), foreground=colors["code_fg"], background=colors["code_bg"])
    widget.tag_configure(
        "md_code_block",
        font=("Courier", 10),
        foreground=colors["code_fg"],
        background=colors["code_bg"],
        lmargin1=14,
        lmargin2=14,
        spacing1=4,
        spacing3=4,
    )
    widget.tag_configure("md_quote", foreground=colors["quote"], lmargin1=14, lmargin2=14, spacing1=2, spacing3=2)
    widget._markdown_tags_ready = True
    widget._markdown_theme = theme


def _is_dark_hex_color(color: str) -> bool:
    value = (color or "").strip()
    if not value.startswith("#"):
        return False
    hex_value = value[1:]
    if len(hex_value) == 3:
        try:
            r = int(hex_value[0] * 2, 16)
            g = int(hex_value[1] * 2, 16)
            b = int(hex_value[2] * 2, 16)
        except ValueError:
            return False
    elif len(hex_value) == 6:
        try:
            r = int(hex_value[0:2], 16)
            g = int(hex_value[2:4], 16)
            b = int(hex_value[4:6], 16)
        except ValueError:
            return False
    else:
        return False
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    return luma < 128


def _widget_prefers_dark_theme(widget: Any) -> bool:
    if hasattr(widget, "_pane_theme"):
        return getattr(widget, "_pane_theme") == "dark"

    bg_color = ""
    if hasattr(widget, "cget"):
        try:
            bg_color = str(widget.cget("bg"))
        except Exception:
            bg_color = ""

    if bg_color and _is_dark_hex_color(bg_color):
        return True

    if hasattr(widget, "winfo_toplevel"):
        try:
            toplevel = widget.winfo_toplevel()
            if hasattr(toplevel, "cget"):
                top_bg = str(toplevel.cget("bg"))
                if _is_dark_hex_color(top_bg):
                    return True
        except Exception:
            return False

    return False


def _style_text_pane(widget: Any, pane_kind: str) -> None:
    is_dark = _widget_prefers_dark_theme(widget)
    base = {
        "font": ("TkDefaultFont", 11),
        "insertbackground": "#f9fafb" if is_dark else "#111827",
        "selectbackground": "#1d4ed8" if is_dark else "#bfdbfe",
        "selectforeground": "#f8fafc" if is_dark else "#111827",
        "relief": tk.FLAT,
        "borderwidth": 0,
        "padx": 8,
        "pady": 8,
    }
    if is_dark:
        palette = {
            "chat": {"bg": "#0f172a", "fg": "#e2e8f0"},
            "followup": {"bg": "#102a43", "fg": "#e2e8f0"},
            "preview": {"bg": "#0b1220", "fg": "#e2e8f0"},
            "timeline": {"bg": "#1e1b4b", "fg": "#e2e8f0"},
        }
        widget._pane_theme = "dark"
    else:
        palette = {
            "chat": {"bg": "#f8fafc", "fg": "#0f172a"},
            "followup": {"bg": "#f0f9ff", "fg": "#0f172a"},
            "preview": {"bg": "#f8fafc", "fg": "#0f172a"},
            "timeline": {"bg": "#f5f3ff", "fg": "#1f2937"},
        }
        widget._pane_theme = "light"
    colors = palette.get(pane_kind, {"bg": "#ffffff", "fg": "#111827"})
    kwargs = dict(base)
    kwargs.update(colors)
    if hasattr(widget, "config"):
        widget.config(**kwargs)


def _inline_markdown_segments(text: str) -> list[tuple[str, Optional[str]]]:
    pattern = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)")
    segments: list[tuple[str, Optional[str]]] = []
    idx = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > idx:
            segments.append((text[idx:start], None))
        token = match.group(0)
        if token.startswith("`") and token.endswith("`"):
            segments.append((token[1:-1], "md_code"))
        elif token.startswith("**") and token.endswith("**"):
            segments.append((token[2:-2], "md_bold"))
        elif token.startswith("*") and token.endswith("*"):
            segments.append((token[1:-1], "md_italic"))
        else:
            segments.append((token, None))
        idx = end
    if idx < len(text):
        segments.append((text[idx:], None))
    return segments


def _insert_markdown_line(widget: Any, line: str, line_tag: Optional[str] = None) -> None:
    def _safe_insert(text: str, tags: tuple[str, ...] = ()) -> None:
        if tags:
            try:
                widget.insert(tk.END, text, tags)
                return
            except TypeError:
                pass
        widget.insert(tk.END, text)

    segments = _inline_markdown_segments(line)
    effective_line_tag = line_tag or "md_body"
    for segment_text, inline_tag in segments:
        if not segment_text:
            continue
        tags = tuple(tag for tag in [effective_line_tag, inline_tag] if tag)
        _safe_insert(segment_text, tags)
    _safe_insert("\n", (effective_line_tag,))


def _render_markdown_to_text_widget(widget: Any, markdown_text: str, append: bool = False) -> None:
    text = markdown_text or ""
    if not append and hasattr(widget, "delete"):
        widget.delete("1.0", tk.END)

    _init_markdown_tags(widget)

    in_code_block = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            _insert_markdown_line(widget, line, line_tag="md_code_block")
            continue

        if stripped.startswith("### "):
            _insert_markdown_line(widget, stripped[4:], line_tag="md_h3")
            continue
        if stripped.startswith("## "):
            _insert_markdown_line(widget, stripped[3:], line_tag="md_h2")
            continue
        if stripped.startswith("# "):
            _insert_markdown_line(widget, stripped[2:], line_tag="md_h1")
            continue
        if stripped.startswith("> "):
            _insert_markdown_line(widget, stripped[2:], line_tag="md_quote")
            continue

        bullet = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if bullet:
            _insert_markdown_line(widget, f"• {bullet.group(1)}")
            continue

        numbered = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
        if numbered:
            _insert_markdown_line(widget, f"{numbered.group(1)}. {numbered.group(2)}")
            continue

        _insert_markdown_line(widget, line)

    if text.endswith("\n"):
        widget.insert(tk.END, "\n")


class OperatorAssistantGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("nanoporethon Operator Assistant (Local, Guardrailed)")
        self.root.geometry("1320x860")

        self.repo_root = _resolve_repo_root(Path.cwd(), module_file=Path(__file__))
        self.policy_path = self.repo_root / "runtime" / "policies.yaml"
        self.policy = _load_policy(self.policy_path)
        self.assistant: Optional[LocalOperatorAssistant] = None
        self.assistant_startup_error: Optional[str] = None
        try:
            _mp = self.policy.get("model_provider") or {}
            _model_adapter = OllamaAdapter(
                model=str(_mp.get("model", "qwen2.5:3b")),
                base_url=str(_mp.get("base_url", "http://localhost:11434")),
                timeout_seconds=int(_mp.get("request_timeout_seconds", 180)),
                max_retries=int(_mp.get("max_retries", 1)),
            )
            self.assistant = LocalOperatorAssistant(
                repo_root=self.repo_root,
                policy=self.policy,
                model_adapter=_model_adapter,
            )
        except AssistantStartupError as exc:
            self.assistant_startup_error = str(exc)

        self.runtime_thread: Optional[threading.Thread] = None
        self.runtime_queue: "queue.Queue[Dict[str, object]]" = queue.Queue()
        self.runtime_running = False
        self.assistant_processing = False
        self.run_watch_started_at: Optional[float] = None
        self.existing_runs: Set[str] = set()
        self.current_run_id: Optional[str] = None
        self.current_run_dir: Optional[Path] = None
        self.events_line_cursor = 0
        self.activity_dot_phase = 0
        self.activity_last_tick = time.monotonic()
        self.activity_last_ui_tick = datetime.now().strftime("%H:%M:%S")

        self.session_state: Dict[str, object] = self.assistant.init_session() if self.assistant else {}
        self.latest_runtime_request: Optional[str] = None
        self.latest_ready_to_run: bool = False

        self._build_gui()
        self._poll_runtime_state()

    def _build_gui(self) -> None:
        top = tk.Frame(self.root)
        top.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        left = tk.LabelFrame(top, text="Local Chat Assistant", padx=8, pady=8)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.intent_badge_var = tk.StringVar(value="Intent: Waiting for message")
        self.intent_badge = tk.Label(
            left,
            textvariable=self.intent_badge_var,
            anchor="w",
            justify=tk.LEFT,
            fg="#555555",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.intent_badge.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))

        self.chat_output = scrolledtext.ScrolledText(left, height=26, state=tk.DISABLED, wrap=tk.WORD)
        _style_text_pane(self.chat_output, "chat")
        self.chat_output.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        chat_input_frame = tk.Frame(left)
        chat_input_frame.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))

        self.chat_input = tk.Entry(chat_input_frame)
        self.chat_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.chat_input.bind("<Return>", self._on_send_chat)
        self.send_button = tk.Button(chat_input_frame, text="Send", command=self._on_send_chat)
        self.send_button.pack(side=tk.LEFT, padx=(6, 0))

        self._log_chat(
            "assistant",
            "I’m your local nanoporethon operator assistant. Describe what you want in normal language. "
            "I will ask follow-up questions only when needed, draft a runtime request preview, and keep core GUI components protected unless you explicitly authorize changes.",
        )

        right = tk.LabelFrame(top, text="Request Preview + Runtime Control", padx=8, pady=8)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        help_text = (
            "How this works:\n"
            "1) Chat naturally about the feature/task.\n"
            "2) Assistant asks follow-up questions only when needed.\n"
            "3) Review the generated runtime request preview below.\n"
            "4) Click 'Run Latest Request' when ready."
        )
        tk.Label(right, text=help_text, justify=tk.LEFT, anchor="w", fg="#444444").pack(side=tk.TOP, fill=tk.X)

        followup_frame = tk.LabelFrame(right, text="Follow-up questions (if needed)")
        followup_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=False, pady=(8, 6))
        self.followup_output = scrolledtext.ScrolledText(followup_frame, height=6, state=tk.DISABLED, wrap=tk.WORD)
        _style_text_pane(self.followup_output, "followup")
        self.followup_output.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        preview_frame = tk.LabelFrame(right, text="Runtime request preview")
        preview_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 6))
        self.preview_output = scrolledtext.ScrolledText(preview_frame, height=18, state=tk.DISABLED, wrap=tk.WORD)
        _style_text_pane(self.preview_output, "preview")
        self.preview_output.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.readiness_var = tk.StringVar(value="Status: waiting for feature request message")
        tk.Label(right, textvariable=self.readiness_var, anchor="w", fg="#333333").pack(side=tk.TOP, fill=tk.X)

        self.activity_var = tk.StringVar(value="Activity: idle")
        self.activity_label = tk.Label(right, textvariable=self.activity_var, anchor="w", fg="#666666")
        self.activity_label.pack(side=tk.TOP, fill=tk.X, pady=(2, 0))

        controls = tk.Frame(right)
        controls.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))
        self.run_button = tk.Button(controls, text="Run Latest Request", command=self._start_runtime, state=tk.DISABLED)
        self.run_button.pack(side=tk.LEFT)
        tk.Button(controls, text="Health Check", command=self._run_health_check).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(controls, text="New Chat Session", command=self._new_session).pack(side=tk.LEFT, padx=(8, 0))

        timeline = tk.LabelFrame(self.root, text="Runtime Timeline (events)", padx=8, pady=8)
        timeline.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=False, padx=10, pady=(0, 10))
        self.timeline_output = scrolledtext.ScrolledText(timeline, height=10, state=tk.DISABLED, wrap=tk.WORD)
        _style_text_pane(self.timeline_output, "timeline")
        self.timeline_output.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        if self.assistant_startup_error:
            self.chat_input.config(state=tk.DISABLED)
            self.send_button.config(state=tk.DISABLED)
            self.run_button.config(state=tk.DISABLED)
            self.readiness_var.set("Status: assistant startup blocked")
            self._set_intent_badge("out_of_scope", 1.0)
            self._log_chat(
                "assistant",
                "Startup error: operator assistant failed to initialize. "
                f"{self.assistant_startup_error}",
            )

        self._refresh_activity_indicator(force=True)

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _log_chat(self, role: str, message: str) -> None:
        self.chat_output.config(state=tk.NORMAL)
        clean_role = (role or "assistant").strip().title()
        body = (message or "").rstrip()
        _render_markdown_to_text_widget(
            self.chat_output,
            f"## [{self._timestamp()}] {clean_role}\n{body}\n\n",
            append=True,
        )
        self.chat_output.see(tk.END)
        self.chat_output.config(state=tk.DISABLED)

    def _set_intent_badge(self, intent: str, confidence: float) -> None:
        text, color = _intent_badge_style(intent, confidence)
        self.intent_badge_var.set(text)
        self.intent_badge.config(fg=color)

    def _log_timeline(self, message: str) -> None:
        self.timeline_output.config(state=tk.NORMAL)
        body = (message or "").rstrip()
        _render_markdown_to_text_widget(
            self.timeline_output,
            f"### [{self._timestamp()}]\n{body}\n",
            append=True,
        )
        self.timeline_output.see(tk.END)
        self.timeline_output.config(state=tk.DISABLED)

    def _set_preview_text(self, text: str) -> None:
        self.preview_output.config(state=tk.NORMAL)
        _render_markdown_to_text_widget(self.preview_output, text, append=False)
        self.preview_output.config(state=tk.DISABLED)

    def _set_followups(self, questions: list[str]) -> None:
        self.followup_output.config(state=tk.NORMAL)
        if questions:
            markdown = "\n".join(f"{idx}. {question}" for idx, question in enumerate(questions, start=1))
            _render_markdown_to_text_widget(self.followup_output, markdown, append=False)
        else:
            _render_markdown_to_text_widget(self.followup_output, "No follow-up questions pending.", append=False)
        self.followup_output.config(state=tk.DISABLED)

    def _new_session(self) -> None:
        if self.assistant is None:
            self._log_chat("assistant", "Cannot start a new session while assistant startup is blocked.")
            return

        self.session_state = self.assistant.init_session()
        self.latest_runtime_request = None
        self.latest_ready_to_run = False
        self.run_button.config(state=tk.DISABLED)
        self.intent_badge_var.set("Intent: Waiting for message")
        self.intent_badge.config(fg="#555555")
        self.readiness_var.set("Status: waiting for feature request message")
        self._set_preview_text("")
        self._set_followups([])
        self.assistant_processing = False
        self._refresh_activity_indicator(force=True)
        self._log_chat("assistant", "Started a new chat session. Describe your next request.")

    def _refresh_activity_indicator(self, force: bool = False) -> None:
        busy = self.runtime_running or self.assistant_processing
        now = time.monotonic()

        if force:
            if not busy:
                self.activity_dot_phase = 0
            self.activity_last_tick = now
        elif busy and now - self.activity_last_tick >= 1.0:
            self.activity_dot_phase = (self.activity_dot_phase + 1) % 3
            self.activity_last_tick = now

        if force or busy:
            self.activity_last_ui_tick = datetime.now().strftime("%H:%M:%S")

        text, color = _activity_indicator_text(
            runtime_running=self.runtime_running,
            assistant_processing=self.assistant_processing,
            dot_phase=self.activity_dot_phase,
        )
        self.activity_var.set(_activity_status_label(text, self.activity_last_ui_tick))
        self.activity_label.config(fg=color)

    def _on_send_chat(self, _event=None) -> None:
        if self.assistant is None:
            self._log_chat(
                "assistant",
                "Message not processed: assistant is unavailable due to startup error. "
                "Fix the local classifier configuration/model and restart the GUI.",
            )
            return

        user_text = self.chat_input.get().strip()
        if not user_text:
            return

        self.chat_input.delete(0, tk.END)
        self._log_chat("user", user_text)

        self.assistant_processing = True
        self._refresh_activity_indicator(force=True)
        self.root.update_idletasks()

        try:
            response = self.assistant.handle_message(user_text, session=self.session_state)
        except RuntimeError as exc:
            self._log_chat(
                "assistant",
                "Routing error while processing this message. "
                f"Details: {exc}",
            )
            self._set_intent_badge("out_of_scope", 1.0)
            self.readiness_var.set("Status: routing error (check local model output)")
            self.run_button.config(state=tk.DISABLED)
            self.assistant_processing = False
            self._refresh_activity_indicator(force=True)
            return
        finally:
            if self.assistant_processing:
                self.assistant_processing = False
                self._refresh_activity_indicator(force=True)
        self.session_state = response.session_updates
        self._set_intent_badge(response.intent, response.confidence)

        self.latest_runtime_request = response.runtime_request or self.latest_runtime_request
        self.latest_ready_to_run = bool(response.ready_to_run and self.latest_runtime_request)

        if response.runtime_request:
            self._set_preview_text(response.runtime_request)
        self._set_followups(response.followup_questions)

        if self.latest_ready_to_run:
            self.run_button.config(state=tk.NORMAL)
            self.readiness_var.set("Status: ready to run")
        elif response.intent == "feature_request":
            self.run_button.config(state=tk.DISABLED)
            if response.followup_questions:
                self.readiness_var.set("Status: waiting for follow-up answers")
            else:
                self.readiness_var.set("Status: feature request captured")

        self._log_chat(
            "assistant",
            f"[{response.intent} | conf={response.confidence:.2f}] {response.message}",
        )

    def _run_health_check(self) -> None:
        result = _classifier_health_check(self.policy)
        ok = result.get("ok", "false") == "true"
        status = result.get("status", "unknown")
        message = result.get("message", "No details available.")

        if ok:
            self._log_chat("assistant", f"Health check passed [{status}]: {message}")
            return

        self._log_chat(
            "assistant",
            "Health check failed "
            f"[{status}]: {message} "
            "Fix the issue and run Health Check again before relying on assistant routing.",
        )

    def _start_runtime(self) -> None:
        if self.runtime_running:
            self._log_timeline("Runtime already running. Please wait for completion.")
            return

        if not self.latest_runtime_request:
            self._log_timeline("No runtime request is available yet. Describe the task in chat first.")
            return

        if not self.latest_ready_to_run:
            self._log_timeline("Please answer pending follow-up questions before running.")
            return

        preflight = _runtime_preflight_check(self.policy, self.repo_root)
        if preflight.get("ok") != "true":
            message = str(preflight.get("message", "Runtime preflight failed."))
            self._log_chat("assistant", f"Runtime launch blocked: {message}")
            self._log_timeline(f"Runtime launch blocked: {message}")
            self.run_button.config(state=tk.DISABLED)
            return

        warnings = preflight.get("warnings", [])
        if isinstance(warnings, list):
            for warning in warnings:
                self._log_timeline(f"Preflight warning: {warning}")

        request_text = self.latest_runtime_request
        self._log_chat("assistant", "Launching attended runtime using the latest conversation-derived request.")

        run_root = Path(self.policy.get("runtime", {}).get("run_root", ".nanopore-runtime/runs"))
        self.existing_runs = {p.name for p in run_root.glob("run_*") if p.is_dir()} if run_root.exists() else set()
        self.run_watch_started_at = datetime.now().timestamp()
        self.current_run_id = None
        self.current_run_dir = None
        self.events_line_cursor = 0

        self.runtime_running = True
        self.runtime_thread = threading.Thread(
            target=self._runtime_worker,
            args=(request_text,),
            daemon=True,
        )
        self.runtime_thread.start()
        self._log_timeline("Runtime execution started (approval_mode=auto, live progress from events).")
        self._refresh_activity_indicator(force=True)

    def _runtime_worker(self, request_text: str) -> None:
        try:
            run_state = run_milestone1(
                request=request_text,
                policy=self.policy,
                repo_root=self.repo_root,
                live_progress=False,
                approval_mode="auto",
            )
            self.runtime_queue.put({"type": "complete", "run_state": run_state})
        except Exception as exc:
            self.runtime_queue.put({"type": "error", "error": str(exc)})

    def _discover_run_dir(self) -> Optional[Path]:
        run_root = Path(self.policy.get("runtime", {}).get("run_root", ".nanopore-runtime/runs"))
        if self.current_run_dir is not None:
            return self.current_run_dir
        if not run_root.exists():
            return None

        for candidate in sorted(run_root.glob("run_*"), key=lambda p: p.stat().st_mtime):
            if not candidate.is_dir() or candidate.name in self.existing_runs:
                continue
            if self.run_watch_started_at and candidate.stat().st_mtime < self.run_watch_started_at:
                continue
            self.current_run_dir = candidate
            self.current_run_id = candidate.name
            self._log_timeline(f"Detected run directory: {candidate.name}")
            return self.current_run_dir
        return None

    def _read_new_events(self) -> None:
        if self.run_watch_started_at is None and self.current_run_dir is None and not self.runtime_running:
            return

        run_dir = self._discover_run_dir()
        if run_dir is None:
            return

        events_file = run_dir / "events.jsonl"
        if not events_file.exists():
            return

        try:
            lines = events_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return

        if self.events_line_cursor >= len(lines):
            return

        new_lines = lines[self.events_line_cursor :]
        self.events_line_cursor = len(lines)

        for raw in new_lines:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            self._log_timeline(self._format_event(event))

    def _format_event(self, event: Dict[str, object]) -> str:
        event_type = str(event.get("type", "event"))
        stage = str(event.get("stage_id", ""))
        decision = str(event.get("decision", ""))

        if event_type == "stage_result":
            return f"stage_result: {stage} -> {event.get('status', 'unknown')}"
        if event_type == "gate_result":
            return f"gate_result: {stage} -> {'PASS' if bool(event.get('passed', False)) else 'FAIL'}"
        if event_type == "approval_requested":
            return f"approval_requested: {event.get('from_stage')} -> {event.get('to_stage')}"
        if event_type == "approval_decision":
            return f"approval_decision: {event.get('from_stage')} -> {event.get('to_stage')} ({decision})"
        if event_type == "promotion_requested":
            return f"promotion_requested: changed_files={event.get('changed_count', 0)}"
        if event_type == "promotion_applied":
            return "promotion_applied"
        if event_type == "promotion_skipped":
            return f"promotion_skipped ({decision})"
        if event_type == "promotion_blocked":
            return f"promotion_blocked: {event.get('reason', 'unknown')}"
        if event_type == "runtime_error":
            return f"runtime_error: {event.get('error', 'unknown')}"
        return event_type

    def _poll_runtime_state(self) -> None:
        self._read_new_events()

        while True:
            try:
                msg = self.runtime_queue.get_nowait()
            except queue.Empty:
                break

            msg_type = msg.get("type")
            if msg_type == "complete":
                run_state = msg.get("run_state", {})
                status = run_state.get("status", "unknown") if isinstance(run_state, dict) else "unknown"
                run_id = run_state.get("run_id", self.current_run_id or "unknown") if isinstance(run_state, dict) else "unknown"
                self._log_timeline(f"Run completed: {run_id} status={status}")
                self.runtime_running = False
                self._refresh_activity_indicator(force=True)
            elif msg_type == "error":
                self._log_timeline(f"Run failed with exception: {msg.get('error', 'unknown')} ")
                self.runtime_running = False
                self._refresh_activity_indicator(force=True)

        self._refresh_activity_indicator(force=False)

        self.root.after(750, self._poll_runtime_state)


def run_gui() -> None:
    root = tk.Tk()
    app = OperatorAssistantGUI(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
