"""Policy-driven orchestrator runtime entrypoint."""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .adapters.ollama import OllamaAdapter
from .contracts import ContractValidationError, ContractValidator
from .executor import SpecialistExecutor, build_gate_evidence
from .gates import evaluate_stage_gates
from .memory_writer import MemoryWriter
from .repo_ops import RepoSandboxManager
from .state import (
    append_event,
    append_stage_result,
    ensure_run_dirs,
    finalize_run_state,
    initialize_run_state,
    load_run_state,
    write_run_state,
)
from .waivers import apply_waivers, write_waiver_log

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_policy(path: Path) -> Dict[str, object]:
    """Load policy yaml if PyYAML is available.

    Milestone-1 allows injecting policy dict directly for deterministic tests.
    """
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required to load runtime/policies.yaml. "
            "Install with `pip install pyyaml` or pass policy dict directly."
        ) from exc

    text = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"Policy file {path} did not parse into a dictionary")
    return loaded


def _build_executor(
    policy: Dict[str, object],
    repo_root: Path,
    repo_ops: Optional[RepoSandboxManager],
    memory_writer: Optional[MemoryWriter],
) -> SpecialistExecutor:
    model_provider = policy.get("model_provider", {})
    specialists = policy.get("specialists", {})

    adapter = None
    if isinstance(model_provider, dict) and model_provider.get("adapter") == "ollama":
        model = str(model_provider.get("model", "qwen2.5-coder:14b"))
        base_url = str(model_provider.get("base_url", "http://localhost:11434"))
        adapter = OllamaAdapter(model=model, base_url=base_url)

    return SpecialistExecutor(
        specialists=specialists,
        model_adapter=adapter,
        repo_root=repo_root,
        repo_ops=repo_ops,
        memory_writer=memory_writer,
        policy=policy,
    )


def _get_stage_map(policy: Dict[str, object]) -> Dict[str, Dict[str, object]]:
    stages: List[Dict[str, object]] = policy.get("stages", [])  # type: ignore[assignment]
    return {str(stage["id"]): stage for stage in stages}


def _read_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_path_value(payload: Dict[str, object], dotted: str) -> object:
    current: object = payload
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _evaluate_condition(condition: str, context: Dict[str, object]) -> bool:
    expression = condition.strip()
    if "==" not in expression:
        return False
    left, right = [p.strip() for p in expression.split("==", 1)]
    left_value = _get_path_value(context, left)
    right_norm = right.lower()
    if right_norm in {"true", "false"}:
        return bool(left_value) is (right_norm == "true")
    if right.startswith('"') and right.endswith('"'):
        return str(left_value) == right[1:-1]
    return str(left_value) == right


def _next_stage(stage_spec: Dict[str, object], context: Dict[str, object]) -> Optional[str]:
    routing = stage_spec.get("routing", {})
    if isinstance(routing, dict):
        when = routing.get("when", [])
        if isinstance(when, list):
            for clause in when:
                if isinstance(clause, dict):
                    condition = str(clause.get("condition", ""))
                    nxt = clause.get("next")
                    if isinstance(nxt, str) and _evaluate_condition(condition, context):
                        return nxt

    next_list = stage_spec.get("next_on_success", [])
    if isinstance(next_list, list) and next_list:
        first = next_list[0]
        if isinstance(first, str):
            return first
    return None


def _build_handoff_packet(
    run_id: str,
    from_stage: str,
    to_stage: str,
    payload: Dict[str, object],
    acceptance_criteria: List[str],
) -> Dict[str, object]:
    return {
        "run_id": run_id,
        "from_stage": from_stage,
        "to_stage": to_stage,
        "summary": f"Handoff from {from_stage} to {to_stage}",
        "artifacts": [{"type": "stage_payload", "path": f"artifacts/stages/{from_stage}_payload.json"}],
        "acceptance_criteria": acceptance_criteria,
        "quality_signals": payload.get("quality_signals", {}),
        "created_at": _utc_now(),
    }


