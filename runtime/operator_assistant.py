"""Local operator assistant for attended runtime workflows.

Chat-first Option-B implementation:
- semantic scope routing with grounded answer modes
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
from typing import Dict, List, Optional, Tuple, Any, Set

from .adapters.ollama import OllamaAdapter


_DEFAULT_GROUNDING_FILES = [
    "README.md",
    "Docs/components.md",
    "Docs/nanoporethon_textbook.md",
    "Docs/UseCases.md",
    "Docs/UserPersonas.md",
    "Docs/technology_context.md",
    "Docs/feature_request_template.md",
    "Docs/papers/README.md",
    "runtime/policies.yaml",
    "runtime/operator_assistant.py",
    "src/nanoporethon/sequence_designer_gui.py",
]

_DEFAULT_DOMAIN_ANCHORS = [
    "nanoporethon",
    "nanopore",
    "pore",
    "workflow",
    "experiment",
    "experiments",
    "folder",
    "folders",
    "event quality",
    "gui",
    "runtime",
    "orchestrator",
    "operator assistant",
    "stage",
    "gate",
    "policy",
    "promotion",
    "docs",
    "tests",
    "repo",
    "repository",
    "qmer",
    "q-mer",
    "hel308",
    "sequence designer",
    "event classifier",
    "data navigator",
    "trace",
    "signal",
    "current",
    "consensus",
    "matlab",
    ".py",
    ".md",
    ".yaml",
    ".json",
    ".m",
    ".mlapp",
]

_DEFAULT_SENSITIVE_DOMAINS = [
    "medical or diagnostic advice",
    "legal advice",
    "financial or investment advice",
    "political persuasion",
    "general lifestyle or relationship counseling",
]

_DEFAULT_REPO_GOAL_TERMS = [
    "nanopore",
    "nanoporethon",
    "event classifier",
    "data navigator",
    "runtime",
    "orchestrator",
    "policy",
    "stage",
    "gate",
    "promotion",
    "repository",
    "repo",
    "documentation",
    "docs",
    "code",
    "python",
    "test",
    "gui",
    "sequence",
    "trace",
    "signal",
    "q-mer",
    "qmer",
    "matlab",
    "event.mat",
    "reduced.mat",
    "meta.mat",
    "csv",
    "export",
]

_ALLOWED_INTENTS = {
    "feature_request",
    "runtime_help",
    "code_explanation",
    "repo_question",
    "nanopore_science_explanation",
    "out_of_scope",
}

_GROUNDED_ANSWER_INTENTS = {
    "runtime_help",
    "code_explanation",
    "repo_question",
    "nanopore_science_explanation",
}


@dataclass
class AssistantDecision:
    intent: str
    confidence: float
    reason: str
    scope_class: str = "unknown"
    sensitivity_class: str = "normal"
    domain_anchor_present: bool = False
    grounding_required: bool = False
    allowed_response_mode: str = "refuse"
    should_ask_clarifying_question: bool = False
    clarifying_question: str = ""


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
        self._grounding_files = self._load_grounding_files_from_policy()
        self._domain_anchors = self._load_domain_anchors_from_policy()
        self._sensitive_domains = self._load_sensitive_domains_from_policy()
        self._repo_goal_terms = self._load_repo_goal_terms_from_policy()
        self._doc_cache = self._load_docs()
        self._known_python_modules = self._load_known_python_modules()
        self._intent_cache: Dict[str, Tuple[str, float, str]] = {}
        self._intent_classifier: Optional[Any] = None
        self._intent_classifier_fallback: Optional[OllamaAdapter] = None
        self._configure_intent_classifiers()

        self._core_gui_file_hints = self._load_protected_file_hints_from_policy()
        self._core_protected_files = sorted(self._core_gui_file_hints.keys())

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
            "scope_relevance_misses": 0,
            "auto_deepness_enabled": True,
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
        state.setdefault("scope_relevance_misses", 0)
        state.setdefault("auto_deepness_enabled", True)

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

        # Continue feature context only when follow-up stays topical and in-scope.
        in_feature_context = self._should_continue_feature_context(message, state)
        if bool(state.get("feature_messages")) and not in_feature_context:
            self._reset_feature_context(state)

        decision = self.classify_intent(message, in_feature_context=in_feature_context, session_state=state)
        state["last_intent"] = decision.intent
        state["last_scope_class"] = decision.scope_class

        if decision.allowed_response_mode == "refuse" or decision.intent == "out_of_scope":
            self._reset_feature_context(state)
            interactive_redirect = (
                " If you intended a PorePythonPeople question, mention a repository file, GUI workflow, runtime stage, or docs section and I’ll help from there."
                if decision.reason
                in {
                    "question_without_repo_relevance",
                    "feature_request_without_repo_relevance",
                    "statement_without_repo_relevance",
                }
                else ""
            )
            followups = (
                [
                    "If this is about PorePythonPeople, what file/workflow should I anchor to (for example `event_classifier_gui.py`, DataNaviGUI, runtime policy, or docs)?"
                ]
                if interactive_redirect
                else []
            )
            refusal_tail = (
                "I also can’t help with sensitive advisory requests such as medical, legal, financial, or political guidance."
                if decision.sensitivity_class == "blocked"
                else "I can’t help with unrelated requests outside those repository/runtime roles."
            )
            return AssistantResponse(
                intent="out_of_scope",
                confidence=decision.confidence,
                reason=decision.reason,
                message=(
                    "I’m scoped to nanoporethon workflows, runtime/agent architecture, and this repository’s code/docs. "
                    f"{refusal_tail}{interactive_redirect}"
                ),
                followup_questions=followups,
                ready_to_run=False,
                runtime_request=None,
                session_updates=state,
            )

        if decision.allowed_response_mode == "clarify" and decision.clarifying_question:
            return AssistantResponse(
                intent=decision.intent,
                confidence=decision.confidence,
                reason=decision.reason,
                message=decision.clarifying_question,
                followup_questions=[decision.clarifying_question],
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

        deep_mode = self._should_enable_deep_mode(state, message, decision)
        answer = self._answer_domain_question(message, decision=decision, deep_mode=deep_mode)
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

        # Continue feature requests across follow-up turns only when pre-validated.
        if in_feature_context:
            return AssistantDecision(
                "feature_request",
                0.88,
                "conditional_feature_context_continuation",
                scope_class="repo_workflow",
                sensitivity_class="normal",
                domain_anchor_present=True,
                grounding_required=False,
                allowed_response_mode="feature_request",
            )

        if self._intent_classifier is not None:
            try:
                model_decision = self._classify_intent_with_model(text, session_state=session_state)
            except RuntimeError:
                model_decision = None
            if model_decision is not None:
                return self._apply_model_decision_guardrails(model_decision, text, session_state=session_state)

        return self._classify_intent_simple(msg, session_state=session_state)

    def _apply_model_decision_guardrails(
        self,
        decision: AssistantDecision,
        text: str,
        session_state: Optional[Dict[str, Any]] = None,
    ) -> AssistantDecision:
        if decision.intent == "out_of_scope":
            return decision

        relevance = self._assess_repo_relevance(text, session_state=session_state)
        if relevance["is_relevant"]:
            return decision

        if decision.intent == "feature_request":
            return AssistantDecision(
                intent="out_of_scope",
                confidence=max(0.85, decision.confidence),
                reason="model_feature_request_without_repo_relevance",
                scope_class="out_of_scope",
                sensitivity_class="normal",
                domain_anchor_present=False,
                grounding_required=False,
                allowed_response_mode="refuse",
            )

        return AssistantDecision(
            intent="out_of_scope",
            confidence=max(0.85, decision.confidence),
            reason="model_question_without_repo_relevance",
            scope_class="out_of_scope",
            sensitivity_class="normal",
            domain_anchor_present=False,
            grounding_required=False,
            allowed_response_mode="refuse",
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
            if self._core_protected_files
            else "- Protected file restrictions: none configured in assistant policy."
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

    def _answer_domain_question(
        self,
        user_text: str,
        decision: Optional[AssistantDecision] = None,
        deep_mode: bool = False,
    ) -> str:
        runtime_event_explanation = self._runtime_event_explanation(user_text)
        if runtime_event_explanation:
            return runtime_event_explanation

        model_routing_explanation = self._model_routing_explanation(user_text)
        if model_routing_explanation:
            return model_routing_explanation

        scope_class = decision.scope_class if decision is not None else "repo_knowledge"
        snippet_limit = 5 if deep_mode else 3
        snippets = self._retrieve_relevant_snippets(user_text, max_items=snippet_limit, scope_class=scope_class)

        if decision is not None and decision.grounding_required and not snippets:
            return self._ungrounded_answer_message(decision)

        if deep_mode and snippets:
            deep_response = self._synthesize_deep_grounded_answer(
                user_text=user_text,
                snippets=snippets,
                scope_class=scope_class,
            )
            if deep_response:
                return deep_response

        if self.model_adapter is not None and snippets:
            response = self._answer_with_grounded_model(
                user_text=user_text,
                snippets=snippets,
                scope_class=scope_class,
            )
            if response:
                return response

        if snippets:
            synthesized = self._synthesize_grounded_answer(user_text=user_text, snippets=snippets, scope_class=scope_class)
            if synthesized:
                return synthesized
            intro = "Here’s what I can tell from local repository docs and code:"
            if scope_class == "nanopore_science":
                intro = "Here’s the nanoporethon-grounded explanation I can support from local docs/code:"
            elif scope_class == "runtime_operations":
                intro = "Here’s the runtime-grounded explanation I can support from local docs/code:"
            return (
                f"{intro}\n\n"
                + "\n\n".join(f"- {self._compress_snippet(s)}" for s in snippets)
            )

        return self._ungrounded_answer_message(decision)

    def _should_enable_deep_mode(
        self,
        session_state: Dict[str, Any],
        current_message: str,
        decision: Optional[AssistantDecision],
    ) -> bool:
        if not bool(session_state.get("auto_deepness_enabled", True)):
            return False

        if decision is None or decision.intent not in _GROUNDED_ANSWER_INTENTS:
            return False

        history = session_state.get("history", [])
        if not isinstance(history, list):
            return False

        user_messages = [
            str(item.get("text", ""))
            for item in history
            if isinstance(item, dict) and str(item.get("role", "")).lower() == "user"
        ]
        if not user_messages:
            return False

        recent = user_messages[-5:]
        question_like_count = sum(1 for msg in recent if self._is_question_like_message(msg))
        return len(recent) >= 3 and question_like_count >= 3 and self._is_question_like_message(current_message)

    def _is_question_like_message(self, text: str) -> bool:
        msg = (text or "").strip().lower()
        if not msg:
            return False
        if "?" in msg:
            return True
        starters = ("how ", "what ", "why ", "when ", "where ", "can ", "could ", "would ", "should ", "is ", "are ")
        return msg.startswith(starters)

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

    def _model_routing_explanation(self, user_text: str) -> Optional[str]:
        text = (user_text or "").strip().lower()
        if not any(token in text for token in ["model", "models", "quant", "quantized", "quantization"]):
            return None

        model_provider = self.policy.get("model_provider", {}) if isinstance(self.policy, dict) else {}
        specialists = self.policy.get("specialists", {}) if isinstance(self.policy, dict) else {}
        if not isinstance(model_provider, dict) or not isinstance(specialists, dict):
            return None

        global_model = str(model_provider.get("model", "")).strip()
        lines: List[str] = ["Here’s the current model map from local runtime policy:", ""]

        if global_model:
            lines.append(f"- Global default / inherited model: `{global_model}`")

        summary_parts: List[str] = []

        explicit_overrides: List[str] = []
        inherited: List[str] = []
        for name, cfg in sorted(specialists.items()):
            if not isinstance(cfg, dict):
                continue
            provider_cfg = cfg.get("model_provider", {})
            if isinstance(provider_cfg, dict) and str(provider_cfg.get("model", "")).strip():
                explicit_overrides.append(f"- `{name}` → `{provider_cfg.get('model')}`")
            else:
                inherited.append(f"- `{name}` (inherits the global default)")

        if global_model:
            summary_parts.append(f"the global default is `{global_model}`")
        if explicit_overrides:
            summary_parts.append("feature_builder/refactor use `qwen3:4b`")
        if inherited:
            summary_parts.append("orchestrator/verifier inherit the global default")

        if summary_parts:
            lines.extend(["", "Short answer: " + "; ".join(summary_parts) + "."])

        if explicit_overrides:
            lines.extend(["", "- Explicit specialist overrides:"])
            lines.extend(explicit_overrides)

        if inherited:
            lines.extend(["", "- Specialists inheriting the global default:"])
            lines.extend(inherited)

        quant_notes: List[str] = []
        textbook = self._doc_cache.get("Docs/nanoporethon_textbook.md", "")
        if textbook and any(token in textbook for token in ["Q4_K_M", "qwen2.5:3b", "qwen3:4b"]):
            quant_notes.append(
                "Docs/nanoporethon_textbook.md records `qwen2.5:3b` and `qwen3:4b` as `Q4_K_M` on the machine used for that documentation update."
            )

        if quant_notes:
            lines.extend(["", "Quantization notes from local docs:"])
            lines.extend(f"- {note}" for note in quant_notes)

        if global_model:
            lines.extend(["", "If you want the exact live artifact build on this machine, check the local Ollama metadata for the model names above."])

        return "\n".join(lines).strip()

    def _answer_with_grounded_model(self, user_text: str, snippets: List[str], scope_class: str) -> Optional[str]:
        context_text = "\n\n".join(snippets)
        system_prompt = (
            "You are a repository-grounded assistant for PorePythonPeople. "
            "Answer using ONLY the provided context excerpts. "
            "If context is insufficient, say that directly. "
            "Return ONLY JSON with keys: answer (string), evidence_quotes (array of exact quotes copied from context), "
            "and uncertainties (array of strings)."
        )
        try:
            payload = _chat_json_response(
                self.model_adapter,
                system_prompt,
                [
                    {
                        "role": "user",
                        "content": (
                            f"Question:\n{user_text}\n\n"
                            f"Requested scope class: {scope_class}\n"
                            f"Context excerpts:\n{context_text}"
                        ),
                    }
                ],
            )
        except Exception:
            return None

        answer = str(payload.get("answer", "")).strip()
        if not answer:
            return None

        if self._contains_unverifiable_module_claim(answer):
            return None

        quotes_raw = payload.get("evidence_quotes", [])
        quotes = [str(q).strip() for q in quotes_raw if str(q).strip()] if isinstance(quotes_raw, list) else []
        valid_quotes = [q for q in quotes if self._quote_in_context(q, context_text)]
        if not valid_quotes:
            return None

        return answer

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
        for file_path in self._core_protected_files:
            stem = Path(file_path).stem.lower()
            core_tokens.append(stem)
        return any(token in q for token in core_tokens) and any(token in q for token in intent_tokens)

    def _is_core_gui_related_question(self, question: str) -> bool:
        q = (question or "").strip().lower()
        if not q:
            return False
        related_tokens = [
            "protected core gui",
            "core gui",
        ]
        for hints in self._core_gui_file_hints.values():
            related_tokens.extend(str(hint).lower() for hint in hints)
        return any(token in q for token in related_tokens)

    def _planned_core_gui_changes(self, session: Dict[str, Any]) -> Dict[str, Any]:
        feature_messages = session.get("feature_messages", [])
        if not isinstance(feature_messages, list):
            return {"files": [], "reason": ""}

        combined = "\n".join(str(msg) for msg in feature_messages)
        lower = combined.lower()
        files: List[str] = []
        for file_path, hints in self._core_gui_file_hints.items():
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
        feature_messages = session.get("feature_messages", [])
        if not isinstance(feature_messages, list):
            feature_messages = []

        combined = "\n".join(str(msg) for msg in feature_messages[-12:]).lower()
        planned_core = self._planned_core_gui_changes(session)

        docs_markers = {"readme", "docs/", "documentation", "textbook", "components.md"}
        code_markers = {
            "python",
            ".py",
            "module",
            "function",
            "class",
            "runtime",
            "gui",
            "test",
            "feature",
            "implement",
            "refactor",
            "fix",
            "add",
            "create",
            "build",
            "modify",
            "update",
            "export",
        }

        has_docs = any(marker in combined for marker in docs_markers)
        has_code = any(marker in combined for marker in code_markers)
        if has_docs and not has_code:
            request_kind = "docs_only"
        elif has_docs and has_code:
            request_kind = "mixed"
        elif has_code:
            request_kind = "code_change"
        else:
            request_kind = "unknown"

        lowered_messages = [str(msg).lower() for msg in feature_messages]
        auth_phrases = (
            "you can modify",
            "you may modify",
            "authorized to modify",
            "permission granted",
            "allowed to modify",
        )
        core_authorized = any(
            any(auth in msg for auth in auth_phrases)
            and any(Path(path).stem.lower() in msg or path.lower() in msg for path in planned_core["files"])
            for msg in lowered_messages
        )

        clarifying_questions: List[str] = []
        if request_kind == "unknown" and not self._request_seems_actionable(session, {"request_kind": request_kind}):
            clarifying_questions = ["What should be changed?"]

        return {
            "request_kind": request_kind,
            "core_gui_change_requested": bool(planned_core["files"]),
            "core_gui_change_authorized": core_authorized,
            "clarifying_questions": clarifying_questions,
        }

    def _classify_intent_simple(
        self,
        text: str,
        session_state: Optional[Dict[str, Any]] = None,
    ) -> AssistantDecision:
        lower = (text or "").strip().lower()
        if not lower:
            return AssistantDecision(intent="out_of_scope", confidence=1.0, reason="empty_message")

        relevance = self._assess_repo_relevance(lower, session_state=session_state)

        if self._intent_classifier is None and self._contains_sensitive_or_offtopic_content(lower):
            return AssistantDecision(
                intent="out_of_scope",
                confidence=0.99,
                reason="sensitive_blocked",
                scope_class="out_of_scope",
                sensitivity_class="blocked",
                domain_anchor_present=False,
                grounding_required=False,
                allowed_response_mode="refuse",
            )

        explicit_feature_request = self._is_feature_request(lower)
        has_anchor = relevance["has_anchor"]
        is_relevant = relevance["is_relevant"]

        if explicit_feature_request:
            if not is_relevant:
                return AssistantDecision(
                    intent="out_of_scope",
                    confidence=0.98,
                    reason="feature_request_without_repo_relevance",
                    scope_class="out_of_scope",
                    sensitivity_class="normal",
                    domain_anchor_present=False,
                    grounding_required=False,
                    allowed_response_mode="refuse",
                )
            return AssistantDecision(
                intent="feature_request",
                confidence=0.9,
                reason="deterministic_feature_request",
                scope_class="repo_workflow",
                sensitivity_class="normal",
                domain_anchor_present=has_anchor,
                grounding_required=False,
                allowed_response_mode="feature_request",
            )

        is_question = self._looks_information_question(lower)

        science_terms = {"q-mer", "qmer", "hel308", "chemistry", "physics", "signal", "current"}
        code_terms = {".py", "module", "function", "class", "operator_assistant.py", "file"}
        runtime_terms = {
            "runtime",
            "stage",
            "gate",
            "promotion",
            "orchestrator",
            "policy",
            "safeguard",
            "safeguards",
            "supervised",
            "standardized",
            "processing",
        }

        has_science = any(term in lower for term in science_terms)
        has_code = any(term in lower for term in code_terms)
        has_runtime = any(term in lower for term in runtime_terms)

        # Science terms → nanopore_science_explanation when repository-relevant.
        if has_science and is_relevant:
            return AssistantDecision(
                intent="nanopore_science_explanation",
                confidence=0.82,
                reason="deterministic_science_route",
                scope_class="nanopore_science",
                sensitivity_class="normal",
                domain_anchor_present=has_anchor,
                grounding_required=True,
                allowed_response_mode="grounded_answer",
            )

        # Code file/module terms + question → code_explanation when repository-relevant.
        if has_code and is_question and is_relevant:
            return AssistantDecision(
                intent="code_explanation",
                confidence=0.85,
                reason="deterministic_code_route",
                scope_class="repo_code",
                sensitivity_class="normal",
                domain_anchor_present=has_anchor,
                grounding_required=True,
                allowed_response_mode="grounded_answer",
            )

        # Runtime/orchestration terms → runtime_help when repository-relevant.
        if has_runtime and is_relevant and (is_question or has_anchor):
            return AssistantDecision(
                intent="runtime_help",
                confidence=0.86,
                reason="deterministic_runtime_route",
                scope_class="runtime_operations",
                sensitivity_class="normal",
                domain_anchor_present=has_anchor,
                grounding_required=True,
                allowed_response_mode="runtime_explanation",
            )

        # Any repository-relevant question routes to repo_question.
        if is_question and is_relevant:
            return AssistantDecision(
                intent="repo_question",
                confidence=0.8,
                reason="deterministic_repo_question",
                scope_class="repo_knowledge",
                sensitivity_class="normal",
                domain_anchor_present=has_anchor,
                grounding_required=True,
                allowed_response_mode="grounded_answer",
            )

        if is_question and not is_relevant:
            return AssistantDecision(
                intent="out_of_scope",
                confidence=0.96,
                reason="question_without_repo_relevance",
                scope_class="out_of_scope",
                sensitivity_class="normal",
                domain_anchor_present=False,
                grounding_required=False,
                allowed_response_mode="refuse",
            )

        if not is_question and is_relevant:
            return AssistantDecision(
                intent="repo_question",
                confidence=0.72,
                reason="deterministic_repo_statement",
                scope_class="repo_knowledge",
                sensitivity_class="normal",
                domain_anchor_present=has_anchor,
                grounding_required=True,
                allowed_response_mode="grounded_answer",
            )

        return AssistantDecision(
            intent="out_of_scope",
            confidence=0.95,
            reason="statement_without_repo_relevance",
            scope_class="out_of_scope",
            sensitivity_class="normal",
            domain_anchor_present=False,
            grounding_required=False,
            allowed_response_mode="refuse",
        )

    def _contains_sensitive_or_offtopic_content(self, lower: str) -> bool:
        # Deterministic fallback-only high-risk lexical blockers when semantic classifier is unavailable.
        high_risk_patterns = [
            r"\bmake\s+(a\s+)?bomb\b",
            r"\bbuild\s+(a\s+)?bomb\b",
            r"\bexplosive\b",
            r"\bweapon\b",
            r"\bhow\s+to\s+kill\b",
            r"\bpoison\b",
            r"\battack\b",
            r"\bmedical\s+advice\b",
            r"\blegal\s+advice\b",
            r"\bfinancial\s+advice\b",
            r"\binvestment\s+advice\b",
            r"\bpolitical\s+advice\b",
            r"\bdiagnos(e|is|ing)\b",
            r"\bprescrib(e|ing)\b",
        ]
        return any(re.search(pattern, lower) for pattern in high_risk_patterns)

    def _assess_repo_relevance(
        self,
        text: str,
        session_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        lower = (text or "").strip().lower()
        has_anchor = self._has_domain_anchor(lower, session_state=session_state)
        has_goal_term = any(term.lower() in lower for term in self._repo_goal_terms)

        specific_terms = self._specific_query_terms(lower)
        snippets: List[str] = []
        if specific_terms:
            snippets = self._retrieve_relevant_snippets(" ".join(specific_terms), max_items=2, scope_class="repo_knowledge")
        snippet_hits = len(snippets)

        # Repository relevance is evidence-based: anchor hit or retrievable repo context.
        is_relevant = has_anchor or has_goal_term or snippet_hits > 0
        return {
            "has_anchor": has_anchor,
            "has_goal_term": has_goal_term,
            "snippet_hits": snippet_hits,
            "is_relevant": is_relevant,
        }

    def _specific_query_terms(self, text: str) -> List[str]:
        words = [w for w in re.split(r"[^a-zA-Z0-9_]+", text.lower()) if len(w) >= 4]
        generic = {
            "help",
            "with",
            "this",
            "that",
            "what",
            "when",
            "where",
            "why",
            "how",
            "make",
            "build",
            "create",
            "give",
            "need",
            "want",
            "please",
            "just",
            "something",
            "anything",
            "both",
            "fine",
            "okay",
            "dont",
            "want",
            "changed",
        }
        return [w for w in words if w not in generic][:10]

    def _is_short_followup_answer(self, message: str, session_state: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(session_state, dict):
            return False
        tokens = [t for t in re.split(r"\s+", (message or "").strip()) if t]
        if not (0 < len(tokens) <= 3):
            return False
        lower = (message or "").strip().lower()
        if "?" in lower:
            return False
        if self._is_feature_request(lower):
            return False
        return True

    def _should_continue_feature_context(self, message: str, session_state: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(session_state, dict):
            return False
        feature_messages = session_state.get("feature_messages", [])
        if not isinstance(feature_messages, list) or not feature_messages:
            return False

        if self._is_short_followup_answer(message, session_state):
            return True

        candidate = self._classify_intent_simple(message, session_state=session_state)
        if candidate.intent == "out_of_scope" or candidate.allowed_response_mode == "refuse":
            return False

        relevance = self._assess_repo_relevance(message, session_state=session_state)
        return bool(relevance["is_relevant"] and candidate.intent == "feature_request")

    def _reset_feature_context(self, session_state: Dict[str, Any]) -> None:
        session_state["feature_messages"] = []
        session_state["latest_runtime_request"] = None
        session_state["pending_questions"] = []

    def _is_feature_request(self, lower: str) -> bool:
        action_terms = {
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
            "remake",
            "rewrite",
            "make",
        }
        if any(re.search(rf"\b{re.escape(term)}\b", lower) for term in action_terms):
            return True
        return False

    def _has_guided_workflow_cue(self, lower: str) -> bool:
        cues = {
            "what should i do next",
            "i'm confused",
            "im confused",
            "different pore type",
            "configurable",
            "hard assumptions",
            "compare traces",
            "reproducible",
            "daily checklist",
            "quality review",
            "consistent exports",
            "supervised",
            "standardized processing",
            "safeguards",
            "what can you help me with",
            "what can you help with",
        }
        return any(cue in lower for cue in cues)

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

        capability_modes = [
            "feature_request",
            "runtime_help",
            "code_explanation",
            "repo_question",
            "nanopore_science_explanation",
        ]
        repo_context = self._classifier_reference_context(text)
        system_prompt = (
            "You are a semantic scope and intent classifier for a local nanoporethon operator assistant. "
            "Use positive scope matching: only classify as in-scope when the message clearly belongs to one of the allowed capability modes "
            f"({', '.join(capability_modes)}). "
            "Classify implementation/edit/build/test/doc requests as feature_request. "
            "Classify runtime execution, stages, promotion, gates, policies, logs, or run-artifact questions as runtime_help. "
            "Classify code/module/file/function explanations as code_explanation. "
            "Classify repository/docs/workflow questions as repo_question. "
            "Classify nanoporethon scientific or algorithmic explanations grounded in local project materials as nanopore_science_explanation. "
            "Use out_of_scope for unrelated requests and for harmful/unsafe requests such as weapons, violent wrongdoing, or dangerous illegal guidance. "
            "If a question seems vaguely scientific or technical but lacks a clear nanoporethon/repository anchor, set domain_anchor_present=false "
            "and allowed_response_mode=clarify. "
            "Prioritize repository-relevance based on these local project references:\n"
            f"{repo_context}\n"
            "Respond with ONLY valid JSON (no markdown, no explanation). Required keys: intent, confidence, reason. "
            "Optional keys: scope_class, sensitivity_class, domain_anchor_present, grounding_required, allowed_response_mode, "
            "should_ask_clarifying_question, clarifying_question."
        )

        classifier_messages = self._build_classifier_messages(text, session_state=session_state)

        payload = self._chat_json_with_classifier_fallback(
            system_prompt,
            classifier_messages,
            operation_name="intent-classification",
            required_keys=["intent", "confidence", "reason"],
        )

        try:
            normalized = self._normalize_classifier_payload(payload, text=text, session_state=session_state)
            intent = normalized["intent"]

            if intent in _ALLOWED_INTENTS:
                return AssistantDecision(
                    intent=intent,
                    confidence=normalized["confidence"],
                    reason=normalized["reason"],
                    scope_class=normalized["scope_class"],
                    sensitivity_class=normalized["sensitivity_class"],
                    domain_anchor_present=normalized["domain_anchor_present"],
                    grounding_required=normalized["grounding_required"],
                    allowed_response_mode=normalized["allowed_response_mode"],
                    should_ask_clarifying_question=normalized["should_ask_clarifying_question"],
                    clarifying_question=normalized["clarifying_question"],
                )

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

    def _classifier_reference_context(self, text: str) -> str:
        snippets = self._retrieve_relevant_snippets(text, max_items=3, scope_class="repo_knowledge")
        persona = self._doc_cache.get("Docs/UserPersonas.md", "")
        use_cases = self._doc_cache.get("Docs/UseCases.md", "")

        context_lines: List[str] = []
        if snippets:
            context_lines.append("- Relevant repo snippets:")
            context_lines.extend(f"  - {snippet}" for snippet in snippets[:3])
        if persona:
            context_lines.append("- User personas document exists and defines expected question styles from students, postdocs, collaborators, and lab staff.")
        if use_cases:
            context_lines.append("- Use cases document exists and defines core repo tasks: data search/selection, event curation, workflow guidance, and reproducible analysis support.")
        if not context_lines:
            context_lines.append("- No cached docs available; default to strict repository relevance requirement.")
        return "\n".join(context_lines)

    def _configure_intent_classifiers(self) -> None:
        if not isinstance(self.policy, dict):
            self._intent_classifier = self.model_adapter
            return

        scope_cfg = self.policy.get("assistant_scope", {})
        classifier_cfg = scope_cfg.get("intent_classifier", {}) if isinstance(scope_cfg, dict) else {}
        enabled = True
        if isinstance(classifier_cfg, dict):
            enabled = bool(classifier_cfg.get("enabled", True))

        self._intent_classifier = self.model_adapter if enabled else None

        if not enabled or not isinstance(classifier_cfg, dict):
            return

        fallback_model = str(classifier_cfg.get("fallback_model", "")).strip()
        if not fallback_model:
            return

        model_provider = self.policy.get("model_provider", {}) if isinstance(self.policy, dict) else {}
        if not isinstance(model_provider, dict):
            return

        adapter_name = str(model_provider.get("adapter", "")).strip().lower()
        if adapter_name != "ollama":
            return

        base_url = str(model_provider.get("base_url", "http://localhost:11434"))
        timeout_seconds = int(model_provider.get("request_timeout_seconds", 180))
        max_retries = int(model_provider.get("max_retries", 1))

        if self.model_adapter is not None and getattr(self.model_adapter, "model", "") == fallback_model:
            self._intent_classifier_fallback = self.model_adapter
            return

        self._intent_classifier_fallback = OllamaAdapter(
            model=fallback_model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

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

    def _load_known_python_modules(self) -> Set[str]:
        modules: Set[str] = {"nanoporethon"}
        package_root = self.repo_root / "src" / "nanoporethon"
        if not package_root.exists() or not package_root.is_dir():
            return modules

        for py_file in package_root.glob("*.py"):
            stem = py_file.stem
            if stem == "__init__":
                continue
            modules.add(f"nanoporethon.{stem}")
        return modules

    def _contains_unverifiable_module_claim(self, answer: str) -> bool:
        text = (answer or "").strip()
        if not text:
            return False

        imported_modules: List[str] = []
        imported_modules.extend(re.findall(r"\bfrom\s+([A-Za-z_][A-Za-z0-9_\.]*)\s+import\b", text))
        imported_modules.extend(re.findall(r"\bimport\s+([A-Za-z_][A-Za-z0-9_\.]*)", text))

        for module in imported_modules:
            normalized = module.strip()
            if normalized.startswith("nanoporethon_"):
                return True
            if normalized == "nanoporethon":
                continue
            if normalized.startswith("nanoporethon.") and normalized not in self._known_python_modules:
                return True
        return False

    def _quote_in_context(self, quote: str, context_text: str) -> bool:
        q = " ".join((quote or "").split()).strip().lower()
        c = " ".join((context_text or "").split()).strip().lower()
        if len(q) < 12:
            return False
        return q in c

    def _load_docs(self) -> Dict[str, str]:
        cache: Dict[str, str] = {}
        for rel in self._grounding_files:
            path = self.repo_root / rel
            if not path.exists() or not path.is_file():
                continue
            try:
                cache[rel] = path.read_text(encoding="utf-8")
            except OSError:
                continue
        return cache

    def _load_protected_file_hints_from_policy(self) -> Dict[str, List[str]]:
        if not isinstance(self.policy, dict):
            return {}

        raw = self.policy.get("assistant_scope", {}).get("protected_file_hints", {})
        if not isinstance(raw, dict):
            return {}

        parsed: Dict[str, List[str]] = {}
        for file_path, hints in raw.items():
            if not isinstance(file_path, str) or not file_path.strip():
                continue
            entries: List[str] = [file_path.strip().lower()]
            if isinstance(hints, list):
                entries.extend(str(h).strip().lower() for h in hints if str(h).strip())
            # Ensure stable dedupe while preserving order.
            deduped: List[str] = []
            seen = set()
            for item in entries:
                if item in seen:
                    continue
                seen.add(item)
                deduped.append(item)
            parsed[file_path.strip()] = deduped
        return parsed

    def _load_grounding_files_from_policy(self) -> List[str]:
        if not isinstance(self.policy, dict):
            return list(_DEFAULT_GROUNDING_FILES)

        raw = self.policy.get("assistant_scope", {}).get("grounding_files", _DEFAULT_GROUNDING_FILES)
        values = self._normalize_text_list(raw)
        return values or list(_DEFAULT_GROUNDING_FILES)

    def _load_domain_anchors_from_policy(self) -> List[str]:
        if not isinstance(self.policy, dict):
            return list(_DEFAULT_DOMAIN_ANCHORS)

        raw = self.policy.get("assistant_scope", {}).get("domain_anchors", _DEFAULT_DOMAIN_ANCHORS)
        values = self._normalize_text_list(raw)
        return values or list(_DEFAULT_DOMAIN_ANCHORS)

    def _load_sensitive_domains_from_policy(self) -> List[str]:
        if not isinstance(self.policy, dict):
            return list(_DEFAULT_SENSITIVE_DOMAINS)

        raw = self.policy.get("assistant_scope", {}).get("sensitive_domains", _DEFAULT_SENSITIVE_DOMAINS)
        values = self._normalize_text_list(raw)
        return values or list(_DEFAULT_SENSITIVE_DOMAINS)

    def _load_repo_goal_terms_from_policy(self) -> List[str]:
        if not isinstance(self.policy, dict):
            return list(_DEFAULT_REPO_GOAL_TERMS)

        raw = self.policy.get("assistant_scope", {}).get("repo_goal_terms", _DEFAULT_REPO_GOAL_TERMS)
        values = self._normalize_text_list(raw)
        return values or list(_DEFAULT_REPO_GOAL_TERMS)

    def _normalize_text_list(self, raw: Any) -> List[str]:
        if not isinstance(raw, list):
            return []

        normalized: List[str] = []
        seen = set()
        for item in raw:
            value = str(item).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    def _retrieve_relevant_snippets(self, query: str, max_items: int = 3, scope_class: str = "unknown") -> List[str]:
        terms = self._query_terms(query)
        query_lower = (query or "").lower()
        is_howto_query = bool(re.search(r"\b(how|run|launch|start|open)\b", query_lower))
        scored: List[Tuple[int, str, str]] = []
        for rel, text in self._doc_cache.items():
            lower = text.lower()
            path_lower = rel.lower()
            score = sum(lower.count(term) for term in terms) + sum(path_lower.count(term) * 2 for term in terms)
            if scope_class == "runtime_operations" and rel.startswith("runtime/"):
                score += 2
            if scope_class == "nanopore_science" and (
                "sequence_designer" in path_lower
                or "technology_context" in path_lower
                or "nanoporethon_textbook" in path_lower
                or "components" in path_lower
            ):
                score += 2
            if is_howto_query and (
                path_lower == "readme.md"
                or path_lower.endswith("event_classifier_gui.py")
                or "nanoporethon_textbook" in path_lower
            ):
                score += 4
            if score <= 0:
                continue
            snippet = self._extract_snippet_window(text, terms, query=query)
            scored.append((score, rel, snippet))

        scored.sort(key=lambda t: t[0], reverse=True)
        selected = scored[:max_items]
        return [f"[{rel}] {snippet}" for _, rel, snippet in selected]

    def _query_terms(self, query: str) -> List[str]:
        words = [w for w in re.split(r"[^a-zA-Z0-9_]+", query.lower()) if len(w) >= 3]
        stop = {"the", "and", "for", "with", "that", "this", "how", "what", "when", "where", "why"}
        aliases = {
            "models": "model",
            "modeling": "model",
            "agents": "agent",
            "agenting": "agent",
            "quantized": "quant",
            "quantization": "quant",
            "runs": "run",
        }

        terms: List[str] = []
        for word in words:
            if word in stop:
                continue
            terms.append(word)
            alias = aliases.get(word)
            if alias and alias not in stop:
                terms.append(alias)
            elif word.endswith("s") and len(word) > 4:
                singular = word[:-1]
                if singular not in stop:
                    terms.append(singular)

        deduped: List[str] = []
        seen = set()
        for term in terms:
            if term in seen:
                continue
            seen.add(term)
            deduped.append(term)
        return deduped[:10]

    def _extract_snippet_window(self, text: str, terms: List[str], max_chars: int = 700, query: str = "") -> str:
        if not text:
            return ""

        lower = text.lower()
        query_lower = (query or "").lower()
        candidate_windows: List[Tuple[int, int, int]] = []

        for term in terms:
            start_idx = 0
            while True:
                idx = lower.find(term, start_idx)
                if idx < 0:
                    break
                start = max(0, idx - 220)
                end = min(len(text), start + max_chars)
                window = text[start:end]
                window_lower = window.lower()
                score = 0
                score += sum(window_lower.count(t) for t in terms)
                if re.search(r"\bpython\s+-m\s+[a-zA-Z0-9_.]+", window_lower):
                    score += 6
                if any(tok in window_lower for tok in ["run", "launch", "start", "open", "gui", "usage"]):
                    score += 3
                if bool(re.search(r"\b(how|run|launch|start|use)\b", query_lower)) and "event classifier" in window_lower:
                    score += 5
                if window_lower.count("(#") >= 3:
                    score -= 4
                candidate_windows.append((score, start, end))
                start_idx = idx + len(term)

        if candidate_windows:
            candidate_windows.sort(key=lambda item: item[0], reverse=True)
            _, start, end = candidate_windows[0]
            snippet = text[start:end].strip()
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(text) else ""
            return f"{prefix}{snippet}{suffix}"

        fallback = text[:max_chars].strip()
        if len(text) > max_chars:
            fallback += "..."
        return fallback

    def _synthesize_grounded_answer(self, user_text: str, snippets: List[str], scope_class: str) -> Optional[str]:
        query = (user_text or "").lower()
        howto_query = bool(re.search(r"\b(how|run|launch|start|open|use|where)\b", query))
        if not snippets:
            return None

        commands: List[Tuple[str, str]] = []
        considerations: List[Tuple[str, str]] = []
        source_refs: List[str] = []

        for snippet in snippets:
            rel = "unknown"
            body = snippet
            match = re.match(r"^\[([^\]]+)\]\s*(.*)$", snippet, flags=re.DOTALL)
            if match:
                rel = match.group(1).strip()
                body = match.group(2).strip()
            source_refs.append(rel)

            for cmd in re.findall(r"\bpython\s+-m\s+[A-Za-z0-9_.]+", body):
                commands.append((cmd.strip(), rel))
            for cmd in re.findall(r"\bpython\s+src/[A-Za-z0-9_./-]+\.py", body):
                commands.append((cmd.strip(), rel))

            cues = [
                "search logs directory",
                "saved query",
                "reduced.mat",
                "event.mat",
                "meta.mat",
                "sampling frequency",
                "troubleshooting",
                "keyboard shortcuts",
                "classify events",
            ]
            body_lower = body.lower()
            for cue in cues:
                if cue in body_lower:
                    considerations.append((cue, rel))

        def _dedupe_pairs(pairs: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
            seen = set()
            out: List[Tuple[str, str]] = []
            for value, src in pairs:
                key = (value.lower(), src)
                if key in seen:
                    continue
                seen.add(key)
                out.append((value, src))
            return out

        commands = _dedupe_pairs(commands)
        considerations = _dedupe_pairs(considerations)

        if howto_query and not commands:
            commands = self._discover_commands_from_docs(query=user_text, max_items=4)

        if howto_query and (commands or considerations):
            lines: List[str] = [
                "Here’s a repo-grounded way to do that:",
                "",
            ]
            if commands:
                lines.append("Run it from the repository root:")
                for cmd, src in commands[:3]:
                    lines.append(f"- `{cmd}` (from `{src}`)")
                lines.append("")

            if considerations:
                lines.append("Things to consider after launch:")
                for cue, src in considerations[:5]:
                    pretty = cue.replace(".mat", " MAT file") if cue.endswith(".mat") else cue
                    lines.append(f"- {pretty} (from `{src}`)")
                lines.append("")

            command_sources = [src for _, src in commands]
            unique_sources = sorted({s for s in (source_refs + command_sources) if s and s != "unknown"})
            if unique_sources:
                lines.append("Grounding sources: " + ", ".join(f"`{s}`" for s in unique_sources[:4]))
            return "\n".join(lines).strip()

        return None

    def _synthesize_deep_grounded_answer(self, user_text: str, snippets: List[str], scope_class: str) -> Optional[str]:
        base = self._synthesize_grounded_answer(user_text=user_text, snippets=snippets, scope_class=scope_class)
        addendum = self._build_deep_followup_addendum(snippets)

        if base and addendum:
            return f"{base}\n\n{addendum}".strip()
        if base:
            return base

        lines: List[str] = [
            "Here’s a deeper repo-grounded summary from local sources:",
            "",
            "Key references:",
        ]

        for snippet in snippets[:4]:
            rel = "unknown"
            body = snippet
            match = re.match(r"^\[([^\]]+)\]\s*(.*)$", snippet, flags=re.DOTALL)
            if match:
                rel = match.group(1).strip()
                body = match.group(2).strip()
            lines.append(f"- `{rel}`: {self._compress_snippet(body)}")

        if addendum:
            lines.extend(["", addendum])
        return "\n".join(lines).strip()

    def _build_deep_followup_addendum(self, snippets: List[str]) -> str:
        source_refs: List[str] = []
        for snippet in snippets:
            match = re.match(r"^\[([^\]]+)\]", snippet)
            if match:
                source_refs.append(match.group(1).strip())

        doc_sources = [
            src
            for src in source_refs
            if src.startswith("Docs/") or src == "README.md" or src.startswith("runtime/")
        ]
        doc_sources = list(OrderedDict.fromkeys(doc_sources))

        paper_sources = self._list_paper_resources(max_items=6)

        if not doc_sources and not paper_sources:
            return ""

        lines: List[str] = [
            "Further reading in repository:",
        ]

        if doc_sources:
            lines.append("- Docs/code references:")
            for src in doc_sources[:5]:
                lines.append(f"  - `{src}`")

        if paper_sources:
            lines.append("- Available paper resources:")
            for src in paper_sources:
                lines.append(f"  - `{src}`")

        return "\n".join(lines)

    def _list_paper_resources(self, max_items: int = 6) -> List[str]:
        papers_root = self.repo_root / "Docs" / "papers"
        if not papers_root.exists() or not papers_root.is_dir():
            return []

        allowed_suffixes = {".md", ".txt", ".pdf", ".docx", ".pptx"}
        resources: List[str] = []

        for path in sorted(papers_root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in allowed_suffixes:
                continue
            try:
                rel = path.relative_to(self.repo_root).as_posix()
            except ValueError:
                rel = str(path)
            resources.append(rel)
            if len(resources) >= max_items:
                break

        return resources

    def _discover_commands_from_docs(self, query: str, max_items: int = 4) -> List[Tuple[str, str]]:
        query_lower = (query or "").lower()
        query_terms = set(self._query_terms(query_lower))
        candidates: List[Tuple[int, str, str]] = []

        for rel, text in self._doc_cache.items():
            lines = text.splitlines()
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                found = re.findall(r"\bpython\s+-m\s+[A-Za-z0-9_.]+|\bpython\s+src/[A-Za-z0-9_./-]+\.py", stripped)
                for cmd in found:
                    cmd_lower = cmd.lower()
                    score = 1
                    score += sum(1 for term in query_terms if term and term in cmd_lower)
                    if "event_classifier_gui" in cmd_lower and "event" in query_lower:
                        score += 5
                    if rel.lower() == "readme.md" and any(term in cmd_lower for term in query_terms):
                        score += 2
                    if ("event" in query_terms or "classifier" in query_terms) and not (
                        "event" in cmd_lower or "classifier" in cmd_lower
                    ):
                        score -= 2
                    candidates.append((score, cmd.strip(), rel))

        candidates.sort(key=lambda x: x[0], reverse=True)
        strong_exists = any(score >= 2 for score, _, _ in candidates)
        deduped: List[Tuple[str, str]] = []
        seen = set()
        for score, cmd, rel in candidates:
            if strong_exists and score < 2:
                continue
            key = cmd.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append((cmd, rel))
            if len(deduped) >= max_items:
                break
        return deduped

    def _normalize_classifier_payload(
        self,
        payload: Dict[str, Any],
        text: str,
        session_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        intent = str(payload.get("intent", "")).lower().strip()
        confidence = float(payload.get("confidence", 0.0))
        reason = str(payload.get("reason", "model_classified")).strip() or "model_classified"

        if intent not in _ALLOWED_INTENTS:
            raise RuntimeError(
                "Operator assistant strict mode: classifier returned an unsupported intent value "
                f"('{intent}')."
            )

        scope_class = str(payload.get("scope_class", "")).strip().lower() or self._intent_default_scope_class(intent)
        sensitivity_class = str(payload.get("sensitivity_class", "")).strip().lower()
        if sensitivity_class not in {"normal", "sensitive", "blocked"}:
            sensitivity_class = "blocked" if intent == "out_of_scope" else "normal"

        raw_anchor = payload.get("domain_anchor_present", None)
        if isinstance(raw_anchor, bool):
            domain_anchor_present = raw_anchor
        else:
            domain_anchor_present = self._has_domain_anchor(text, session_state=session_state)

        raw_grounding_required = payload.get("grounding_required", None)
        grounding_required = (
            bool(raw_grounding_required)
            if isinstance(raw_grounding_required, bool)
            else intent in _GROUNDED_ANSWER_INTENTS
        )

        allowed_response_mode = str(payload.get("allowed_response_mode", "")).strip().lower()
        if allowed_response_mode not in {"feature_request", "runtime_explanation", "grounded_answer", "clarify", "refuse"}:
            allowed_response_mode = self._default_response_mode(
                intent=intent,
                sensitivity_class=sensitivity_class,
                domain_anchor_present=domain_anchor_present,
                grounding_required=grounding_required,
            )

        should_ask_clarifying_question = bool(payload.get("should_ask_clarifying_question", False))
        clarifying_question = str(payload.get("clarifying_question", "")).strip()
        if (
            not clarifying_question
            and grounding_required
            and not domain_anchor_present
            and intent in {"repo_question", "code_explanation", "nanopore_science_explanation"}
        ):
            should_ask_clarifying_question = True
            clarifying_question = self._grounding_anchor_question(intent)

        if allowed_response_mode == "grounded_answer" and grounding_required and not domain_anchor_present:
            allowed_response_mode = "clarify"

        if allowed_response_mode == "clarify" and not clarifying_question:
            clarifying_question = self._grounding_anchor_question(intent)

        return {
            "intent": intent,
            "confidence": confidence,
            "reason": reason,
            "scope_class": scope_class,
            "sensitivity_class": sensitivity_class,
            "domain_anchor_present": domain_anchor_present,
            "grounding_required": grounding_required,
            "allowed_response_mode": allowed_response_mode,
            "should_ask_clarifying_question": should_ask_clarifying_question,
            "clarifying_question": clarifying_question,
        }

    def _intent_default_scope_class(self, intent: str) -> str:
        mapping = {
            "feature_request": "repo_workflow",
            "runtime_help": "runtime_operations",
            "code_explanation": "repo_code",
            "repo_question": "repo_knowledge",
            "nanopore_science_explanation": "nanopore_science",
            "out_of_scope": "out_of_scope",
        }
        return mapping.get(intent, "unknown")

    def _default_response_mode(
        self,
        intent: str,
        sensitivity_class: str,
        domain_anchor_present: bool,
        grounding_required: bool,
    ) -> str:
        if sensitivity_class == "blocked" or intent == "out_of_scope":
            return "refuse"
        if intent == "feature_request":
            return "feature_request"
        if intent == "runtime_help":
            return "runtime_explanation"
        if grounding_required and not domain_anchor_present:
            return "clarify"
        return "grounded_answer"

    def _has_domain_anchor(
        self,
        text: str,
        session_state: Optional[Dict[str, Any]] = None,
    ) -> bool:
        lower = (text or "").strip().lower()
        if not lower:
            return False

        if any(anchor.lower() in lower for anchor in self._domain_anchors):
            return True

        if re.search(r"[A-Za-z0-9_./\\-]+\.(py|md|yaml|json|m|mlapp)\b", lower):
            return True

        return False

    def _grounding_anchor_question(self, intent: str) -> str:
        if intent == "nanopore_science_explanation":
            return (
                "Which nanoporethon component, file, or local reference should I ground that nanopore explanation in? "
                "For example: a runtime module, `sequence_designer_gui.py`, a docs section, or a MATLAB reference."
            )
        return (
            "Which nanoporethon component, workflow, file, or local reference should I ground that answer in? "
            "Mention a module, docs section, runtime stage, or file path and I’ll stay anchored there."
        )

    def _ungrounded_answer_message(self, decision: Optional[AssistantDecision]) -> str:
        if decision is not None and decision.intent == "nanopore_science_explanation":
            return (
                "I can explain nanoporethon scientific or algorithmic behavior, but only when I can ground it in local repo materials. "
                "Mention the relevant component, file, workflow, or reference so I can stay evidence-first."
            )
        return (
            "I can help with nanoporethon workflows, runtime behavior, repository/code questions, and grounded nanopore explanations. "
            "Mention a repository-specific term (for example: runtime, stage, policy, docs, tests, q-mer map, or a file/module name) "
            "so I can anchor the answer locally."
        )

    def _compress_snippet(self, snippet: str) -> str:
        s = " ".join(snippet.split())
        if len(s) <= 280:
            return s
        return s[:277] + "..."
