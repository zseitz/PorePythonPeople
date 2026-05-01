"""Specialist stage executor interfaces for runtime."""

from __future__ import annotations

import fnmatch
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .context_manager import ContextBudgetManager
from .memory_writer import MemoryWriter
from .planner import build_triage_plan
from .repo_ops import RepoSandboxManager


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_STAGE_REQUIRED_FIELDS: Dict[str, List[str]] = {
    "triage_plan": ["complexity", "staged_plan", "acceptance_criteria", "impacted_components"],
    "implement": ["changed_files", "implementation_summary", "test_updates", "unresolved_risks", "noop_justified", "actions"],
    "verify": ["checks_run", "quality_signals", "failures_or_warnings", "tests_exit_code"],
    "verify_after_refactor": ["checks_run", "quality_signals", "failures_or_warnings", "tests_exit_code"],
    "refactor_or_docsync": ["route_decision"],
    "refactor": ["refactor_candidates", "selected_refactor", "changed_files", "behavior_preservation_notes", "checks_run"],
    "doc_sync": [
        "docs_updated",
        "doc_change_summary",
        "request_log_entry",
        "request_log_updated",
        "contract_change_required",
        "user_workflow_change_required",
        "changed_files",
        "actions",
    ],
    "memory_sync": ["memory_updates", "reusable_patterns", "followup_constraints", "changed_files"],
    "closeout": ["final_summary", "artifacts_index"],
}

_ACTION_REQUIRED_FIELDS: Dict[str, List[str]] = {
    "write_file": ["type", "path", "content"],
    "append_file": ["type", "path", "content"],
    "replace_in_file": ["type", "path", "old", "new"],
}

_ACTION_ALLOWED_FIELDS: Dict[str, List[str]] = {
    "write_file": ["type", "path", "content"],
    "append_file": ["type", "path", "content"],
    "replace_in_file": ["type", "path", "old", "new"],
}


