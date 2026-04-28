"""Repository memory writing helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryWriter:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def resolve_target(self, target: str) -> Path:
        path = Path(target)
        if path.is_absolute():
            return path
        return self.repo_root / path

    def append_bullets(self, target: str, bullets: Iterable[str], run_id: str) -> Path:
        resolved = self.resolve_target(target)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        existing = resolved.read_text(encoding="utf-8") if resolved.exists() else ""
        lines: List[str] = [line for line in existing.splitlines() if line.strip()]
        with resolved.open("a", encoding="utf-8") as handle:
            if not lines:
                handle.write(f"# Memory log\n\n")
            handle.write(f"## {run_id} ({_utc_now()})\n")
            for bullet in bullets:
                handle.write(f"- {bullet}\n")
            handle.write("\n")
        return resolved
