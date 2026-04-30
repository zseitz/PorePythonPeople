import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import runtime.orchestrator as orchestrator_module
from runtime.executor import SpecialistExecutor, build_gate_evidence
from runtime.gates import evaluate_stage_gates
from runtime.orchestrator import _build_cli_summary, _build_executor, run_milestone1
from runtime.planner import build_triage_plan, classify_complexity
from runtime.context_manager import ContextBudgetManager
from runtime.repo_ops import RepoSandboxManager


def _policy_with_run_root(run_root: Path):
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
                "commands": {
                    "tests": "pytest -q tests/test_runtime_milestone1.py::test_classify_complexity_large_for_contract_migration",
                },
            },
            "verify_after_refactor": {
                "required_checks": [
                    {"id": "tests_pass"},
                    {"id": "no_new_errors"},
                    {"id": "coverage_meets_policy"},
                ],
                "commands": {
                    "tests": "pytest -q tests/test_runtime_milestone1.py::test_classify_complexity_large_for_contract_migration",
                },
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


def _init_git_repo(repo_dir: Path, branch: str = "feature/runtime-guardrails") -> Path:
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "README.md").write_text("initial\n", encoding="utf-8")

    init_cmd = ["git", "init", "-b", branch]
    init_result = subprocess.run(init_cmd, cwd=repo_dir, capture_output=True, text=True, check=False)
    if init_result.returncode != 0:
        subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True, text=True, check=True)
        subprocess.run(["git", "checkout", "-b", branch], cwd=repo_dir, capture_output=True, text=True, check=True)

    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=repo_dir, capture_output=True, text=True, check=True)
    subprocess.run(["git", "config", "user.name", "Runtime Tests"], cwd=repo_dir, capture_output=True, text=True, check=True)
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, capture_output=True, text=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, capture_output=True, text=True, check=True)
    return repo_dir


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
    assert "repo_snapshot_file" in persisted
    assert "startup_warnings" in persisted


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
    policy["gates"]["verify"]["commands"] = {"tests": "python -m pytest --help"}
    policy["gates"]["verify_after_refactor"]["commands"] = {"tests": "python -m pytest --help"}
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
    run_dir = tmp_path / run_state["run_id"]
    payload = json.loads((run_dir / "artifacts" / "stages" / "memory_sync_payload.json").read_text(encoding="utf-8"))
    assert "memories/repo/testing.md" in payload.get("changed_files", [])


def test_verify_treats_pytest_no_tests_collected_as_pass(tmp_path):
    policy = _policy_with_run_root(tmp_path)
    # Force pytest to collect zero tests (exit code 5).
    policy["gates"]["verify"]["commands"] = {
        "tests": "pytest -q -k definitely_no_test_should_match tests/test_runtime_milestone1.py",
    }
    policy["gates"]["verify_after_refactor"]["commands"] = {
        "tests": "pytest -q -k definitely_no_test_should_match tests/test_runtime_milestone1.py",
    }

    run_state = run_milestone1(
        request="No-tests-collected verify command",
        policy=policy,
        executor=SpecialistExecutor(),
        repo_root=Path(__file__).resolve().parents[1],
    )

    assert run_state["status"] == "completed"


def test_promotion_applies_doc_sync_changes_to_repo(tmp_path):
    fixture_repo = Path(__file__).resolve().parent / "fixtures" / "runtime_fixture_repo"
    temp_repo = tmp_path / "fixture_repo"
    shutil.copytree(fixture_repo, temp_repo)

    policy = _policy_with_run_root(tmp_path)
    policy["runtime"]["promotion"] = {"enabled": True, "require_approval": False}
    policy["runtime"]["git_guardrails"] = {"require_clean_worktree": False, "recommend_feature_branch": False}
    # Keep verify deterministic and quick for this promotion-path test.
    policy["gates"]["verify"]["commands"] = {"tests": "python -m pytest --help"}
    policy["gates"]["verify_after_refactor"]["commands"] = {"tests": "python -m pytest --help"}

    run_state = run_milestone1(
        request="Promotion path test",
        policy=policy,
        executor=None,
        repo_root=temp_repo,
    )

    assert run_state["status"] == "completed"
    promoted = run_state.get("promoted_files", [])
    assert isinstance(promoted, list)
    assert "Docs/agent_logs/REQUEST_LOG.md" in promoted

    request_log = temp_repo / "Docs" / "agent_logs" / "REQUEST_LOG.md"
    assert request_log.exists()
    assert "Runtime doc sync fallback entry" in request_log.read_text(encoding="utf-8")


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