class SpecialistExecutor:
    """Milestone-1 specialist executor.

    This class is intentionally deterministic and provider-agnostic so the
    orchestration spine can be tested without an active model backend.
    """

    def __init__(
        self,
        specialists: Optional[Dict[str, object]] = None,
        model_adapter: Optional[object] = None,
        model_adapters: Optional[Dict[str, object]] = None,
        repo_root: Optional[Path] = None,
        repo_ops: Optional[RepoSandboxManager] = None,
        memory_writer: Optional[MemoryWriter] = None,
        policy: Optional[Dict[str, object]] = None,
        context_manager: Optional[ContextBudgetManager] = None,
    ) -> None:
        self.specialists = specialists or {}
        self.model_adapter = model_adapter
        self.model_adapters = model_adapters or {}
        self.repo_root = repo_root or Path.cwd()
        self.repo_ops = repo_ops
        self.memory_writer = memory_writer
        self.policy = policy or {}
        self.context_manager = context_manager

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

        before_changed: set[str] = set()
        if self.repo_ops is not None:
            before_changed = set(self.repo_ops.changed_files())

        fallback_payload = self._stage_payload(run_id, stage_id, request, context)
        payload = dict(fallback_payload)

        llm_response = self._try_model_response(owner, stage_id, request, context)
        parse_warning: Optional[str] = None
        used_llm_payload = False
        fallback_used = False

        if llm_response:
            llm_payload, parse_warning = self._parse_model_payload(llm_response)
            if llm_payload is not None:
                valid_payload, validation_warning = self._validate_stage_payload(stage_id, llm_payload)
                if valid_payload:
                    payload = self._merge_payload(fallback_payload, llm_payload)
                    used_llm_payload = True
                else:
                    payload = dict(fallback_payload)
                    fallback_used = True
                    parse_warning = validation_warning
            else:
                fallback_used = True

        action_warnings: List[str] = []
        applied_actions: List[str] = []
        if stage_id in {"implement", "doc_sync", "refactor"}:
            applied_actions, action_warnings = self._apply_actions(payload)

        if self.repo_ops is not None:
            after_changed = set(self.repo_ops.changed_files())
            stage_changed = sorted(after_changed - before_changed)
            payload_changed = payload.get("changed_files", [])
            if not isinstance(payload_changed, list):
                payload_changed = []
            payload["changed_files"] = sorted(set(str(p) for p in payload_changed + stage_changed))

        if stage_id == "implement" and self.repo_ops is not None:
            changed_files = payload.get("changed_files", [])
            if not isinstance(changed_files, list):
                changed_files = []
            merge_markers_found = self._has_unresolved_merge_markers([str(path) for path in changed_files])
            payload["merge_markers_found"] = merge_markers_found

        meta_warnings: List[str] = []
        if parse_warning:
            meta_warnings.append(parse_warning)
        meta_warnings.extend(action_warnings)
        if llm_response:
            payload["llm_integration"] = {
                "response_received": True,
                "used_llm_payload": used_llm_payload,
                "fallback_used": fallback_used,
                "applied_actions": applied_actions,
                "warnings": meta_warnings,
            }

        # --- context budget compaction + metrics recording ---
        context_metrics: Dict[str, object] = {}
        if self.context_manager is not None:
            payload, compactions = self.context_manager.maybe_compact(stage_id, payload)
            stage_metrics = self.context_manager.record_stage(stage_id, payload, compactions)
            context_metrics = {
                "estimated_tokens": stage_metrics.estimated_tokens,
                "budget_tokens": stage_metrics.budget_tokens,
                "utilization_pct": stage_metrics.utilization_pct,
                "compacted": stage_metrics.compacted,
            }

        stage_artifacts_dir = artifacts_dir / "stages"
        stage_artifacts_dir.mkdir(parents=True, exist_ok=True)
        payload_path = stage_artifacts_dir / f"{stage_id}_payload.json"
        payload_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        ended_at = _utc_now()

        result: Dict[str, object] = {
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
        if context_metrics:
            result["context_metrics"] = context_metrics
        return result

    def _merge_payload(self, fallback_payload: Dict[str, object], llm_payload: Dict[str, object]) -> Dict[str, object]:
        merged = dict(fallback_payload)
        merged.update(llm_payload)
        return merged

    def _parse_model_payload(self, llm_response: str) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
        text = llm_response.strip()
        if not text:
            return None, "Model returned empty payload; using deterministic fallback."

        candidates = [text]
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                candidates.append("\n".join(lines[1:-1]).strip())

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed, None

        return None, "Model payload was not valid JSON; using deterministic fallback."

    def _validate_stage_payload(self, stage_id: str, payload: Dict[str, object]) -> Tuple[bool, Optional[str]]:
        required = _STAGE_REQUIRED_FIELDS.get(stage_id, [])
        missing = [field for field in required if field not in payload]
        if missing:
            return False, (
                f"Model payload missing required fields for stage '{stage_id}': {', '.join(missing)}; "
                "using deterministic fallback."
            )

        # Minimal semantic checks for known structured fields.
        list_fields = {"changed_files", "checks_run", "actions", "acceptance_criteria", "memory_updates", "reusable_patterns"}
        for key in list_fields:
            if key in payload and not isinstance(payload.get(key), list):
                return False, f"Model payload field '{key}' must be a list; using deterministic fallback."

        if stage_id in {"verify", "verify_after_refactor"}:
            quality = payload.get("quality_signals", {})
            if not isinstance(quality, dict):
                return False, "Model payload field 'quality_signals' must be an object; using deterministic fallback."

        actions = payload.get("actions")
        if actions is not None:
            valid_actions, action_warning = self._validate_actions_schema(stage_id, actions)
            if not valid_actions:
                return False, action_warning

        return True, None

    def _action_limits(self) -> Dict[str, int]:
        defaults = {
            "max_actions_per_stage": 20,
            "max_content_chars": 200_000,
            "max_replace_chars": 50_000,
        }
        if not isinstance(self.policy, dict):
            return defaults

        raw = self.policy.get("policies", {}).get("action_limits", {})
        if not isinstance(raw, dict):
            return defaults

        limits = dict(defaults)
        for key in defaults:
            value = raw.get(key)
            if isinstance(value, int) and value > 0:
                limits[key] = value
        return limits

    def _validate_actions_schema(
        self, stage_id: str, actions: object
    ) -> Tuple[bool, Optional[str]]:
        if stage_id not in {"implement", "doc_sync", "refactor"}:
            return False, f"Stage '{stage_id}' is not allowed to emit actions; using deterministic fallback."

        if not isinstance(actions, list):
            return False, "Model payload field 'actions' must be a list; using deterministic fallback."

        limits = self._action_limits()
        max_actions = limits["max_actions_per_stage"]
        max_content_chars = limits["max_content_chars"]
        max_replace_chars = limits["max_replace_chars"]

        if len(actions) > max_actions:
            return False, (
                f"Model payload contains {len(actions)} actions, exceeding max_actions_per_stage={max_actions}; "
                "using deterministic fallback."
            )

        for idx, action in enumerate(actions, start=1):
            if not isinstance(action, dict):
                return False, f"Action #{idx} must be an object; using deterministic fallback."

            action_type = action.get("type")
            if not isinstance(action_type, str) or action_type not in _ACTION_REQUIRED_FIELDS:
                return False, f"Action #{idx} has unsupported type '{action_type}'; using deterministic fallback."

            required = set(_ACTION_REQUIRED_FIELDS[action_type])
            allowed = set(_ACTION_ALLOWED_FIELDS[action_type])
            action_keys = set(action.keys())
            missing = sorted(required - action_keys)
            unexpected = sorted(action_keys - allowed)
            if missing:
                return False, (
                    f"Action #{idx} of type '{action_type}' is missing required fields: {', '.join(missing)}; "
                    "using deterministic fallback."
                )
            if unexpected:
                return False, (
                    f"Action #{idx} of type '{action_type}' contains unexpected fields: {', '.join(unexpected)}; "
                    "using deterministic fallback."
                )

            path = action.get("path")
            if not isinstance(path, str) or not path.strip():
                return False, f"Action #{idx} requires a non-empty string path; using deterministic fallback."
            try:
                normalized = self._normalize_relative_path(path)
            except ValueError as exc:
                return False, f"Action #{idx} path invalid: {exc}; using deterministic fallback."

            if not self._is_path_allowed(normalized):
                return False, (
                    f"Action #{idx} path not allowed by policy edit scope: {normalized}; using deterministic fallback."
                )

            if action_type in {"write_file", "append_file"}:
                content = action.get("content")
                if not isinstance(content, str):
                    return False, (
                        f"Action #{idx} of type '{action_type}' requires string content; using deterministic fallback."
                    )
                if len(content) > max_content_chars:
                    return False, (
                        f"Action #{idx} content exceeds max_content_chars={max_content_chars}; using deterministic fallback."
                    )

            if action_type == "replace_in_file":
                old = action.get("old")
                new = action.get("new")
                if not isinstance(old, str) or not isinstance(new, str):
                    return False, (
                        f"Action #{idx} of type 'replace_in_file' requires string old/new fields; using deterministic fallback."
                    )
                if not old:
                    return False, "replace_in_file requires a non-empty 'old' value; using deterministic fallback."
                if len(old) > max_replace_chars or len(new) > max_replace_chars:
                    return False, (
                        f"Action #{idx} replace values exceed max_replace_chars={max_replace_chars}; using deterministic fallback."
                    )

        return True, None

    def _allowed_edit_globs(self) -> List[str]:
        if not isinstance(self.policy, dict):
            return []
        globs = self.policy.get("policies", {}).get("edit_scope", {}).get("default_paths", [])
        if isinstance(globs, list):
            return [str(g) for g in globs if isinstance(g, str)]
        return []

    def _normalize_relative_path(self, raw_path: str) -> str:
        rel = Path(raw_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"Unsafe action path: {raw_path}")
        return rel.as_posix().lstrip("/")

    def _is_path_allowed(self, relative_path: str) -> bool:
        globs = self._allowed_edit_globs()
        if not globs:
            return True
        normalized = relative_path.lstrip("/")
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in globs)

    def _append_relative_file(self, relative_path: str, content: str) -> Path:
        if self.repo_ops is None:
            raise RuntimeError("Sandbox repository manager is required for append actions")
        path = self.repo_ops.sandbox_repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def _replace_in_relative_file(self, relative_path: str, old: str, new: str) -> Path:
        if self.repo_ops is None:
            raise RuntimeError("Sandbox repository manager is required for replace actions")
        path = self.repo_ops.sandbox_repo / relative_path
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"replace_in_file target missing: {relative_path}")
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise ValueError(f"replace_in_file old string not found in: {relative_path}")
        path.write_text(text.replace(old, new), encoding="utf-8")
        return path

    def _has_unresolved_merge_markers(self, relative_paths: List[str]) -> bool:
        if self.repo_ops is None:
            return False
        markers = ("<<<<<<< ", "=======", ">>>>>>> ")
        for relative in relative_paths:
            candidate = self.repo_ops.sandbox_repo / relative
            if not candidate.exists() or not candidate.is_file():
                continue
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if any(marker in text for marker in markers):
                return True
        return False

    def _allow_no_tests_collected(self, stage_id: str) -> bool:
        if not isinstance(self.policy, dict):
            return False
        gates = self.policy.get("gates", {})
        if not isinstance(gates, dict):
            return False
        key = "verify_after_refactor" if stage_id == "verify_after_refactor" else "verify"
        cfg = gates.get(key, {})
        if not isinstance(cfg, dict):
            return False
        return bool(cfg.get("allow_no_tests_collected", False))

    def _apply_actions(self, payload: Dict[str, object]) -> Tuple[List[str], List[str]]:
        if self.repo_ops is None:
            return [], []

        raw_actions = payload.get("actions", [])
        if not isinstance(raw_actions, list):
            return [], ["Actions field was not a list; ignored."]

        applied: List[str] = []
        warnings: List[str] = []

        for idx, action in enumerate(raw_actions):
            if not isinstance(action, dict):
                warnings.append(f"Action #{idx + 1} was not an object and was skipped.")
                continue

            action_type = str(action.get("type", "")).strip()
            raw_path = action.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                warnings.append(f"Action #{idx + 1} missing valid path and was skipped.")
                continue

            try:
                relative_path = self._normalize_relative_path(raw_path)
            except ValueError as exc:
                warnings.append(str(exc))
                continue

            if not self._is_path_allowed(relative_path):
                warnings.append(f"Action path not allowed by policy edit scope: {relative_path}")
                continue

            if action_type == "write_file":
                content = action.get("content")
                if not isinstance(content, str):
                    warnings.append(f"write_file missing string content for: {relative_path}")
                    continue
                self.repo_ops.write_file(relative_path, content)
                applied.append(f"write_file:{relative_path}")
                continue

            if action_type == "append_file":
                content = action.get("content")
                if not isinstance(content, str):
                    warnings.append(f"append_file missing string content for: {relative_path}")
                    continue
                self._append_relative_file(relative_path, content)
                applied.append(f"append_file:{relative_path}")
                continue

            if action_type == "replace_in_file":
                old = action.get("old")
                new = action.get("new")
                if not isinstance(old, str) or not isinstance(new, str):
                    warnings.append(f"replace_in_file requires string old/new fields for: {relative_path}")
                    continue
                try:
                    self._replace_in_relative_file(relative_path, old, new)
                except (FileNotFoundError, ValueError) as exc:
                    warnings.append(str(exc))
                    continue
                applied.append(f"replace_in_file:{relative_path}")
                continue

            warnings.append(f"Unsupported action type '{action_type}' for path {relative_path}; skipped.")

        return applied, warnings

    def _verify_commands(self, stage_id: str) -> Dict[str, str]:
        default_tests = "pytest -q"
        commands: Dict[str, str] = {"tests": default_tests}
        if not isinstance(self.policy, dict):
            return commands

        gates = self.policy.get("gates", {})
        if not isinstance(gates, dict):
            return commands

        verify_cfg = gates.get("verify", {})
        if isinstance(verify_cfg, dict):
            raw = verify_cfg.get("commands", {})
            if isinstance(raw, dict):
                tests_cmd = raw.get("tests")
                coverage_cmd = raw.get("coverage")
                if isinstance(tests_cmd, str) and tests_cmd.strip():
                    commands["tests"] = tests_cmd.strip()
                if isinstance(coverage_cmd, str) and coverage_cmd.strip():
                    commands["coverage"] = coverage_cmd.strip()

        # Allow an explicit verify_after_refactor override if configured.
        if stage_id == "verify_after_refactor":
            after_cfg = gates.get("verify_after_refactor", {})
            if isinstance(after_cfg, dict):
                raw = after_cfg.get("commands", {})
                if isinstance(raw, dict):
                    tests_cmd = raw.get("tests")
                    coverage_cmd = raw.get("coverage")
                    if isinstance(tests_cmd, str) and tests_cmd.strip():
                        commands["tests"] = tests_cmd.strip()
                    if isinstance(coverage_cmd, str) and coverage_cmd.strip():
                        commands["coverage"] = coverage_cmd.strip()

        return commands

    def _run_verify_commands(self, stage_id: str, context: Dict[str, object]) -> Dict[str, object]:
        commands = self._verify_commands(stage_id)
        checks_run: List[str] = []
        failures_or_warnings: List[str] = []
        tests_exit_code: Optional[int] = None
        coverage_exit_code: Optional[int] = None

        if self.repo_ops is None:
            checks_run.append(f"{commands['tests']} (planned)")
            return {
                "checks_run": checks_run,
                "quality_signals": {"require_refactor": False},
                "failures_or_warnings": failures_or_warnings,
                "tests_exit_code": 0,
                "coverage_exit_code": coverage_exit_code,
            }

        allowlist = self._command_allowlist()
        blocklist = self._command_blocklist()

        tests_result = self.repo_ops.run_command(
            commands["tests"], allowlist, blocklist
        )
        tests_exit_code = int(tests_result.get("exit_code", 1))
        if tests_exit_code == 5 and self._allow_no_tests_collected(stage_id):
            checks_run.append(f"{tests_result.get('command')} -> {tests_exit_code} (no tests collected; policy-allowed)")
            tests_exit_code = 0
        else:
            checks_run.append(f"{tests_result.get('command')} -> {tests_exit_code}")
            if tests_exit_code != 0:
                stderr = str(tests_result.get("stderr", "")).strip()
                failures_or_warnings.append(f"tests failed ({tests_exit_code}): {stderr[:400]}")

        if tests_exit_code == 5 and not self._allow_no_tests_collected(stage_id):
            failures_or_warnings.append(
                "pytest reported no tests collected (exit code 5) and policy does not allow promotion on empty test scope."
            )

        coverage_command = commands.get("coverage")
        if isinstance(coverage_command, str) and coverage_command.strip():
            coverage_result = self.repo_ops.run_command(
                coverage_command, allowlist, blocklist
            )
            coverage_exit_code = int(coverage_result.get("exit_code", 1))
            checks_run.append(f"{coverage_result.get('command')} -> {coverage_exit_code}")
            if coverage_exit_code != 0:
                stderr = str(coverage_result.get("stderr", "")).strip()
                failures_or_warnings.append(f"coverage failed ({coverage_exit_code}): {stderr[:400]}")

        require_refactor = False
        if stage_id == "verify" and tests_exit_code == 0:
            implement_ctx = context.get("implement", {})
            if isinstance(implement_ctx, dict):
                unresolved = implement_ctx.get("unresolved_risks", [])
                llm_meta = implement_ctx.get("llm_integration", {})
                llm_warnings = llm_meta.get("warnings", []) if isinstance(llm_meta, dict) else []
                require_refactor = bool(unresolved) or bool(llm_warnings)

        return {
            "checks_run": checks_run,
            "quality_signals": {"require_refactor": require_refactor},
            "failures_or_warnings": failures_or_warnings,
            "tests_exit_code": tests_exit_code,
            "coverage_exit_code": coverage_exit_code,
        }

    def _stage_payload(
        self, run_id: str, stage_id: str, request: str, context: Dict[str, object]
    ) -> Dict[str, object]:
        if stage_id == "triage_plan":
            return build_triage_plan(request)

        if stage_id == "implement":
            return {
                "changed_files": [],
                "implementation_summary": (
                    "Deterministic fallback mode: implementation actions were not model-authored."
                ),
                "test_updates": [],
                "unresolved_risks": [],
                "noop_justified": True,
                "checks_run": [],
                "actions": [],
            }

        if stage_id in {"verify", "verify_after_refactor"}:
            return self._run_verify_commands(stage_id, context)

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
            request_log_entry = f"| {_utc_now()[:10]} | runtime | Runtime doc sync fallback entry | Runtime | `Docs/agent_logs/REQUEST_LOG.md` | completed | Deterministic fallback path recorded. |\n"
            request_log_updated = False
            if self.repo_ops is not None:
                path = self._append_relative_file("Docs/agent_logs/REQUEST_LOG.md", request_log_entry)
                changed_files = [path.relative_to(self.repo_ops.sandbox_repo).as_posix()]
                request_log_updated = bool(changed_files)
            else:
                request_log_updated = True
            return {
                "docs_updated": changed_files,
                "doc_change_summary": "Fallback doc sync appended a request-log entry in sandbox.",
                "request_log_entry": request_log_entry.strip(),
                "request_log_updated": request_log_updated,
                "contract_change_required": False,
                "user_workflow_change_required": False,
                "checks_run": [],
                "changed_files": changed_files,
                "actions": [],
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
        adapter = self.model_adapters.get(owner, self.model_adapter)
        if adapter is None:
            return None

        specialist_cfg = self.specialists.get(owner, {}) if isinstance(self.specialists, dict) else {}
        if not isinstance(specialist_cfg, dict):
            specialist_cfg = {}

        system_prompt = self._load_specialist_prompt(specialist_cfg)
        if not system_prompt:
            system_prompt = f"You are the {owner} specialist for stage {stage_id}."

        user_payload: Dict[str, object] = {
            "stage": stage_id,
            "request": request,
            "context_keys": sorted(list(context.keys())),
        }

        # For the implement stage, enrich the payload so the LLM can produce
        # a valid "actions" list that _apply_actions() knows how to execute.
        if stage_id == "implement":
            triage_ctx = context.get("triage_plan", {})
            if isinstance(triage_ctx, dict):
                user_payload["acceptance_criteria"] = triage_ctx.get("acceptance_criteria", [])
                user_payload["impacted_components"] = triage_ctx.get("impacted_components", [])
            user_payload["response_format"] = (
                "Return ONLY a raw JSON object (no markdown fences) with an 'actions' list. "
                "Each action: {\"type\": \"write_file\"|\"append_file\", \"path\": \"relative/path\", \"content\": \"...\"}. "
                "Allowed root paths: src/, tests/, Docs/, runtime/. "
                "Use write_file to create/replace a file; append_file to add lines to an existing file."
            )

        # For doc_sync, tell the LLM about the implementation results so it can
        # write a meaningful REQUEST_LOG row via an append_file action.
        if stage_id == "doc_sync":
            impl_ctx = context.get("implement", {})
            if isinstance(impl_ctx, dict):
                user_payload["implementation_summary"] = impl_ctx.get("implementation_summary", "")
                user_payload["changed_files"] = impl_ctx.get("changed_files", [])
            user_payload["response_format"] = (
                "Return ONLY a raw JSON object with an 'actions' list containing one append_file action "
                "targeting 'Docs/agent_logs/REQUEST_LOG.md'. The content must be a single Markdown table row: "
                "| DATE | team | OBJECTIVE | orchestrator | FILES | completed | NOTES |\\n"
            )

        return adapter.chat(system_prompt, [{"role": "user", "content": json.dumps(user_payload)}])

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
        merge_markers_found = bool(stage_artifacts.get("merge_markers_found", False))
        return {
            "changeset_nonempty_or_noop_justified": bool(changed_files) or noop_justified,
            "no_unresolved_merge_markers": not merge_markers_found,
        }

    if stage_id == "verify":
        tests_exit = stage_artifacts.get("tests_exit_code")
        coverage_exit = stage_artifacts.get("coverage_exit_code")
        failures = stage_artifacts.get("failures_or_warnings", [])
        tests_pass = tests_exit == 0 if isinstance(tests_exit, int) else False
        coverage_meets = tests_pass if coverage_exit is None else coverage_exit == 0
        return {
            "tests_pass": tests_pass,
            "no_new_errors": tests_pass and not bool(failures),
            "coverage_meets_policy": coverage_meets,
        }

    if stage_id == "verify_after_refactor":
        tests_exit = stage_artifacts.get("tests_exit_code")
        coverage_exit = stage_artifacts.get("coverage_exit_code")
        failures = stage_artifacts.get("failures_or_warnings", [])
        tests_pass = tests_exit == 0 if isinstance(tests_exit, int) else False
        coverage_meets = tests_pass if coverage_exit is None else coverage_exit == 0
        return {
            "tests_pass": tests_pass,
            "no_new_errors": tests_pass and not bool(failures),
            "coverage_meets_policy": coverage_meets,
        }

    if stage_id == "doc_sync":
        changed_files = stage_artifacts.get("changed_files", [])
        if not isinstance(changed_files, list):
            changed_files = []
        normalized = [str(path) for path in changed_files]
        contract_required = bool(stage_artifacts.get("contract_change_required", False))
        workflow_required = bool(stage_artifacts.get("user_workflow_change_required", False))

        components_updated = any(path == "Docs/components.md" for path in normalized)
        textbook_updated = any(path == "Docs/nanoporethon_textbook.md" for path in normalized)
        request_log_updated = bool(stage_artifacts.get("request_log_updated", False)) or any(
            path == "Docs/agent_logs/REQUEST_LOG.md" for path in normalized
        )

        return {
            "components_updated_if_contract_changed": (not contract_required) or components_updated,
            "textbook_updated_if_user_workflow_changed": (not workflow_required) or textbook_updated,
            "request_log_appended": request_log_updated,
        }

    if stage_id == "memory_sync":
        return {
            "repo_memory_updated": bool(stage_artifacts.get("memory_updates")),
        }

    return {}
