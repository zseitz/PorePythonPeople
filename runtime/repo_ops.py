"""Sandboxed repository operations for the Local Specialist runtime."""

from __future__ import annotations

import hashlib
import subprocess
import shlex
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Optional


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8192)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


class RepoSandboxManager:
    """Create and operate on a safe copy of the repository."""

    _IGNORED_DIR_NAMES = frozenset({".git", ".nanopore-runtime", "__pycache__", ".pytest_cache"})
    _IGNORED_FILE_NAMES = frozenset({".coverage"})

    def __init__(self, repo_root: Path, sandbox_root: Path) -> None:
        self.repo_root = repo_root
        self.sandbox_root = sandbox_root
        self.sandbox_repo = sandbox_root / "repo"
        self._baseline_hashes: Dict[str, str] = {}
        self._baseline_commit = ""
        self._baseline_branch = ""
        self._baseline_is_git_repo = False
        self._baseline_worktree_clean = False

    def _should_ignore_relative(self, relative: Path) -> bool:
        if relative.name in self._IGNORED_FILE_NAMES:
            return True
        return any(part in self._IGNORED_DIR_NAMES for part in relative.parts)

    def _file_hash_manifest(self, root: Path) -> Dict[str, str]:
        manifest: Dict[str, str] = {}
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(root)
            if self._should_ignore_relative(relative):
                continue
            manifest[relative.as_posix()] = _sha256(candidate)
        return manifest

    def _run_git(self, args: List[str]) -> Optional[subprocess.CompletedProcess[str]]:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return None

    def is_git_repo(self) -> bool:
        result = self._run_git(["rev-parse", "--is-inside-work-tree"])
        if result is None or result.returncode != 0:
            return False
        return result.stdout.strip().lower() == "true"

    def current_head_commit(self) -> str:
        result = self._run_git(["rev-parse", "HEAD"])
        if result is None or result.returncode != 0:
            return ""
        return result.stdout.strip()

    def current_branch_name(self) -> str:
        result = self._run_git(["branch", "--show-current"])
        if result is None or result.returncode != 0:
            return ""
        return result.stdout.strip()

    def working_tree_is_clean(self) -> bool:
        result = self._run_git(["status", "--porcelain"])
        if result is None or result.returncode != 0:
            return False
        return result.stdout.strip() == ""

    def inspect_start_state(self, require_clean: bool = True, recommend_feature_branch: bool = True) -> Dict[str, object]:
        is_git_repo = self.is_git_repo()
        head_commit = ""
        branch = ""
        worktree_clean = False
        warnings: List[str] = []

        if is_git_repo:
            head_commit = self.current_head_commit()
            branch = self.current_branch_name()
            worktree_clean = self.working_tree_is_clean()
            if require_clean and not worktree_clean:
                raise RuntimeError(
                    "Refusing to start runtime because the local repository working tree is not clean. "
                    "Commit, stash, or discard local changes before starting a run."
                )
            if recommend_feature_branch:
                if branch in {"main", "master"}:
                    warnings.append(
                        f"Current branch is '{branch}'. Strongly recommended: run the runtime from a dedicated feature branch in your local clone."
                    )
                elif not branch:
                    warnings.append(
                        "Current repository is in detached HEAD state. Strongly recommended: run the runtime from a dedicated feature branch in your local clone."
                    )

        file_hashes = self._file_hash_manifest(self.repo_root)
        payload = {
            "is_git_repo": is_git_repo,
            "base_commit": head_commit,
            "base_branch": branch,
            "working_tree_clean": worktree_clean,
            "warnings": warnings,
            "file_hashes": file_hashes,
        }
        self.restore_baseline(payload)
        return payload

    def restore_baseline(self, payload: Dict[str, object]) -> None:
        file_hashes = payload.get("file_hashes", {})
        self._baseline_hashes = {
            str(path): str(file_hash)
            for path, file_hash in file_hashes.items()
        } if isinstance(file_hashes, dict) else {}
        self._baseline_commit = str(payload.get("base_commit", ""))
        self._baseline_branch = str(payload.get("base_branch", ""))
        self._baseline_is_git_repo = bool(payload.get("is_git_repo", False))
        self._baseline_worktree_clean = bool(payload.get("working_tree_clean", False))

    def prepare(self) -> Path:
        if self.sandbox_repo.exists():
            shutil.rmtree(self.sandbox_repo)
        ignore = shutil.ignore_patterns(
            ".git",
            ".nanopore-runtime",
            "__pycache__",
            ".pytest_cache",
            ".coverage",
        )
        shutil.copytree(self.repo_root, self.sandbox_repo, ignore=ignore)
        return self.sandbox_repo

    def run_command(
        self,
        command: str,
        allowlist: Iterable[str],
        blocklist: Iterable[str],
        cwd: Optional[Path] = None,
        timeout: int = 120,
    ) -> Dict[str, object]:
        stripped = command.strip()
        if not stripped:
            raise ValueError("Command cannot be empty")

        if "\n" in stripped or "\r" in stripped:
            raise PermissionError("Command contains newline characters and was rejected")

        if any(token in stripped for token in [";", "&&", "||", "|", "`", "$("]):
            raise PermissionError("Command contains disallowed shell control characters")

        args = shlex.split(stripped)
        if not args:
            raise ValueError("Command parsing produced no arguments")

        for blocked in blocklist:
            if blocked and blocked in stripped:
                raise PermissionError(f"Blocked command fragment detected: {blocked}")

        allowed = True
        if allowlist:
            allowed = False
            for allowed_cmd in allowlist:
                if not isinstance(allowed_cmd, str) or not allowed_cmd.strip():
                    continue
                allowed_tokens = shlex.split(allowed_cmd.strip())
                if not allowed_tokens:
                    continue
                if args[: len(allowed_tokens)] == allowed_tokens:
                    allowed = True
                    break

        if not allowed:
            raise PermissionError(f"Command not allowed by policy: {command}")

        completed = subprocess.run(
            args,
            cwd=str(cwd or self.sandbox_repo),
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": stripped,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    def write_file(self, relative_path: str, content: str) -> Path:
        path = self.sandbox_repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def changed_files(self) -> List[str]:
        baseline_hashes = self._baseline_hashes or self._file_hash_manifest(self.repo_root)
        changed: List[str] = []
        for sandbox_path in self.sandbox_repo.rglob("*"):
            if not sandbox_path.is_file():
                continue
            relative = sandbox_path.relative_to(self.sandbox_repo)
            if self._should_ignore_relative(relative):
                continue
            source_hash = baseline_hashes.get(relative.as_posix())
            if source_hash != _sha256(sandbox_path):
                changed.append(relative.as_posix())
        return sorted(changed)

    def summarize_changes(self, max_files: int = 200) -> Dict[str, object]:
        changed = self.changed_files()
        limited = changed[:max_files]
        return {
            "changed_files": limited,
            "total_changed_files": len(changed),
            "truncated": len(changed) > max_files,
        }

    def detect_repo_drift_since_start(self, relative_paths: Iterable[str]) -> Dict[str, object]:
        current_hashes = self._file_hash_manifest(self.repo_root)
        target_files = [str(path) for path in relative_paths]
        conflicting_files: List[str] = []
        for relative in target_files:
            baseline_hash = self._baseline_hashes.get(relative)
            current_hash = current_hashes.get(relative)
            if baseline_hash != current_hash:
                conflicting_files.append(relative)

        current_commit = self.current_head_commit() if self._baseline_is_git_repo else ""
        current_branch = self.current_branch_name() if self._baseline_is_git_repo else ""
        current_worktree_clean = self.working_tree_is_clean() if self._baseline_is_git_repo else True

        head_changed = bool(self._baseline_commit and current_commit and self._baseline_commit != current_commit)
        branch_changed = bool(self._baseline_branch != current_branch)
        working_tree_changed = bool(self._baseline_is_git_repo and self._baseline_worktree_clean and not current_worktree_clean)
        repo_changed_since_start = head_changed or branch_changed or working_tree_changed or bool(conflicting_files)

        return {
            "repo_changed_since_start": repo_changed_since_start,
            "head_changed": head_changed,
            "branch_changed": branch_changed,
            "working_tree_changed": working_tree_changed,
            "conflicting_files": sorted(set(conflicting_files)),
            "base_commit": self._baseline_commit,
            "current_commit": current_commit,
            "base_branch": self._baseline_branch,
            "current_branch": current_branch,
            "current_working_tree_clean": current_worktree_clean,
        }

    def promote_changes(self, relative_paths: Optional[Iterable[str]] = None) -> List[str]:
        paths = list(relative_paths) if relative_paths is not None else self.changed_files()
        promoted: List[str] = []
        for relative in paths:
            rel = Path(relative)
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError(f"Unsafe relative path for promotion: {relative}")

            src = self.sandbox_repo / rel
            dst = self.repo_root / rel
            if not src.exists() or not src.is_file():
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            promoted.append(rel.as_posix())

        return sorted(set(promoted))
