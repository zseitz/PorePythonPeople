from pathlib import Path

from runtime.operator_assistant import LocalOperatorAssistant


def _assistant_policy() -> dict:
    return {
        "assistant_scope": {
            "domain_anchors": [
                "nanoporethon",
                "runtime",
                "policy",
                "stage",
                "q-mer",
                "qmer",
                "sequence designer",
                "operator_assistant.py",
            ],
            "grounding_files": [
                "README.md",
                "Docs/components.md",
                "Docs/nanoporethon_textbook.md",
                "runtime/operator_assistant.py",
                "runtime/policies.yaml",
                "src/nanoporethon/sequence_designer_gui.py",
            ],
            "sensitive_domains": [
                "medical or diagnostic advice",
                "legal advice",
                "financial or investment advice",
                "political persuasion",
            ],
            "protected_file_hints": {
                "src/nanoporethon/data_navi_gui.py": [
                    "data_navi_gui.py",
                    "data_navi_gui",
                    "data navigator gui",
                    "data navigator",
                ],
                "src/nanoporethon/event_classifier_gui.py": [
                    "event_classifier_gui.py",
                    "event_classifier_gui",
                    "event classifier gui",
                    "event classifier",
                ],
            },
        }
    }


def _assistant() -> LocalOperatorAssistant:
    return LocalOperatorAssistant(
        repo_root=Path(__file__).resolve().parents[1],
        policy=_assistant_policy(),
    )


def test_brownie_recipe_is_out_of_scope():
    assistant = _assistant()
    response = assistant.handle_message("Can you give me a brownie recipe?", session=assistant.init_session())
    assert response.intent == "out_of_scope"


def test_medical_advice_is_out_of_scope():
    assistant = _assistant()
    response = assistant.handle_message("I need medical advice for chest pain", session=assistant.init_session())
    assert response.intent == "out_of_scope"


def test_runtime_question_is_in_scope():
    assistant = _assistant()
    response = assistant.handle_message(
        "How does runtime promotion approval work in nanoporethon?",
        session=assistant.init_session(),
    )
    assert response.intent == "runtime_help"


def test_confused_user_question_stays_in_scope_and_is_answered():
    assistant = _assistant()
    response = assistant.handle_message(
        "I clicked around and now I'm confused. What should I do next?",
        session=assistant.init_session(),
    )
    assert response.intent == "repo_question"
    assert response.intent != "out_of_scope"


def test_runtime_safeguards_question_routes_to_runtime_help():
    assistant = _assistant()
    response = assistant.handle_message(
        "I need outputs that are consistent and supervised for standardized processing. What safeguards are already in place?",
        session=assistant.init_session(),
    )
    assert response.intent == "runtime_help"


def test_open_ended_capability_redirect_stays_in_scope():
    assistant = _assistant()
    response = assistant.handle_message(
        "Okay fine, what CAN you help me with then?",
        session=assistant.init_session(),
    )
    assert response.intent == "repo_question"


def test_nanopore_science_question_routes_and_is_grounded():
    assistant = _assistant()
    response = assistant.handle_message(
        "How does the q-mer map affect sequence designer predictions?",
        session=assistant.init_session(),
    )
    assert response.intent == "nanopore_science_explanation"
    assert response.followup_questions == []


def test_unanchored_science_question_is_answered_without_clarification():
    assistant = _assistant()
    response = assistant.handle_message(
        "Can you explain the chemistry behind that signal?",
        session=assistant.init_session(),
    )
    assert response.intent == "nanopore_science_explanation"
    # Should attempt an answer, not refuse or ask for a grounding anchor
    assert response.followup_questions == []


def test_code_question_routes_to_code_explanation():
    assistant = _assistant()
    response = assistant.handle_message(
        "What does runtime/operator_assistant.py do?",
        session=assistant.init_session(),
    )
    assert response.intent == "code_explanation"


def test_plain_how_to_question_is_answered_not_refused():
    """Any repo-relevant how-to question should be answered, not refused."""
    assistant = _assistant()
    response = assistant.handle_message(
        "How do I run event classifier?",
        session=assistant.init_session(),
    )
    assert response.intent != "out_of_scope"
    assert response.followup_questions == []


