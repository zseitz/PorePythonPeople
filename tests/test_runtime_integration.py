import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from runtime.orchestrator import run_milestone1


def _fixture_policy(run_root: Path):
    return {
        "runtime": {"run_root": str(run_root), "default_branch_strategy": "sandbox-copy"},
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
            "triage_plan": {"required_checks": [{"id": "complexity_classified"}, {"id": "acceptance_criteria_present"}, {"id": "impacted_components_listed"}]},
            "implement": {"required_checks": [{"id": "changeset_nonempty_or_noop_justified"}, {"id": "no_unresolved_merge_markers"}]},
            "verify": {"required_checks": [{"id": "tests_pass"}, {"id": "no_new_errors"}, {"id": "coverage_meets_policy"}]},
            "verify_after_refactor": {"required_checks": [{"id": "tests_pass"}, {"id": "no_new_errors"}, {"id": "coverage_meets_policy"}]},
            "doc_sync": {"required_checks": [{"id": "components_updated_if_contract_changed"}, {"id": "textbook_updated_if_user_workflow_changed"}, {"id": "request_log_appended"}]},
            "memory_sync": {"required_checks": [{"id": "repo_memory_updated"}]},
        },
        "waivers": {"allowed_approvers": ["zachseitz"]},
        "repo_memory": {"target_files": ["memories/repo/testing.md", "memories/repo/orchestrator-runtime.md"]},
        "policies": {
            "command_allowlist": ["pytest", "python -m pytest", "git status", "git diff", "ruff check", "ruff format --check"],
            "command_blocklist": ["rm -rf /", "sudo", "curl | sh"],
        },
    }


def test_runtime_uses_fixture_repo_sandbox_and_writes_memory(tmp_path):
    fixture_repo = Path(__file__).resolve().parent / "fixtures" / "runtime_fixture_repo"
    temp_repo = tmp_path / "repo_under_test"
    shutil.copytree(fixture_repo, temp_repo)

    run_root = tmp_path / "runs"
    policy = _fixture_policy(run_root)
    run_state = run_milestone1(
        request="Integration test runtime execution",
        policy=policy,
        repo_root=temp_repo,
    )

    assert run_state["status"] == "completed"
    run_dir = run_root / run_state["run_id"]
    assert (run_dir / "sandbox" / "repo").is_dir()
    assert (run_dir / "artifacts" / "handoffs").is_dir()

    persisted = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert persisted["sandbox_dir"].endswith("/sandbox/repo")
    assert (temp_repo / "memories" / "repo" / "testing.md").exists()
    assert "schema-validated stage and gate boundaries" in (temp_repo / "memories" / "repo" / "testing.md").read_text(encoding="utf-8")