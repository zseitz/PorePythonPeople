# implementation-strategy skill

Purpose: reduce hallucinated edits by favoring small, contract-safe, testable diffs.

## Heuristics

- Prefer minimal edits over broad rewrites.
- Keep GUI modules orchestration-focused; put reusable logic in runtime utilities/subcomponents.
- Preserve public behavior unless user request requires change.

## Anti-hallucination checklist

- Contract-safe: preserve schema/policy/gate compatibility.
- Scoped: avoid unrelated refactors.
- Operator-supervised: branch-local edits with human review.

## Validation expectations

- Add/adjust targeted regression tests for each new behavior.
- Ensure changed files are explicitly listed.
- Surface unresolved risks when confidence is incomplete.
