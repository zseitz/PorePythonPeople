---
agent: ask
description: "Use when: starting any nanoporethon change through a single orchestrator-first intake prompt."
---
Use **Nanopore Orchestrator Agent** for this request.

# Reusable Orchestrator Prompt

## 1) Change request summary
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

## 4.5) Complexity triage indicators
- **Estimated blast radius**: (single file / multi-file / cross-component)
- **Components likely impacted** (C1–C10):
- **Contract/data format changes expected?** (yes/no)
- **Potential requirement inconsistencies or unknowns**:
- **If medium/large or uncertain**: list follow-up questions the orchestrator should resolve first.

## 5) Architecture placement and orchestration
- **Target component(s)** (C1–C10 in `Docs/components.md`):
- **New subcomponent needed?** (yes/no)
- **If yes, proposed name + public API**:
- **Likely specialist path** (if needed):
	- refactor-heavy → Python Refactor Agent conventions
	- net-new feature → Nanopore Feature Builder Agent conventions
	- docs sync → Nanopore Doc Sync Agent conventions

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

## 8) MATLAB reference context (when relevant)
- **Relevant MATLAB file/function**:
- **Behavior to preserve**:
- **Known legacy behavior to avoid**:
- **Python pattern(s) to mirror/reuse first** (module/class/test):
- **Authority rule acknowledgment**:
	- [ ] If MATLAB and validated Python contracts/tests diverge, Python is authoritative.

## 9) Documentation and traceability requirements
- [ ] Update `Docs/components.md` if contracts/components change
- [ ] Update `Docs/nanoporethon_textbook.md` if user workflow changes
- [ ] Append row to `Docs/agent_logs/REQUEST_LOG.md`
- [ ] Note user-facing workflow changes

## 10) Done definition
A request is ready for orchestrated implementation when:
- [ ] Scope is explicit and bounded
- [ ] Inputs/outputs are defined
- [ ] Acceptance criteria are testable
- [ ] Affected components are identified
- [ ] Backward compatibility constraints are stated
- [ ] Test/update/doc/log steps are explicitly requested

---

If any required section is missing, or if requirements are inconsistent/ambiguous, ask targeted follow-up questions before implementation starts.

Then execute through **Nanopore Orchestrator Agent** with staged delivery:
plan → implementation → verification → documentation → request-log update.
