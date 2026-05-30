# nanoporethon Components and Architecture

This document explains what `nanoporethon` does and how its components fit together.
It is written for three audiences:

- **Users**: What workflow the tool supports.
- **Developers**: Where responsibilities live in code.
- **Future coding agents**: Stable component contracts, data flow, and extension points.

---

## What nanoporethon is for

`nanoporethon` is a Python GUI toolkit for nanopore data workflows in two major stages:

1. **Find and capture a reproducible set of experiment folders** from a large database using inclusion/exclusion search terms.
2. **Load and inspect selected experiment traces/events** from MATLAB files (`reduced.mat`, `event.mat`, `meta.mat`) and edit per-event quality values.

In short: **search → persist query log → inspect/classify events**.

---

## High-level architecture

The codebase is intentionally split into:

- **User-facing GUIs** (`data_navi_gui.py`, `event_classifier_gui.py`)
- **Reusable utilities** (config, directory handling, log parsing, MAT loading)
- **Core operations** (search filtering and query-log output)
- **Agent governance artifacts** (agent definitions, instructions, context index, request logs)

Primary package location: `src/nanoporethon/`.

---

## End-user workflow

### 1) Data navigation and selection (`DataNaviGUI`)

- Select a **database directory** containing experiment folders/files.
- Provide **inclusion** and **exclusion** terms.
- Run cumulative searches and interactively toggle selected items.
- Confirm selection to write a timestamped query folder containing `search_query.txt`.

### 2) Event inspection/classification (`EventClassifierGUI`)

- Select a **search logs directory**.
- Pick a saved query folder.
- Load each selected experiment folder.
- Plot reduced trace data and event overlays.
- Navigate events and write updated event quality back to `event.mat`.

---

## Component catalog (source-of-truth)

> Note: file names keep historical `subcomponent_*` numbering, but responsibilities are best understood by function (below).

### C1. Directory prompt utility

- **File**: `subcomponent_1_prompt_user.py`
- **Public function**: `prompt_user()`
- **Purpose**: Minimal standalone directory picker using tkinter; stores selection in module-level `database_directory`.
- **Used by**: Primarily standalone/manual usage.

### C2. Search filter engine

- **File**: `subcomponent_2_data_navigator.py`
- **Public function**: `data_navi(database_directory, array_1, array_2) -> List[str]`
- **Purpose**: Returns names from a directory that match **all** inclusion terms (`array_1`) and **none** of the exclusion terms (`array_2`).
- **Key behavior**:
  - Raises `ValueError` if source directory is invalid.
  - Operates on `os.listdir(...)` names (string matching, not metadata parsing).

### C3. Query log writer

- **File**: `subcomponent_3_data_navi_sub_directory.py`
- **Public function**: `data_navi_sub_directory(...)`
- **Purpose**: Creates `<logs_dir>/<safe_query_name>_<timestamp>/search_query.txt` and records:
  - source directory
  - inclusion/exclusion arrays
  - selected file/folder names
- **Important**: Does **not** copy selected data; it logs references only.

### C4. Persistent config manager

- **File**: `subcomponent_4_config_manager.py`
- **Public API**:
  - `load_config()`, `save_config(...)`
  - `get_config_value(...)`, `set_config_value(...)`
  - `get_database_directory()`, `set_database_directory(...)`
  - `get_logs_directory()`, `set_logs_directory(...)`
  - `clear_config()`
- **Purpose**: Stores GUI path preferences in `.nanoporethon_config.json` (inside package directory).

### C5. Directory selection helpers

- **File**: `subcomponent_5_directory_utilities.py`
- **Public API**:
  - `browse_for_directory(title)`
  - `select_database_directory(...)`
  - `select_logs_directory(...)`
  - `validate_directory(...)`
- **Purpose**: Shared directory-dialog + validation wrapper used across GUIs.

### C6. Search log parser

- **File**: `subcomponent_6_search_log_utilities.py`
- **Public API**:
  - `load_search_log(log_file_path) -> (source_directory, selected_files)`
  - `find_search_queries(directory) -> List[str]`
