# request-triage skill

Purpose: improve stage-1 planning quality while keeping execution deterministic.

## Heuristics

- Classify complexity as `Small`, `Medium`, or `Large` based on scope breadth, touched components, and risk.
- Prefer clarification only when acceptance criteria cannot be inferred from the request.
- Identify impacted components explicitly (runtime files, operator-assistant files, tests, docs).

## Guardrails

- Keep proposals branch-local and human-reviewed.
- Avoid planning actions that bypass deterministic gate evidence.
- Preserve existing contracts unless the request explicitly asks for contract evolution.

## Output shape guidance

- Include acceptance criteria that are testable and observable.
- Include impacted components and expected validation checks.
- Keep staged plan actionable and minimal.
