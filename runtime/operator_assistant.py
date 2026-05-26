"""Local operator assistant for attended runtime workflows.

Chat-first Option-B implementation:
- strict domain guardrails with deterministic out-of-scope refusal
- conversational feature-request drafting (no mandatory long form)
- just-in-time clarification questions when requests are ambiguous
- default protection for core GUIs unless explicitly authorized by user
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from .adapters.ollama import OllamaAdapter


_DEFAULT_DOC_FILES = [
    "README.md",
    "Docs/components.md",
    "Docs/nanoporethon_textbook.md",
    "Docs/UseCases.md",
    "Docs/technology_context.md",
    "Docs/feature_request_template.md",
]

_CORE_GUI_FILE_HINTS = {
    "src/nanoporethon/data_navi_gui.py": [
        "src/nanoporethon/data_navi_gui.py",
        "data_navi_gui.py",
        "data_navi_gui",
        "data navigator gui",
        "data navigator",
    ],
    "src/nanoporethon/event_classifier_gui.py": [
        "src/nanoporethon/event_classifier_gui.py",
        "event_classifier_gui.py",
        "event_classifier_gui",
        "event classifier gui",
        "event classifier",
    ],
}


@dataclass
class AssistantDecision:
    intent: str
    confidence: float
    reason: str


@dataclass
class AssistantResponse:
    intent: str
    message: str
    confidence: float
    reason: str
    followup_questions: List[str]
    ready_to_run: bool
    runtime_request: Optional[str]
    session_updates: Dict[str, Any]


class AssistantStartupError(RuntimeError):
    """Raised when the operator assistant cannot start in strict LLM mode."""


def _extract_json_object(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty model output")

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            return candidate

    raise ValueError("no JSON object found in model output")


def _chat_json_response(adapter: Any, system_prompt: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    if hasattr(adapter, "chat_json"):
        raw = adapter.chat_json(system_prompt, messages)
    else:
        raw = adapter.chat(system_prompt, messages)
    return _extract_json_object(str(raw))


class LocalOperatorAssistant:
    """Local assistant that is intentionally scoped to nanoporethon/runtime tasks.

    The assistant enforces strict guardrails so off-topic domains are refused
    deterministically even when a local model is available.
    """

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        policy: Optional[Dict[str, object]] = None,
        model_adapter: Optional[OllamaAdapter] = None,
    ) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.policy = policy or {}
        self.model_adapter = model_adapter
        self._doc_cache = self._load_docs()
        self._intent_cache: Dict[str, Tuple[str, float, str]] = {}
        self._intent_classifier_fallback: Optional[OllamaAdapter] = None

        self._core_protected_files = [
            "src/nanoporethon/data_navi_gui.py",
            "src/nanoporethon/event_classifier_gui.py",
        ]

        classifier_config = {}
        if isinstance(self.policy, dict):
            classifier_config = self.policy.get("assistant_scope", {}).get("intent_classifier", {})

        if not isinstance(classifier_config, dict) or not bool(classifier_config.get("enabled")):
            raise AssistantStartupError(
                "Operator assistant startup blocked: assistant_scope.intent_classifier.enabled must be true. "
                "Strict mode requires a local classifier model for all routing behavior."
            )

        model_name = str(classifier_config.get("model", "mistral:7b"))
        base_url = str(classifier_config.get("base_url", "http://localhost:11434"))
        timeout_seconds = int(classifier_config.get("request_timeout_seconds", 180))
        max_retries = int(classifier_config.get("max_retries", 1))
        try:
            self._intent_classifier: OllamaAdapter = OllamaAdapter(
                model=model_name,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            )
        except Exception as exc:
            raise AssistantStartupError(
                "Operator assistant startup blocked: failed to initialize local intent classifier "
                f"(model={model_name}, base_url={base_url}). Ensure Ollama is running and the model is installed."
            ) from exc

        fallback_config = classifier_config.get("fallback", {}) if isinstance(classifier_config, dict) else {}
        if isinstance(fallback_config, dict) and bool(fallback_config.get("enabled", False)):
            fallback_model = str(fallback_config.get("model", "")).strip()
            if fallback_model:
                fallback_base_url = str(fallback_config.get("base_url", base_url))
                fallback_timeout_seconds = int(
                    fallback_config.get("request_timeout_seconds", max(10, min(timeout_seconds, 30)))
                )
                fallback_max_retries = int(fallback_config.get("max_retries", 1))
                try:
                    self._intent_classifier_fallback = OllamaAdapter(
                        model=fallback_model,
                        base_url=fallback_base_url,
                        timeout_seconds=fallback_timeout_seconds,
                        max_retries=fallback_max_retries,
                    )
                except Exception as exc:
                    raise AssistantStartupError(
                        "Operator assistant startup blocked: failed to initialize fallback intent classifier "
                        f"(model={fallback_model}, base_url={fallback_base_url}). "
                        "Either fix the fallback model configuration or disable assistant_scope.intent_classifier.fallback.enabled."
                    ) from exc

    def init_session(self) -> Dict[str, Any]:
        return {
            "history": [],
            "feature_messages": [],
            "core_change_authorized": False,
            "core_change_decision_made": False,
            "latest_runtime_request": None,
            "pending_questions": [],
            "last_intent": None,
            "file_reference_questions_asked": [],
        }

    def handle_message(self, text: str, session: Optional[Dict[str, Any]] = None) -> AssistantResponse:
        message = (text or "").strip()
        state = dict(session or self.init_session())
        state.setdefault("history", [])
        state.setdefault("feature_messages", [])
        state.setdefault("core_change_authorized", False)
        state.setdefault("core_change_decision_made", False)
        state.setdefault("latest_runtime_request", None)
        state.setdefault("pending_questions", [])
        state.setdefault("file_reference_questions_asked", [])

        history = state["history"]
        if isinstance(history, list):
            history.append({"role": "user", "text": message})

        self._apply_pending_question_answers(state, message)

        if not message:
            return AssistantResponse(
                intent="out_of_scope",
                confidence=1.0,
                reason="empty_message",
                message="Please enter a request. I can help with nanoporethon features, runtime operations, and repository/code questions.",
                followup_questions=[],
                ready_to_run=False,
                runtime_request=None,
                session_updates=state,
            )

        # Check if we're currently in a feature_request conversation.
        # If so, treat follow-up messages as part of that request (only reject if explicitly out-of-scope).
        in_feature_context = bool(state.get("feature_messages"))
        decision = self.classify_intent(message, in_feature_context=in_feature_context, session_state=state)
        state["last_intent"] = decision.intent

        if decision.intent == "out_of_scope":
            return AssistantResponse(
                intent=decision.intent,
                confidence=decision.confidence,
                reason=decision.reason,
                message=(
                    "I’m scoped to nanoporethon workflows, runtime/agent architecture, and this repository’s code/docs. "
                    "I can’t help with off-topic advice (for example medical, political, financial, legal, or general lifestyle/cooking requests)."
                ),
                followup_questions=[],
                ready_to_run=False,
                runtime_request=None,
                session_updates=state,
            )

        if decision.intent == "feature_request":
            feature_messages = state.get("feature_messages", [])
            if isinstance(feature_messages, list):
                feature_messages.append(message)

            analysis = self._analyze_feature_session_with_model(state)
            state["core_change_authorized"] = bool(state.get("core_change_authorized", False)) or bool(
                analysis.get("core_gui_change_authorized", False)
            )

            followups = self._clarifying_questions(state, analysis)
            request_packet = self._build_runtime_request_from_session(state, analysis)
            state["latest_runtime_request"] = request_packet
            state["pending_questions"] = followups

            ready = len(followups) == 0
            response_msg = (
                "I understood this as a feature implementation request. "
                "I drafted a runtime request from this conversation. It is ready to run now."
                if ready
                else "I understood this as a feature implementation request. I drafted a runtime request. "
                "Please answer the follow-up questions below before running."
            )

            return AssistantResponse(
                intent=decision.intent,
                confidence=decision.confidence,
                reason=decision.reason,
                message=response_msg,
                followup_questions=followups,
                ready_to_run=ready,
                runtime_request=request_packet,
                session_updates=state,
            )

        answer = self._answer_domain_question(message)
        return AssistantResponse(
            intent=decision.intent,
            confidence=decision.confidence,
            reason=decision.reason,
            message=answer,
            followup_questions=[],
            ready_to_run=False,
            runtime_request=None,
            session_updates=state,
        )

    def classify_intent(
        self,
        text: str,
        in_feature_context: bool = False,
        session_state: Optional[Dict[str, Any]] = None,
    ) -> AssistantDecision:
        msg = text.lower().strip()

        # If we're in a feature_request context, treat follow-up messages as part of that request
        # (unless they're explicitly out-of-scope via forbidden patterns, which we already checked).
        if in_feature_context:
            return AssistantDecision("feature_request", 0.88, "in_feature_context_continuation")

        model_decision = self._classify_intent_with_model(msg, session_state=session_state)
        if model_decision:
            return model_decision

        raise RuntimeError(
            "Operator assistant strict mode: intent classifier did not return valid JSON intent output. "
            "Non-LLM routing fallback is disabled."
        )

    def _build_runtime_request_from_session(self, session: Dict[str, Any], analysis: Dict[str, Any]) -> str:
        feature_messages = session.get("feature_messages", [])
        if not isinstance(feature_messages, list):
            feature_messages = []

        request_body = "\n".join(f"- {m}" for m in feature_messages[-8:]) if feature_messages else "- (no feature details captured yet)"
        core_change_authorized = bool(session.get("core_change_authorized", False))

        core_guardrail_line = (
            "- Core GUI changes are explicitly authorized by the user for this request."
            if core_change_authorized
            else (
                "- Do NOT modify core GUI components unless user explicitly authorizes: "
                + ", ".join(self._core_protected_files)
            )
        )

        request_kind = str(analysis.get("request_kind", "code_change"))
        verification_guardrail_line = (
            "- Verification default for code changes: require BOTH automated tests and behavior checks unless user explicitly narrows scope."
            if request_kind in {"code_change", "mixed", "unknown"}
            else "- For non-code changes, include a lightweight behavior/documentation sanity check before closeout."
        )

        return (
            "Conversation-derived request for attended runtime execution:\n\n"
            "User request details:\n"
            f"{request_body}\n\n"
            "Execution guardrails:\n"
            "- Keep runtime attended and operator-reviewed.\n"
            "- Keep changes branch-local until operator-approved promotion/merge.\n"
            f"{core_guardrail_line}\n"
            f"{verification_guardrail_line}\n"
            "- Anti-hallucination quality rubric (mandatory):\n"
            "  - Contract-safe: preserve schema/policy/gate compatibility.\n"
            "  - Evidence-first: run deterministic tests and behavior checks.\n"
            "  - Surface-consistent: sync Docs/components.md and textbook when behavior changes.\n"
            "  - Traceable: append a concise Docs/agent_logs/REQUEST_LOG.md row.\n"
            "  - Scoped: prefer minimal diffs and avoid unrelated refactors.\n"
            "  - Operator-supervised: maintain branch-local, human-reviewed execution.\n"
            "- Update tests/docs/request log as required by repository policy when behavior/contracts change.\n"
        )

    def _answer_domain_question(self, user_text: str) -> str:
        runtime_event_explanation = self._runtime_event_explanation(user_text)
        if runtime_event_explanation:
            return runtime_event_explanation

        snippets = self._retrieve_relevant_snippets(user_text, max_items=3)

        if self.model_adapter is not None and snippets:
            context_text = "\n\n".join(snippets)
            system_prompt = (
                "You are a local nanoporethon operator assistant. "
                "You MUST stay in scope: nanoporethon usage, repository architecture, runtime workflow, and code/docs guidance. "
                "If asked for unrelated advice, refuse and redirect to in-scope help. "
                "Be concise and practical."
            )
            try:
                response = self.model_adapter.chat(
                    system_prompt,
                    [{"role": "user", "content": f"Question:\n{user_text}\n\nContext:\n{context_text}"}],
                )
                if response.strip():
                    return response.strip()
            except Exception:
                # Fall back to deterministic response if local model is unavailable.
                pass

        if snippets:
            return (
                "Here’s what I can tell from local repository docs:\n\n"
                + "\n\n".join(f"- {self._compress_snippet(s)}" for s in snippets)
            )

        return (
            "I can help with nanoporethon workflows, runtime behavior, and code/docs in this repository. "
            "Try asking with repository-specific terms (for example: runtime, stages, policies, docs, tests, or a file/module name)."
        )

    def _runtime_event_explanation(self, user_text: str) -> Optional[str]:
        text = (user_text or "").strip().lower()
        if "promotion_disabled" in text:
            return (
                "`promotion_disabled` means the run completed without applying post-closeout file promotion. "
                "In practice, this happens when runtime promotion is disabled by policy for that run/session. "
                "Your stage outputs and artifacts are still recorded under `.nanopore-runtime/runs/<run_id>/`; "
                "it just means no final promotion step was executed."
            )
        if "promotion_skipped" in text:
            return (
                "`promotion_skipped` means promotion was available but intentionally not applied (for example, operator declined approval)."
            )
        if "promotion_blocked" in text:
            return (
                "`promotion_blocked` means runtime refused promotion due to a guardrail (for example dirty/changed target paths or policy constraints)."
            )
        return None

    def _clarifying_questions(self, session: Dict[str, Any], analysis: Dict[str, Any]) -> List[str]:
        questions = analysis.get("clarifying_questions", [])
        if not isinstance(questions, list):
            questions = []

        file_reference_followup = self._file_reference_followup(session)
        if file_reference_followup:
            return [file_reference_followup]

        planned_core_gui = self._planned_core_gui_changes(session)

        normalized_questions = [str(q).strip() for q in questions if str(q).strip()]
        deduped: List[str] = []
        seen = set()
        for q in normalized_questions:
            if q in seen:
                continue
            seen.add(q)
            deduped.append(q)

        normalized_questions = [
            q
            for q in deduped
            if not self._is_core_gui_authorization_question(q)
            and not (self._is_core_gui_related_question(q) and not planned_core_gui["files"])
        ]

        actionable_request = self._request_seems_actionable(session, analysis)
        blocked_without_clarification = self._request_is_blocked(session, analysis)

        normalized_questions = [
            q for q in normalized_questions if not self._is_generic_expected_behavior_question(q)
        ]

        needs_core_gui_authorization = (
            bool(planned_core_gui["files"])
            and not bool(session.get("core_change_authorized", False))
            and not bool(session.get("core_change_decision_made", False))
        )
        if needs_core_gui_authorization:
            return [
                self._core_gui_authorization_prompt(
                    files=planned_core_gui["files"],
                    reason=planned_core_gui["reason"],
                )
            ]

        if not blocked_without_clarification or actionable_request:
            return []

        return normalized_questions[:1]

    def _file_reference_followup(self, session: Dict[str, Any]) -> Optional[str]:
        feature_messages = session.get("feature_messages", [])
        if not isinstance(feature_messages, list) or not feature_messages:
            return None

        combined = "\n".join(str(msg) for msg in feature_messages)
        candidates = self._extract_file_candidates(combined)
        if not candidates:
            return None

        asked = session.get("file_reference_questions_asked", [])
        if not isinstance(asked, list):
            asked = []

        search_roots = self._discover_reference_search_roots(combined)

        for candidate in candidates:
            if not candidate.lower().endswith(".m"):
                continue
            if candidate in asked:
                continue

            suggestion = self._find_reference_alternative(candidate, search_roots)
            if not suggestion:
                continue

            asked.append(candidate)
            session["file_reference_questions_asked"] = asked
            return (
                f"I couldn't find `{candidate}` as referenced, but I found a near match `{suggestion}`. "
                "Should I use that as the source reference for the Python rewrite?"
            )

        return None

    def _extract_file_candidates(self, text: str) -> List[str]:
        pattern = r"([A-Za-z0-9_./\\-]+\.[A-Za-z0-9_]+)"
        matches = re.findall(pattern, text)
        unique = OrderedDict()
        for match in matches:
            candidate = str(match).strip().strip("'\"`)")
            if not candidate:
                continue
            unique[candidate] = None
        return list(unique.keys())

    def _discover_reference_search_roots(self, text: str) -> List[Path]:
        roots: List[Path] = []

        def _add_root(path: Path) -> None:
            resolved = path.expanduser().resolve()
            if resolved.exists() and resolved.is_dir() and resolved not in roots:
                roots.append(resolved)

        _add_root(self.repo_root)

        lower = text.lower()
        downloads_dir = Path.home() / "Downloads"
        if "downloads folder" in lower:
            _add_root(downloads_dir)

        named_dir_matches = re.findall(r"directory\s+(?:called|named)\s+([A-Za-z0-9_.-]+)", text, flags=re.IGNORECASE)
        for name in named_dir_matches:
            if downloads_dir.exists():
                _add_root(downloads_dir / name)

        abs_path_matches = re.findall(r"(/[^\s'\"`]+)", text)
        for raw in abs_path_matches:
            path = Path(raw)
            if path.suffix:
                if path.parent.exists() and path.parent.is_dir() and path.parent not in roots:
                    roots.append(path.parent.resolve())
            else:
                _add_root(path)

        return roots

    def _find_reference_alternative(self, candidate: str, roots: List[Path]) -> Optional[str]:
        candidate_path = Path(candidate)
        candidate_name = candidate_path.name or candidate
        stem = candidate_path.stem
        if not stem:
            return None

        # If exact target already exists in one of the search roots, no clarification needed.
        for root in roots:
            exact = root / candidate_name
            if exact.exists() and exact.is_file():
                return None

        alternatives = [f"{stem}.mlapp", f"{stem}.mlx", f"{stem}.m"]
        for root in roots:
            for alt in alternatives:
                path = root / alt
                if path.exists() and path.is_file() and alt != candidate_name:
                    return str(path)

        for root in roots:
            for ext in [".mlapp", ".mlx", ".m"]:
                path = root / f"{stem}{ext}"
                if path.exists() and path.is_file() and path.name != candidate_name:
                    return str(path)

        return None

    def _core_gui_authorization_prompt(self, files: List[str], reason: str) -> str:
        file_list = ", ".join(files)
        return (
            f"I think this task may require changing protected file(s): {file_list}. "
            f"Planned reason: {reason} "
            "Is it okay for the agent to modify those file(s) for this task?"
        )

    def _is_core_gui_authorization_question(self, question: str) -> bool:
        q = (question or "").strip().lower()
        if not q:
            return False
        core_tokens = ["data_navi_gui", "event_classifier_gui", "core gui", "protected file"]
        intent_tokens = ["allow", "allowed", "modify", "necessary", "interact", "okay"]
        return any(token in q for token in core_tokens) and any(token in q for token in intent_tokens)

    def _is_core_gui_related_question(self, question: str) -> bool:
        q = (question or "").strip().lower()
        if not q:
            return False
        related_tokens = [
            "data_navi_gui",
            "event_classifier_gui",
            "data navigator gui",
            "event classifier gui",
            "protected core gui",
            "core gui",
        ]
        return any(token in q for token in related_tokens)

    def _planned_core_gui_changes(self, session: Dict[str, Any]) -> Dict[str, Any]:
        feature_messages = session.get("feature_messages", [])
        if not isinstance(feature_messages, list):
            return {"files": [], "reason": ""}

        combined = "\n".join(str(msg) for msg in feature_messages)
        lower = combined.lower()
        files: List[str] = []
        for file_path, hints in _CORE_GUI_FILE_HINTS.items():
            if any(hint in lower for hint in hints):
                files.append(file_path)

        if not files:
            return {"files": [], "reason": ""}

        latest_message = str(feature_messages[-1]).strip()
        reason = (
            f"the request references behavior tied to these GUI surfaces ({latest_message})"
            if latest_message
            else "the request references behavior tied to these GUI surfaces"
        )
        return {"files": files, "reason": reason}

    def _is_generic_expected_behavior_question(self, question: str) -> bool:
        q = (question or "").strip().lower()
        generic_markers = [
            "concrete example",
            "expected behavior",
            "expected output",
            "what should happen",
            "what output should",
        ]
        return any(marker in q for marker in generic_markers)

    def _request_seems_actionable(self, session: Dict[str, Any], analysis: Dict[str, Any]) -> bool:
        feature_messages = session.get("feature_messages", [])
        if not isinstance(feature_messages, list) or not feature_messages:
            return False

        combined = "\n".join(str(msg) for msg in feature_messages[-8:]).lower()
        request_kind = str(analysis.get("request_kind", "unknown")).strip().lower()

        if request_kind == "unknown":
            return False

        action_tokens = [
            "add",
            "build",
            "create",
            "generate",
            "implement",
            "modify",
            "refactor",
            "update",
            "fix",
            "export",
        ]
        target_tokens = [
            "file",
            "gui",
            "module",
            "runtime",
            "feature",
            "button",
            "function",
            "class",
            "csv",
            "docs",
            "test",
            "policy",
        ]

        has_action = any(token in combined for token in action_tokens)
        has_target = any(token in combined for token in target_tokens)
        enough_detail = len(combined.split()) >= 6

        return has_action and (has_target or enough_detail)

    def _request_is_blocked(self, session: Dict[str, Any], analysis: Dict[str, Any]) -> bool:
        feature_messages = session.get("feature_messages", [])
        if not isinstance(feature_messages, list) or not feature_messages:
            return True

        request_kind = str(analysis.get("request_kind", "unknown")).strip().lower()
        if self._request_seems_actionable(session, analysis):
            return False

        latest_message = str(feature_messages[-1]).strip().lower()
        if len(latest_message.split()) <= 3:
            return True

        if request_kind == "unknown":
            return True

        vague_markers = {
            "something",
            "stuff",
            "thing",
            "things",
            "workflow tweak",
            "help",
            "improve",
        }
        return any(marker in latest_message for marker in vague_markers)

    def _looks_yes(self, message: str) -> bool:
        msg = (message or "").lower()
        return bool(
            re.search(
                r"\b(yes|yep|yeah|allow|allowed|authorize|authorized|permission granted)\b",
                msg,
            )
        )

    def _looks_no(self, message: str) -> bool:
        msg = (message or "").lower()
        return bool(re.search(r"\b(no|nope|nah|do not|don't|dont|not allowed)\b", msg))

    def _apply_pending_question_answers(self, session: Dict[str, Any], message: str) -> None:
        pending = session.get("pending_questions", [])
        if not isinstance(pending, list) or not pending:
            return

        has_core_question = any(self._is_core_gui_authorization_question(str(q)) for q in pending)
        if not has_core_question:
            return

        if self._looks_yes(message):
            session["core_change_authorized"] = True
            session["core_change_decision_made"] = True
        elif self._looks_no(message):
            session["core_change_authorized"] = False
            session["core_change_decision_made"] = True

    def _analyze_feature_session_with_model(self, session: Dict[str, Any]) -> Dict[str, Any]:
        default_payload: Dict[str, Any] = {
            "request_kind": "code_change",
            "core_gui_change_requested": False,
            "core_gui_change_authorized": False,
            "clarifying_questions": [],
        }

        feature_messages = session.get("feature_messages", [])
        if not isinstance(feature_messages, list):
            raise RuntimeError(
                "Operator assistant strict mode: feature session state is invalid and cannot be analyzed."
            )

        conversation = "\n".join(f"- {str(msg)}" for msg in feature_messages[-12:])
        system_prompt = (
            "You are a semantic analyzer for a local coding assistant. "
            "Infer request characteristics from the conversation (no keyword matching). "
            "Return ONLY valid JSON with keys: "
            "request_kind, core_gui_change_requested, core_gui_change_authorized, clarifying_questions. "
            "Rules: request_kind must be one of [code_change, docs_only, mixed, unknown]. "
            "If core GUI files are likely targeted, set core_gui_change_requested=true. "
            "If the user explicitly authorizes those core GUI edits, set core_gui_change_authorized=true. "
            "clarifying_questions must be an array of 0-3 concise strings and should only include genuinely missing details."
        )

        user_prompt = (
            "Protected core GUI files:\n"
            "- src/nanoporethon/data_navi_gui.py\n"
            "- src/nanoporethon/event_classifier_gui.py\n\n"
            "Feature conversation:\n"
            f"{conversation}\n"
        )

        try:
            payload = self._chat_json_with_classifier_fallback(
                system_prompt,
                [{"role": "user", "content": user_prompt}],
                operation_name="session-analysis",
                required_keys=[
                    "request_kind",
                    "core_gui_change_requested",
                    "core_gui_change_authorized",
                    "clarifying_questions",
                ],
            )
            request_kind = str(payload.get("request_kind", "unknown")).strip().lower()
            if request_kind not in {"code_change", "docs_only", "mixed", "unknown"}:
                request_kind = "unknown"
            questions_raw = payload.get("clarifying_questions", [])
            clarifying_questions = questions_raw if isinstance(questions_raw, list) else []

            return {
                "request_kind": request_kind,
                "core_gui_change_requested": bool(payload.get("core_gui_change_requested", False)),
                "core_gui_change_authorized": bool(payload.get("core_gui_change_authorized", False)),
                "clarifying_questions": [str(q).strip() for q in clarifying_questions if str(q).strip()][:3],
            }
        except RuntimeError as exc:
            raise RuntimeError(
                "Operator assistant strict mode: session-analysis model did not return valid JSON. "
                "Non-LLM analysis fallback is disabled. "
                f"Details: {exc}"
            ) from exc

    def _looks_information_question(self, msg: str) -> bool:
        return "?" in msg

    def _classify_intent_with_model(
        self,
        text: str,
        session_state: Optional[Dict[str, Any]] = None,
    ) -> Optional[AssistantDecision]:
        """Use local model for semantic intent classification with JSON structure.

        Strict mode requires a valid structured response from at least one
        configured classifier adapter (primary and optional fallback).
        """
        if not self._intent_classifier:
            return None

        system_prompt = (
            "You are a semantic intent classifier for a code assistant. "
            "Analyze the user message semantically and classify it as one of: feature_request, "
            "runtime_help, code_explanation, repo_question, or out_of_scope. "
            "Treat nanoporethon/repository/runtime/code/docs assistance as in scope. "
            "Treat unrelated lifestyle, medical, political, legal, or investing requests as out_of_scope. "
            "Respond with ONLY valid JSON (no markdown, no explanation): "
            '{"intent": "...", "confidence": 0.X, "reason": "..."}'
        )

        classifier_messages = self._build_classifier_messages(text, session_state=session_state)

        payload = self._chat_json_with_classifier_fallback(
            system_prompt,
            classifier_messages,
            operation_name="intent-classification",
            required_keys=["intent", "confidence", "reason"],
        )

        try:
            intent = str(payload.get("intent", "")).lower().strip()
            confidence = float(payload.get("confidence", 0.0))
            reason = str(payload.get("reason", "model_classified"))

            if intent in {
                "feature_request",
                "runtime_help",
                "code_explanation",
                "repo_question",
                "out_of_scope",
            }:
                return AssistantDecision(intent, confidence, reason)

            raise RuntimeError(
                "Operator assistant strict mode: classifier returned an unsupported intent value "
                f"('{intent}')."
            )
        except (ValueError, KeyError, AttributeError) as exc:
            raise RuntimeError(
                "Operator assistant strict mode: classifier returned malformed structured output. "
                f"Details: {exc}"
            ) from exc

        return None

    def _build_classifier_messages(
        self,
        text: str,
        session_state: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        if not isinstance(session_state, dict):
            return [{"role": "user", "content": text}]

        history = session_state.get("history", [])
        if not isinstance(history, list):
            history = []
        history_tail = history[-8:]
        rendered_history: List[str] = []
        for item in history_tail:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "user")).strip().lower() or "user"
            content = str(item.get("text", "")).strip()
            if content:
                rendered_history.append(f"{role}: {content}")

        pending_questions = session_state.get("pending_questions", [])
        if not isinstance(pending_questions, list):
            pending_questions = []
        pending_tail = [str(q).strip() for q in pending_questions[:3] if str(q).strip()]

        feature_messages = session_state.get("feature_messages", [])
        feature_count = len(feature_messages) if isinstance(feature_messages, list) else 0
        latest_runtime_request = bool(session_state.get("latest_runtime_request"))
        last_intent = str(session_state.get("last_intent", "")).strip() or "none"

        history_text = "\n".join(f"- {line}" for line in rendered_history) if rendered_history else "- (no prior messages)"
        pending_text = "\n".join(f"- {line}" for line in pending_tail) if pending_tail else "- (none)"

        content = (
            f"Current user message:\n{text}\n\n"
            "Recent conversation context:\n"
            f"{history_text}\n\n"
            "Session signals:\n"
            f"- last_intent: {last_intent}\n"
            f"- feature_message_count: {feature_count}\n"
            f"- latest_runtime_request_present: {str(latest_runtime_request).lower()}\n"
            "Pending follow-up questions:\n"
            f"{pending_text}\n"
        )
        return [{"role": "user", "content": content}]

    def _chat_json_with_classifier_fallback(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        operation_name: str,
        required_keys: List[str],
    ) -> Dict[str, Any]:
        adapters: List[Tuple[str, Optional[Any]]] = [
            ("primary", self._intent_classifier),
            ("fallback", self._intent_classifier_fallback),
        ]

        errors: List[str] = []
        for label, adapter in adapters:
            if adapter is None:
                continue
            model_name = getattr(adapter, "model", "unknown")
            try:
                payload = _chat_json_response(adapter, system_prompt, messages)
                missing = [key for key in required_keys if key not in payload]
                if missing:
                    errors.append(
                        f"{label} classifier ({model_name}) missing keys: {', '.join(missing)}"
                    )
                    continue
                return payload
            except Exception as exc:
                errors.append(f"{label} classifier ({model_name}) failed: {exc}")

        if not errors:
            raise RuntimeError(
                f"Operator assistant strict mode: no classifier adapters available for {operation_name}."
            )
        raise RuntimeError(
            f"Operator assistant strict mode: all {operation_name} classifier attempts failed. "
            "Diagnostics: " + " | ".join(errors)
        )

    def _load_docs(self) -> Dict[str, str]:
        cache: Dict[str, str] = {}
        for rel in _DEFAULT_DOC_FILES:
            path = self.repo_root / rel
            if not path.exists() or not path.is_file():
                continue
            try:
                cache[rel] = path.read_text(encoding="utf-8")
            except OSError:
                continue
        return cache

    def _retrieve_relevant_snippets(self, query: str, max_items: int = 3) -> List[str]:
        terms = self._query_terms(query)
        scored: List[Tuple[int, str, str]] = []
        for rel, text in self._doc_cache.items():
            lower = text.lower()
            score = sum(lower.count(term) for term in terms)
            if score <= 0:
                continue
            snippet = text[:900].strip()
            scored.append((score, rel, snippet))

        scored.sort(key=lambda t: t[0], reverse=True)
        selected = scored[:max_items]
        return [f"[{rel}] {snippet}" for _, rel, snippet in selected]

    def _query_terms(self, query: str) -> List[str]:
        words = [w for w in re.split(r"[^a-zA-Z0-9_]+", query.lower()) if len(w) >= 3]
        stop = {"the", "and", "for", "with", "that", "this", "how", "what", "when", "where", "why"}
        return [w for w in words if w not in stop][:10]

    def _compress_snippet(self, snippet: str) -> str:
        s = " ".join(snippet.split())
        if len(s) <= 280:
            return s
        return s[:277] + "..."
