# nanoporethon Textbook (User + Agent Guide)

This document is a practical handbook for using nanoporethon both:

- **as a user** running data workflows, and
- **as a developer/team member** collaborating with coding agents.

It complements `Docs/components.md` by focusing on *how to use the system* in day-to-day work.

---

## 1. What nanoporethon does

nanoporethon supports a two-stage workflow:

1. **Find relevant experiments** from a large directory using inclusion/exclusion search terms.
2. **Inspect and classify events** from selected experiments using MATLAB-derived data files.

Primary package: `src/nanoporethon/`.

---

## 2. Core user workflows

### 2.1 Data navigation workflow

Use `DataNaviGUI` to:

1. select database directory,
2. search using inclusion/exclusion terms,
3. manually curate selected files,
4. save a query log containing `search_query.txt`.

Output artifact: a query folder in your logs directory.

### 2.2 Event classification workflow

Use `EventClassifierGUI` to:

1. choose a saved query,
2. load selected experiment folders,
3. visualize traces and event overlays,
4. navigate events and update event quality.

Writes event quality updates back to `event.mat`.

---

## 3. Data expectations and contracts

Each selected experiment folder should contain:

- `reduced.mat` (required)
- `event.mat` (required)
- `meta.mat` (optional)

Search-log format details are defined in `Docs/components.md` and must remain compatible with parser expectations.

---

## 4. Running nanoporethon with coding agents

### 4.1 Which agent to use

- **Nanopore Orchestrator Agent**: best default for non-trivial change requests.
- **Python Refactor Agent**: structural cleanup with behavior preservation.
- **Nanopore Feature Builder Agent**: implement new functionality.
- **Nanopore Doc Sync Agent**: synchronize docs/logs with merged behavior.

### 4.2 Recommended request sequence

1. Draft request using `Docs/feature_request_template.md`.
2. Execute via **Nanopore Orchestrator Agent**.
3. Verify tests/checks pass.
4. Confirm docs + request log updates are included.

---

## 5. Development guardrails

- Prefer reusable logic in subcomponents over GUI-level duplication.
- Preserve existing contracts unless migration is explicitly planned.
- Keep changes incremental and test-backed.
- Update `Docs/components.md` for contract/component changes.
- Append a row to `Docs/agent_logs/REQUEST_LOG.md` for traceability.

---

## 6. MATLAB relationship (important)

Legacy files in `MATLABcode/` are **reference-only**.

- Use MATLAB for context and behavior inspiration.
- Do **not** treat MATLAB as architectural authority.
- If MATLAB behavior conflicts with validated Python contracts/tests, **Python is authoritative**.

---

## 7. Troubleshooting quick guide

### Issue: Query loads but no experiments appear

- Verify `search_query.txt` format was preserved.
- Verify selected folder names still exist under source directory.

### Issue: Event viewer cannot plot data

- Confirm `reduced.mat` and `event.mat` exist in target folder.
- Confirm MAT loader fallback paths still handle file variant.

### Issue: Agent output seems inconsistent with codebase

- Re-check `Docs/components.md` and `Docs/technology_context.md`.
- Ensure request included clear scope and acceptance criteria.
- Prefer orchestrator flow to enforce tests + docs + logging.

---

## 8. Change checklist (for human + agent contributors)

- [ ] Behavior implemented/refactored
- [ ] Relevant tests added or updated
- [ ] `Docs/components.md` updated (if contracts/components changed)
- [ ] `Docs/nanoporethon_textbook.md` updated (if user workflow changed)
- [ ] `Docs/agent_logs/REQUEST_LOG.md` appended