def test_run_blocks_when_stage_transition_not_approved(tmp_path):
    policy = _policy_with_run_root(tmp_path)

    def approval_handler(request):
        assert request["from_stage"] == "triage_plan"
        assert request["to_stage"] == "implement"
        return "reject"

    run_state = run_milestone1(
        request="Pause after planning",
        policy=policy,
        executor=SpecialistExecutor(),
        repo_root=Path(__file__).resolve().parents[1],
        approval_mode="per_stage",
        approval_handler=approval_handler,
    )

    assert run_state["status"] == "blocked"
    assert _stage_ids_from_run_state(run_state) == ["triage_plan"]
    pending = run_state["pending_approval"]
    assert pending["from_stage"] == "triage_plan"
    assert pending["to_stage"] == "implement"

    events_text = (tmp_path / run_state["run_id"] / "events.jsonl").read_text(encoding="utf-8")
    assert '"type": "approval_requested"' in events_text
    assert '"decision": "rejected"' in events_text


def test_resume_after_stage_transition_approval_block(tmp_path):
    policy = _policy_with_run_root(tmp_path)
    repo_root = Path(__file__).resolve().parents[1]
    decisions = iter(["reject", "approve", "approve", "approve", "approve", "approve", "approve"])

    def approval_handler(_request):
        return next(decisions)

    first_run = run_milestone1(
        request="Pause and resume",
        policy=policy,
        executor=SpecialistExecutor(),
        repo_root=repo_root,
        approval_mode="per_stage",
        approval_handler=approval_handler,
    )
    assert first_run["status"] == "blocked"

    resumed_run = run_milestone1(
        request="Pause and resume",
        policy=policy,
        executor=SpecialistExecutor(),
        repo_root=repo_root,
        resume_run_id=first_run["run_id"],
        resume_choice="resume_from_last_completed",
        approval_handler=approval_handler,
    )

    assert resumed_run["status"] == "completed"
    assert resumed_run["pending_approval"] == {}
    assert resumed_run["approval_mode"] == "per_stage"
    assert resumed_run["stage_history"][-1]["stage_id"] == "closeout"


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


def test_executor_applies_llm_json_actions_in_sandbox(tmp_path):
    class FakeAdapter:
        def chat(self, _system_prompt, _messages):
            return json.dumps(
                {
                    "changed_files": [],
                    "implementation_summary": "Implemented from model payload",
                    "test_updates": ["Added regression coverage"],
                    "unresolved_risks": [],
                    "noop_justified": False,
                    "actions": [
                        {
                            "type": "write_file",
                            "path": "runtime/generated_from_model.txt",
                            "content": "hello from llm json\n",
                        }
                    ],
                }
            )

    repo_root = Path(__file__).resolve().parents[1]
    sandbox = RepoSandboxManager(repo_root=repo_root, sandbox_root=tmp_path / "sandbox")
    sandbox.prepare()

    executor = SpecialistExecutor(
        specialists={"feature_builder": {"prompt_inline": "feature"}},
        model_adapter=FakeAdapter(),
        repo_root=repo_root,
        repo_ops=sandbox,
        policy=_policy_with_run_root(tmp_path),
    )

    result = executor.run_stage(
        run_id="run_test",
        stage_id="implement",
        owner="feature_builder",
        request="Generate file",
        context={"request": "Generate file"},
        artifacts_dir=tmp_path / "artifacts",
    )

    payload_path = Path(result["artifacts"][0]["path"])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert "runtime/generated_from_model.txt" in payload["changed_files"]
    assert payload["llm_integration"]["used_llm_payload"] is True
    assert (sandbox.sandbox_repo / "runtime/generated_from_model.txt").exists()


def test_executor_falls_back_when_llm_payload_is_invalid(tmp_path):
    class FakeAdapter:
        def chat(self, _system_prompt, _messages):
            return "this is not json"

    repo_root = Path(__file__).resolve().parents[1]
    sandbox = RepoSandboxManager(repo_root=repo_root, sandbox_root=tmp_path / "sandbox")
    sandbox.prepare()

    executor = SpecialistExecutor(
        specialists={"feature_builder": {"prompt_inline": "feature"}},
        model_adapter=FakeAdapter(),
        repo_root=repo_root,
        repo_ops=sandbox,
        policy=_policy_with_run_root(tmp_path),
    )

    result = executor.run_stage(
        run_id="run_test",
        stage_id="implement",
        owner="feature_builder",
        request="Generate file",
        context={"request": "Generate file"},
        artifacts_dir=tmp_path / "artifacts",
    )

    payload_path = Path(result["artifacts"][0]["path"])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["noop_justified"] is True
    assert payload["llm_integration"]["fallback_used"] is True


