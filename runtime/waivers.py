"""Waiver handling for stage gates."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_waivers(
    gate_results: List[Dict[str, object]],
    requested_waivers: Dict[str, Dict[str, str]],
    allowed_approvers: Iterable[str],
) -> Tuple[bool, List[Dict[str, object]]]:
    """Convert failing gate results to waived when approved."""
    allowed = set(allowed_approvers)
    all_cleared = True

    for gate_result in gate_results:
        gate_id = str(gate_result.get("gate_id", ""))
        if gate_result.get("status") == "pass":
            continue

        waiver = requested_waivers.get(gate_id)
        if not waiver:
            all_cleared = False
            continue

        approver = waiver.get("approver", "")
        if approver not in allowed:
            all_cleared = False
            continue

        gate_result["status"] = "waived"
        gate_result["details"] = waiver.get("reason", "Waived by approved operator.")
        gate_result["waiver"] = {
            "waiver_id": waiver.get("waiver_id", f"waiver_{uuid.uuid4().hex[:8]}"),
            "reason": waiver.get("reason", "No reason provided."),
            "approver": approver,
            "scope": waiver.get("scope", "single gate"),
        }
        gate_result["checked_at"] = _utc_now()

    if any(result.get("status") == "fail" for result in gate_results):
        all_cleared = False

    return all_cleared, gate_results


def write_waiver_log(log_path: Path, run_id: str, gate_results: List[Dict[str, object]]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        for gate_result in gate_results:
            if gate_result.get("status") != "waived":
                continue
            handle.write(
                json.dumps(
                    {
                        "run_id": run_id,
                        "stage_id": gate_result.get("stage_id"),
                        "gate_id": gate_result.get("gate_id"),
                        "waiver": gate_result.get("waiver"),
                        "recorded_at": _utc_now(),
                    }
                )
                + "\n"
            )
