"""Operator Assistant GUI (Option B).

Local-only attended runtime interface with:
- strict-guardrail chat assistant
- chat-first request drafting (dynamic clarifications when needed)
- runtime execution with live event timeline updates
"""

from __future__ import annotations

import json
import queue
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
    from runtime.operator_assistant import AssistantStartupError, LocalOperatorAssistant, _chat_json_response
    from runtime.orchestrator import run_milestone1
except ModuleNotFoundError:
    # Support direct-file launch, e.g. `python src/nanoporethon/operator_assistant_gui.py`,
    # where the repository root may not be on sys.path.
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from runtime.adapters.ollama import OllamaAdapter
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
    assistant_scope = policy.get("assistant_scope", {}) if isinstance(policy, dict) else {}
    classifier_cfg = assistant_scope.get("intent_classifier", {}) if isinstance(assistant_scope, dict) else {}

    if not isinstance(classifier_cfg, dict) or not bool(classifier_cfg.get("enabled")):
        return {
            "ok": "false",
            "status": "config_error",
            "message": (
                "Classifier is disabled in policy. Set assistant_scope.intent_classifier.enabled=true "
                "to run the operator assistant in strict LLM mode."
            ),
        }

    model = str(classifier_cfg.get("model", "mistral:7b"))
    base_url = str(classifier_cfg.get("base_url", "http://localhost:11434"))

    try:
        adapter = adapter_factory(model=model, base_url=base_url)
    except Exception as exc:
        return {
            "ok": "false",
            "status": "adapter_init_error",
            "message": (
                f"Failed to initialize classifier adapter (model={model}, base_url={base_url}). "
                f"Details: {exc}"
            ),
        }

    try:
        payload = _chat_json_response(
            adapter,
            "Return ONLY valid JSON: {\"intent\": \"feature_request\", \"confidence\": 0.9, \"reason\": \"healthcheck\"}",
            [{"role": "user", "content": "Health check: classify this as feature_request."}],
        )
    except Exception as exc:
        msg = str(exc)
        lowered = msg.lower()
        if "not found" in lowered and "model" in lowered:
            return {
                "ok": "false",
                "status": "model_missing",
                "message": (
                    f"Classifier model '{model}' is not available in local Ollama. "
                    "Install/pull it and retry (for example: ollama pull <model>). "
                    f"Details: {msg}"
                ),
            }
        if any(token in lowered for token in ["connection refused", "failed to connect", "timed out", "connection error"]):
            return {
                "ok": "false",
                "status": "service_unreachable",
                "message": (
                    f"Cannot reach Ollama at {base_url}. Ensure the local service is running and accessible. "
                    f"Details: {msg}"
                ),
            }
        if "json" in lowered or "no json object found" in lowered or "empty model output" in lowered:
            return {
                "ok": "false",
                "status": "malformed_output",
                "message": (
                    "Classifier returned non-JSON output during health check. "
                    f"Details: {msg}"
                ),
            }
        return {
            "ok": "false",
            "status": "chat_error",
            "message": f"Classifier call failed for model={model} at {base_url}. Details: {msg}",
        }

    intent = str(payload.get("intent", "")).strip().lower()
    if intent not in {"feature_request", "runtime_help", "code_explanation", "repo_question", "out_of_scope"}:
        return {
            "ok": "false",
            "status": "invalid_schema",
            "message": (
                "Classifier JSON is missing/invalid 'intent' value. "
                f"Received intent={intent!r}."
            ),
        }

    return {
        "ok": "true",
        "status": "healthy",
        "message": f"Classifier healthy (model={model}, base_url={base_url}, intent={intent}).",
    }


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
            self.assistant = LocalOperatorAssistant(repo_root=self.repo_root, policy=self.policy)
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
        self.followup_output.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        preview_frame = tk.LabelFrame(right, text="Runtime request preview")
        preview_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 6))
        self.preview_output = scrolledtext.ScrolledText(preview_frame, height=18, state=tk.DISABLED, wrap=tk.WORD)
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
        self.timeline_output.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        if self.assistant_startup_error:
            self.chat_input.config(state=tk.DISABLED)
            self.send_button.config(state=tk.DISABLED)
            self.run_button.config(state=tk.DISABLED)
            self.readiness_var.set("Status: assistant startup blocked")
            self._set_intent_badge("out_of_scope", 1.0)
            self._log_chat(
                "assistant",
                "Startup error: strict local-LLM mode is required for routing and session analysis. "
                f"{self.assistant_startup_error}",
            )

        self._refresh_activity_indicator(force=True)

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _log_chat(self, role: str, message: str) -> None:
        self.chat_output.config(state=tk.NORMAL)
        self.chat_output.insert(tk.END, f"[{self._timestamp()}] {role}: {message}\n\n")
        self.chat_output.see(tk.END)
        self.chat_output.config(state=tk.DISABLED)

    def _set_intent_badge(self, intent: str, confidence: float) -> None:
        text, color = _intent_badge_style(intent, confidence)
        self.intent_badge_var.set(text)
        self.intent_badge.config(fg=color)

    def _log_timeline(self, message: str) -> None:
        self.timeline_output.config(state=tk.NORMAL)
        self.timeline_output.insert(tk.END, f"[{self._timestamp()}] {message}\n")
        self.timeline_output.see(tk.END)
        self.timeline_output.config(state=tk.DISABLED)

    def _set_preview_text(self, text: str) -> None:
        self.preview_output.config(state=tk.NORMAL)
        self.preview_output.delete("1.0", tk.END)
        self.preview_output.insert(tk.END, text)
        self.preview_output.config(state=tk.DISABLED)

    def _set_followups(self, questions: list[str]) -> None:
        self.followup_output.config(state=tk.NORMAL)
        self.followup_output.delete("1.0", tk.END)
        if questions:
            for idx, question in enumerate(questions, start=1):
                self.followup_output.insert(tk.END, f"{idx}. {question}\n")
        else:
            self.followup_output.insert(tk.END, "No follow-up questions pending.")
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
                "Routing error: strict LLM mode requires valid structured model output for each message. "
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
            "Fix the issue and run Health Check again before relying on strict routing.",
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
