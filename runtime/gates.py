"""Gate evaluation for runtime stage promotion."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Tuple


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate_stage_gates(
    run_id: str,
    stage_id: str,
    required_checks: List[Dict[str, str]],
    evidence: Dict[str, bool],
) -> Tuple[bool, List[Dict[str, object]]]:
    """Evaluate required checks for one stage.

    Returns:
        overall_passed, gate_results
    """
    gate_results: List[Dict[str, object]] = []
    overall_passed = True

    for check in required_checks:
        gate_id = check.get("id", "unknown_gate")
        passed = bool(evidence.get(gate_id, False))
        if not passed:
            overall_passed = False
        gate_results.append(
            {
                "run_id": run_id,
                "stage_id": stage_id,
                "gate_id": gate_id,
                "status": "pass" if passed else "fail",
                "evidence": [f"{gate_id}={passed}"],
                "checked_at": _utc_now(),
            }
        )

    return overall_passed, gate_results
