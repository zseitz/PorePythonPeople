"""Planning utilities for nanopore orchestrator runtime."""

from __future__ import annotations

from typing import Dict, List


def classify_complexity(request: str) -> str:
    """Classify request complexity as Small/Medium/Large.

    This heuristic is intentionally conservative for Milestone-1.
    """
    text = (request or "").lower()
    score = 0

    large_markers = [
        "schema",
        "migration",
        "contract",
        "cross-component",
        "external dependency",
        "breaking",
    ]
    medium_markers = [
        "refactor",
        "multi-file",
        "multi file",
        "runtime",
        "architecture",
        "docs",
        "tests",
    ]

    for marker in large_markers:
        if marker in text:
            score += 2
    for marker in medium_markers:
        if marker in text:
            score += 1

    if len(text) > 300:
        score += 1

    if score >= 4:
        return "Large"
    if score >= 2:
        return "Medium"
    return "Small"


def derive_acceptance_criteria(request: str) -> List[str]:
    """Produce deterministic acceptance criteria from user request."""
    base = [
        "Changes are implemented or explicitly documented as no-op.",
        "Relevant tests are executed and results recorded.",
        "No unresolved merge markers remain in changed files.",
    ]
    text = (request or "").lower()
    if "doc" in text or "textbook" in text:
        base.append("Documentation is updated when workflow/contracts change.")
    return base


def build_triage_plan(request: str) -> Dict[str, object]:
    """Build triage output payload used by the triage_plan stage."""
    complexity = classify_complexity(request)
    return {
        "complexity": complexity,
        "staged_plan": [
            "triage_plan",
            "implement",
            "verify",
            "refactor_or_docsync",
            "refactor (conditional)",
            "verify_after_refactor (conditional)",
            "doc_sync",
            "memory_sync",
            "closeout",
        ],
        "acceptance_criteria": derive_acceptance_criteria(request),
        "impacted_components": ["C11"],
    }
