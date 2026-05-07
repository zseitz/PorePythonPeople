# Operator Assistant Hybrid Architecture Plan (No-MCP, Local-First)

Date: 2026-05-07  
Status: Proposed (planning only)

## Goal

Rebalance nanoporethon's runtime from "executable-agent heavy" toward a **hybrid architecture**:

- **Markdown skills** for stable knowledge, workflows, and judgment rules
- **Executable runtime stages** for deterministic actions, validation, and guarded repo mutation
- **No MCP connectivity** (explicitly out of scope)

This preserves privacy/local operation and reduces orchestration complexity while improving decision quality.

## Design principles

1. **No MCP requirement**
   - Runtime and assistant must remain fully local-first and functional without MCP servers.
2. **Know vs Do separation**
   - If it is mostly institutional know-how, encode it in markdown skill files.
   - If it mutates state or executes commands, keep it in executable runtime stages.
3. **Standalone skill usefulness**
   - Every skill should still produce useful output without tool execution (analysis, plan, copy-ready patch intent, checklist, draft docs, etc.).
4. **Deterministic execution boundaries**
   - Skill files guide behavior; executable stages remain the source of truth for action gating, verification, and promotion safeguards.
5. **Human-supervised irreversible actions**
   - Keep explicit approvals and guardrails for risky/irreversible operations.

## Proposed architecture shape

### A) Knowledge layer (new markdown skills)

Add `runtime/skills/` with focused SKILL-style files:

- `runtime/skills/request-triage.SKILL.md`
  - Complexity/risk triage heuristics and clarification strategy.
- `runtime/skills/implementation-strategy.SKILL.md`
  - Small-diff coding policy, test targeting strategy, compatibility guardrails.
- `runtime/skills/verification-strategy.SKILL.md`
  - How to choose checks, interpret failures, and report actionable evidence.
- `runtime/skills/doc-sync-rules.SKILL.md`
  - Contract/workflow doc sync rules, textbook update triggers, request-log hygiene.
- `runtime/skills/operator-assistant-routing.SKILL.md`
  - Chat routing expectations, protected-core-file authorization behavior, blocked-only follow-up policy.

### B) Execution layer (existing runtime)

Keep deterministic stage flow in:

- `runtime/orchestrator.py`
- `runtime/executor.py`
- `runtime/gates.py`
- `runtime/state.py`
- `runtime/contracts.py`

No protocol migration is required. `runtime/adapters/ollama.py` remains the local model transport.

### C) Skill-loading integration

- Add a lightweight skill loader (`runtime/skill_loader.py`) to read selected markdown skills by stage.
- Inject relevant skill snippets into stage prompts or handoff payload context (bounded by existing context budgets).
- Keep execution payload schemas unchanged unless a contract evolution is explicitly needed.

## Implementation phases

### Phase 0 — Guardrails & policy declaration (small, immediate)

1. Declare explicit no-MCP policy and hybrid rules in agent guidance/docs.
2. Keep current runtime behavior unchanged.

Success criteria:

- Documentation and agent policy clearly say: local-first, no MCP required, hybrid knowledge+execution model.

### Phase 1 — Add skill artifacts without runtime behavior change

1. Create `runtime/skills/*.SKILL.md` files.
2. Update runtime prompts to reference these skill artifacts conceptually (without mandatory loader wiring yet).

Success criteria:

- Skills exist, versioned in git, and can be reviewed independently.

### Phase 2 — Wire skill loader into orchestrator/executor

1. Implement `runtime/skill_loader.py` with stage-to-skill mapping.
2. Inject selected skill text into stage context with size caps.
3. Add tests for skill loading, missing-skill fallback, and budget-aware truncation.

Success criteria:

- Stages receive the right knowledge context without changing gate determinism.

### Phase 3 — Operator assistant hybrid routing refinement

1. Use skills to drive request analysis/playbook generation before run-ready state.
2. Keep strict structured-output contracts and blocked-only clarification behavior.
3. Preserve protected core GUI authorization handling.

Success criteria:

- Fewer repetitive clarifications; stronger plan quality in runtime request previews.

### Phase 4 — Evaluate and simplify stage complexity

1. Audit whether specific executable stages can be simplified once skill guidance is strong.
2. Keep verify/doc-sync/memory-sync gates deterministic.

Success criteria:

- Lower orchestration complexity without reducing safety/traceability.

## Test strategy

- `tests/test_runtime_milestone1.py`
  - Add coverage for skill-loading and stage-context injection boundaries.
- `tests/test_operator_assistant.py`
  - Add coverage for skill-informed planning behavior and fallback behavior.
- `tests/test_operator_assistant_gui.py`
  - Ensure UX remains actionable and guarded under strict mode.

## Non-goals

- Adding MCP servers or remote SaaS dependencies.
- Replacing deterministic gate evidence with model-generated assertions.
- Turning runtime into unattended autonomous operation.

## Immediate next sprint (recommended)

1. Land Phase 0 and Phase 1 only.
2. Validate no behavior regressions.
3. Then implement Phase 2 behind a small policy flag if desired.
