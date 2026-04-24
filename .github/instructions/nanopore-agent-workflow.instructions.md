---
description: "Use when: implementing, refactoring, or documenting nanoporethon subcomponents and workflows."
---
For nanoporethon tasks, follow this sequence:

1. Read minimal context first:
   - `Docs/agent_context_index.md`
   - `Docs/components.md`
2. Read deeper context only as needed:
   - `Docs/UseCases.md`
   - `Docs/UserPersonas.md`
   - `Docs/technology_context.md`
3. Change code incrementally with tests.
4. If component contracts change, update `Docs/components.md` in the same change.
5. Append a short row to `Docs/agent_logs/REQUEST_LOG.md` for traceability.

Quality guardrails:

- Preserve compatibility for search logs and MAT loading pathways unless migration is explicitly requested.
- Keep GUI files orchestration-focused; push reusable logic into subcomponents.
- Prefer clarity and composability over one-off quick fixes.
- When MATLAB behavior conflicts with validated Python contracts/tests, Python is authoritative.
- Use MATLAB as reference context only; do not copy legacy structure by default.
