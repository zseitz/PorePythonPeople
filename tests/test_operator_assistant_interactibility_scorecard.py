from __future__ import annotations

import json
from pathlib import Path

from runtime.operator_assistant_interactibility_scorecard import (
    PROMPT_CASES,
    build_scorecard,
    write_scorecard_artifacts,
)


class _FakeAssistantResponse:
    def __init__(self, intent: str, session_updates: dict):
        self.intent = intent
        self.confidence = 0.95
        self.reason = "fake_assistant"
        self.message = "mock response"
        self.followup_questions = []
        self.ready_to_run = False
        self.runtime_request = None
        self.session_updates = session_updates


class _FakeAssistant:
    def __init__(self) -> None:
        self._mapping = {
            case.prompt: case.expected_intents[0]
            for case in PROMPT_CASES
        }

    def init_session(self) -> dict:
        return {"history": []}

    def handle_message(self, text: str, session: dict | None = None) -> _FakeAssistantResponse:
        session_updates = dict(session or {})
        history = session_updates.get("history", [])
        if not isinstance(history, list):
            history = []
        history.append(text)
        session_updates["history"] = history
        intent = self._mapping.get(text, "repo_question")
        return _FakeAssistantResponse(intent=intent, session_updates=session_updates)


def test_build_scorecard_dry_mode_records_pending_cases() -> None:
    scorecard = build_scorecard(mode="dry")

    assert scorecard["component"] == "operator_assistant_interactibility"
    assert scorecard["mode"] == "dry"
    assert scorecard["summary"]["pending"] == len(PROMPT_CASES)
    assert scorecard["summary"]["failed"] == 0
    assert all(case["status"] == "pending" for case in scorecard["cases"])


def test_build_scorecard_live_mode_with_fake_assistant_passes() -> None:
    scorecard = build_scorecard(mode="live", assistant=_FakeAssistant())

    assert scorecard["mode"] == "live"
    assert scorecard["summary"]["failed"] == 0
    assert scorecard["summary"]["passed"] == len(PROMPT_CASES)
    assert scorecard["summary"]["adversarial_clean"] is True
    assert scorecard["summary"]["graduation_ready"] is True


def test_write_interactibility_scorecard_artifacts(tmp_path: Path) -> None:
    scorecard = build_scorecard(mode="live", assistant=_FakeAssistant())

    artifacts = write_scorecard_artifacts(scorecard, tmp_path)

    json_path = artifacts["json"]
    markdown_path = artifacts["markdown"]

    assert json_path.exists()
    assert markdown_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["failed"] == 0

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Porsche Interactibility Scorecard" in markdown
    assert "Category summary" in markdown
    assert "Case results" in markdown