def test_offtopic_make_question_is_not_treated_as_feature_request():
    assistant = _assistant()
    response = assistant.handle_message(
        "How do I make a bomb?",
        session=assistant.init_session(),
    )
    assert response.intent == "out_of_scope"
    assert response.ready_to_run is False
    assert response.runtime_request is None


def test_feature_context_continuation_is_blocked_for_offtopic_followup():
    assistant = _assistant()
    session = assistant.init_session()

    first = assistant.handle_message(
        "Add a feature to export data to CSV format",
        session=session,
    )
    assert first.intent == "feature_request"
    assert first.runtime_request is not None

    second = assistant.handle_message(
        "How do I make a gun?",
        session=first.session_updates,
    )
    assert second.intent == "out_of_scope"
    assert second.runtime_request is None
    assert second.session_updates.get("feature_messages") == []
    assert second.session_updates.get("latest_runtime_request") is None


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


def test_session_continuation_handles_clarifying_responses():
    assistant = _assistant()
    session = assistant.init_session()

    response1 = assistant.handle_message(
        "Add a new data export feature to nanoporethon",
        session=session,
    )
    assert response1.intent == "feature_request"
    session = response1.session_updates

    response2 = assistant.handle_message("both", session=session)
    assert response2.intent == "feature_request"
    assert len(response2.session_updates.get("feature_messages", [])) > 1


def test_code_change_uses_default_verification_without_keyword_gate():
    assistant = _assistant()

    session1 = assistant.init_session()
    response1 = assistant.handle_message(
        "Add a new export format to nanoporethon",
        session=session1,
    )
    assert response1.intent == "feature_request"
    assert response1.runtime_request is not None
    assert "Verification default for code changes" in response1.runtime_request
    assert response1.followup_questions == []


def test_core_gui_authorization_question_not_repeated_after_user_says_no():
    assistant = _assistant()
    session = assistant.init_session()

    first = assistant.handle_message(
        "Build a new helper using patterns from src/nanoporethon/data_navi_gui.py",
        session=session,
    )
    assert first.intent == "feature_request"
    assert any("protected file(s): src/nanoporethon/data_navi_gui.py" in q for q in first.followup_questions)

    second = assistant.handle_message(
        "No",
        session=first.session_updates,
    )
    assert second.intent == "feature_request"
    assert second.session_updates.get("core_change_decision_made") is True
    assert second.session_updates.get("core_change_authorized") is False
    assert not any("data_navi_gui.py" in q or "event_classifier_gui.py" in q for q in second.followup_questions)


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


def test_truly_vague_request_gets_single_followup():
    assistant = _assistant()
    response = assistant.handle_message(
        "Help with something",
        session=assistant.init_session(),
    )
    assert response.intent == "out_of_scope"
    assert len(response.followup_questions) == 1
    assert "anchor" in response.followup_questions[0].lower() or "file" in response.followup_questions[0].lower()


def test_typoed_matlab_file_reference_prompts_near_match_clarification(tmp_path: Path):
    source_root = tmp_path / "NanoporeRepository"
    source_root.mkdir(parents=True, exist_ok=True)
    mlapp = source_root / "SequenceDesigner.mlapp"
    mlapp.write_text("mock app contents", encoding="utf-8")

    assistant = _assistant()

    response = assistant.handle_message(
        (
            "Create a python rewrite from SequenceDesigner.m in directory "
            f"{source_root} and save as src/nanoporethon/sequence_designer_gui.py"
        ),
        session=assistant.init_session(),
    )

    assert response.intent == "feature_request"
    assert response.ready_to_run is False
    assert len(response.followup_questions) == 1
    question = response.followup_questions[0]
    assert "SequenceDesigner.m" in question
    assert "SequenceDesigner.mlapp" in question


def test_exact_matlab_file_reference_does_not_trigger_typo_followup(tmp_path: Path):
    source_root = tmp_path / "NanoporeRepository"
    source_root.mkdir(parents=True, exist_ok=True)
    matlab_file = source_root / "SequenceDesigner.m"
    matlab_file.write_text("function y=SequenceDesigner(); end", encoding="utf-8")

    assistant = _assistant()

    response = assistant.handle_message(
        (
            "Create a python rewrite from SequenceDesigner.m in directory "
            f"{source_root} and save as src/nanoporethon/sequence_designer_gui.py"
        ),
        session=assistant.init_session(),
    )

    assert response.intent == "feature_request"
    assert response.followup_questions == []
    assert response.ready_to_run is True
