from pathlib import Path
import json
import pytest

from runtime.operator_assistant import AssistantStartupError, LocalOperatorAssistant
from runtime.adapters.ollama import OllamaAdapter


class SemanticTestModelAdapter:
    """Semantic mock model for intent classification and feature-session analysis."""

    def chat(self, system_prompt: str, messages: list) -> str:
        content = messages[0].get("content", "") if messages else ""
        lower = content.lower()
        prompt_lower = system_prompt.lower()

        # Session-analysis path.
        if "request_kind" in prompt_lower and "clarifying_questions" in prompt_lower:
            if "readme" in lower or "documentation" in lower:
                request_kind = "docs_only"
            else:
                request_kind = "code_change"

            core_requested = "data_navi_gui" in lower or "event_classifier_gui" in lower
            core_authorized = "you can modify data_navi_gui" in lower or "you can modify event_classifier_gui" in lower

            questions = []
            if "expected" not in lower and "output" not in lower:
                questions.append("Can you give one concrete example of the expected behavior/output?")

            return json.dumps(
                {
                    "request_kind": request_kind,
                    "core_gui_change_requested": core_requested,
                    "core_gui_change_authorized": core_authorized,
                    "clarifying_questions": questions,
                }
            )

        # Intent-classification path.
        if any(term in lower for term in ["brownie", "recipe", "medical", "election", "stocks", "meaning of life"]):
            return json.dumps({"intent": "out_of_scope", "confidence": 0.98, "reason": "semantic_out_of_scope"})

        if "runtime" in lower and "?" in lower:
            return json.dumps({"intent": "runtime_help", "confidence": 0.9, "reason": "semantic_runtime_question"})

        if "?" in lower:
            return json.dumps({"intent": "repo_question", "confidence": 0.8, "reason": "semantic_repo_question"})

        return json.dumps({"intent": "feature_request", "confidence": 0.88, "reason": "semantic_feature"})


def _assistant():
    assistant = LocalOperatorAssistant(
        repo_root=Path(__file__).resolve().parents[1],
        policy={"assistant_scope": {"intent_classifier": {"enabled": True, "model": "semantic-test"}}},
    )
    assistant._intent_classifier = SemanticTestModelAdapter()
    return assistant


def test_brownie_recipe_is_out_of_scope():
    assistant = _assistant()
    response = assistant.handle_message("Can you give me a brownie recipe?", session=assistant.init_session())
    assert response.intent == "out_of_scope"
    assert "scoped to nanoporethon" in response.message


def test_medical_advice_is_out_of_scope():
    assistant = _assistant()
    response = assistant.handle_message("I need medical advice for chest pain", session=assistant.init_session())
    assert response.intent == "out_of_scope"


def test_political_advice_is_out_of_scope():
    assistant = _assistant()
    response = assistant.handle_message("Who should I vote for in this election?", session=assistant.init_session())
    assert response.intent == "out_of_scope"


def test_investing_advice_is_out_of_scope():
    assistant = _assistant()
    response = assistant.handle_message("What stocks should I buy this week?", session=assistant.init_session())
    assert response.intent == "out_of_scope"


def test_general_philosophy_advice_is_out_of_scope():
    assistant = _assistant()
    response = assistant.handle_message("What is the meaning of life?", session=assistant.init_session())
    assert response.intent == "out_of_scope"


def test_runtime_question_is_in_scope():
    assistant = _assistant()
    response = assistant.handle_message(
        "How does runtime promotion approval work in nanoporethon?",
        session=assistant.init_session(),
    )
    assert response.intent in {"runtime_help", "repo_question"}


def test_feature_request_generates_runtime_request_preview():
    assistant = _assistant()
    response = assistant.handle_message(
        "Add a feature to export data to CSV format",
        session=assistant.init_session(),
    )
    assert response.intent == "feature_request"
    assert response.runtime_request is not None
    assert "Conversation-derived request" in response.runtime_request
    assert "Anti-hallucination quality rubric (mandatory)" in response.runtime_request
    assert "Contract-safe" in response.runtime_request
    assert "Evidence-first" in response.runtime_request
    assert "ready to run now" in response.message.lower()
    assert response.followup_questions == []


