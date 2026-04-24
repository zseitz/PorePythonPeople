# Agent Context Index (Cost-Aware)

Use this file as the first stop for agent tasks.

## Why this exists

To keep agent quality high **without** loading the whole repository every time.

## Context tiers

### Tier 0 (always read first)

1. `Docs/agent_context_index.md` (this file)
2. `Docs/components.md`

### Tier 1 (read when planning/feature work)

3. `Docs/UseCases.md`
4. `Docs/UserPersonas.md`
5. `Docs/technology_context.md`

### Tier 2 (read only if task requires)

6. `MATLABcode/*.m` files relevant to the requested functionality
7. Specific Python source files under `src/nanoporethon/`
8. Tests related to touched components

## Minimum context policy for coding agents

- Start with Tier 0.
- Add Tier 1 only for design-heavy or new-feature tasks.
- Add Tier 2 only for files directly affected by the request.
- Avoid full-repo reads unless debugging a cross-cutting issue.

## Mandatory maintenance policy

When a component behavior or contract changes:

1. Update source code.
2. Update tests (or add tests) for behavior.
3. Update `Docs/components.md` in the same change.
4. Append a short entry to `Docs/agent_logs/REQUEST_LOG.md`.