def run_milestone1(
    request: str,
    policy: Optional[Dict[str, object]] = None,
    run_root: Optional[Path] = None,
    executor: Optional[SpecialistExecutor] = None,
    repo_root: Optional[Path] = None,
    requested_waivers: Optional[Dict[str, Dict[str, str]]] = None,
    resume_run_id: Optional[str] = None,
    resume_choice: Optional[str] = None,
) -> Dict[str, object]:
    """Run policy-driven orchestration across all configured stages."""
    if policy is None:
        policy = _load_policy(Path("runtime/policies.yaml"))
    if repo_root is None:
        repo_root = Path.cwd()
    if run_root is None:
        run_root = Path(policy["runtime"]["run_root"])  # type: ignore[index]

    if resume_run_id and not resume_choice:
        raise ValueError(
            "Resume requested but no operator choice was provided. "
            "Use resume_choice='restart_from_beginning' or 'resume_from_last_completed'."
        )

    run_id = resume_run_id or f"run_{uuid.uuid4().hex[:12]}"
    run_dir = ensure_run_dirs(run_root, run_id)
    runtime_dir = Path(__file__).resolve().parent
    validator = ContractValidator(runtime_dir=runtime_dir)
    sandbox_manager = RepoSandboxManager(repo_root=repo_root, sandbox_root=run_dir / "sandbox")
    sandbox_repo = sandbox_manager.prepare()
    memory_writer = MemoryWriter(repo_root=repo_root)

    if executor is None:
        executor = _build_executor(policy, repo_root, sandbox_manager, memory_writer)

    if resume_run_id and resume_choice == "resume_from_last_completed" and (run_dir / "run.json").exists():
        run_state = load_run_state(run_dir)
        run_state["resume_source_run_id"] = resume_run_id
        run_state["status"] = "running"
    else:
        run_state = initialize_run_state(run_id=run_id, request=request)
    run_state["sandbox_dir"] = str(sandbox_repo.as_posix())
    validator.validate("run_state", run_state)
    write_run_state(run_dir, run_state)

    stage_map = _get_stage_map(policy)
    gates = policy.get("gates", {})
    context: Dict[str, object] = {"request": request, "stage_history": []}
    stage_order = list(stage_map.keys())
    if not stage_order:
        finalize_run_state(run_state, "failed")
        write_run_state(run_dir, run_state)
        return run_state

    if resume_run_id and resume_choice == "resume_from_last_completed" and run_state.get("stage_history"):
        previous_stage_ids = [entry.get("stage_id") for entry in run_state.get("stage_history", []) if isinstance(entry, dict)]
        last_stage = previous_stage_ids[-1] if previous_stage_ids else None
        if last_stage in stage_order:
            idx = stage_order.index(last_stage)
            current_stage_id = stage_order[idx + 1] if idx + 1 < len(stage_order) else None
        else:
            current_stage_id = stage_order[0]
    else:
        current_stage_id = stage_order[0]
    visited = 0

    try:
        while current_stage_id:
            visited += 1
            if visited > len(stage_order) * 4:
                raise RuntimeError("Stage graph traversal exceeded safety limit")

            stage_spec = stage_map.get(current_stage_id)
            if not stage_spec:
                raise RuntimeError(f"Stage '{current_stage_id}' not found in policy")

            owner = str(stage_spec.get("owner", "orchestrator"))
            stage_result = executor.run_stage(
                run_id,
                current_stage_id,
                owner,
                request,
                context,
                artifacts_dir=run_dir / "artifacts",
            )
            validator.validate("stage_result", stage_result)

            append_stage_result(run_state, stage_result)
            context["stage_history"] = run_state.get("stage_history", [])

            append_event(
                run_dir,
                {
                    "type": "stage_result",
                    "run_id": run_id,
                    "stage_id": current_stage_id,
                    "status": stage_result.get("status"),
                    "timestamp": _utc_now(),
                },
            )

            payload_artifacts = stage_result.get("artifacts", [])
            stage_payload: Dict[str, object] = {}
            if isinstance(payload_artifacts, list) and payload_artifacts:
                first = payload_artifacts[0]
                if isinstance(first, dict):
                    payload_path = first.get("path")
                    if isinstance(payload_path, str):
                        stage_payload = _read_json(Path(payload_path))

            context[current_stage_id] = stage_payload
            if isinstance(stage_payload.get("quality_signals"), dict):
                context["quality_signals"] = stage_payload["quality_signals"]

            required_checks = gates.get(current_stage_id, {}).get("required_checks", [])
            evidence = build_gate_evidence(current_stage_id, stage_payload)
            passed, gate_results = evaluate_stage_gates(run_id, current_stage_id, required_checks, evidence)
            waiver_config = policy.get("waivers", {}) if isinstance(policy, dict) else {}
            allowed_approvers = waiver_config.get("allowed_approvers", []) if isinstance(waiver_config, dict) else []
            requested = requested_waivers or {}
            if isinstance(allowed_approvers, list) and requested:
                passed, gate_results = apply_waivers(gate_results, requested, allowed_approvers)
            for gate_result in gate_results:
                validator.validate("gate_result", gate_result)

            write_waiver_log(run_dir / "artifacts" / "waivers.jsonl", run_id, gate_results)

            append_event(
                run_dir,
                {
                    "type": "gate_result",
                    "run_id": run_id,
                    "stage_id": current_stage_id,
                    "passed": passed,
                    "timestamp": _utc_now(),
                },
            )

            if not passed:
                finalize_run_state(run_state, "failed")
                validator.validate("run_state", run_state)
                write_run_state(run_dir, run_state)
                return run_state

            nxt = _next_stage(stage_spec, context)
            if nxt:
                acceptance_criteria = context.get("triage_plan", {}).get("acceptance_criteria", [])
                if not isinstance(acceptance_criteria, list):
                    acceptance_criteria = []
                handoff_packet = _build_handoff_packet(
                    run_id=run_id,
                    from_stage=current_stage_id,
                    to_stage=nxt,
                    payload=stage_payload,
                    acceptance_criteria=acceptance_criteria,
                )
                validator.validate("handoff_packet", handoff_packet)
                handoff_dir = run_dir / "artifacts" / "handoffs"
                handoff_dir.mkdir(parents=True, exist_ok=True)
                handoff_path = handoff_dir / f"{current_stage_id}_to_{nxt}.json"
                handoff_path.write_text(json.dumps(handoff_packet, indent=2), encoding="utf-8")

            current_stage_id = nxt
            validator.validate("run_state", run_state)
            write_run_state(run_dir, run_state)

    except (ContractValidationError, RuntimeError, OSError, ValueError) as exc:
        append_event(
            run_dir,
            {
                "type": "runtime_error",
                "run_id": run_id,
                "stage_id": run_state.get("current_stage", "unknown"),
                "error": str(exc),
                "timestamp": _utc_now(),
            },
        )
        finalize_run_state(run_state, "failed")
        validator.validate("run_state", run_state)
        write_run_state(run_dir, run_state)
        return run_state

    finalize_run_state(run_state, "completed")
    validator.validate("run_state", run_state)
    write_run_state(run_dir, run_state)
    return run_state


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run policy-driven orchestrator flow")
    parser.add_argument("--request", required=True, help="User request text")
    parser.add_argument(
        "--policy",
        default="runtime/policies.yaml",
        help="Path to policy YAML",
    )
    parser.add_argument("--resume-run-id", help="Existing run id to resume")
    parser.add_argument(
        "--resume-choice",
        choices=["restart_from_beginning", "resume_from_last_completed"],
        help="Operator-selected resume behavior",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run_state = run_milestone1(
        request=args.request,
        policy=_load_policy(Path(args.policy)),
        resume_run_id=args.resume_run_id,
        resume_choice=args.resume_choice,
    )
    print(json.dumps(run_state, indent=2))


if __name__ == "__main__":
    main()
