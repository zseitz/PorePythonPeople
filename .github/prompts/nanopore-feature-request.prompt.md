---
agent: ask
description: "Use when: creating a high-quality feature request for nanoporethon with clear scope, acceptance criteria, and implementation guardrails."
---
Create a new nanoporethon feature request using the template below.

# Nanoporethon Feature Request

## 1) Request summary
- **Title**:
- **Requested by**:
- **Date**:
- **Priority**: (P0 critical / P1 high / P2 normal / P3 nice-to-have)

## 2) Problem and user value
- **Who is this for?** (e.g., undergrad, grad student, postdoc, collaborator)
- **Current pain point**:
- **Why this matters scientifically or operationally**:

## 3) Desired behavior
- **What should the software do?**
- **What should it explicitly NOT do?**
- **Expected inputs**:
- **Expected outputs/artifacts**:

## 4) Scope boundaries
- **In scope**:
- **Out of scope**:
- **Backward compatibility requirements**:

## 5) Architecture placement
- **Target component(s)** (C1–C10 in `Docs/components.md`):
- **New subcomponent needed?** (yes/no)
- **If yes, proposed name + public API**:

## 6) Data contracts and dependencies
- **Does this affect `search_query.txt` format?** (yes/no)
- **Does this affect MAT loading behavior?** (yes/no)
- **Any new files/artifacts introduced?**:
- **External dependencies needed?**:

## 7) Validation and acceptance criteria
- **Functional acceptance criteria** (bullet list):
- **Edge cases to handle**:
- **Failure behavior / error messages expected**:
- **Test expectations** (unit/integration/manual):

## 8) MATLAB reference context (optional)
- **Relevant MATLAB file/function**:
- **Behavior to preserve**:
- **Known legacy behavior to avoid**:

## 9) Documentation and traceability requirements
- [ ] Update `Docs/components.md` if contracts/components change
- [ ] Append row to `Docs/agent_logs/REQUEST_LOG.md`
- [ ] Note user-facing workflow changes

## 10) Done definition
A request is ready for implementation when:
- [ ] Scope is explicit and bounded
- [ ] Inputs/outputs are defined
- [ ] Acceptance criteria are testable
- [ ] Affected components are identified
- [ ] Backward compatibility constraints are stated

---

If any required section is missing, ask targeted follow-up questions before implementation starts.
