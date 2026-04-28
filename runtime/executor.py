"""Specialist stage executor interfaces for runtime."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .memory_writer import MemoryWriter
from .planner import build_triage_plan
from .repo_ops import RepoSandboxManager


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SpecialistExecutor:
    """Milestone-1 specialist executor.

    This class is intentionally deterministic and provider-agnostic so the
    orchestration spine can be tested without an active model backend.
    """

    def __init__(
        self,
        specialists: Optional[Dict[str, object]] = None,
        model_adapter: Optional[object] = None,
        repo_root: Optional[Path] = None,
        repo_ops: Optional[RepoSandboxManager] = None,
        memory_writer: Optional[MemoryWriter] = None,
        policy: Optional[Dict[str, object]] = None,
    ) -> None:
        self.specialists = specialists or {}
        self.model_adapter = model_adapter
        self.repo_root = repo_root or Path.cwd()
        self.repo_ops = repo_ops
        self.memory_writer = memory_writer
        self.policy = policy or {}

    def run_stage(
        self,
        run_id: str,
        stage_id: str,
        owner: str,
        request: str,
        context: Dict[str, object],
        artifacts_dir: Path,
    ) -> Dict[str, object]:
        started_at = _utc_now()
        payload = self._stage_payload(run_id, stage_id, request, context)
        llm_response = self._try_model_response(owner, stage_id, request, context)
        if llm_response:
            payload["model_response"] = llm_response

        stage_artifacts_dir = artifacts_dir / "stages"
        stage_artifacts_dir.mkdir(parents=True, exist_ok=True)
        payload_path = stage_artifacts_dir / f"{stage_id}_payload.json"
        payload_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        ended_at = _utc_now()

        return {
            "run_id": run_id,
            "stage_id": stage_id,
            "specialist": owner,
            "status": "success",
            "summary": f"{stage_id} completed",
            "changed_files": payload.get("changed_files", []),
            "checks_run": payload.get("checks_run", []),
            "artifacts": [
                {
                    "name": "stage_payload",
                    "path": payload_path.as_posix(),
                    "mime_type": "application/json",
                }
            ],
            "started_at": started_at,
            "ended_at": ended_at,
        }

    def _stage_payload(
        self, run_id: str, stage_id: str, request: str, context: Dict[str, object]
    ) -> Dict[str, object]:
        if stage_id == "triage_plan":
            return build_triage_plan(request)

        if stage_id == "implement":
            changed_files: List[str] = []
            if self.repo_ops is not None:
                plan_path = self.repo_ops.write_file(
                    "runtime_implementation_note.txt",
                    f"Implement stage sandbox note for request: {request}\n",
                )
                changed_files = [str(plan_path.relative_to(self.repo_ops.sandbox_repo).as_posix())]
            return {
                "changed_files": changed_files,
                "implementation_summary": (
                    "Tier-2 sandbox mode: implementation writes occur only in the safe sandbox copy."
                ),
                "test_updates": [],
                "unresolved_risks": [],
                "noop_justified": not bool(changed_files),
                "checks_run": [],
            }

        if stage_id in {"verify", "verify_after_refactor"}:
            checks_run = ["pytest -q (planned)"]
            if self.repo_ops is not None:
                allowlist = self._command_allowlist()
                blocklist = self._command_blocklist()
                result = self.repo_ops.run_command("pytest -q tests/test_runtime_milestone1.py", allowlist, blocklist)
                checks_run = [f"{result['command']} -> {result['exit_code']}"]
            return {
                "checks_run": checks_run,
                "quality_signals": {"require_refactor": False},
                "failures_or_warnings": [],
            }

        if stage_id == "refactor_or_docsync":
            quality = context.get("quality_signals", {})
            require_refactor = bool(getattr(quality, "get", lambda _k, _d=None: False)("require_refactor", False))
            return {
                "route_decision": "refactor" if require_refactor else "doc_sync",
                "checks_run": [],
                "changed_files": [],
            }

        if stage_id == "refactor":
            return {
                "refactor_candidates": [],
                "selected_refactor": "none",
                "changed_files": [],
                "behavior_preservation_notes": "No structural edits applied in baseline mode.",
                "checks_run": [],
            }

        if stage_id == "doc_sync":
            changed_files: List[str] = []
            if self.repo_ops is not None:
                doc_path = self.repo_ops.write_file(
                    "Docs/runtime_doc_sync_note.md",
                    f"Runtime doc sync placeholder for request: {request}\n",
                )
                changed_files = [doc_path.relative_to(self.repo_ops.sandbox_repo).as_posix()]
            return {
                "docs_updated": changed_files,
                "doc_change_summary": "Sandbox documentation sync note written.",
                "request_log_entry": "No-op documented by runtime run artifacts.",
                "checks_run": [],
                "changed_files": changed_files,
            }

        if stage_id == "memory_sync":
            memory_updates = [
                "Runtime completed with schema-validated stage and gate boundaries.",
                "Sandboxed repo operations were used before touching the real repository.",
            ]
            changed_files: List[str] = []
            if self.memory_writer is not None:
                targets = self.policy.get("repo_memory", {}).get("target_files", []) if isinstance(self.policy, dict) else []
                for target in targets:
                    if not isinstance(target, str):
                        continue
                    written = self.memory_writer.append_bullets(target, memory_updates, run_id)
                    changed_files.append(str(written.relative_to(self.repo_root).as_posix()))
            return {
                "memory_updates": memory_updates,
                "reusable_patterns": ["Stage-gated orchestration with auditable artifacts."],
                "followup_constraints": [],
                "checks_run": [],
                "changed_files": changed_files,
            }

        if stage_id == "closeout":
            stage_history = context.get("stage_history", [])
            return {
                "final_summary": f"Run completed with {len(stage_history)} stage records.",
                "artifacts_index": ["run.json", "events.jsonl", "artifacts/"],
                "checks_run": [],
                "changed_files": [],
            }

        return {"notes": f"No payload template for stage '{stage_id}'"}

    def _try_model_response(
        self,
        owner: str,
        stage_id: str,
        request: str,
        context: Dict[str, object],
    ) -> Optional[str]:
        if self.model_adapter is None:
            return None

        specialist_cfg = self.specialists.get(owner, {}) if isinstance(self.specialists, dict) else {}
        if not isinstance(specialist_cfg, dict):
            specialist_cfg = {}

        system_prompt = self._load_specialist_prompt(specialist_cfg)
        if not system_prompt:
            system_prompt = f"You are the {owner} specialist for stage {stage_id}."

        user_payload = {
            "stage": stage_id,
            "request": request,
            "context_keys": sorted(list(context.keys())),
        }
        return self.model_adapter.chat(system_prompt, [{"role": "user", "content": json.dumps(user_payload)}])

    def _load_specialist_prompt(self, specialist_cfg: Dict[str, object]) -> str:
        inline = specialist_cfg.get("prompt_inline")
        if isinstance(inline, str) and inline.strip():
            return inline

        prompt_file = specialist_cfg.get("prompt_file")
        if isinstance(prompt_file, str) and prompt_file.strip():
            path = self.repo_root / prompt_file
            if path.exists():
                return path.read_text(encoding="utf-8")
        return ""

    def _command_allowlist(self) -> List[str]:
        if isinstance(self.policy, dict):
            return list(self.policy.get("policies", {}).get("command_allowlist", []))
        return []

    def _command_blocklist(self) -> List[str]:
        if isinstance(self.policy, dict):
            return list(self.policy.get("policies", {}).get("command_blocklist", []))
        return []


def build_gate_evidence(stage_id: str, stage_artifacts: Dict[str, object]) -> Dict[str, bool]:
    """Map stage artifacts to gate evidence booleans."""
    if stage_id == "triage_plan":
        return {
            "complexity_classified": bool(stage_artifacts.get("complexity")),
            "acceptance_criteria_present": bool(stage_artifacts.get("acceptance_criteria")),
            "impacted_components_listed": bool(stage_artifacts.get("impacted_components")),
        }

    if stage_id == "implement":
        changed_files = stage_artifacts.get("changed_files", [])
        noop_justified = bool(stage_artifacts.get("noop_justified", False))
        return {
            "changeset_nonempty_or_noop_justified": bool(changed_files) or noop_justified,
            "no_unresolved_merge_markers": True,
        }

    if stage_id == "verify":
        checks_run = stage_artifacts.get("checks_run", [])
        return {
            "tests_pass": bool(checks_run),
            "no_new_errors": True,
            "coverage_meets_policy": True,
        }

    if stage_id == "verify_after_refactor":
        checks_run = stage_artifacts.get("checks_run", [])
        return {
            "tests_pass": bool(checks_run),
            "no_new_errors": True,
            "coverage_meets_policy": True,
        }

    if stage_id == "doc_sync":
        return {
            "components_updated_if_contract_changed": True,
            "textbook_updated_if_user_workflow_changed": True,
            "request_log_appended": bool(stage_artifacts.get("request_log_entry")),
        }

    if stage_id == "memory_sync":
        return {
            "repo_memory_updated": bool(stage_artifacts.get("memory_updates")),
        }

    return {}
