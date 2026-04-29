import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from runtime.executor import SpecialistExecutor
from runtime.gates import evaluate_stage_gates
from runtime.orchestrator import _build_cli_summary, _build_executor, run_milestone1
from runtime.planner import build_triage_plan, classify_complexity
from runtime.context_manager import ContextBudgetManager


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
        def _stage_payload(self, run_id, stage_id, request, context):
            payload = super()._stage_payload(run_id, stage_id, request, context)
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
    assert persisted["sandbox_dir"].endswith("/sandbox/repo")


def test_run_applies_approved_waiver(tmp_path):
    policy = _policy_with_run_root(tmp_path)
    policy["waivers"] = {"allowed_approvers": ["zachseitz"]}
    policy["gates"]["verify"]["required_checks"].append({"id": "must_be_false_for_test"})

    run_state = run_milestone1(
        request="Run waiver path test",
        policy=policy,
        executor=SpecialistExecutor(),
        requested_waivers={
            "must_be_false_for_test": {
                "approver": "zachseitz",
                "reason": "Operator approved skip for controlled test.",
                "scope": "single gate",
            }
        },
        repo_root=Path(__file__).resolve().parents[1],
    )

    assert run_state["status"] == "completed"
    waiver_log = tmp_path / run_state["run_id"] / "artifacts" / "waivers.jsonl"
    assert waiver_log.exists()
    assert "must_be_false_for_test" in waiver_log.read_text(encoding="utf-8")


def test_resume_requires_operator_choice(tmp_path):
    policy = _policy_with_run_root(tmp_path)
    try:
        run_milestone1(
            request="Resume without choice",
            policy=policy,
            executor=SpecialistExecutor(),
            resume_run_id="run_abc123",
            repo_root=Path(__file__).resolve().parents[1],
        )
    except ValueError as exc:
        assert "Resume requested but no operator choice" in str(exc)
    else:
        raise AssertionError("Expected ValueError when resume_choice is missing")


def test_memory_sync_writes_directly_to_repo_memory(tmp_path):
    fixture_repo = Path(__file__).resolve().parent / "fixtures" / "runtime_fixture_repo"
    temp_repo = tmp_path / "fixture_repo"
    shutil.copytree(fixture_repo, temp_repo)

    policy = _policy_with_run_root(tmp_path)
    policy["repo_memory"] = {
        "target_files": ["memories/repo/testing.md", "memories/repo/orchestrator-runtime.md"]
    }
    policy["waivers"] = {"allowed_approvers": ["zachseitz"]}

    run_state = run_milestone1(
        request="Write memory updates",
        policy=policy,
        executor=None,
        repo_root=temp_repo,
    )

    assert run_state["status"] == "completed"
    memory_file = temp_repo / "memories" / "repo" / "testing.md"
    assert memory_file.exists()
    assert "schema-validated stage and gate boundaries" in memory_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# ContextBudgetManager unit tests
# ---------------------------------------------------------------------------

def test_context_manager_below_threshold_no_compact():
    mgr = ContextBudgetManager(
        stage_budgets={"triage_plan": 10000},
        default_budget=10000,
        compaction_thresholds=[60, 75, 85],
    )
    small_payload = {"key": "value"}
    assert mgr.should_compact("triage_plan", small_payload) is False
    compacted, n = mgr.maybe_compact("triage_plan", small_payload)
    assert n == 0
    assert compacted == small_payload


def test_context_manager_above_threshold_compacts():
    # Tiny budget forces the payload over the threshold.
    mgr = ContextBudgetManager(
        stage_budgets={"implement": 1},
        default_budget=1,
        compaction_thresholds=[1, 75, 85],
    )
    payload = {"notes": "drop me", "summary": "A" * 600}
    assert mgr.should_compact("implement", payload) is True
    compacted, n = mgr.compact_payload(payload)
    # "notes" key should be dropped and "summary" should be truncated
    assert "notes" not in compacted
    assert len(compacted["summary"]) < 600
    assert n >= 2


def test_context_manager_record_stage_and_summary():
    mgr = ContextBudgetManager(
        stage_budgets={"verify": 4000},
        default_budget=4000,
        compaction_thresholds=[60, 75, 85],
    )
    payload = {"checks_run": ["pytest -q -> 0"], "quality_signals": {"require_refactor": False}}
    mgr.record_stage("verify", payload, compactions_applied=0)
    summary = mgr.summary()
    assert summary["stages_tracked"] == 1
    assert summary["total_compactions"] == 0
    assert summary["peak_utilization_pct"] >= 0.0
    assert summary["per_stage"][0]["stage_id"] == "verify"


def test_context_manager_empty_summary():
    mgr = ContextBudgetManager()
    summary = mgr.summary()
    assert summary["stages_tracked"] == 0
    assert summary["total_estimated_tokens"] == 0
    assert summary["per_stage"] == []


def test_context_manager_from_policy():
    policy = {
        "context_budgets": {
            "default_budget": 5000,
            "triage_plan": 2000,
            "implement": 7000,
            "compaction_thresholds": [50, 75, 90],
        }
    }
    mgr = ContextBudgetManager.from_policy(policy)
    assert mgr.default_budget == 5000
    assert mgr.get_budget("triage_plan") == 2000
    assert mgr.get_budget("implement") == 7000
    assert mgr.get_budget("unknown_stage") == 5000
    assert mgr.compaction_thresholds == [50, 75, 90]


