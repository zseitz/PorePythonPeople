import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from runtime.executor import SpecialistExecutor
from runtime.gates import evaluate_stage_gates
from runtime.orchestrator import run_milestone1
from runtime.planner import build_triage_plan, classify_complexity


def _policy_with_run_root(run_root: Path):
    return {
        "runtime": {"run_root": str(run_root)},
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
                ]
            },
            "verify_after_refactor": {
                "required_checks": [
                    {"id": "tests_pass"},
                    {"id": "no_new_errors"},
                    {"id": "coverage_meets_policy"},
                ]
            },
            "doc_sync": {
                "required_checks": [
                    {"id": "components_updated_if_contract_changed"},
                    {"id": "textbook_updated_if_user_workflow_changed"},
                    {"id": "request_log_appended"},
                ]
            },
            "memory_sync": {
                "required_checks": [
                    {"id": "repo_memory_updated"},
                ]
            },
        },
    }


def _stage_ids_from_run_state(run_state):
    return [entry["stage_id"] for entry in run_state["stage_history"]]


def test_classify_complexity_large_for_contract_migration():
    request = "Plan a cross-component contract migration with schema changes"
    assert classify_complexity(request) == "Large"


def test_build_triage_plan_contains_required_outputs():
    plan = build_triage_plan("Add runtime verification improvements")
    assert plan["complexity"] in {"Small", "Medium", "Large"}
    assert isinstance(plan["acceptance_criteria"], list)
    assert bool(plan["impacted_components"])


def test_evaluate_stage_gates_pass_and_fail():
    required = [{"id": "a"}, {"id": "b"}]

    passed, gate_results = evaluate_stage_gates("run_1", "triage_plan", required, {"a": True, "b": True})
    assert passed is True
    assert [g["status"] for g in gate_results] == ["pass", "pass"]

    passed, gate_results = evaluate_stage_gates("run_1", "triage_plan", required, {"a": True, "b": False})
    assert passed is False
    assert [g["status"] for g in gate_results] == ["pass", "fail"]


def test_run_routing_without_refactor_path(tmp_path):
    policy = _policy_with_run_root(tmp_path)
    run_state = run_milestone1(
        request="Run doc sync path",
        policy=policy,
        executor=SpecialistExecutor(),
        repo_root=Path(__file__).resolve().parents[1],
    )

    assert run_state["status"] == "completed"
    stage_ids = _stage_ids_from_run_state(run_state)
    assert "refactor" not in stage_ids
    assert stage_ids[-1] == "closeout"

    run_id = run_state["run_id"]
    run_dir = tmp_path / run_id
    assert (run_dir / "run.json").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "artifacts" / "handoffs").is_dir()


def test_run_routing_with_refactor_path(tmp_path):
    class RefactorRequiredExecutor(SpecialistExecutor):
        def _stage_payload(self, stage_id, request, context):
            payload = super()._stage_payload(stage_id, request, context)
            if stage_id == "verify":
                payload["quality_signals"] = {"require_refactor": True}
            return payload

    policy = _policy_with_run_root(tmp_path)
    run_state = run_milestone1(
        request="Run refactor path",
        policy=policy,
        executor=RefactorRequiredExecutor(),
        repo_root=Path(__file__).resolve().parents[1],
    )

    assert run_state["status"] == "completed"
    stage_ids = _stage_ids_from_run_state(run_state)
    assert "refactor" in stage_ids
    assert "verify_after_refactor" in stage_ids


def test_run_fails_when_gate_check_missing(tmp_path):
    policy = _policy_with_run_root(tmp_path)
    policy["gates"]["verify"]["required_checks"].append({"id": "must_be_false_for_test"})

    run_state = run_milestone1(
        request="Run verify failure path test",
        policy=policy,
        executor=SpecialistExecutor(),
        repo_root=Path(__file__).resolve().parents[1],
    )

    assert run_state["status"] == "failed"


def test_run_state_artifact_contract_written(tmp_path):
    policy = _policy_with_run_root(tmp_path)
    run_state = run_milestone1(
        request="Validate run artifacts",
        policy=policy,
        executor=SpecialistExecutor(),
        repo_root=Path(__file__).resolve().parents[1],
    )

    run_dir = tmp_path / run_state["run_id"]
    persisted = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "completed"
    assert isinstance(persisted["stage_history"], list)
    assert persisted["artifacts_dir"].endswith("/artifacts")
    assert persisted["events_file"].endswith("/events.jsonl")
