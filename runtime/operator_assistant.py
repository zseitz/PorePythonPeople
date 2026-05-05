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
        try:
            self._intent_classifier: OllamaAdapter = OllamaAdapter(model=model_name, base_url=base_url)
        except Exception as exc:
            raise AssistantStartupError(
                "Operator assistant startup blocked: failed to initialize local intent classifier "
                f"(model={model_name}, base_url={base_url}). Ensure Ollama is running and the model is installed."
            ) from exc

    def init_session(self) -> Dict[str, Any]:
        return {
            "history": [],
            "feature_messages": [],
            "core_change_authorized": False,
            "latest_runtime_request": None,
            "pending_questions": [],
        }

    def handle_message(self, text: str, session: Optional[Dict[str, Any]] = None) -> AssistantResponse:
        message = (text or "").strip()
        state = dict(session or self.init_session())
        state.setdefault("history", [])
        state.setdefault("feature_messages", [])
        state.setdefault("core_change_authorized", False)
        state.setdefault("latest_runtime_request", None)
        state.setdefault("pending_questions", [])

        history = state["history"]
        if isinstance(history, list):
            history.append({"role": "user", "text": message})

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
        decision = self.classify_intent(message, in_feature_context=in_feature_context)

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
                "I drafted a runtime request from this conversation. "
                "You can run it now, or answer the follow-up questions first for better precision."
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

    def classify_intent(self, text: str, in_feature_context: bool = False) -> AssistantDecision:
        msg = text.lower().strip()

        # If we're in a feature_request context, treat follow-up messages as part of that request
        # (unless they're explicitly out-of-scope via forbidden patterns, which we already checked).
        if in_feature_context:
            return AssistantDecision("feature_request", 0.88, "in_feature_context_continuation")

        model_decision = self._classify_intent_with_model(msg)
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
            "- Update tests/docs/request log as required by repository policy when behavior/contracts change.\n"
        )

    def _answer_domain_question(self, user_text: str) -> str:
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

    def _clarifying_questions(self, session: Dict[str, Any], analysis: Dict[str, Any]) -> List[str]:
        questions = analysis.get("clarifying_questions", [])
        if not isinstance(questions, list):
            questions = []

        normalized_questions = [str(q).strip() for q in questions if str(q).strip()]

        needs_core_gui_authorization = bool(analysis.get("core_gui_change_requested", False)) and not bool(
            session.get("core_change_authorized", False)
        )
        if needs_core_gui_authorization:
            normalized_questions.append(
                "Your request appears to involve core GUI behavior. Should the agent be allowed to modify "
                "src/nanoporethon/data_navi_gui.py and/or src/nanoporethon/event_classifier_gui.py for this task?"
            )

        # Remove duplicates while preserving order.
        deduped: List[str] = []
        seen = set()
        for q in normalized_questions:
            if q in seen:
                continue
            seen.add(q)
            deduped.append(q)
        return deduped

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
            response = self._intent_classifier.chat(
                system_prompt,
                [{"role": "user", "content": user_prompt}],
            )
            payload = json.loads(response.strip())
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
        except (json.JSONDecodeError, ValueError, KeyError, AttributeError) as exc:
            raise RuntimeError(
                "Operator assistant strict mode: session-analysis model did not return valid JSON. "
                "Non-LLM analysis fallback is disabled."
            ) from exc

    def _looks_information_question(self, msg: str) -> bool:
        return "?" in msg

    def _classify_intent_with_model(self, text: str) -> Optional[AssistantDecision]:
        """Use local model for semantic intent classification with JSON structure.

        Falls back to None if model unavailable or fails, triggering rule-based fallback.
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

        try:
            response = self._intent_classifier.chat(
                system_prompt,
                [{"role": "user", "content": text}],
            )
            payload = json.loads(response.strip())
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
        except (json.JSONDecodeError, ValueError, KeyError, AttributeError):
            # Model failed to return valid JSON or parse error; fall back to rules.
            pass

        return None

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