- **Purpose**: Reads `search_query.txt` and enumerates saved query folders.

### C7. MAT file loading layer

- **File**: `subcomponent_7_mat_file_loader.py`
- **Public API**:
  - `load_reduced_mat(path)`
  - `load_event_data(path)`
  - `load_fsamp_from_event_mat(path)`
  - `load_fsamp_from_meta_mat(path)`
- **Purpose**: Robustly load MATLAB data across HDF5/non-HDF5 variants, including fallback strategies and normalized key lookup.

### C8. Data navigator GUI

- **File**: `data_navi_gui.py`
- **Class**: `DataNaviGUI`
- **Purpose**: User-facing app for building and confirming file selections.
- **Depends on**: C2, C3, C4, C5.

### C9. Event classifier GUI

- **File**: `event_classifier_gui.py`
- **Class**: `EventClassifierGUI`
- **Purpose**: User-facing app for plotting data, navigating events, and editing event quality.
- **Depends on**: C4, C5, C6, C7.

### C10. Agent operations and governance layer

- **Files**:
  - `runtime/prompts/nanopore-orchestrator.prompt.md`
  - `runtime/prompts/nanopore-python-refactor.prompt.md`
  - `runtime/prompts/nanopore-feature-builder.prompt.md`
  - `runtime/prompts/nanopore-doc-sync.prompt.md`
  - `.github/instructions/nanopore-agent-workflow.instructions.md`
  - `.github/prompts/nanopore-feature-request.prompt.md`
  - `.github/archive/tier1-agents/*`
  - `Docs/agent_context_index.md`
  - `Docs/technology_context.md`
  - `Docs/feature_request_template.md`
  - `Docs/nanoporethon_textbook.md`
  - `Docs/agent_logs/REQUEST_LOG.md`
- **Purpose**: Standardize how agents refactor/add features, maintain architecture docs, and keep a paper trail of requests.
- **Key behavior**:
  - Enforces a cost-aware context loading order (`agent_context_index.md`).
  - Uses an orchestration-first agent workflow for complex changes (`runtime/prompts/nanopore-orchestrator.prompt.md`).
  - Requires mandatory complexity triage and clarification-first follow-up for large/ambiguous/inconsistent requests.
  - Provides a standardized orchestrator-first intake prompt (`nanopore-feature-request.prompt.md`) and optional detailed worksheet (`feature_request_template.md`).
  - Keeps superseded legacy prompt-only agent files archived under `.github/archive/tier1-agents/` for audit/history while runtime uses `runtime/prompts/` as canonical prompt source.
  - Requires doc synchronization when component contracts change.
  - Requires request logging for traceability.

### C11. Orchestrator runtime execution layer (delegation plumbing)

- **Files**:
  - `runtime/policies.yaml`
  - `runtime/stage_templates.yaml`
  - `runtime/orchestrator.py`
  - `runtime/planner.py`
  - `runtime/executor.py`
  - `runtime/context_manager.py`
  - `runtime/skill_loader.py`
  - `runtime/gates.py`
  - `runtime/state.py`
  - `runtime/repo_ops.py`
  - `runtime/waivers.py`
  - `runtime/memory_writer.py`
  - `runtime/adapters/ollama.py`
  - `runtime/schemas/handoff_packet.schema.json`
  - `runtime/schemas/stage_result.schema.json`
  - `runtime/schemas/gate_result.schema.json`
  - `runtime/schemas/run_state.schema.json`
  - `runtime/skills/*.SKILL.md`