def test_repo_ops_blocks_shell_control_tokens(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sandbox = RepoSandboxManager(repo_root=repo_root, sandbox_root=tmp_path / "sandbox")
    sandbox.prepare()

    try:
        sandbox.run_command(
            "pytest -q; echo hacked",
            allowlist=["pytest"],
            blocklist=["rm -rf /"],
        )
    except PermissionError as exc:
        assert "disallowed shell control characters" in str(exc)
    else:
        raise AssertionError("Expected shell control token command to be blocked")


def test_promotion_rejected_by_operator_records_skip_event(tmp_path):
    policy = _policy_with_run_root(tmp_path)
    policy["runtime"]["promotion"] = {"enabled": True, "require_approval": True}

    def approval_handler(request):
        if "from_stage" in request:
            return "approve"
        return "reject"

    run_state = run_milestone1(
        request="Create changes but reject promotion",
        policy=policy,
        executor=None,
        repo_root=Path(__file__).resolve().parents[1],
        approval_handler=approval_handler,
    )

    assert run_state["status"] == "completed"
    events_path = tmp_path / run_state["run_id"] / "events.jsonl"
    events_text = events_path.read_text(encoding="utf-8")
    assert '"type": "promotion_requested"' in events_text
    assert '"type": "promotion_skipped"' in events_text


def test_run_records_git_baseline_and_feature_branch_warning(tmp_path, capsys):
    repo_root = _init_git_repo(tmp_path / "git_repo", branch="main")
    policy = _policy_with_run_root(tmp_path / "runs")
    policy["runtime"]["git_guardrails"] = {"require_clean_worktree": True, "recommend_feature_branch": True}
    policy["gates"]["verify"]["commands"] = {"tests": "python -m pytest --help"}
    policy["gates"]["verify_after_refactor"]["commands"] = {"tests": "python -m pytest --help"}
    policy["repo_memory"] = {"target_files": ["memories/repo/testing.md"]}

    run_state = run_milestone1(
        request="Record git baseline metadata",
        policy=policy,
        repo_root=repo_root,
    )

    assert run_state["status"] == "completed"
    assert run_state["base_commit"]
    assert run_state["base_branch"] == "main"
    assert run_state["repo_snapshot_file"].endswith("repo_start_snapshot.json")
    assert run_state["startup_warnings"]
    out = capsys.readouterr().out
    assert "feature branch" in out


def test_run_refuses_dirty_git_worktree_before_start(tmp_path):
    repo_root = _init_git_repo(tmp_path / "dirty_repo")
    (repo_root / "README.md").write_text("dirty change\n", encoding="utf-8")

    policy = _policy_with_run_root(tmp_path / "runs")
    policy["runtime"]["git_guardrails"] = {"require_clean_worktree": True, "recommend_feature_branch": False}
    run_state = run_milestone1(
        request="Reject dirty repo",
        policy=policy,
        repo_root=repo_root,
        executor=SpecialistExecutor(),
    )

    assert run_state["status"] == "failed"
    run_dir = Path(policy["runtime"]["run_root"]) / run_state["run_id"]
    assert (run_dir / "run.json").exists()
    events_text = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert '"type": "startup_error"' in events_text


def test_promotion_blocked_when_target_file_changes_during_run(tmp_path, monkeypatch):
    class PromotionChangeExecutor(SpecialistExecutor):
        def _stage_payload(self, run_id, stage_id, request, context):
            payload = super()._stage_payload(run_id, stage_id, request, context)
            if stage_id == "implement":
                payload.update(
                    {
                        "changed_files": [],
                        "implementation_summary": "Modify README in sandbox",
                        "test_updates": [],
                        "unresolved_risks": [],
                        "noop_justified": False,
                        "actions": [
                            {
                                "type": "write_file",
                                "path": "README.md",
                                "content": "sandbox change\n",
                            }
                        ],
                    }
                )
            return payload

    repo_root = _init_git_repo(tmp_path / "promotion_repo")
    policy = _policy_with_run_root(tmp_path / "runs")
    policy["runtime"]["promotion"] = {"enabled": True, "require_approval": True}
    policy["runtime"]["git_guardrails"] = {"require_clean_worktree": True, "recommend_feature_branch": False}
    policy["gates"]["verify"]["commands"] = {"tests": "python -m pytest --help"}
    policy["gates"]["verify_after_refactor"]["commands"] = {"tests": "python -m pytest --help"}
    policy["repo_memory"] = {"target_files": ["memories/repo/testing.md"]}

    def fake_build_executor(policy, repo_root, repo_ops, memory_writer, context_manager):
        return PromotionChangeExecutor(
            repo_root=repo_root,
            repo_ops=repo_ops,
            memory_writer=memory_writer,
            policy=policy,
            context_manager=context_manager,
        )

    monkeypatch.setattr(orchestrator_module, "_build_executor", fake_build_executor)

    def approval_handler(request):
        if request.get("from_stage") == "memory_sync" and request.get("to_stage") == "closeout":
            (repo_root / "README.md").write_text("real repo drift\n", encoding="utf-8")
        return "approve"

    run_state = run_milestone1(
        request="Block promotion on target drift",
        policy=policy,
        repo_root=repo_root,
        executor=None,
        approval_mode="per_stage",
        approval_handler=approval_handler,
    )

    assert run_state["status"] == "completed"
    assert run_state["promoted_files"] == []
    run_dir = Path(policy["runtime"]["run_root"]) / run_state["run_id"]
    promotion_payload = json.loads((run_dir / "artifacts" / "promotion_diff.json").read_text(encoding="utf-8"))
    guardrails = promotion_payload["repo_guardrails"]
    assert "README.md" in guardrails["conflicting_files"]
    events_text = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert '"type": "promotion_blocked"' in events_text


def test_implement_gate_fails_when_merge_markers_found():
    evidence = build_gate_evidence(
        "implement",
        {
            "changed_files": ["src/example.py"],
            "noop_justified": False,
            "merge_markers_found": True,
        },
    )
    assert evidence["changeset_nonempty_or_noop_justified"] is True
    assert evidence["no_unresolved_merge_markers"] is False


def test_verify_uses_sandbox_default_cwd(tmp_path):
    class CapturingRepoOps:
        sandbox_repo = Path("/tmp/sandbox")

        def run_command(self, _command, _allowlist, _blocklist, cwd=None, timeout=120):
            self.captured_cwd = cwd
            return {"command": "pytest -q", "exit_code": 0, "stdout": "", "stderr": ""}

        def changed_files(self):
            return []

    repo_ops = CapturingRepoOps()
    policy = _policy_with_run_root(tmp_path)
    policy["gates"]["verify"] = {"required_checks": [], "commands": {"tests": "pytest -q"}}
    executor = SpecialistExecutor(policy=policy, repo_ops=repo_ops)

    payload = executor._run_verify_commands("verify", context={})
    assert payload["tests_exit_code"] == 0
    assert getattr(repo_ops, "captured_cwd", "sentinel") is None


def test_no_tests_collected_fails_without_opt_in(tmp_path):
    class ExitFiveRepoOps:
        sandbox_repo = Path("/tmp/sandbox")

        def run_command(self, _command, _allowlist, _blocklist, cwd=None, timeout=120):
            return {"command": "pytest -q", "exit_code": 5, "stdout": "", "stderr": "no tests collected"}

        def changed_files(self):
            return []

    policy = _policy_with_run_root(tmp_path)
    policy["gates"]["verify"] = {
        "required_checks": [{"id": "tests_pass"}],
        "commands": {"tests": "pytest -q"},
        "allow_no_tests_collected": False,
    }
    executor = SpecialistExecutor(policy=policy, repo_ops=ExitFiveRepoOps())
    payload = executor._run_verify_commands("verify", context={})
    evidence = build_gate_evidence("verify", payload)
    assert payload["tests_exit_code"] == 5
    assert evidence["tests_pass"] is False


def test_no_tests_collected_passes_with_opt_in(tmp_path):
    class ExitFiveRepoOps:
        sandbox_repo = Path("/tmp/sandbox")

        def run_command(self, _command, _allowlist, _blocklist, cwd=None, timeout=120):
            return {"command": "pytest -q", "exit_code": 5, "stdout": "", "stderr": "no tests collected"}

        def changed_files(self):
            return []

    policy = _policy_with_run_root(tmp_path)
    policy["gates"]["verify"] = {
        "required_checks": [{"id": "tests_pass"}],
        "commands": {"tests": "pytest -q"},
        "allow_no_tests_collected": True,
    }
    executor = SpecialistExecutor(policy=policy, repo_ops=ExitFiveRepoOps())
    payload = executor._run_verify_commands("verify", context={})
    evidence = build_gate_evidence("verify", payload)
    assert payload["tests_exit_code"] == 0
    assert evidence["tests_pass"] is True


def test_valid_json_missing_required_fields_falls_back(tmp_path):
    class FakeAdapter:
        def chat(self, _system_prompt, _messages):
            return json.dumps({"implementation_summary": "partial"})

    repo_root = Path(__file__).resolve().parents[1]
    sandbox = RepoSandboxManager(repo_root=repo_root, sandbox_root=tmp_path / "sandbox")
    sandbox.prepare()

    executor = SpecialistExecutor(
        specialists={"feature_builder": {"prompt_inline": "feature"}},
        model_adapter=FakeAdapter(),
        repo_root=repo_root,
        repo_ops=sandbox,
        policy=_policy_with_run_root(tmp_path),
    )

    result = executor.run_stage(
        run_id="run_test",
        stage_id="implement",
        owner="feature_builder",
        request="Generate file",
        context={"request": "Generate file"},
        artifacts_dir=tmp_path / "artifacts",
    )

    payload_path = Path(result["artifacts"][0]["path"])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["noop_justified"] is True
    assert payload["llm_integration"]["fallback_used"] is True


def test_executor_supports_replace_in_file_action(tmp_path):
    class FakeAdapter:
        def chat(self, _system_prompt, _messages):
            return json.dumps(
                {
                    "changed_files": [],
                    "implementation_summary": "Replace text via model action",
                    "test_updates": [],
                    "unresolved_risks": [],
                    "noop_justified": False,
                    "actions": [
                        {
                            "type": "replace_in_file",
                            "path": "runtime/replace_target.txt",
                            "old": "OLD_VALUE",
                            "new": "NEW_VALUE",
                        }
                    ],
                }
            )

    repo_root = Path(__file__).resolve().parents[1]
    sandbox = RepoSandboxManager(repo_root=repo_root, sandbox_root=tmp_path / "sandbox")
    sandbox.prepare()
    sandbox.write_file("runtime/replace_target.txt", "key=OLD_VALUE\n")

    executor = SpecialistExecutor(
        specialists={"feature_builder": {"prompt_inline": "feature"}},
        model_adapter=FakeAdapter(),
        repo_root=repo_root,
        repo_ops=sandbox,
        policy=_policy_with_run_root(tmp_path),
    )

    executor.run_stage(
        run_id="run_test",
        stage_id="implement",
        owner="feature_builder",
        request="Replace value",
        context={"request": "Replace value"},
        artifacts_dir=tmp_path / "artifacts",
    )

    text = (sandbox.sandbox_repo / "runtime/replace_target.txt").read_text(encoding="utf-8")
    assert "NEW_VALUE" in text
    assert "OLD_VALUE" not in text


def test_verify_sets_require_refactor_when_unresolved_risks_exist(tmp_path):
    class PassingRepoOps:
        sandbox_repo = Path("/tmp/sandbox")

        def run_command(self, _command, _allowlist, _blocklist, cwd=None, timeout=120):
            return {"command": "pytest -q", "exit_code": 0, "stdout": "", "stderr": ""}

        def changed_files(self):
            return []

    policy = _policy_with_run_root(tmp_path)
    policy["gates"]["verify"] = {"required_checks": [], "commands": {"tests": "pytest -q"}}
    executor = SpecialistExecutor(policy=policy, repo_ops=PassingRepoOps())

    payload = executor._run_verify_commands(
        "verify",
        context={"implement": {"unresolved_risks": ["cleanup needed"]}},
    )
    assert payload["quality_signals"]["require_refactor"] is True


def test_repo_ops_allowlist_token_matching_blocks_prefix_spoof(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sandbox = RepoSandboxManager(repo_root=repo_root, sandbox_root=tmp_path / "sandbox")
    sandbox.prepare()

    try:
        sandbox.run_command(
            "pytestx -q",
            allowlist=["pytest", "python -m pytest"],
            blocklist=["rm -rf /"],
        )
    except PermissionError as exc:
        assert "Command not allowed by policy" in str(exc)
    else:
        raise AssertionError("Expected prefix-spoofed command to be blocked")

