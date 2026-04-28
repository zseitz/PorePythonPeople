"""Sandboxed repository operations for Tier-2 runtime."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
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

    def __init__(self, repo_root: Path, sandbox_root: Path) -> None:
        self.repo_root = repo_root
        self.sandbox_root = sandbox_root
        self.sandbox_repo = sandbox_root / "repo"

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
        for blocked in blocklist:
            if blocked and blocked in command:
                raise PermissionError(f"Blocked command fragment detected: {blocked}")

        if allowlist and not any(command.startswith(allowed) for allowed in allowlist):
            raise PermissionError(f"Command not allowed by policy: {command}")

        completed = subprocess.run(
            command,
            cwd=str(cwd or self.sandbox_repo),
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
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
        changed: List[str] = []
        for sandbox_path in self.sandbox_repo.rglob("*"):
            if not sandbox_path.is_file():
                continue
            relative = sandbox_path.relative_to(self.sandbox_repo)
            source_path = self.repo_root / relative
            if not source_path.exists() or _sha256(source_path) != _sha256(sandbox_path):
                changed.append(relative.as_posix())
        return sorted(changed)