- **Purpose**: Provide executable delegation contracts so one orchestrator run can route work across specialists with stage gates and auditable handoffs.
- **Key behavior**:
  - Documents a deliberately modest operating model: local, branch-scoped, human-reviewed feature-work assistance rather than unattended autonomous repository management.
  - Declares specialist registry and stage ownership.
  - Executes full policy-driven stage graph with conditional routing (`refactor_or_docsync`).
  - Parses specialist model output as structured JSON stage payloads, validates required stage fields, and falls back to deterministic payloads when parsing/validation fails.
  - Deterministic implement fallback now attempts targeted scaffold actions for explicit "create new python GUI file at <path>" requests, reducing silent no-op completions when model-authored implement payloads are missing.
  - Deterministic implement fallback now supports template-backed outputs under `runtime/templates/` (including `sequence_designer_gui_template.py`) so generated files can preserve higher-fidelity behavior without requiring model-authored implement actions.
  - Deterministic implement target extraction now prioritizes explicit output-target wording (for example, `as "new_gui.py"`) over unrelated `.py` paths embedded in guardrail text, and filters protected-file mentions from fallback target selection.
  - Deterministic fallback scaffolding is runtime-generic (module-level and GUI-level Python stubs) and no longer hardcodes behavior for specific generated application files.
  - Runtime request-file context ingestion supports explicit absolute local paths and `.mlapp` files by extracting `matlab/document.xml`, allowing MATLAB app audits to inform implement-stage payloads and deterministic fallbacks.
  - Runtime path discovery for request-file context is path-agnostic and avoids hardcoded user-home folder assumptions (for example no implicit `Downloads` dependency).
  - Validates model-authored action payloads against strict per-action schemas, policy-driven size/count limits, and stage-allowed action types before any repository mutation occurs.
  - Applies model-authored edit intents (`write_file`, `append_file`, `replace_in_file`) only after action-schema validation and edit-scope checks succeed.
  - Treats `verify` and `verify_after_refactor` command execution as authoritative gate evidence (`tests_exit_code`/`coverage_exit_code`); model verify output is retained only as metadata and cannot override deterministic verification results.
  - Defines conditional route to refactor stage when verification quality signals require it.
  - Enforces gate checks for plan/build/verify/doc-sync/memory-sync transitions.
  - Executes implementation/doc-sync work directly in the active local feature-branch workspace.
  - Uses git-porcelain-based changed-file detection in workspace mode to avoid repeated full-repo hashing stalls between stages.
  - Requires a clean git working tree before starting a fresh run when the repository root is a git checkout.
  - Captures base commit/branch metadata plus a start-of-run file-hash snapshot for promotion guardrails.
  - Executes verification commands from policy (`gates.verify.commands`) in the active workspace rather than fixed hardcoded test commands.
  - Normalizes bare `pytest ...` verify commands to `python -m pytest ...` before execution to avoid interpreter entrypoint mismatches between shell scripts and runtime Python environments.
  - Enforces implementation gate merge-marker checks by scanning changed files line-by-line for unresolved conflict markers, avoiding false positives from literal marker strings embedded in code.
  - Supports per-stage policy-controlled handling for pytest code `5` (`allow_no_tests_collected`) for both `verify` and `verify_after_refactor` instead of implicitly treating empty test scope as pass.
  - Defines waiver structure for explicit, auditable gate bypasses, restricted to approved operators.
  - Validates handoff, stage-result, gate-result, and run-state artifacts against JSON schemas at stage boundaries.
  - Writes repository-memory synchronization targets directly to `memories/repo/` in the repository.
  - Emits startup warnings when users run from `main`/`master` or detached HEAD, strongly recommending a dedicated feature branch inside the local clone.
  - Supports optional operator-gated promotion after closeout, with a recorded `promotion_diff.json` artifact, explicit approve/reject decision, refusal when target files changed in the local repository after run start, and allowlist-based blocking for changes outside configured promotion paths.
  - Assumes promotion remains part of a normal human review path: operators inspect changes, decide what to keep, and merge via their usual branch workflow.
  - Applies per-stage context budgets from policy and compacts oversized stage payloads before artifact write/model handoff.
  - Stores context utilization metrics in stage results and final run state for budget tuning.
  - Supports local specialist prompting through Ollama adapter + specialist `prompt_file`/`prompt_inline` contexts.
  - Applies a hard wall-clock timeout around specialist model calls; on timeout/error the stage records a warning and falls back to deterministic payload behavior instead of stalling run progression.
  - Loads stage-specific markdown skill context via `runtime/skill_loader.py` and injects bounded `skill_context` into specialist model payloads to improve plan/implementation quality without changing deterministic gates.
  - Supports optional per-specialist model-provider overrides (with global fallback) so different agents can use different local models.
  - Current balanced default routing keeps the global runtime default on `qwen2.5:3b`, routes coding-heavy `feature_builder` and `refactor` stages to `qwen3:4b`, and keeps lightweight `doc_sync`/`memory_sync` on `qwen2.5:3b` so attended runtime remains viable on 16 GB-class machines while improving code-stage quality.
  - Supports optional operator approval pauses at stage transitions, persisting pending approvals in run state so blocked runs can be resumed safely.
  - Supports operator-selected resume behavior for interrupted runs.
  - Is intentionally a secondary development aid for the main nanoporethon codebase, so guardrails should optimize for safe occasional use instead of heavy always-on platform complexity.