def test_core_gui_is_protected_by_default_in_runtime_request():
    assistant = _assistant()
    response = assistant.handle_message(
        "Modify the data_navi_gui to add a new button",
        session=assistant.init_session(),
    )
    assert response.intent == "feature_request"
    assert response.runtime_request is not None
    assert "Do NOT modify core GUI components unless user explicitly authorizes" in response.runtime_request


def test_explicit_core_gui_authorization_updates_runtime_request():
    assistant = _assistant()
    session = assistant.init_session()
    response = assistant.handle_message(
        "Modify the data_navi_gui to add a new button, you can modify data_navi_gui",
        session=session,
    )
    assert response.intent == "feature_request"
    assert response.runtime_request is not None
    assert "Core GUI changes are explicitly authorized" in response.runtime_request
    assert response.session_updates.get("core_change_authorized") is True


def test_feature_request_returns_session_updates():
    assistant = _assistant()
    session = assistant.init_session()
    response = assistant.handle_message(
        "Build a new analysis module",
        session=session,
    )
    assert response.intent == "feature_request"
    assert response.session_updates is not None
    assert len(response.session_updates.get("feature_messages", [])) > 0


def test_remake_matlab_file_request_routes_to_feature_request():
    assistant = _assistant()
    response = assistant.handle_message(
        "Remake the consensusMaker.m file into a Python module",
        session=assistant.init_session(),
    )
    assert response.intent == "feature_request"


def test_generate_python_version_of_matlab_gui_routes_to_feature_request():
    assistant = _assistant()
    response = assistant.handle_message(
        "Generate a python version of consensusMaker and save in src/nanoporethon",
        session=assistant.init_session(),
    )
    assert response.intent == "feature_request"


def test_in_scope_non_question_defaults_to_feature_request():
    assistant = _assistant()
    # Imperative, in-scope, non-question should route to feature_request.
    response = assistant.handle_message(
        "make a new utility for the runtime",
        session=assistant.init_session(),
    )
    assert response.intent == "feature_request"


def test_runtime_information_question_not_forced_to_feature_request():
    assistant = _assistant()
    response = assistant.handle_message(
        "What is a runtime stage?",
        session=assistant.init_session(),
    )
    # Should treat as information request, not auto-route to feature_request.
    assert response.intent in {"runtime_help", "repo_question"}


