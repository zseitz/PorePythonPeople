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
- **Purpose**: Creates `<logs_dir>/<query_name>_<timestamp>/search_query.txt` and records:
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
  - `.github/agents/nanopore-orchestrator.agent.md`
  - `.github/agents/nanopore-python-refactor.agent.md`
  - `.github/agents/nanopore-feature-builder.agent.md`
  - `.github/agents/nanopore-doc-sync.agent.md`
  - `.github/instructions/nanopore-agent-workflow.instructions.md`
  - `.github/prompts/nanopore-feature-request.prompt.md`
  - `Docs/agent_context_index.md`
  - `Docs/technology_context.md`
  - `Docs/feature_request_template.md`
  - `Docs/nanoporethon_textbook.md`
  - `Docs/agent_logs/REQUEST_LOG.md`
- **Purpose**: Standardize how agents refactor/add features, maintain architecture docs, and keep a paper trail of requests.
- **Key behavior**:
  - Enforces a cost-aware context loading order (`agent_context_index.md`).
  - Uses an orchestration-first agent workflow for complex changes (`nanopore-orchestrator.agent.md`).
  - Provides a standardized feature-request intake template (`nanopore-feature-request.prompt.md`, `feature_request_template.md`).
  - Requires doc synchronization when component contracts change.
  - Requires request logging for traceability.

---

## Data contracts and artifacts

### Search log folder contract

- **Folder name pattern**: `<query_name>_YYYYMMDD_HH:MM:SS`
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

---

## Dependency map

### DataNaviGUI path

`DataNaviGUI` → C5 (directory dialogs), C4 (path persistence), C2 (search), C3 (write query log)

### EventClassifierGUI path

`EventClassifierGUI` → C5 (directory dialogs), C4 (persistence), C6 (load query selections), C7 (load MAT/event data)

### Agent workflow path

`Agent request` → C10 context index → targeted code/docs changes → tests/verification → `components.md` sync (if needed) → request log append

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
- Follow context tiers in `Docs/agent_context_index.md` to limit unnecessary token/cost usage.
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

`subcomponent_7_mat_file_loader.py` can also use `scipy` when available for non-HDF5 MAT fallback loading.