### C12. Local operator assistant GUI (Option B)

- **Files**:
  - `src/nanoporethon/operator_assistant_gui.py`
  - `runtime/operator_assistant.py`
  - `runtime/policies.yaml` (`assistant_scope` guardrail configuration)
- **Purpose**: Provide a user-facing, local-only attended interface that combines guided request intake, scoped chat assistance, and step-by-step runtime visibility.
- **Key behavior**:
  - Provides a chat-first local assistant for in-scope repository/runtime interaction.
  - Displays a live intent badge above chat output (for example Feature Request / Runtime Help / Out-of-Scope) so routing decisions are immediately visible.
  - Uses a semantic-first hybrid scope gate with two lanes: **feature requests** and **general questions**.
  - Applies an evidence-based repository relevance check before any answer/run action: prompts must align with configured anchors/goal terms and retrievable local repo context.
  - Off-topic/sensitive prompts are refused before runtime request drafting; ambiguous prompts get one targeted re-anchoring follow-up.
  - Uses model-based semantic intent/safety classification as the primary route when available, with deterministic fallback when classifier output is unavailable/invalid.
  - Treats common guided-workflow phrasing (for example confusion, reproducibility/checklist, safeguards, and capability-redirect prompts) as in-scope support requests rather than off-topic by default.
  - Uses a positive capability model in policy (`feature_request`, `runtime_help`, `code_explanation`, `repo_question`, `nanopore_science_explanation`) instead of denylist-style topic filtering.
  - Supports a dedicated `nanopore_science_explanation` route for scientific/algorithmic nanoporethon questions when they can be grounded in local repository materials.
  - Requires a repository/domain anchor (for example runtime terms, file/module references, q-mer/sequence-designer concepts, or retrieved local snippets) before answering explanation-style prompts.
  - Fails closed on ungrounded questions: if a scientific/code question lacks a clear local anchor, the assistant asks for one precise grounding clarification instead of guessing.
  - Uses LLM-based session analysis (request-kind inference, clarifying-question generation, and core-GUI authorization detection) instead of hard-coded keyword detectors for follow-up routing and request drafting.
  - Uses recent conversation/session context for continuation handling while preventing context contamination.
  - Avoids redundant clarification loops by collapsing overlapping core-GUI authorization questions and remembering explicit user decisions (for example, repeated "No" answers do not trigger the same authorization prompt again).
  - Builds a runtime request preview directly from conversation context (instead of requiring a long static form upfront).
  - Asks targeted clarification questions only when more precision is needed.
  - Favors low-friction execution for actionable requests: the assistant now defaults to zero follow-up questions unless execution is actually blocked (for example, protected core-GUI authorization or a genuinely underspecified request), and even then asks at most one question per turn.
  - Detects likely source-file reference mistakes in feature prompts (for example `.m` vs `.mlapp`) by checking referenced directories for near matches and asking a targeted one-question confirmation before runtime launch.
  - When protected core GUI files are implicated, authorization prompts are plan-specific: the assistant names the file(s) it expects to change and explains why it believes those file edits are needed before asking for permission.
  - **Session-aware continuation**: Follow-up responses are treated as feature-request continuation only when they remain repository-relevant and pass scope/safety checks; off-topic follow-ups reset feature context and are blocked from runtime request handling.
  - **Default verification policy for code changes**: Feature requests are treated as code-changing by default (unless clearly docs-only), and runtime request packets automatically require both automated tests and behavior checks without requiring users to include testing keywords.
  - Classifies intents into in-scope runtime/repo workflows vs out-of-scope domains.
  - Separates off-topic refusal from sensitive-domain blocking: unrelated prompts are redirected, while sensitive advisory domains (for example medical/legal/financial/political guidance) are explicitly blocked before any runtime action can occur.
  - Grounds answer-mode responses in configured local docs/code files (`assistant_scope.grounding_files`) and refuses to freewheel beyond retrieved local evidence.
  - Keeps response depth balanced by default and auto-switches to deeper guidance only when follow-up question density is high across recent turns.
  - Builds a runtime request packet from chat context and launches attended runtime execution locally.
  - Enforces runtime launch preflight before assistant-triggered runs: clean working tree (policy-controlled) plus feature-branch requirement (policy-controlled), with explicit blocked-state diagnostics.
  - Protects policy-configured core files by default (repository default policy includes `data_navi_gui.py` and `event_classifier_gui.py`) unless user explicitly authorizes modifying them.
  - Includes an explicit anti-hallucination quality rubric in generated runtime request packets (contract-safe, evidence-first, surface-consistent, traceable, scoped, operator-supervised).
  - Streams runtime progress to users by reading `.nanopore-runtime/runs/<run_id>/events.jsonl` and surfacing stage/gate/promotion events.
  - Shows a live animated activity indicator (dot-cycling heartbeat) during assistant-processing and runtime execution, including a last-UI-tick timestamp, so users can distinguish active work from a frozen UI even between major timeline events.
  - Uses a cleaner single-chat-centric interaction surface: follow-up questions and runtime-plan review are rendered inline in the main chat stream (instead of separate follow-up/preview panes), while runtime controls remain available in a compact side control area.
  - Renders chat and runtime timeline text with lightweight markdown formatting (for example headings, lists, inline code, and fenced code blocks) plus pane-specific typography/color theming that adapts to light/dark UI backgrounds for improved readability without requiring network/cloud renderers.
  - Chat and timeline entries render each message with an explicit heading line (timestamp/role or timestamp/event) so users get larger bold visual anchors similar to Copilot-style section headers even when assistant body text does not include markdown heading markers.
  - Chat and timeline entries also render a subtle separator rule under each message block to improve scanability during longer sessions.
  - Surfaces explicit routing errors in the GUI when message processing fails.
  - Includes a manual **Health Check** button that validates scope-gate policy readiness (anchors, grounding files, and semantic classifier configuration/availability) with actionable remediation messages.
  - Provides deterministic explanations for common runtime timeline terms (for example `promotion_disabled`, `promotion_skipped`, `promotion_blocked`) to keep post-run Q&A low-friction.
  - Answers repository questions using the local Ollama model (from `model_provider` policy) when available, but constrains responses to retrievable local documentation/code evidence.
  - Enforces evidence-validated answer synthesis for model-backed Q&A: model answers must include verifiable context quotes, and responses with unverifiable repository import/module claims are rejected.
  - Falls back to relevant doc/code snippet excerpts when the model is not reachable.
  - Also falls back to deterministic snippet-grounded answers when model output is malformed or fails evidence validation, reducing hallucinated run/API instructions.
  - Deterministic fallback now synthesizes practical guidance for how/use/find/work questions (for example runnable commands + usage considerations + source references) rather than dumping raw snippet fragments.
  - In deeper follow-up mode, Porsche prioritizes presenting existing repository information with explicit references and adds a "Further reading in repository" section that includes available paper resources from `Docs/papers/`.
  - Treats common guided-workflow phrasing (for example confusion, reproducibility/checklist, safeguards, and capability-redirect prompts) as in-scope support requests.
  - Keeps the operational model branch-local and human-supervised by design.

  ### C13. Sequence designer GUI (sequence-to-signal utility)

  - **File**:
    - `src/nanoporethon/sequence_designer_gui.py`
  - **Purpose**: Provide a deterministic sequence-to-signal design surface aligned with MATLAB Sequence Designer controls.
  - **Key behavior**:
    - Validates DNA input to strict A/C/G/T (sequence entered in 5'→3' direction).
    - Computes deterministic normalized current levels per k-mer window.
    - Exposes explicit design controls for feeding orientation (5'/3'), pore orientation (forwards/backwards), display order (5'→3'/3'→5'), and phase shift (0..1).
    - Exposes MATLAB-style edit-at-position controls (position slider/index, A/C/G/T mutation buttons, delete, random mutation) for rapid iterative sequence design.
    - Includes Hel308 mode toggle plus save/export actions for generated traces (figure save and JSON level export).
    - Applies display-order and phase-shift transforms prior to plotting.
    - Uses q-mer-map lookup when available (with env override `NANOPORETHON_QMER_MAP_PATH` and auto-detect disable switch `NANOPORETHON_DISABLE_QMER_AUTODETECT`) to match MATLAB-aligned default level outputs for the validated reference sequence.
    - Supports MLAPP-style map-profile branching for exhaustive parity targets: forwards/backwards pore orientation × 5'/3' feeding orientation plus Hel308 profile handling, including branch-specific warning semantics.
    - For MLAPP parity, feeding/pore choices are applied via map-profile selection (rather than sequence transformation), while display order controls output ordering semantics.
    - Export payload now carries MATLAB-aligned parity metadata (levels, error, x-axis indices, details text, phase, and numstep) for golden acceptance checks.
    - Provides a dedicated parity scorecard generator at `runtime/sequence_designer_parity_scorecard.py` that emits JSON/Markdown graduation artifacts under `.nanopore-runtime/parity/sequence_designer/latest/`.
    - When the runtime falls back without model-authored implement actions, it now emits a contract-aware `sequence_designer_gui.py` template instead of a blank GUI placeholder.
    - Deterministic fallback template plotting now mirrors MATLAB visual parity more closely by emitting a step-style levels trace centered on attributed points, plus per-base sequence-letter overlays aligned to level positions.
    - Is self-contained: sequence sanitization and signal helpers are implemented in the same module (no GUI-to-GUI dependency).

