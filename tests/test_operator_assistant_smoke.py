import json
import shutil
from pathlib import Path

from runtime.operator_assistant import LocalOperatorAssistant
from runtime.orchestrator import run_milestone1


class _SemanticSmokeModel:
    """Semantic mock that returns strict JSON for intent and session analysis."""

    def chat(self, system_prompt: str, messages: list) -> str:
        prompt = (system_prompt or "").lower()
        if "request_kind" in prompt and "clarifying_questions" in prompt:
            return json.dumps(
                {
                    "request_kind": "code_change",
                    "core_gui_change_requested": False,
                    "core_gui_change_authorized": False,
                    "clarifying_questions": [],
                }
            )
        return json.dumps(
            {
                "intent": "feature_request",
                "confidence": 0.93,
                "reason": "smoke_feature_request",
            }
        )


def _smoke_policy(run_root: Path):
    return {
        "runtime": {
            "run_root": str(run_root),
            "promotion": {"enabled": False, "require_approval": True},
            "git_guardrails": {"require_clean_worktree": False, "recommend_feature_branch": False},
        },
        "model_provider": {"adapter": "none", "model": "test"},
        "specialists": {
            "orchestrator": {"prompt_inline": "orchestrator"},
            "feature_builder": {"prompt_inline": "builder"},
            "verifier": {"prompt_inline": "verifier"},
            "refactor": {"prompt_inline": "refactor"},
            "doc_sync": {"prompt_inline": "doc"},
            "memory_sync": {"prompt_inline": "memory"},
        },
        "stages": [
            {"id": "triage_plan", "owner": "orchestrator", "next_on_success": ["implement"]},
            {"id": "implement", "owner": "feature_builder", "next_on_success": ["verify"]},
            {"id": "verify", "owner": "verifier", "next_on_success": ["refactor_or_docsync"]},
            {
                "id": "refactor_or_docsync",
                "owner": "orchestrator",
                "next_on_success": ["refactor", "doc_sync"],
                "routing": {
                    "when": [
                        {"condition": "quality_signals.require_refactor == true", "next": "refactor"},
                        {"condition": "quality_signals.require_refactor == false", "next": "doc_sync"},
                    ]
                },
            },
            {"id": "refactor", "owner": "refactor", "required": False, "next_on_success": ["verify_after_refactor"]},
            {"id": "verify_after_refactor", "owner": "verifier", "required": False, "next_on_success": ["doc_sync"]},
            {"id": "doc_sync", "owner": "doc_sync", "next_on_success": ["memory_sync"]},
            {"id": "memory_sync", "owner": "memory_sync", "next_on_success": ["closeout"]},
            {"id": "closeout", "owner": "orchestrator"},
        ],
        "gates": {
            "triage_plan": {
                "required_checks": [
                    {"id": "complexity_classified"},
                    {"id": "acceptance_criteria_present"},
                    {"id": "impacted_components_listed"},
                ]
            },
            "implement": {
                "required_checks": [
                    {"id": "changeset_nonempty_or_noop_justified"},
                    {"id": "no_unresolved_merge_markers"},
                ]
            },
            "verify": {
                "required_checks": [
                    {"id": "tests_pass"},
                    {"id": "no_new_errors"},
                    {"id": "coverage_meets_policy"},
                ],
                "commands": {"tests": "python -m pytest --help"},
            },
            "verify_after_refactor": {
                "required_checks": [
                    {"id": "tests_pass"},
                    {"id": "no_new_errors"},
                    {"id": "coverage_meets_policy"},
                ],
                "commands": {"tests": "python -m pytest --help"},
            },
            "doc_sync": {
                "required_checks": [
                    {"id": "components_updated_if_contract_changed"},
                    {"id": "textbook_updated_if_user_workflow_changed"},
                    {"id": "request_log_appended"},
                ]
            },
            "memory_sync": {"required_checks": [{"id": "repo_memory_updated"}]},
        },
        "repo_memory": {"target_files": ["memories/repo/testing.md", "memories/repo/orchestrator-runtime.md"]},
        "skills": {
            "enabled": True,
            "max_chars_per_stage": 450,
            "stage_map": {
                "triage_plan": ["request-triage"],
                "implement": ["implementation-strategy"],
                "verify": ["verification-strategy"],
                "doc_sync": ["doc-sync-rules"],
            },
        },
        "policies": {
            "command_allowlist": ["pytest", "python -m pytest", "git status", "git diff", "ruff check", "ruff format --check"],
            "command_blocklist": ["rm -rf /", "sudo", "curl | sh"],
            "edit_scope": {"default_paths": ["src/**", "tests/**", "Docs/**", "runtime/**", "memories/repo/**"]},
            "action_limits": {"max_actions_per_stage": 20, "max_content_chars": 200000, "max_replace_chars": 50000},
        },
    }


def test_operator_assistant_smoke_request_to_runtime_artifacts(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    assistant = LocalOperatorAssistant(
        repo_root=repo_root,
        policy={"assistant_scope": {"intent_classifier": {"enabled": True, "model": "semantic-test"}}},
    )
    assistant._intent_classifier = _SemanticSmokeModel()

    response = assistant.handle_message(
        "Add a tiny runtime quality note and keep verification strict",
        session=assistant.init_session(),
    )

    assert response.intent == "feature_request"
    assert response.ready_to_run is True
    assert response.runtime_request is not None
    assert "Verification default for code changes" in response.runtime_request

    fixture_repo = Path(__file__).resolve().parent / "fixtures" / "runtime_fixture_repo"
    temp_repo = tmp_path / "repo_under_test"
    shutil.copytree(fixture_repo, temp_repo)

    run_root = tmp_path / "runs"
    run_state = run_milestone1(
        request=response.runtime_request,
        policy=_smoke_policy(run_root),
        repo_root=temp_repo,
    )

    assert run_state["status"] == "completed"
    run_dir = run_root / run_state["run_id"]
    assert (run_dir / "run.json").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "artifacts" / "handoffs").is_dir()
