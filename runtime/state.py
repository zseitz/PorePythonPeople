"""Run state persistence helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_run_state(run_id: str, request: str) -> Dict[str, object]:
    return {
        "run_id": run_id,
        "request": request,
        "status": "running",
        "current_stage": "triage_plan",
        "stage_history": [],
        "artifacts_dir": "",
        "sandbox_dir": "",
        "events_file": "",
        "resume_source_run_id": "",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }


def append_stage_result(run_state: Dict[str, object], stage_result: Dict[str, object]) -> None:
    history: List[Dict[str, object]] = run_state.setdefault("stage_history", [])  # type: ignore[assignment]
    history.append(
        {
            "stage_id": stage_result.get("stage_id", "unknown"),
            "status": stage_result.get("status", "unknown"),
            "timestamp": _utc_now(),
            "note": stage_result.get("summary", ""),
        }
    )
    run_state["current_stage"] = stage_result.get("stage_id")
    run_state["updated_at"] = _utc_now()


def finalize_run_state(run_state: Dict[str, object], status: str) -> None:
    run_state["status"] = status
    run_state["updated_at"] = _utc_now()


def ensure_run_dirs(run_root: Path, run_id: str) -> Path:
    run_dir = run_root / run_id
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    return run_dir


def write_run_state(run_dir: Path, run_state: Dict[str, object]) -> Path:
    run_file = run_dir / "run.json"
    run_state["artifacts_dir"] = str((run_dir / "artifacts").as_posix())
    run_state["events_file"] = str((run_dir / "events.jsonl").as_posix())
    run_file.write_text(json.dumps(run_state, indent=2), encoding="utf-8")
    return run_file


def load_run_state(run_dir: Path) -> Dict[str, object]:
    return json.loads((run_dir / "run.json").read_text(encoding="utf-8"))


def append_event(run_dir: Path, event: Dict[str, object]) -> Path:
    events_file = run_dir / "events.jsonl"
    with events_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    return events_file