#### Golden output acceptance workflow (sequence designer)

- Treat MATLAB-derived numeric traces and branch semantics as **golden acceptance targets** for this component.
- Runtime/template updates are not considered complete until:
  1. default validated reference-sequence output parity passes,
  2. branch-profile selection semantics (forwards/backwards, 5'/3', hel308 warnings) are covered by tests,
  3. regenerated `src/nanoporethon/sequence_designer_gui.py` is produced through the runtime path,
  4. verification evidence is recorded in run artifacts/tests.
- This workflow is used to both improve deterministic fallback quality and establish a clear quality floor for Porsche-generated code.
- Recommended evidence bundle now includes the parity scorecard artifacts (`sequence_designer_parity_scorecard.json` and `.md`) in addition to pytest output.

---

## Data contracts and artifacts

### Search log folder contract

- **Folder name pattern**: `<safe_query_name>_YYYYMMDD_HHMMSS`
- **Naming rule**: `query_name` is normalized to Windows-safe filename characters before the timestamp is appended.
- **Required file**: `search_query.txt`
- **Required content cues used downstream**:
  - `Source Directory: ...`
  - `Selected Files/Directories:` followed by `- <name>` entries

### Experiment folder contract (for event classification)

Each selected item is expected to be a folder containing at least:

- `reduced.mat` (required for plotting)
- `event.mat` (required for event overlays/quality editing)
- `meta.mat` (optional source of sampling frequency)

