# verification-strategy skill

Purpose: keep deterministic verify outputs as source-of-truth while improving reporting quality.

## Heuristics

- Run policy-defined verify commands first.
- Treat command exit codes as authoritative gate evidence.
- Use model commentary only as supplemental diagnostics.

## Quality expectations

- Evidence-first: tests pass and behavior checks are executed.
- Report failures with concise root-cause hints.
- If no tests are collected, honor per-stage policy (`allow_no_tests_collected`).
- For MATLAB-parity components, include golden-output checks (numeric and branch-semantics) as explicit acceptance evidence, not optional commentary.

## Output shape guidance

- Record checks_run, failures_or_warnings, tests_exit_code, coverage_exit_code.
- Set quality_signals.require_refactor only with concrete reasons.
