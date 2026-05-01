# Technology Context for nanoporethon

This document gives coding agents deeper, domain-specific context beyond component names.

## Project intent

`nanoporethon` modernizes and extends a legacy MATLAB workflow into a maintainable Python toolkit with:

- reproducible experiment selection
- interactive event inspection and quality labeling
- future extensibility toward ML-assisted analysis

The repository also contains local runtime/agent infrastructure for development assistance, but that layer is intentionally secondary. It is meant for occasional, human-supervised feature work and documentation/refactor help—not for unattended autonomous repository operation.

## Legacy MATLAB relationship

Reference legacy scripts are in `MATLABcode/`:

- `preprocess.m`
- `eventclassifier.m`
- `makeJumpsZMS.m`
- `consensusMaker.m`

These scripts are **functional references**, not style or architecture references.

Agent rule:

- MATLAB scripts are reference-only.
- Port behavior where useful and validated.
- If MATLAB conflicts with Python contracts/tests, Python contracts/tests win.

## Current stable Python contracts

See `Docs/components.md` for source-of-truth contracts, especially:

- search and query log format
- search log parser expectations
- MAT loading fallback behavior
- GUI orchestration responsibilities

## Domain glossary (working terms)

- **Open state**: trace behavior associated with a stable open pore condition.
- **Event**: transient segment in trace data corresponding to molecular interaction/translocation behavior.
- **Gating event**: non-productive/undesired channel behavior that may resemble true events.
- **Jump/level**: substructure within an event used for finer interpretation.
- **Consensus alignment**: mapping event substructure to expected sequence-derived consensus features.

## Near-term engineering priorities

1. Keep Data Navigator and Event Classifier stable for daily lab use.
2. Increase modularity in reusable subcomponents before adding new GUI complexity.
3. Strengthen test coverage around data contracts and loaders.
4. Build ML-ready interfaces (clear input/output schemas) before adding heavy models.
5. Keep runtime/developer tooling proportional to the real operating model: local, branch-scoped, and human-reviewed.

## ML readiness constraints (future-facing)

Before introducing neural-network components, define:

- training/inference data schemas
- labeling provenance and quality controls
- reproducible evaluation metrics and baselines
- clear separation between deterministic preprocessing and probabilistic models

## Agent guardrails

- Prefer incremental PR-sized changes.
- Keep backward compatibility for shared artifacts (`search_query.txt`, MAT loading behavior).
- Update docs and request logs alongside code changes.
- Treat runtime/agent workflows as supervised engineering assistance, not as a substitute for human review.
- If uncertain about scientific interpretation, ask for clarification instead of guessing.