### Agent request log contract

- **File**: `Docs/agent_logs/REQUEST_LOG.md`
- **Required columns**:
  - `Date`
  - `Requester`
  - `Objective`
  - `Agent`
  - `Files Changed`
  - `Status`
  - `Notes`
- **Expectation**: each meaningful agent task appends a concise entry.

### Runtime run artifact contract

- **Run root pattern**: `.nanopore-runtime/runs/<run_id>/`
- **Canonical artifacts**:
  - `run.json` (schema-aligned run state)
  - `events.jsonl` (chronological execution/gate events)
  - `artifacts/` (outputs generated by specialists)
- **Expectation**: each stage produces schema-valid output before handoff to the next stage.

---

## Dependency map

### DataNaviGUI path

`DataNaviGUI` → C5 (directory dialogs), C4 (path persistence), C2 (search), C3 (write query log)

### EventClassifierGUI path

`EventClassifierGUI` → C5 (directory dialogs), C4 (persistence), C6 (load query selections), C7 (load MAT/event data)

### Agent workflow path

`Agent request` → C10 context index → targeted code/docs changes → tests/verification → `components.md` sync (if needed) → request log append

### Runtime delegation path

`User request` → C11 `triage_plan` → `implement` → `verify` → (`refactor` if needed) → `doc_sync` → `memory_sync` → closeout artifacts