class MockModelAdapter:
    """Mock Ollama adapter for testing model-based classification."""

    def __init__(self, model: str = "test-model", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.responses = {}

    def set_response(self, prompt_fragment: str, response: str) -> None:
        """Configure a response for messages containing a fragment."""
        self.responses[prompt_fragment] = response

    def chat(self, system_prompt: str, messages: list) -> str:
        """Return pre-configured or default JSON response."""
        user_text = messages[0].get("content", "") if messages else ""

        # Check if we have a configured response for this text.
        for fragment, response in self.responses.items():
            if fragment.lower() in user_text.lower():
                return response

        # Default: valid JSON response.
        return json.dumps({"intent": "feature_request", "confidence": 0.87, "reason": "default_fallback"})


def test_model_based_classification_for_feature_request():
    """Test that model-based classification can identify feature requests."""
    mock = MockModelAdapter()
    mock.set_response(
        "build",
        json.dumps({"intent": "feature_request", "confidence": 0.92, "reason": "model_decision"}),
    )
    policy = {
        "assistant_scope": {
            "intent_classifier": {"enabled": True, "model": "test-model"},
            "scope_keywords": ["nanoporethon", "python", "code"],
        }
    }
    assistant = LocalOperatorAssistant(
        repo_root=Path(__file__).resolve().parents[1],
        policy=policy,
    )
    # Inject mock classifier.
    assistant._intent_classifier = mock

    response = assistant.handle_message(
        "Build a new feature in nanoporethon",
        session=assistant.init_session(),
    )
    # Model should classify as feature_request.
    assert response.intent == "feature_request"
    assert response.runtime_request is not None


def test_model_classification_extracts_embedded_json_object():
    class WrappedJsonModelAdapter:
        def chat_json(self, system_prompt: str, messages: list) -> str:
            return 'Classifier result: {"intent": "feature_request", "confidence": 0.91, "reason": "wrapped_json"}'

    policy = {
        "assistant_scope": {
            "intent_classifier": {"enabled": True, "model": "test-model"},
            "scope_keywords": ["nanoporethon", "python", "code"],
        }
    }
    assistant = LocalOperatorAssistant(
        repo_root=Path(__file__).resolve().parents[1],
        policy=policy,
    )
    assistant._intent_classifier = WrappedJsonModelAdapter()

    response = assistant.handle_message(
        "Build a new feature in nanoporethon",
        session=assistant.init_session(),
    )
    assert response.intent == "feature_request"


def test_model_classification_raises_on_invalid_json_in_strict_mode():
    """Strict mode should raise when model returns invalid JSON (no non-LLM fallback)."""
    mock = MockModelAdapter()
    mock.set_response("invalid", "This is not JSON at all")
    policy = {
        "assistant_scope": {
            "intent_classifier": {"enabled": True, "model": "test-model"},
            "scope_keywords": ["nanoporethon", "python", "code"],
        }
    }
    assistant = LocalOperatorAssistant(
        repo_root=Path(__file__).resolve().parents[1],
        policy=policy,
    )
    assistant._intent_classifier = mock

    with pytest.raises(RuntimeError, match="strict mode"):
        assistant.handle_message(
            "invalid response: add a feature to nanoporethon code",
            session=assistant.init_session(),
        )


def test_classifier_disabled_raises_startup_error():
    """Strict mode should block startup when classifier is disabled."""
    policy = {
        "assistant_scope": {
            "intent_classifier": {"enabled": False},
            "scope_keywords": ["nanoporethon", "python"],
        }
    }
    with pytest.raises(AssistantStartupError, match="intent_classifier.enabled"):
        LocalOperatorAssistant(
            repo_root=Path(__file__).resolve().parents[1],
            policy=policy,
        )


def test_session_continuation_handles_clarifying_responses():
    """Test that follow-up responses to clarifying questions are treated as continuation, not new messages.
    
    Regression test for bug: User answers "both" to verification question, but system treats it as
    out-of-scope instead of as part of the active feature_request.
    """
    assistant = _assistant()
    session = assistant.init_session()

    # Step 1: User makes a feature request
    response1 = assistant.handle_message(
        "Add a new data export feature to nanoporethon",
        session=session,
    )
    assert response1.intent == "feature_request"
    session = response1.session_updates  # Use updated session for next message

    # Step 2: User provides a short follow-up (e.g. answering a prior clarification flow)
    # This should NOT be rejected as out_of_scope, even though "both" has no scope keywords.
    # Instead, it should be treated as a continuation of the feature_request.
    response2 = assistant.handle_message("both", session=session)
    assert response2.intent == "feature_request", (
        f"Expected 'both' to continue feature_request session, but got intent='{response2.intent}'. "
        "This is the session-context-loss bug."
    )
    assert len(response2.session_updates.get("feature_messages", [])) > 1, (
        "Expected feature_messages to accumulate across the session"
    )


def test_code_change_uses_default_verification_without_keyword_gate():
    """Code-change requests should default to tests+behavior checks without keyword gating."""
    assistant = _assistant()

    # Case 1: No testing mention; should still set default verification policy in runtime request.
    session1 = assistant.init_session()
    response1 = assistant.handle_message(
        "Add a new export format to nanoporethon",
        session=session1,
    )
    assert response1.intent == "feature_request"
    verification_q_1 = any("verify" in q.lower() for q in response1.followup_questions)
    assert not verification_q_1, (
        "Verification should not depend on keyword-triggered follow-up questions for code changes, "
        f"but got followup_questions: {response1.followup_questions}"
    )
    assert response1.runtime_request is not None
    assert "Verification default for code changes" in response1.runtime_request
    assert "BOTH automated tests and behavior checks" in response1.runtime_request

    # Case 2: Explicit testing mention still keeps the same default guardrail and no verification follow-up.
    session2 = assistant.init_session()
    response2 = assistant.handle_message(
        "Add a data filter feature to nanoporethon, test it with both unit and acceptance tests",
        session=session2,
    )
    assert response2.intent == "feature_request"
    verification_q_2 = any("verify" in q.lower() for q in response2.followup_questions)
    assert not verification_q_2, (
        "Verification follow-up should remain unnecessary for code changes even with explicit testing text, "
        f"but got followup_questions: {response2.followup_questions}"
    )
    assert response2.runtime_request is not None
    assert "Verification default for code changes" in response2.runtime_request

    # Case 3: Another code-change request should keep default verification requirements.
    session3 = assistant.init_session()
    response3 = assistant.handle_message(
        "Refactor the data navigator, add comprehensive unit tests",
        session=session3,
    )
    assert response3.intent == "feature_request"
    verification_q_3 = any("verify" in q.lower() for q in response3.followup_questions)
    assert not verification_q_3, (
        "Verification follow-up should not be required as a keyword gate, "
        f"but got followup_questions: {response3.followup_questions}"
    )
    assert response3.runtime_request is not None
    assert "Verification default for code changes" in response3.runtime_request


def test_core_gui_authorization_question_not_repeated_after_user_says_no():
    assistant = _assistant()
    session = assistant.init_session()

    first = assistant.handle_message(
        "Build a new helper using patterns from src/nanoporethon/data_navi_gui.py",
        session=session,
    )
    assert first.intent == "feature_request"
    assert any("protected file(s): src/nanoporethon/data_navi_gui.py" in q for q in first.followup_questions)
    assert any("Planned reason:" in q for q in first.followup_questions)

    second = assistant.handle_message(
        "1. No, 2. No, 3. No",
        session=first.session_updates,
    )
    assert second.intent == "feature_request"
    assert second.session_updates.get("core_change_decision_made") is True
    assert second.session_updates.get("core_change_authorized") is False
    assert not any("data_navi_gui.py" in q or "event_classifier_gui.py" in q for q in second.followup_questions)


def test_core_gui_authorization_clarifications_are_collapsed_to_single_prompt():
    class _RedundantCoreQuestionModel:
        def chat(self, system_prompt: str, messages: list) -> str:
            prompt_lower = system_prompt.lower()
            if "request_kind" in prompt_lower and "clarifying_questions" in prompt_lower:
                return json.dumps(
                    {
                        "request_kind": "code_change",
                        "core_gui_change_requested": True,
                        "core_gui_change_authorized": False,
                        "clarifying_questions": [
                            "Is it necessary to modify the protected core GUI files 'src/nanoporethon/data_navi_gui.py' or 'src/nanoporethon/event_classifier_gui.py' for this task?",
                            "Is it necessary for the new Python file to interact with any specific core GUI files (src/nanoporethon/data_navi_gui.py or src/nanoporethon/event_classifier_gui.py)?",
                        ],
                    }
                )
            return json.dumps({"intent": "feature_request", "confidence": 0.9, "reason": "semantic_feature"})

    assistant = LocalOperatorAssistant(
        repo_root=Path(__file__).resolve().parents[1],
        policy={"assistant_scope": {"intent_classifier": {"enabled": True, "model": "semantic-test"}}},
    )
    assistant._intent_classifier = _RedundantCoreQuestionModel()

    response = assistant.handle_message(
        "Please create a new file based on data_navi_gui behavior",
        session=assistant.init_session(),
    )
    core_questions = [
        q for q in response.followup_questions if ("data_navi_gui.py" in q or "event_classifier_gui.py" in q)
    ]
    assert len(core_questions) == 1
    assert "protected file(s): src/nanoporethon/data_navi_gui.py" in core_questions[0]
    assert "Planned reason:" in core_questions[0]


def test_core_gui_authorization_prompt_lists_specific_files_and_reason():
    assistant = _assistant()
    response = assistant.handle_message(
        "Update the Event Classifier GUI to add a CSV export button",
        session=assistant.init_session(),
    )
    assert len(response.followup_questions) == 1
    prompt = response.followup_questions[0]
    assert "src/nanoporethon/event_classifier_gui.py" in prompt
    assert "Planned reason:" in prompt
    assert "CSV export button" in prompt


def test_ambiguous_model_output_is_capped_to_single_followup_question():
    class _ManyQuestionModel:
        def chat_json(self, system_prompt: str, messages: list) -> str:
            prompt_lower = system_prompt.lower()
            if "request_kind" in prompt_lower and "clarifying_questions" in prompt_lower:
                return json.dumps(
                    {
                        "request_kind": "code_change",
                        "core_gui_change_requested": False,
                        "core_gui_change_authorized": False,
                        "clarifying_questions": [
                            "Can you give one concrete example of the expected behavior/output?",
                            "What should happen when the user clicks the button?",
                            "Do you have any design constraints?",
                        ],
                    }
                )
            return json.dumps({"intent": "feature_request", "confidence": 0.9, "reason": "semantic_feature"})

    assistant = LocalOperatorAssistant(
        repo_root=Path(__file__).resolve().parents[1],
        policy={"assistant_scope": {"intent_classifier": {"enabled": True, "model": "semantic-test"}}},
    )
    assistant._intent_classifier = _ManyQuestionModel()

    response = assistant.handle_message(
        "Need a new workflow tweak",
        session=assistant.init_session(),
    )
    assert len(response.followup_questions) <= 1


def test_actionable_request_with_possible_model_questions_asks_none_under_strict_policy():
    class _QuestionHappyModel:
        def chat_json(self, system_prompt: str, messages: list) -> str:
            prompt_lower = system_prompt.lower()
            if "request_kind" in prompt_lower and "clarifying_questions" in prompt_lower:
                return json.dumps(
                    {
                        "request_kind": "code_change",
                        "core_gui_change_requested": False,
                        "core_gui_change_authorized": False,
                        "clarifying_questions": [
                            "Can you give one concrete example of the expected behavior/output?",
                            "Do you have any design constraints?",
                        ],
                    }
                )
            return json.dumps({"intent": "feature_request", "confidence": 0.9, "reason": "semantic_feature"})

    assistant = LocalOperatorAssistant(
        repo_root=Path(__file__).resolve().parents[1],
        policy={"assistant_scope": {"intent_classifier": {"enabled": True, "model": "semantic-test"}}},
    )
    assistant._intent_classifier = _QuestionHappyModel()

    response = assistant.handle_message(
        "Add CSV export support to the runtime results view",
        session=assistant.init_session(),
    )
    assert response.followup_questions == []


def test_truly_vague_request_still_gets_single_blocking_followup():
    class _VagueQuestionModel:
        def chat_json(self, system_prompt: str, messages: list) -> str:
            prompt_lower = system_prompt.lower()
            if "request_kind" in prompt_lower and "clarifying_questions" in prompt_lower:
                return json.dumps(
                    {
                        "request_kind": "unknown",
                        "core_gui_change_requested": False,
                        "core_gui_change_authorized": False,
                        "clarifying_questions": [
                            "What should be changed?",
                            "Do you have any design constraints?",
                        ],
                    }
                )
            return json.dumps({"intent": "feature_request", "confidence": 0.9, "reason": "semantic_feature"})

    assistant = LocalOperatorAssistant(
        repo_root=Path(__file__).resolve().parents[1],
        policy={"assistant_scope": {"intent_classifier": {"enabled": True, "model": "semantic-test"}}},
    )
    assistant._intent_classifier = _VagueQuestionModel()

    response = assistant.handle_message(
        "Help with something",
        session=assistant.init_session(),
    )
    assert len(response.followup_questions) == 1
    assert response.followup_questions[0] == "What should be changed?"