def test_run_state_includes_context_metrics_after_completion(tmp_path):
    policy = _policy_with_run_root(tmp_path)
    policy["context_budgets"] = {
        "default_budget": 8000,
        "compaction_thresholds": [60, 75, 85],
    }
    run_state = run_milestone1(
        request="Validate context metrics in run artifacts",
        policy=policy,
        executor=SpecialistExecutor(),
        repo_root=Path(__file__).resolve().parents[1],
    )
    assert run_state["status"] == "completed"
    metrics = run_state.get("context_metrics", {})
    assert isinstance(metrics, dict)
    assert metrics["stages_tracked"] > 0
    assert "peak_utilization_pct" in metrics
    assert "per_stage" in metrics
    # Verify it is also persisted to run.json
    run_dir = tmp_path / run_state["run_id"]
    persisted = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert persisted["context_metrics"]["stages_tracked"] == metrics["stages_tracked"]


def test_cli_summary_includes_context_budget_data():
    run_state = {
        "run_id": "run_test123",
        "status": "completed",
        "current_stage": "closeout",
        "stage_history": [{"stage_id": "triage_plan"}, {"stage_id": "implement"}],
        "context_metrics": {
            "stages_tracked": 2,
            "total_estimated_tokens": 1200,
            "peak_utilization_pct": 42.5,
            "total_compactions": 1,
            "per_stage": [
                {
                    "stage_id": "triage_plan",
                    "estimated_tokens": 300,
                    "budget_tokens": 4000,
                    "utilization_pct": 7.5,
                    "compacted": False,
                },
                {
                    "stage_id": "implement",
                    "estimated_tokens": 900,
                    "budget_tokens": 8000,
                    "utilization_pct": 11.2,
                    "compacted": True,
                },
            ],
        },
    }
    summary = _build_cli_summary(run_state)
    assert "Context Budget Summary:" in summary
    assert "Peak utilization: 42.5%" in summary
    assert "implement: 900/8000 tokens (11.2%) (compacted)" in summary


def test_live_progress_outputs_traffic_light_lines(tmp_path, capsys):
    policy = _policy_with_run_root(tmp_path)
    policy["context_budgets"] = {
        "default_budget": 8000,
        "compaction_thresholds": [60, 75, 85],
    }
    run_state = run_milestone1(
        request="Emit live progress lines",
        policy=policy,
        executor=SpecialistExecutor(),
        repo_root=Path(__file__).resolve().parents[1],
        live_progress=True,
    )
    assert run_state["status"] == "completed"
    out = capsys.readouterr().out
    assert "gate:PASS" in out
    assert "triage_plan" in out
    assert "🟢" in out or "🟡" in out or "🔴" in out


def test_live_progress_can_be_disabled(tmp_path, capsys):
    policy = _policy_with_run_root(tmp_path)
    run_state = run_milestone1(
        request="Do not emit live progress lines",
        policy=policy,
        executor=SpecialistExecutor(),
        repo_root=Path(__file__).resolve().parents[1],
        live_progress=False,
    )
    assert run_state["status"] == "completed"
    out = capsys.readouterr().out
    assert out == ""


def test_build_executor_supports_specialist_model_overrides(tmp_path):
    policy = _policy_with_run_root(tmp_path)
    policy["model_provider"] = {
        "adapter": "ollama",
        "model": "global-model",
        "base_url": "http://localhost:11434",
    }
    policy["specialists"]["feature_builder"]["model_provider"] = {
        "model": "feature-model"
    }
    policy["specialists"]["doc_sync"]["model_provider"] = {
        "model": "docs-model",
        "base_url": "http://localhost:11435",
    }

    executor = _build_executor(
        policy=policy,
        repo_root=Path(__file__).resolve().parents[1],
        repo_ops=None,
        memory_writer=None,
        context_manager=None,
    )

    assert executor.model_adapter is not None
    assert getattr(executor.model_adapter, "model") == "global-model"
    assert "feature_builder" in executor.model_adapters
    assert getattr(executor.model_adapters["feature_builder"], "model") == "feature-model"
    assert "doc_sync" in executor.model_adapters
    assert getattr(executor.model_adapters["doc_sync"], "model") == "docs-model"
    assert getattr(executor.model_adapters["doc_sync"], "base_url") == "http://localhost:11435"


def test_executor_uses_owner_specific_adapter_when_present():
    class FakeAdapter:
        def __init__(self, label):
            self.label = label

        def chat(self, _system_prompt, _messages):
            return f"from-{self.label}"

    executor = SpecialistExecutor(
        specialists={"doc_sync": {"prompt_inline": "doc specialist"}},
        model_adapter=FakeAdapter("default"),
        model_adapters={"doc_sync": FakeAdapter("doc")},
    )

    doc_response = executor._try_model_response(
        owner="doc_sync",
        stage_id="doc_sync",
        request="Update docs",
        context={"request": "Update docs"},
    )
    verify_response = executor._try_model_response(
        owner="verifier",
        stage_id="verify",
        request="Run checks",
        context={"request": "Run checks"},
    )

    assert doc_response == "from-doc"
    assert verify_response == "from-default"