### Operator-assistant path

`User chat/form input` → C12 intent + scope guardrails → structured request packet → C11 runtime execution → event timeline updates in GUI

### Consensus maker path

`User sequence input` → C13 sequence validation + k-mer mapping → consensus step-signal plot

Current implementation status:

- executable flow includes routing stage and closeout: `triage_plan` → `implement` → `verify` → `refactor_or_docsync` → (`refactor` → `verify_after_refactor`)? → `doc_sync` → `memory_sync` → `closeout`
- each stage transition emits validated handoff and gate artifacts under `.nanopore-runtime/runs/<run_id>/`
- integration coverage for runtime lives under `tests/test_runtime_milestone1.py`, `tests/test_runtime_integration.py`, and `tests/fixtures/runtime_fixture_repo/`

---

## Agent-oriented implementation notes

If using this document to build an automated coding agent, treat the following as stable entry points:

- **Search operation**: `subcomponent_2_data_navigator.data_navi`
- **Persist selected search**: `subcomponent_3_data_navi_sub_directory.data_navi_sub_directory`
- **Load query selection**: `subcomponent_6_search_log_utilities.load_search_log`
- **Load numerical data/events**: `subcomponent_7_mat_file_loader.*`
- **Launch GUIs**: `data_navi_gui.run_gui()`, `event_classifier_gui.run_gui()`

Recommended agent guardrails:

- Do not assume strict filename schema beyond substring matching in C2.
- Preserve `search_query.txt` parsing markers expected by C6.
- Keep GUI modules focused on orchestration; extend reusable logic in C4–C7 first.
- Maintain backward compatibility for MAT loading fallbacks (HDF5 + scipy fallback paths).
- Follow context levels in `Docs/agent_context_index.md` to limit unnecessary token/cost usage.
- MATLAB behavior is not authoritative when it conflicts with Python contracts/tests.
- Keep `Docs/nanoporethon_textbook.md` synchronized when user-facing workflows change.

---

## Developer maintenance guidance

- **Prefer composition over duplication**: put shared logic in C4–C7.
- **Preserve query log format**: changes must coordinate C3 and C6 together.
- **Keep user flows intact**:
  - DataNaviGUI confirms selection and exits after successful save.
  - EventClassifierGUI supports event navigation + quality save to `event.mat`.
- **Keep docs/logs synchronized**:
  - If component behavior/contracts change, update this file in the same change.
  - If user workflow changes, update `Docs/nanoporethon_textbook.md` in the same change.
  - Append a brief task entry to `Docs/agent_logs/REQUEST_LOG.md`.
- **Tests**: use `tests/test_nanoporethon_comprehensive.py` as the main compatibility suite. Tests are the authoritative arbiter when MATLAB and Python behavior diverge.

---

## Runtime dependencies (current project)

From `pyproject.toml`, primary dependencies include:

- `numpy`
- `matplotlib`
- `h5py`
- `pytest`, `pytest-cov` (testing)
- `PyYAML` (runtime policy loading)
- `jsonschema` (runtime contract enforcement)

`subcomponent_7_mat_file_loader.py` can also use `scipy` when available for non-HDF5 MAT fallback loading.
