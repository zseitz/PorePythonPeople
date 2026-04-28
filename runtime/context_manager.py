"""Context budget management and payload compaction for the orchestrator runtime.

Tracks estimated token usage per stage, triggers compaction when utilization
crosses configured thresholds, and provides a summary of context metrics for
each run artifact.

Token estimation: chars / 4 (standard rough approximation for LLM context windows).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Keys considered low-priority — dropped first during compaction.
_LOW_PRIORITY_KEYS = frozenset(
    {"notes", "artifacts", "artifacts_index", "followup_constraints", "behavior_preservation_notes"}
)

# Strings longer than this are truncated during compaction.
_STRING_TRUNCATE_CHARS = 500

# Lists longer than this are truncated during compaction.
_LIST_TRUNCATE_ITEMS = 10


@dataclass
class StageContextMetrics:
    stage_id: str
    payload_chars: int
    estimated_tokens: int
    budget_tokens: int
    utilization_pct: float
    compactions_applied: int
    compacted: bool


@dataclass
class ContextBudgetManager:
    """Tracks context utilization per stage and compacts payloads on demand.

    Usage::

        mgr = ContextBudgetManager.from_policy(policy)
        payload, n = mgr.maybe_compact(stage_id, payload)
        mgr.record_stage(stage_id, payload, compactions_applied=n)
        summary = mgr.summary()
    """

    stage_budgets: Dict[str, int] = field(default_factory=dict)
    default_budget: int = 8000
    compaction_thresholds: List[int] = field(default_factory=lambda: [60, 75, 85])
    _metrics: List[StageContextMetrics] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_policy(cls, policy: Dict[str, Any]) -> "ContextBudgetManager":
        """Build a manager from a loaded policy dict."""
        cfg: Dict[str, Any] = policy.get("context_budgets", {})
        thresholds = cfg.get("compaction_thresholds", [60, 75, 85])
        default_budget = cfg.get("default_budget", 8000)
        # Stage budgets are any key that is not a control key.
        control_keys = {"compaction_thresholds", "default_budget"}
        stage_budgets = {k: int(v) for k, v in cfg.items() if k not in control_keys and isinstance(v, int)}
        return cls(
            stage_budgets=stage_budgets,
            default_budget=int(default_budget),
            compaction_thresholds=[int(t) for t in thresholds],
        )

    # ------------------------------------------------------------------
    # Budget helpers
    # ------------------------------------------------------------------

    def get_budget(self, stage_id: str) -> int:
        """Return the token budget for *stage_id*, falling back to default."""
        return self.stage_budgets.get(stage_id, self.default_budget)

    @staticmethod
    def estimate_tokens(payload: Any) -> int:
        """Rough token estimate: serialised character count divided by 4."""
        text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
        return max(1, len(text) // 4)

    def utilization_pct(self, stage_id: str, payload: Any) -> float:
        """Return the estimated utilization percentage for *stage_id*."""
        tokens = self.estimate_tokens(payload)
        budget = self.get_budget(stage_id)
        return round((tokens / budget) * 100.0, 1)

    def should_compact(self, stage_id: str, payload: Any) -> bool:
        """Return True if the payload utilization is at or above the first threshold."""
        if not self.compaction_thresholds:
            return False
        pct = self.utilization_pct(stage_id, payload)
        return pct >= self.compaction_thresholds[0]

    # ------------------------------------------------------------------
    # Compaction
    # ------------------------------------------------------------------

    def compact_payload(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """Compact *payload* and return *(compacted_dict, num_compactions_applied)*.

        Compaction strategy (applied in order):
        1. Drop keys listed in ``_LOW_PRIORITY_KEYS``.
        2. Truncate string values longer than ``_STRING_TRUNCATE_CHARS``.
        3. Truncate list values longer than ``_LIST_TRUNCATE_ITEMS``.
        """
        compacted: Dict[str, Any] = {}
        compactions = 0

        for key, value in payload.items():
            if key in _LOW_PRIORITY_KEYS:
                compactions += 1
                continue

            if isinstance(value, str) and len(value) > _STRING_TRUNCATE_CHARS:
                compacted[key] = value[:_STRING_TRUNCATE_CHARS] + "... [truncated]"
                compactions += 1
            elif isinstance(value, list) and len(value) > _LIST_TRUNCATE_ITEMS:
                compacted[key] = value[:_LIST_TRUNCATE_ITEMS]
                compactions += 1
            else:
                compacted[key] = value

        return compacted, compactions

    def maybe_compact(
        self, stage_id: str, payload: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], int]:
        """Compact *payload* only if ``should_compact`` returns True.

        Returns *(payload, num_compactions_applied)*.  If no compaction was
        needed, returns the original payload with zero compactions.
        """
        if self.should_compact(stage_id, payload):
            return self.compact_payload(payload)
        return payload, 0

    # ------------------------------------------------------------------
    # Metrics recording
    # ------------------------------------------------------------------

    def record_stage(
        self,
        stage_id: str,
        payload: Any,
        compactions_applied: int = 0,
    ) -> StageContextMetrics:
        """Record context metrics for a completed stage and return the entry."""
        chars = len(json.dumps(payload, default=str))
        tokens = max(1, chars // 4)
        budget = self.get_budget(stage_id)
        pct = round((tokens / budget) * 100.0, 1)
        metrics = StageContextMetrics(
            stage_id=stage_id,
            payload_chars=chars,
            estimated_tokens=tokens,
            budget_tokens=budget,
            utilization_pct=pct,
            compactions_applied=compactions_applied,
            compacted=compactions_applied > 0,
        )
        self._metrics.append(metrics)
        return metrics

    # ------------------------------------------------------------------
    # Summary (written to run artifacts)
    # ------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Return a JSON-serialisable summary of all recorded stage metrics."""
        if not self._metrics:
            return {
                "stages_tracked": 0,
                "total_estimated_tokens": 0,
                "peak_utilization_pct": 0.0,
                "total_compactions": 0,
                "per_stage": [],
            }
        return {
            "stages_tracked": len(self._metrics),
            "total_estimated_tokens": sum(m.estimated_tokens for m in self._metrics),
            "peak_utilization_pct": max(m.utilization_pct for m in self._metrics),
            "total_compactions": sum(m.compactions_applied for m in self._metrics),
            "per_stage": [
                {
                    "stage_id": m.stage_id,
                    "estimated_tokens": m.estimated_tokens,
                    "budget_tokens": m.budget_tokens,
                    "utilization_pct": m.utilization_pct,
                    "compacted": m.compacted,
                }
                for m in self._metrics
            ],
        }
