# Agent Context Index (Cost-Aware)

Use this file as the first stop for agent tasks.

## Why this exists

To keep agent quality high **without** loading the whole repository every time.

Operating-model default: treat runtime/agent behavior as supervised engineering assistance (local + branch-based + human-reviewed), not unattended autonomous platform behavior.

## Context levels

### Level 0 (always read first)

1. `Docs/agent_context_index.md` (this file)
2. `Docs/components.md`

### Level 1 (read when planning/feature work)

3. `Docs/UseCases.md`
4. `Docs/UserPersonas.md`
5. `Docs/technology_context.md`
6. `Docs/nanoporethon_textbook.md`

### Level 2 (read only if task requires)

7. `MATLABcode/*.m` files relevant to the requested functionality
8. Specific Python source files under `src/nanoporethon/`
9. Tests related to touched components

## Minimum context policy for coding agents

- Start with Level 0.
- Add Level 1 only for design-heavy or new-feature tasks.
- Add Level 2 only for files directly affected by the request.
- Avoid full-repo reads unless debugging a cross-cutting issue.
- Keep generated plans and edits aligned with the supervised operating model unless the user explicitly requests and approves a different mode.

## Mandatory maintenance policy

When a component behavior or contract changes:

1. Update source code.
2. Update tests (or add tests) for behavior.
3. Update `Docs/components.md` in the same change.
4. Update `Docs/nanoporethon_textbook.md` when user workflow changes.
5. Append a short entry to `Docs/agent_logs/REQUEST_LOG.md`.
