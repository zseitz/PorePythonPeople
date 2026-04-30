"""Policy-driven orchestrator runtime entrypoint."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .adapters.ollama import OllamaAdapter
from .context_manager import ContextBudgetManager
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


StageApprovalHandler = Callable[[Dict[str, object]], str]


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
    context_manager: Optional[ContextBudgetManager] = None,
) -> SpecialistExecutor:
    model_provider = policy.get("model_provider", {})
    specialists = policy.get("specialists", {})

    def _build_ollama_adapter(provider_cfg: Dict[str, object]) -> Optional[OllamaAdapter]:
        if provider_cfg.get("adapter") != "ollama":
            return None
        model = str(provider_cfg.get("model", "qwen3:4b"))
        base_url = str(provider_cfg.get("base_url", "http://localhost:11434"))
        return OllamaAdapter(model=model, base_url=base_url)

    adapter = None
    model_adapters: Dict[str, object] = {}
    if isinstance(model_provider, dict):
        adapter = _build_ollama_adapter(model_provider)

    if isinstance(specialists, dict):
        for owner, cfg in specialists.items():
            if not isinstance(owner, str) or not isinstance(cfg, dict):
                continue
            override = cfg.get("model_provider")
            if not isinstance(override, dict):
                continue
            merged: Dict[str, object] = {}
            if isinstance(model_provider, dict):
                merged.update(model_provider)
            merged.update(override)
            specialist_adapter = _build_ollama_adapter(merged)
            if specialist_adapter is not None:
                model_adapters[owner] = specialist_adapter

    return SpecialistExecutor(
        specialists=specialists,
        model_adapter=adapter,
        model_adapters=model_adapters,
        repo_root=repo_root,
        repo_ops=repo_ops,
        memory_writer=memory_writer,
        policy=policy,
        context_manager=context_manager,
    )


def _collect_ollama_targets(policy: Dict[str, object]) -> List[Dict[str, str]]:
    """Collect effective Ollama model targets used by runtime specialists."""
    targets: List[Dict[str, str]] = []
    global_provider = policy.get("model_provider", {})
    if not isinstance(global_provider, dict):
        global_provider = {}

    specialists = policy.get("specialists", {})
    if not isinstance(specialists, dict):
        specialists = {}

    def _effective_provider(override: Optional[Dict[str, object]]) -> Dict[str, object]:
        merged: Dict[str, object] = {}
        merged.update(global_provider)
        if isinstance(override, dict):
            merged.update(override)
        return merged

    # Global target (if configured) for visibility.
    if global_provider.get("adapter") == "ollama":
        targets.append(
            {
                "owner": "global",
                "model": str(global_provider.get("model", "")),
                "base_url": str(global_provider.get("base_url", "http://localhost:11434")),
            }
        )

    # Specialist effective targets (inherit global provider unless overridden).
    for owner, cfg in specialists.items():
        if not isinstance(owner, str) or not isinstance(cfg, dict):
            continue
        effective = _effective_provider(cfg.get("model_provider") if isinstance(cfg.get("model_provider"), dict) else None)
        if effective.get("adapter") != "ollama":
            continue
        targets.append(
            {
                "owner": owner,
                "model": str(effective.get("model", "")),
                "base_url": str(effective.get("base_url", "http://localhost:11434")),
            }
        )

    return [t for t in targets if t.get("model")]


def _ollama_show(base_url: str, model: str, timeout: int = 3) -> Dict[str, object]:
    payload = {"model": model}
    req = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/api/show",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = json.loads(response.read().decode("utf-8"))
        return raw if isinstance(raw, dict) else {}


def _extract_quantization(show_payload: Dict[str, object]) -> str:
    details = show_payload.get("details", {})
    if isinstance(details, dict):
        q = details.get("quantization_level")
        if isinstance(q, str) and q.strip():
            return q.strip()

    q_top = show_payload.get("quantization")
    if isinstance(q_top, str) and q_top.strip():
        return q_top.strip()

    return ""


def _emit_ollama_startup_warnings(policy: Dict[str, object]) -> None:
    """Best-effort startup checks for configured Ollama models.

    This is intentionally non-blocking and warning-only.
    """
    targets = _collect_ollama_targets(policy)
    if not targets:
        return

    # Deduplicate model/base_url checks while preserving owner visibility.
    grouped: Dict[str, Dict[str, object]] = {}
    for target in targets:
        key = f"{target['base_url']}::{target['model']}"
        entry = grouped.setdefault(
            key,
            {
                "base_url": target["base_url"],
                "model": target["model"],
                "owners": [],
            },
        )
        owners = entry.get("owners", [])
        if isinstance(owners, list):
            owners.append(target["owner"])

    for entry in grouped.values():
        base_url = str(entry.get("base_url", "http://localhost:11434"))
        model = str(entry.get("model", ""))
        owners = entry.get("owners", [])
        owners_label = ", ".join(str(o) for o in owners) if isinstance(owners, list) else "unknown"

        try:
            show_payload = _ollama_show(base_url=base_url, model=model)
        except urllib.error.HTTPError as exc:
            print(
                "[runtime startup warning] "
                f"Configured Ollama model '{model}' (owners: {owners_label}) was not available at {base_url} "
                f"(HTTP {exc.code})."
            )
            continue
        except urllib.error.URLError:
            print(
                "[runtime startup warning] "
                f"Could not reach Ollama at {base_url} to validate model '{model}' "
                f"(owners: {owners_label})."
            )
            continue
        except TimeoutError:
            print(
                "[runtime startup warning] "
                f"Timed out validating Ollama model '{model}' at {base_url} "
                f"(owners: {owners_label})."
            )
            continue

        quant = _extract_quantization(show_payload)
        if not quant:
            print(
                "[runtime startup warning] "
                f"Could not determine quantization for model '{model}' (owners: {owners_label})."
            )
            continue

        quant_upper = quant.upper()
        if not quant_upper.startswith("Q"):
            print(
                "[runtime startup warning] "
                f"Model '{model}' reports quantization '{quant}' (owners: {owners_label}); "
                "this may be unquantized and use more RAM."
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


def _traffic_light_from_utilization(utilization_pct: float, thresholds: List[float]) -> str:
    if not thresholds:
        low, high = 60.0, 85.0
    elif len(thresholds) == 1:
        low, high = float(thresholds[0]), 85.0
    elif len(thresholds) == 2:
        low, high = float(thresholds[0]), float(thresholds[1])
    else:
        low, high = float(thresholds[0]), float(thresholds[2])

    if utilization_pct >= high:
        return "🔴"
    if utilization_pct >= low:
        return "🟡"
    return "🟢"


def _build_live_progress_line(
    stage_id: str,
    stage_result: Dict[str, object],
    gate_passed: bool,
    thresholds: List[float],
) -> str:
    gate_label = "PASS" if gate_passed else "FAIL"
    context_metrics = stage_result.get("context_metrics", {})
    if not isinstance(context_metrics, dict) or not context_metrics:
        return f"⚪ {stage_id} context:n/a gate:{gate_label}"

    tokens = context_metrics.get("estimated_tokens", "?")
    budget = context_metrics.get("budget_tokens", "?")
    utilization_raw = context_metrics.get("utilization_pct", 0.0)
    try:
        utilization = float(utilization_raw)
    except (TypeError, ValueError):
        utilization = 0.0
    compacted = bool(context_metrics.get("compacted", False))
    compacted_marker = " compacted" if compacted else ""
    light = _traffic_light_from_utilization(utilization, thresholds)
    return f"{light} {stage_id} {tokens}/{budget} tok {utilization:.1f}% gate:{gate_label}{compacted_marker}"


def _normalize_approval_mode(approval_mode: Optional[str]) -> str:
    normalized = (approval_mode or "auto").strip().lower()
    if normalized not in {"auto", "per_stage"}:
        raise ValueError("approval_mode must be either 'auto' or 'per_stage'")
    return normalized


def _normalize_approval_decision(decision: object) -> str:
    normalized = str(decision).strip().lower()
    if normalized in {"y", "yes", "a", "approve", "approved"}:
        return "approved"
    if normalized in {"n", "no", "r", "reject", "rejected"}:
        return "rejected"
    if normalized in {"q", "quit", "cancel", "cancelled", "c"}:
        return "cancelled"
    raise ValueError(f"Unsupported approval decision: {decision}")


def _prompt_for_stage_approval(request: Dict[str, object]) -> str:
    from_stage = request.get("from_stage", "unknown")
    to_stage = request.get("to_stage", "unknown")
    review_paths = request.get("review_artifacts", [])
    if isinstance(review_paths, list) and review_paths:
        print(f"Review artifacts before proceeding: {', '.join(str(path) for path in review_paths)}")

    prompt = (
        f"Approve transition {from_stage} -> {to_stage}? "
        "[a]pprove/[r]eject/[q]uit: "
    )
    while True:
        try:
            return _normalize_approval_decision(input(prompt))
        except EOFError:
            return "cancelled"
        except ValueError:
            print("Please enter a, r, or q.")


def _request_stage_transition_approval(
    run_dir: Path,
    run_state: Dict[str, object],
    approval_request: Dict[str, object],
    approval_mode: str,
    approval_handler: Optional[StageApprovalHandler],
) -> Optional[Dict[str, object]]:
    pending = run_state.get("pending_approval", {})
    if not isinstance(pending, dict):
        pending = {}

    if approval_mode != "per_stage":
        if pending:
            run_state["pending_approval"] = {}
        return None

    append_event(
        run_dir,
        {
            "type": "approval_requested",
            "run_id": approval_request.get("run_id", run_state.get("run_id", "unknown")),
            "from_stage": approval_request.get("from_stage"),
            "to_stage": approval_request.get("to_stage"),
            "timestamp": _utc_now(),
        },
    )

    decision_raw = approval_handler(approval_request) if approval_handler else _prompt_for_stage_approval(approval_request)
    decision = _normalize_approval_decision(decision_raw)
    append_event(
        run_dir,
        {
            "type": "approval_decision",
            "run_id": approval_request.get("run_id", run_state.get("run_id", "unknown")),
            "from_stage": approval_request.get("from_stage"),
            "to_stage": approval_request.get("to_stage"),
            "decision": decision,
            "timestamp": _utc_now(),
        },
    )

    if decision == "approved":
        run_state["pending_approval"] = {}
        run_state["updated_at"] = _utc_now()
        return None

    blocked_state = dict(approval_request)
    blocked_state["decision"] = decision
    blocked_state["requested_at"] = blocked_state.get("requested_at", _utc_now())
    blocked_state["updated_at"] = _utc_now()
    run_state["pending_approval"] = blocked_state
    finalize_run_state(run_state, "cancelled" if decision == "cancelled" else "blocked")
    return run_state


def _maybe_resume_pending_approval(
    run_dir: Path,
    run_state: Dict[str, object],
    approval_mode: str,
    approval_handler: Optional[StageApprovalHandler],
    next_stage_id: Optional[str],
) -> Optional[Dict[str, object]]:
    pending = run_state.get("pending_approval", {})
    if not isinstance(pending, dict) or not pending:
        return None

    pending_to_stage = pending.get("to_stage")
    if next_stage_id and pending_to_stage not in {next_stage_id, None, ""}:
        return None

    return _request_stage_transition_approval(
        run_dir=run_dir,
        run_state=run_state,
        approval_request=pending,
        approval_mode=approval_mode,
        approval_handler=approval_handler,
    )


def run_milestone1(
    request: str,
    policy: Optional[Dict[str, object]] = None,
    run_root: Optional[Path] = None,
    executor: Optional[SpecialistExecutor] = None,
    repo_root: Optional[Path] = None,
    requested_waivers: Optional[Dict[str, Dict[str, str]]] = None,
    resume_run_id: Optional[str] = None,
    resume_choice: Optional[str] = None,
    live_progress: bool = False,
    approval_mode: Optional[str] = None,
    approval_handler: Optional[StageApprovalHandler] = None,
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

    effective_approval_mode = _normalize_approval_mode(approval_mode)

    run_id = resume_run_id or f"run_{uuid.uuid4().hex[:12]}"
    run_dir = ensure_run_dirs(run_root, run_id)
    runtime_dir = Path(__file__).resolve().parent
    validator = ContractValidator(runtime_dir=runtime_dir)
    sandbox_manager = RepoSandboxManager(repo_root=repo_root, sandbox_root=run_dir / "sandbox")
    sandbox_repo = sandbox_manager.prepare()
    memory_writer = MemoryWriter(repo_root=repo_root)

    context_mgr = ContextBudgetManager.from_policy(policy if isinstance(policy, dict) else {})

    if executor is None and isinstance(policy, dict):
        _emit_ollama_startup_warnings(policy)

    if executor is None:
        executor = _build_executor(policy, repo_root, sandbox_manager, memory_writer, context_mgr)
    elif executor.context_manager is None:
        executor.context_manager = context_mgr

    if resume_run_id and resume_choice == "resume_from_last_completed" and (run_dir / "run.json").exists():
        run_state = load_run_state(run_dir)
        run_state["resume_source_run_id"] = resume_run_id
        run_state["status"] = "running"
        if approval_mode is None and isinstance(run_state.get("approval_mode"), str):
            effective_approval_mode = _normalize_approval_mode(str(run_state.get("approval_mode")))
    else:
        run_state = initialize_run_state(run_id=run_id, request=request, approval_mode=effective_approval_mode)
    run_state["approval_mode"] = effective_approval_mode
    run_state["sandbox_dir"] = str(sandbox_repo.as_posix())
    validator.validate("run_state", run_state)
    write_run_state(run_dir, run_state)

    stage_map = _get_stage_map(policy)
    gates = policy.get("gates", {})
    budget_cfg = policy.get("context_budgets", {}) if isinstance(policy, dict) else {}
    threshold_values = [60.0, 75.0, 85.0]
    if isinstance(budget_cfg, dict):
        raw = budget_cfg.get("compaction_thresholds", [60, 75, 85])
        if isinstance(raw, list) and raw:
            parsed: List[float] = []
            for value in raw:
                try:
                    parsed.append(float(value))
                except (TypeError, ValueError):
                    continue
            if parsed:
                threshold_values = parsed
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

    pending_resume_result = _maybe_resume_pending_approval(
        run_dir=run_dir,
        run_state=run_state,
        approval_mode=effective_approval_mode,
        approval_handler=approval_handler,
        next_stage_id=current_stage_id,
    )
    if pending_resume_result is not None:
        validator.validate("run_state", run_state)
        write_run_state(run_dir, run_state)
        return pending_resume_result

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

            if live_progress:
                print(_build_live_progress_line(current_stage_id, stage_result, passed, threshold_values))

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

                approval_result = _request_stage_transition_approval(
                    run_dir=run_dir,
                    run_state=run_state,
                    approval_request={
                        "run_id": run_id,
                        "from_stage": current_stage_id,
                        "to_stage": nxt,
                        "requested_at": _utc_now(),
                        "review_artifacts": [
                            str((run_dir / "run.json").as_posix()),
                            str(handoff_path.as_posix()),
                        ],
                    },
                    approval_mode=effective_approval_mode,
                    approval_handler=approval_handler,
                )
                if approval_result is not None:
                    validator.validate("run_state", run_state)
                    write_run_state(run_dir, run_state)
                    return approval_result

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

    run_state["context_metrics"] = context_mgr.summary()
    run_state["pending_approval"] = {}
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
    parser.add_argument(
        "--output",
        choices=["json", "summary", "both"],
        default="json",
        help="CLI output format. 'summary' includes context budget utilization details.",
    )
    parser.add_argument(
        "--live-progress",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print a compact traffic-light line after each stage while the run is executing.",
    )
    parser.add_argument(
        "--approval-mode",
        choices=["auto", "per_stage"],
        default=None,
        help="Require explicit operator approval at each stage transition when set to 'per_stage'.",
    )
    return parser.parse_args()


def _build_cli_summary(run_state: Dict[str, object]) -> str:
    lines: List[str] = []
    run_id = str(run_state.get("run_id", "unknown"))
    status = str(run_state.get("status", "unknown"))
    current_stage = str(run_state.get("current_stage", "unknown"))
    stage_history = run_state.get("stage_history", [])
    stage_count = len(stage_history) if isinstance(stage_history, list) else 0

    lines.append(f"Run ID: {run_id}")
    lines.append(f"Status: {status}")
    lines.append(f"Current Stage: {current_stage}")
    lines.append(f"Stages Recorded: {stage_count}")

    context_metrics = run_state.get("context_metrics", {})
    if isinstance(context_metrics, dict) and context_metrics:
        lines.append("")
        lines.append("Context Budget Summary:")
        lines.append(f"- Stages tracked: {context_metrics.get('stages_tracked', 0)}")
        lines.append(f"- Total estimated tokens: {context_metrics.get('total_estimated_tokens', 0)}")
        lines.append(f"- Peak utilization: {context_metrics.get('peak_utilization_pct', 0.0)}%")
        lines.append(f"- Total compactions: {context_metrics.get('total_compactions', 0)}")

        per_stage = context_metrics.get("per_stage", [])
        if isinstance(per_stage, list) and per_stage:
            lines.append("- Per-stage utilization:")
            for entry in per_stage:
                if not isinstance(entry, dict):
                    continue
                stage_id = entry.get("stage_id", "unknown")
                tokens = entry.get("estimated_tokens", 0)
                budget = entry.get("budget_tokens", 0)
                pct = entry.get("utilization_pct", 0.0)
                compacted = entry.get("compacted", False)
                compacted_marker = " (compacted)" if compacted else ""
                lines.append(f"  - {stage_id}: {tokens}/{budget} tokens ({pct}%){compacted_marker}")

    return "\n".join(lines)


def main() -> None:
    args = _parse_args()
    run_state = run_milestone1(
        request=args.request,
        policy=_load_policy(Path(args.policy)),
        resume_run_id=args.resume_run_id,
        resume_choice=args.resume_choice,
        live_progress=args.live_progress,
        approval_mode=args.approval_mode,
    )
    if args.output in {"summary", "both"}:
        print(_build_cli_summary(run_state))
    if args.output in {"json", "both"}:
        if args.output == "both":
            print()
        print(json.dumps(run_state, indent=2))


if __name__ == "__main__":
    main()
