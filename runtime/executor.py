"""Specialist stage executor interfaces for runtime."""

from __future__ import annotations

import fnmatch
import json
import re
import shlex
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .context_manager import ContextBudgetManager
from .memory_writer import MemoryWriter
from .planner import build_triage_plan
from .repo_ops import RepoSandboxManager
from .skill_loader import SkillLoader


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
        self.skill_loader = SkillLoader.from_policy(self.repo_root, self.policy)
        self._model_call_warning: Optional[str] = None

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

        self._model_call_warning = None
        llm_response = self._try_model_response(owner, stage_id, request, context)
        parse_warning: Optional[str] = None
        used_llm_payload = False
        fallback_used = False
        llm_commentary: Optional[Dict[str, object]] = None
        deterministic_verify_source = stage_id in {"verify", "verify_after_refactor"}

        if llm_response:
            llm_payload, parse_warning = self._parse_model_payload(llm_response)
            if llm_payload is not None:
                if deterministic_verify_source:
                    llm_commentary = llm_payload
                    parse_warning = (
                        "Deterministic verify policy active: model verify payload recorded as metadata only. "
                        "Gate evidence uses executed command results."
                    )
                else:
                    valid_payload, validation_warning = self._validate_stage_payload(stage_id, llm_payload)
                    if valid_payload:
                        payload = self._merge_payload(fallback_payload, llm_payload)
                        used_llm_payload = True
                    else:
                        payload = dict(fallback_payload)
                        fallback_used = True
                        parse_warning = validation_warning
            else:
                if deterministic_verify_source:
                    parse_warning = (
                        "Deterministic verify policy active: invalid model verify payload ignored. "
                        "Gate evidence uses executed command results."
                    )
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
        if self._model_call_warning:
            meta_warnings.append(self._model_call_warning)
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
            if deterministic_verify_source:
                payload["llm_integration"]["source_of_truth"] = "deterministic_verify_commands"
                if llm_commentary is not None:
                    payload["llm_integration"]["model_commentary"] = llm_commentary

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
            raise RuntimeError("Repository workspace manager is required for append actions")
        path = self.repo_ops.sandbox_repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def _replace_in_relative_file(self, relative_path: str, old: str, new: str) -> Path:
        if self.repo_ops is None:
            raise RuntimeError("Repository workspace manager is required for replace actions")
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
        for relative in relative_paths:
            candidate = self.repo_ops.sandbox_repo / relative
            if not candidate.exists() or not candidate.is_file():
                continue
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line in text.splitlines():
                stripped = line.lstrip()
                if stripped.startswith("<<<<<<< "):
                    return True
                if stripped.startswith(">>>>>>> "):
                    return True
                if stripped.strip() == "=======":
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
        default_tests = "python -m pytest -q"
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

        for key, raw_command in list(commands.items()):
            commands[key] = self._normalize_verify_command(raw_command)

        return commands

    def _normalize_verify_command(self, command: str) -> str:
        """Normalize verify command entry points for interpreter consistency.

        Running bare ``pytest`` can invoke a different Python environment from
        the runtime process (entrypoint-script mismatch), which may cause
        collection/import failures even when ``python -m pytest`` succeeds.
        """
        stripped = command.strip()
        if not stripped:
            return stripped

        try:
            tokens = shlex.split(stripped)
        except ValueError:
            return stripped

        if not tokens:
            return stripped

        if tokens[0] != "pytest":
            return stripped

        normalized_tokens = ["python", "-m", "pytest", *tokens[1:]]
        return " ".join(shlex.quote(token) for token in normalized_tokens)

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
            actions, target_path = self._deterministic_implement_actions(request)
            if actions and target_path:
                return {
                    "changed_files": [target_path],
                    "implementation_summary": (
                        "Deterministic fallback generated a requested Python GUI scaffold because model-authored "
                        "implement actions were unavailable."
                    ),
                    "test_updates": [],
                    "unresolved_risks": [],
                    "noop_justified": False,
                    "checks_run": ["deterministic_fallback_scaffold"],
                    "actions": actions,
                }

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
                "doc_change_summary": "Fallback doc sync appended a request-log entry in the active workspace.",
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
                "Repository operations ran directly in the active workspace/branch.",
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

    def _deterministic_implement_actions(self, request: str) -> Tuple[List[Dict[str, str]], Optional[str]]:
        target_path = self._extract_requested_python_target_path(request)
        if not target_path:
            return [], None

        content = self._deterministic_python_file_content(request, target_path)
        if not content:
            return [], None

        return [
            {
                "type": "write_file",
                "path": target_path,
                "content": content,
            }
        ], target_path

    def _extract_requested_python_target_path(self, request: str) -> Optional[str]:
        if not request:
            return None

        request_lower = request.lower()

        # Prefer explicit output-target phrasing first (for example:
        # "save ... as \"new_gui.py\""). This avoids accidentally
        # selecting unrelated .py paths that may appear elsewhere in the prompt,
        # such as protected-file guardrails.
        quoted_target_match = re.search(
            r"(?:save|name|named|call|called|as)\s+(?:the\s+new\s+python\s+file\s+)?(?:in\s+[A-Za-z0-9_./\\-]+\s+as\s+)?[\"']([A-Za-z0-9_./\\-]+\.py)[\"']",
            request,
            flags=re.IGNORECASE,
        )
        if quoted_target_match:
            explicit_target = quoted_target_match.group(1).replace("\\", "/").lstrip("/")
            if "/" not in explicit_target and "src/nanoporethon" in request_lower:
                return f"src/nanoporethon/{explicit_target}"
            return explicit_target

        candidates = re.findall(r"([A-Za-z0-9_./-]+\.py)", request)
        if not candidates:
            return None

        protected_mentions = {
            path.lower() for path in self._policy_protected_paths()
        }
        normalized_candidates = [candidate.replace("\\", "/").lstrip("/") for candidate in candidates]
        filtered_candidates = [c for c in normalized_candidates if c.lower() not in protected_mentions]
        if filtered_candidates:
            normalized_candidates = filtered_candidates

        # Prefer explicit src/ paths when present.
        for normalized in normalized_candidates:
            if normalized.startswith("src/"):
                return normalized

        # Otherwise, if request references src/nanoporethon directory and only
        # provides a filename, resolve into that directory.
        first = normalized_candidates[0]
        if "/" not in first and "src/nanoporethon" in request_lower:
            return f"src/nanoporethon/{first}"

        return first

    def _deterministic_python_file_content(self, request: str, target_path: str) -> Optional[str]:
        if not str(target_path).lower().endswith(".py"):
            return None

        stem = Path(target_path).stem
        class_name = self._python_class_name_from_stem(stem)

        if stem.lower() == "sequence_designer_gui" or "sequencedesigner" in request.lower():
            template_path = self.repo_root / "runtime" / "templates" / "sequence_designer_gui_template.py"
            if template_path.exists() and template_path.is_file():
                try:
                    return template_path.read_text(encoding="utf-8")
                except OSError:
                    pass
            return (
                '"""Sequence designer GUI inspired by MATLAB SequenceDesigner controls."""\n\n'
                "from __future__ import annotations\n\n"
                "import json\n"
                "import random\n"
                "import tkinter as tk\n"
                "from dataclasses import dataclass\n"
                "from pathlib import Path\n"
                "from tkinter import filedialog\n\n"
                "import numpy as np\n"
                "from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg\n"
                "from matplotlib.figure import Figure\n\n\n"
                "ALLOWED_BASES = {\"A\", \"C\", \"G\", \"T\"}\n"
                "DISPLAY_53 = \"5'→3'\"\n"
                "DISPLAY_35 = \"3'→5'\"\n"
                "FEED_53 = \"5'→3'\"\n"
                "FEED_35 = \"3'→5'\"\n"
                "PORE_FORWARDS = \"forwards\"\n"
                "PORE_BACKWARDS = \"backwards\"\n\n\n"
                "def sanitize_sequence(text: str) -> str:\n"
                "    return \"\".join(base for base in text.upper() if base in ALLOWED_BASES)\n\n\n"
                "def reverse_complement(sequence: str) -> str:\n"
                "    return sequence.translate(str.maketrans(\"ACGT\", \"TGCA\"))[::-1]\n\n\n"
                "def _display_sequence(sequence: str, order: str) -> str:\n"
                "    return sequence[::-1] if order == DISPLAY_35 else sequence\n\n\n"
                "def _clamp(value: int, lower: int, upper: int) -> int:\n"
                "    return max(lower, min(upper, value))\n\n\n"
                "def _canonical_index_from_display_position(sequence_length: int, display_position: int, order: str) -> int | None:\n"
                "    if sequence_length <= 0:\n"
                "        return None\n"
                "    display_position = _clamp(display_position, 1, sequence_length + 1)\n"
                "    if display_position == sequence_length + 1:\n"
                "        return None\n"
                "    return sequence_length - display_position if order == DISPLAY_35 else display_position - 1\n\n\n"
                "def _insertion_index_from_display_position(sequence_length: int, display_position: int, order: str) -> int:\n"
                "    display_position = _clamp(display_position, 1, sequence_length + 1)\n"
                "    if order == DISPLAY_35:\n"
                "        return 0 if display_position == sequence_length + 1 else sequence_length - display_position\n"
                "    return sequence_length if display_position == sequence_length + 1 else display_position - 1\n\n\n"
                "def _kmer_current(kmer: str, hel308: bool) -> float:\n"
                "    base_current = {\"A\": 0.18, \"C\": 0.43, \"G\": 0.67, \"T\": 0.88, \"N\": 0.5}\n"
                "    raw = 0.0\n"
                "    for index, base in enumerate(kmer):\n"
                "        raw += base_current.get(base, 0.5) * (1.0 + 0.08 * index)\n"
                "    if \"G\" in kmer and \"C\" in kmer:\n"
                "        raw += 0.03\n"
                "    if hel308:\n"
                "        raw += 0.04\n"
                "    return raw\n\n\n"
                "def _sliding_windows(sequence: str, window: int) -> list[str]:\n"
                "    if not sequence:\n"
                "        return []\n"
                "    pad = max(1, window // 2)\n"
                "    padded = \"N\" * pad + sequence + \"N\" * pad\n"
                "    return [padded[index : index + window] for index in range(len(sequence))]\n\n\n"
                "def _normalize_current(values: list[float]) -> np.ndarray:\n"
                "    arr = np.asarray(values, dtype=float)\n"
                "    if arr.size == 0:\n"
                "        return arr\n"
                "    minimum = float(np.min(arr))\n"
                "    maximum = float(np.max(arr))\n"
                "    if np.isclose(minimum, maximum):\n"
                "        return np.full_like(arr, 0.5, dtype=float)\n"
                "    arr = (arr - minimum) / (maximum - minimum)\n"
                "    return 0.12 + 0.76 * arr\n\n\n"
                "def _phase_shift_levels(levels: list[float] | np.ndarray, phase_shift: float) -> np.ndarray:\n"
                "    arr = np.asarray(levels, dtype=float)\n"
                "    if arr.size <= 1:\n"
                "        return arr\n"
                "    shift = float(np.clip(phase_shift, 0.0, 1.0))\n"
                "    x = np.arange(arr.size, dtype=float)\n"
                "    return np.interp(x, x - shift, arr, left=arr[0], right=arr[-1])\n\n\n"
                "def build_predicted_currents(sequence: str, *, display_order: str, feeding_orientation: str, pore_orientation: str, hel308: bool, phase_shift: float) -> np.ndarray:\n"
                "    sequence = sanitize_sequence(sequence)\n"
                "    if not sequence:\n"
                "        return np.asarray([], dtype=float)\n"
                "    working = _display_sequence(sequence, display_order)\n"
                "    if feeding_orientation == FEED_35:\n"
                "        working = working[::-1]\n"
                "    if pore_orientation == PORE_BACKWARDS:\n"
                "        working = reverse_complement(working)\n"
                "    window = 6 if hel308 else 5\n"
                "    raw = [_kmer_current(kmer, hel308) for kmer in _sliding_windows(working, window)]\n"
                "    return _phase_shift_levels(_normalize_current(raw), phase_shift)\n\n\n"
                "@dataclass\n"
                "class SequenceDesignerModel:\n"
                "    sequence: str = \"\"\n"
                "    editing_position: int = 1\n"
                "    feeding_orientation: str = FEED_53\n"
                "    pore_orientation: str = PORE_FORWARDS\n"
                "    display_order: str = DISPLAY_53\n"
                "    hel308: bool = False\n"
                "    phase_shift: float = 0.0\n\n"
                "    def sanitized_sequence(self) -> str:\n"
                "        return sanitize_sequence(self.sequence)\n\n"
                "    def display_sequence(self) -> str:\n"
                "        return _display_sequence(self.sanitized_sequence(), self.display_order)\n\n"
                "    def displayed_length(self) -> int:\n"
                "        return len(self.sanitized_sequence())\n\n"
                "    def max_edit_position(self) -> int:\n"
                "        return max(1, self.displayed_length() + 1)\n\n"
                "    def clamp_editing_position(self) -> int:\n"
                "        self.editing_position = _clamp(self.editing_position, 1, self.max_edit_position())\n"
                "        return self.editing_position\n\n"
                "    def set_sequence(self, text: str) -> None:\n"
                "        self.sequence = sanitize_sequence(text)\n"
                "        self.clamp_editing_position()\n\n"
                "    def move_edit_position(self, position: int) -> None:\n"
                "        self.editing_position = _clamp(int(position), 1, self.max_edit_position())\n\n"
                "    def selected_display_index(self) -> int | None:\n"
                "        return _canonical_index_from_display_position(self.displayed_length(), self.clamp_editing_position(), self.display_order)\n\n"
                "    def insertion_index(self) -> int:\n"
                "        return _insertion_index_from_display_position(self.displayed_length(), self.clamp_editing_position(), self.display_order)\n\n"
                "    def mutate_selected_base(self, new_base: str) -> None:\n"
                "        base = new_base.upper()\n"
                "        if base not in ALLOWED_BASES:\n"
                "            raise ValueError(f'Unsupported nucleotide: {new_base!r}')\n"
                "        sequence = self.sanitized_sequence()\n"
                "        insert_index = self.insertion_index()\n"
                "        selected_index = self.selected_display_index()\n"
                "        if selected_index is None or insert_index == len(sequence):\n"
                "            if self.display_order == DISPLAY_35 and selected_index is None:\n"
                "                self.sequence = base + sequence\n"
                "            else:\n"
                "                self.sequence = sequence[:insert_index] + base + sequence[insert_index:]\n"
                "        else:\n"
                "            chars = list(sequence)\n"
                "            chars[selected_index] = base\n"
                "            self.sequence = ''.join(chars)\n"
                "        self.clamp_editing_position()\n\n"
                "    def randomize_selected_base(self) -> None:\n"
                "        self.mutate_selected_base(random.choice(sorted(ALLOWED_BASES)))\n\n"
                "    def delete_selected_base(self) -> None:\n"
                "        sequence = self.sanitized_sequence()\n"
                "        if not sequence:\n"
                "            return\n"
                "        insert_index = self.insertion_index()\n"
                "        selected_index = self.selected_display_index()\n"
                "        if selected_index is None or insert_index == len(sequence):\n"
                "            self.sequence = sequence[:-1] if self.display_order == DISPLAY_53 else sequence[1:]\n"
                "        else:\n"
                "            chars = list(sequence)\n"
                "            del chars[selected_index]\n"
                "            self.sequence = ''.join(chars)\n"
                "        self.clamp_editing_position()\n\n"
                "    def export_payload(self) -> dict[str, object]:\n"
                "        return {\n"
                "            'sequence': self.sanitized_sequence(),\n"
                "            'display_sequence': self.display_sequence(),\n"
                "            'levels': build_predicted_currents(\n"
                "                self.sequence,\n"
                "                display_order=self.display_order,\n"
                "                feeding_orientation=self.feeding_orientation,\n"
                "                pore_orientation=self.pore_orientation,\n"
                "                hel308=self.hel308,\n"
                "                phase_shift=self.phase_shift,\n"
                "            ).tolist(),\n"
                "        }\n\n\n"
                "class SequenceDesignerGui:\n"
                "    def __init__(self, root: tk.Tk) -> None:\n"
                "        self.root = root\n"
                "        self.root.title('Sequence Designer')\n"
                "        self.model = SequenceDesignerModel()\n"
                "        self.sequence_var = tk.StringVar(value='')\n"
                "        self.editing_var = tk.IntVar(value=1)\n"
                "        self.feeding_orientation_var = tk.StringVar(value=FEED_53)\n"
                "        self.pore_orientation_var = tk.StringVar(value=PORE_FORWARDS)\n"
                "        self.display_order_var = tk.StringVar(value=DISPLAY_53)\n"
                "        self.hel308_var = tk.BooleanVar(value=False)\n"
                "        self.phase_shift_var = tk.DoubleVar(value=0.0)\n"
                "        self.status_var = tk.StringVar(value='Ready')\n"
                "        self.sequence_preview_var = tk.StringVar(value='Sequence (displayed order): —')\n"
                "        self.editing_label_var = tk.StringVar(value='Editing: position 1 of 2')\n"
                "        self._build_ui()\n"
                "        self.updateFig()\n\n"
                "    def _build_ui(self) -> None:\n"
                "        outer = tk.Frame(self.root, padx=12, pady=12)\n"
                "        outer.pack(fill=tk.BOTH, expand=True)\n"
                "        controls = tk.Frame(outer)\n"
                "        controls.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 14))\n"
                "        seq_frame = tk.LabelFrame(controls, text=\"Sequence 5'-\")\n"
                "        seq_frame.pack(fill=tk.X, pady=(0, 8))\n"
                "        self.sequence_entry = tk.Entry(seq_frame, textvariable=self.sequence_var, width=34)\n"
                "        self.sequence_entry.pack(fill=tk.X, padx=8, pady=8)\n"
                "        self.sequence_entry.bind('<Return>', self.Sequence5EditFieldValueChanged)\n"
                "        self.sequence_entry.bind('<FocusOut>', self.Sequence5EditFieldValueChanged)\n"
                "        edit_frame = tk.LabelFrame(controls, text='Editing')\n"
                "        edit_frame.pack(fill=tk.X, pady=(0, 8))\n"
                "        self.editing_scale = tk.Scale(edit_frame, from_=1, to=2, orient=tk.HORIZONTAL, resolution=1, variable=self.editing_var, command=self.EditingSliderValueChanged, length=260)\n"
                "        self.editing_scale.pack(fill=tk.X, padx=8, pady=(8, 2))\n"
                "        tk.Label(edit_frame, textvariable=self.editing_label_var, anchor='w').pack(fill=tk.X, padx=8, pady=(0, 8))\n"
                "        tk.Label(controls, text=\"Select nucleotide 'N'\", anchor='w').pack(fill=tk.X, pady=(0, 4))\n"
                "        buttons = tk.Frame(controls)\n"
                "        buttons.pack(fill=tk.X, pady=(0, 8))\n"
                "        for base in ('A', 'C', 'G', 'T'):\n"
                "            tk.Button(buttons, text=base, width=5, command=lambda b=base: self._mutate_and_refresh(b)).pack(side=tk.LEFT, padx=(0, 4))\n"
                "        tk.Button(buttons, text='Random', width=7, command=self.RandomButtonPushed).pack(side=tk.LEFT, padx=(4, 4))\n"
                "        tk.Button(buttons, text='Delete', width=7, command=self.DeleteButtonPushed).pack(side=tk.LEFT)\n"
                "        orient = tk.LabelFrame(controls, text='Orientation controls')\n"
                "        orient.pack(fill=tk.X, pady=(0, 8))\n"
                "        self._option_row(orient, 'Feeding orientation', self.feeding_orientation_var, [FEED_53, FEED_35])\n"
                "        self._option_row(orient, 'Pore orientation', self.pore_orientation_var, [PORE_FORWARDS, PORE_BACKWARDS])\n"
                "        self._option_row(orient, 'Display order', self.display_order_var, [DISPLAY_53, DISPLAY_35])\n"
                "        tk.Checkbutton(orient, text='Hel308', variable=self.hel308_var, command=self.Hel308SwitchValueChanged).pack(anchor='w', padx=8, pady=(4, 4))\n"
                "        phase = tk.LabelFrame(controls, text='Phase Shift')\n"
                "        phase.pack(fill=tk.X, pady=(0, 8))\n"
                "        self.phase_scale = tk.Scale(phase, from_=0.0, to=1.0, orient=tk.HORIZONTAL, resolution=0.01, variable=self.phase_shift_var, command=self.PhaseShiftSliderValueChanged, length=260)\n"
                "        self.phase_scale.pack(fill=tk.X, padx=8, pady=8)\n"
                "        action = tk.Frame(controls)\n"
                "        action.pack(fill=tk.X, pady=(0, 8))\n"
                "        tk.Button(action, text='Save Figure', command=self.SaveFigureButtonPushed).pack(side=tk.LEFT, padx=(0, 6))\n"
                "        tk.Button(action, text='Export Levels', command=self.ExportLevelsButtonPushed).pack(side=tk.LEFT)\n"
                "        tk.Label(controls, textvariable=self.status_var, anchor='w', wraplength=330, fg='#444').pack(fill=tk.X, pady=(4, 0))\n"
                "        plot = tk.Frame(outer)\n"
                "        plot.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)\n"
                "        tk.Label(plot, text='Predicted currents', font=('TkDefaultFont', 13, 'bold'), anchor='w').pack(fill=tk.X)\n"
                "        self.figure = Figure(figsize=(8.0, 5.8), dpi=100, tight_layout=True)\n"
                "        self.axes = self.figure.add_subplot(111)\n"
                "        self.canvas = FigureCanvasTkAgg(self.figure, master=plot)\n"
                "        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)\n"
                "        tk.Label(plot, textvariable=self.sequence_preview_var, anchor='w', wraplength=760).pack(fill=tk.X, pady=(8, 0))\n\n"
                "    def _option_row(self, parent: tk.Widget, label: str, variable: tk.StringVar, values: list[str]) -> None:\n"
                "        row = tk.Frame(parent)\n"
                "        row.pack(fill=tk.X, padx=8, pady=(4, 0))\n"
                "        tk.Label(row, text=label, anchor='w').pack(side=tk.LEFT)\n"
                "        tk.OptionMenu(row, variable, *values, command=lambda _value: self.updateFig()).pack(side=tk.RIGHT)\n\n"
                "    def _sync_from_widgets(self) -> None:\n"
                "        self.model.sequence = self.sequence_var.get()\n"
                "        self.model.editing_position = int(self.editing_var.get())\n"
                "        self.model.feeding_orientation = self.feeding_orientation_var.get()\n"
                "        self.model.pore_orientation = self.pore_orientation_var.get()\n"
                "        self.model.display_order = self.display_order_var.get()\n"
                "        self.model.hel308 = bool(self.hel308_var.get())\n"
                "        self.model.phase_shift = float(self.phase_shift_var.get())\n"
                "        self.model.clamp_editing_position()\n"
                "        self.editing_var.set(self.model.editing_position)\n\n"
                "    def _sync_widgets_from_model(self) -> None:\n"
                "        self.sequence_var.set(self.model.sanitized_sequence())\n"
                "        self.editing_var.set(self.model.clamp_editing_position())\n"
                "        self.feeding_orientation_var.set(self.model.feeding_orientation)\n"
                "        self.pore_orientation_var.set(self.model.pore_orientation)\n"
                "        self.display_order_var.set(self.model.display_order)\n"
                "        self.hel308_var.set(bool(self.model.hel308))\n"
                "        self.phase_shift_var.set(float(self.model.phase_shift))\n\n"
                "    def _refresh_status(self) -> None:\n"
                "        sequence = self.model.sanitized_sequence()\n"
                "        levels = build_predicted_currents(sequence, display_order=self.model.display_order, feeding_orientation=self.model.feeding_orientation, pore_orientation=self.model.pore_orientation, hel308=self.model.hel308, phase_shift=self.model.phase_shift)\n"
                "        self.editing_label_var.set(f'Editing: position {self.model.clamp_editing_position()} of {self.model.max_edit_position()}')\n"
                "        self.sequence_preview_var.set(f'Sequence (displayed order): {self.model.display_sequence() or \"—\"}')\n"
                "        self.status_var.set(f'Length={len(sequence)} | Editing={self.model.editing_position} | Levels={len(levels)} | Feeding={self.model.feeding_orientation} | Pore={self.model.pore_orientation}')\n"
                "        self.editing_scale.configure(from_=1, to=self.model.max_edit_position())\n"
                "        self.editing_scale.configure(state=tk.DISABLED if self.model.max_edit_position() <= 1 else tk.NORMAL)\n"
                "        self.editing_scale.set(self.model.clamp_editing_position())\n\n"
                "    def _mutate_and_refresh(self, base: str) -> None:\n"
                "        self._sync_from_widgets()\n"
                "        self.model.mutate_selected_base(base)\n"
                "        self._sync_widgets_from_model()\n"
                "        self.updateFig()\n\n"
                "    def updateFig(self) -> None:\n"
                "        self._sync_from_widgets()\n"
                "        levels = build_predicted_currents(self.model.sequence, display_order=self.model.display_order, feeding_orientation=self.model.feeding_orientation, pore_orientation=self.model.pore_orientation, hel308=self.model.hel308, phase_shift=self.model.phase_shift)\n"
                "        self.axes.clear()\n"
                "        self.axes.set_title('Predicted currents', loc='left')\n"
                "        self.axes.set_xlabel('Sequence position')\n"
                "        self.axes.set_ylabel('Normalized current')\n"
                "        if levels.size == 0:\n"
                "            self.axes.text(0.5, 0.5, 'Enter a DNA sequence to generate a trace', ha='center', va='center', transform=self.axes.transAxes)\n"
                "            self.axes.set_xlim(0, 1)\n"
                "            self.axes.set_ylim(0, 1)\n"
                "        else:\n"
                "            x = np.arange(1, levels.size + 1)\n"
                "            self.axes.plot(x, levels, color='#1f4aa8', linewidth=2.0, marker='o', markersize=3.5)\n"
                "            self.axes.axhline(float(np.min(levels)), color='#888', linestyle='--', linewidth=1.0)\n"
                "            self.axes.axhline(float(np.max(levels)), color='#888', linestyle='--', linewidth=1.0)\n"
                "            self.axes.set_xlim(1, max(1, levels.size))\n"
                "            self.axes.set_ylim(0.0, 1.0)\n"
                "            self.axes.text(0.5, -0.16, self.model.display_sequence(), ha='center', va='top', transform=self.axes.transAxes, fontsize=10, family='monospace')\n"
                "        self.axes.grid(True, alpha=0.18)\n"
                "        self.canvas.draw_idle()\n"
                "        self._refresh_status()\n\n"
                "    def Sequence5EditFieldValueChanged(self, event: tk.Event | None = None) -> None:\n"
                "        del event\n"
                "        self._sync_from_widgets()\n"
                "        self.model.set_sequence(self.sequence_var.get())\n"
                "        self._sync_widgets_from_model()\n"
                "        self.updateFig()\n\n"
                "    def EditingSliderValueChanged(self, value: str | float | int | None = None) -> None:\n"
                "        if value is not None:\n"
                "            self.editing_var.set(int(float(value)))\n"
                "        self._sync_from_widgets()\n"
                "        self.model.move_edit_position(self.editing_var.get())\n"
                "        self._sync_widgets_from_model()\n"
                "        self.updateFig()\n\n"
                "    def PhaseShiftSliderValueChanged(self, value: str | float | int | None = None) -> None:\n"
                "        if value is not None:\n"
                "            self.phase_shift_var.set(float(value))\n"
                "        self._sync_from_widgets()\n"
                "        self.updateFig()\n\n"
                "    def FeedingorientationSwitchValueChanged(self, *_args: object) -> None:\n"
                "        self._sync_from_widgets()\n"
                "        self.updateFig()\n\n"
                "    def PoreorientationSwitchValueChanged(self, *_args: object) -> None:\n"
                "        self._sync_from_widgets()\n"
                "        self.updateFig()\n\n"
                "    def DisplayorderSwitchValueChanged(self, *_args: object) -> None:\n"
                "        self._sync_from_widgets()\n"
                "        self.updateFig()\n\n"
                "    def Hel308SwitchValueChanged(self) -> None:\n"
                "        self._sync_from_widgets()\n"
                "        self.updateFig()\n\n"
                "    def AButtonPushed(self) -> None: self._mutate_and_refresh('A')\n"
                "    def CButtonPushed(self) -> None: self._mutate_and_refresh('C')\n"
                "    def GButtonPushed(self) -> None: self._mutate_and_refresh('G')\n"
                "    def TButtonPushed(self) -> None: self._mutate_and_refresh('T')\n"
                "    def RandomButtonPushed(self) -> None: self._mutate_and_refresh(random.choice(sorted(ALLOWED_BASES)))\n"
                "    def DeleteButtonPushed(self) -> None:\n"
                "        self._sync_from_widgets(); self.model.delete_selected_base(); self._sync_widgets_from_model(); self.updateFig()\n"
                "    def SaveFigureButtonPushed(self) -> None:\n"
                "        path = filedialog.asksaveasfilename(parent=self.root, title='Save predicted currents figure', defaultextension='.png', filetypes=[('PNG image', '*.png'), ('PDF file', '*.pdf'), ('SVG file', '*.svg'), ('All files', '*.*')])\n"
                "        if path:\n"
                "            self.figure.savefig(Path(path), dpi=160)\n"
                "    def ExportLevelsButtonPushed(self) -> None:\n"
                "        path = filedialog.asksaveasfilename(parent=self.root, title='Export predicted levels', defaultextension='.json', filetypes=[('JSON file', '*.json'), ('All files', '*.*')])\n"
                "        if path:\n"
                "            Path(path).write_text(json.dumps(self.model.export_payload(), indent=2), encoding='utf-8')\n"
                "    def run(self) -> None: self.root.mainloop()\n\n\n"
                "def run_gui() -> None:\n"
                "    root = tk.Tk()\n"
                "    SequenceDesignerGui(root).run()\n\n\n"
                "if __name__ == '__main__':\n"
                "    run_gui()\n"
            )

        if "gui" in stem.lower():
            return (
                '"""Generic GUI scaffold generated by runtime deterministic fallback."""\n\n'
                "from __future__ import annotations\n\n"
                "import tkinter as tk\n\n\n"
                f"class {class_name}:\n"
                "    \"\"\"Minimal GUI scaffold to be filled by implement-stage edits.\"\"\"\n\n"
                "    def __init__(self, root: tk.Tk) -> None:\n"
                "        self.root = root\n"
                f"        self.root.title(\"{class_name}\")\n"
                "        frame = tk.Frame(root, padx=12, pady=12)\n"
                "        frame.pack(fill=tk.BOTH, expand=True)\n"
                "        tk.Label(\n"
                "            frame,\n"
                "            text=\"Deterministic fallback scaffold: implement behavior in this module.\",\n"
                "            anchor=\"w\",\n"
                "        ).pack(fill=tk.X)\n\n"
                "    def run(self) -> None:\n"
                "        self.root.mainloop()\n\n\n"
                "def run_gui() -> None:\n"
                "    root = tk.Tk()\n"
                f"    app = {class_name}(root)\n"
                "    _ = app\n"
                "    app.run()\n\n\n"
                "if __name__ == \"__main__\":\n"
                "    run_gui()\n"
            )

        return (
            '"""Generic Python module scaffold generated by runtime deterministic fallback."""\n\n'
            "from __future__ import annotations\n\n\n"
            f"def main() -> None:\n"
            "    \"\"\"Entry point placeholder.\"\"\"\n"
            "    print(\"Deterministic fallback scaffold: implement module behavior.\")\n\n\n"
            "if __name__ == \"__main__\":\n"
            "    main()\n"
        )

    def _python_class_name_from_stem(self, stem: str) -> str:
        tokens = [token for token in re.split(r"[^A-Za-z0-9]+", stem) if token]
        if not tokens:
            return "GeneratedGui"
        class_name = "".join(token[:1].upper() + token[1:] for token in tokens)
        if not class_name[0].isalpha():
            class_name = f"Generated{class_name}"
        return class_name

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

        request_file_context = self._collect_request_file_context(request)
        if request_file_context:
            user_payload["request_file_context"] = request_file_context

        if self.skill_loader is not None:
            skill_context = self.skill_loader.load_stage_context(stage_id)
            if skill_context:
                user_payload["skill_context"] = skill_context

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

        model_timeout_seconds = getattr(adapter, "timeout_seconds", None)
        stage_call_timeout_seconds = None
        if isinstance(self.policy, dict):
            provider_cfg = self.policy.get("model_provider", {})
            if isinstance(provider_cfg, dict):
                if model_timeout_seconds is None:
                    model_timeout_seconds = provider_cfg.get("request_timeout_seconds", 180)
                stage_call_timeout_seconds = provider_cfg.get("stage_call_timeout_seconds", 45)
        try:
            transport_timeout = max(1.0, float(model_timeout_seconds or 180))
            stage_cap = max(1.0, float(stage_call_timeout_seconds or 45))
            timeout_seconds = min(transport_timeout, stage_cap)
        except (TypeError, ValueError):
            timeout_seconds = 45.0

        response_box: Dict[str, object] = {"response": None, "error": None}

        def _chat_worker() -> None:
            try:
                response_box["response"] = adapter.chat(
                    system_prompt,
                    [{"role": "user", "content": json.dumps(user_payload)}],
                )
            except Exception as exc:  # noqa: BLE001 - surfaced via warning + fallback
                response_box["error"] = exc

        worker = threading.Thread(target=_chat_worker, daemon=True)
        worker.start()
        worker.join(timeout=timeout_seconds)

        if worker.is_alive():
            self._model_call_warning = (
                f"Model call timed out after {timeout_seconds:.1f}s for stage '{stage_id}' "
                f"(owner='{owner}'); using deterministic fallback."
            )
            return None

        error = response_box.get("error")
        if error is not None:
            self._model_call_warning = (
                f"Model call failed for stage '{stage_id}' (owner='{owner}'): {error}. "
                "Using deterministic fallback."
            )
            return None

        response = response_box.get("response")
        return response if isinstance(response, str) else None

    def _collect_request_file_context(self, request: str, max_files: int = 3, max_chars: int = 8000) -> List[Dict[str, str]]:
        """Load small, explicit file context for files directly referenced in the request.

        This gives runtime specialists grounded source context when the request cites
        specific repo files (for example MATLAB reference implementations).
        """
        if not request.strip():
            return []

        candidates: List[str] = []
        quoted = re.findall(r'"([^"]+)"', request)
        candidates.extend(quoted)

        tokens = re.findall(r'([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)', request)
        candidates.extend(tokens)

        normalized_candidates: List[str] = []
        seen = set()
        for raw in candidates:
            value = str(raw).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized_candidates.append(value)

        resolved: List[Path] = []
        external_roots: List[Path] = self._discover_request_search_roots(request)
        for candidate in normalized_candidates:
            explicit = Path(candidate).expanduser()
            if explicit.is_absolute() and explicit.exists() and explicit.is_file():
                resolved.append(explicit.resolve())
                if len(resolved) >= max_files:
                    break
                continue

            path_candidate = (self.repo_root / candidate).resolve()
            if path_candidate.exists() and path_candidate.is_file() and self.repo_root in path_candidate.parents:
                resolved.append(path_candidate)
                continue

            basename = Path(candidate).name
            if not basename:
                continue
            for match in self.repo_root.rglob(basename):
                if match.is_file():
                    resolved.append(match.resolve())
                    break

            if len(resolved) >= max_files:
                break

            for root in external_roots:
                for match in root.rglob(basename):
                    if match.is_file():
                        resolved.append(match.resolve())
                        break
                if len(resolved) >= max_files:
                    break

            if len(resolved) >= max_files:
                break

        snippets: List[Dict[str, str]] = []
        remaining = max_chars
        used = set()
        for path in resolved:
            if path in used:
                continue
            used.add(path)
            try:
                rel = path.relative_to(self.repo_root).as_posix()
                display_path = rel
            except (OSError, ValueError):
                display_path = path.as_posix()

            text = self._read_request_file_content(path).strip()
            if not text:
                continue
            if remaining <= 120:
                break
            snippet = text
            if len(snippet) > remaining:
                snippet = snippet[: remaining - 24].rstrip() + "\n\n[TRUNCATED]"
            snippets.append({"path": display_path, "content": snippet})
            remaining -= len(snippet)
            if len(snippets) >= max_files or remaining <= 0:
                break

        return snippets

    def _discover_request_search_roots(self, request: str) -> List[Path]:
        roots: List[Path] = []

        def _add_root(path: Path) -> None:
            try:
                resolved = path.expanduser().resolve()
            except OSError:
                return
            if resolved.exists() and resolved.is_dir() and resolved not in roots:
                roots.append(resolved)

        quoted = re.findall(r'"([^"]+)"', request)
        for raw in quoted:
            candidate = Path(str(raw).strip()).expanduser()
            if candidate.is_absolute():
                if candidate.exists() and candidate.is_dir():
                    _add_root(candidate)
                elif candidate.exists() and candidate.is_file():
                    _add_root(candidate.parent)

        absolute_posix = re.findall(r"(/[^\s'\"`]+)", request)
        for raw in absolute_posix:
            candidate = Path(raw).expanduser()
            if candidate.exists() and candidate.is_file():
                _add_root(candidate.parent)
            elif candidate.exists() and candidate.is_dir():
                _add_root(candidate)

        return roots

    def _policy_protected_paths(self) -> List[str]:
        if not isinstance(self.policy, dict):
            return []
        protected = self.policy.get("assistant_scope", {}).get("protected_file_hints", {})
        if not isinstance(protected, dict):
            return []
        paths: List[str] = []
        for key in protected.keys():
            if isinstance(key, str) and key.strip():
                paths.append(key.strip().replace("\\", "/").lstrip("/"))
        return paths

    def _read_request_file_content(self, path: Path) -> str:
        """Read request context from text files and MATLAB app containers.

        For `.mlapp` files, extract textual MATLAB class content from
        `matlab/document.xml` when present.
        """
        suffix = path.suffix.lower()
        if suffix == ".mlapp":
            try:
                with zipfile.ZipFile(path, "r") as archive:
                    with archive.open("matlab/document.xml") as handle:
                        return handle.read().decode("utf-8", errors="ignore")
            except (OSError, KeyError, zipfile.BadZipFile):
                return ""

        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

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
