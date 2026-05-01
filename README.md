# PorePythonPeople

Developing a standardized, open Python workflow for nanopore data analysis.

`PorePythonPeople` is a user-facing and developer-friendly toolkit for working with nanopore experiment datasets. Its current strength is a clear two-stage workflow:

1. **Search and save a reproducible experiment subset** using `DataNaviGUI`
2. **Inspect traces and curate event quality** using `EventClassifierGUI`

Unlike proprietary analysis environments, this project is intended to be transparent, customizable, and extensible for research use.

---

## Why use PorePythonPeople?

PorePythonPeople is useful when you need to:

- search large nanopore experiment archives by metadata encoded in names,
- compare experiments across conditions,
- inspect traces and event overlays interactively,
- save reproducible search results for later reuse,
- and build an analysis workflow that can be improved over time rather than locked behind proprietary tooling.

### Key advantages

- **Reproducible experiment selection**: saved query logs make it easier to revisit the same dataset later
- **Open architecture**: code and behavior can be inspected, tested, and extended
- **GUI-first workflow**: supports users who are more comfortable with graphical tools
- **Developer-friendly structure**: reusable subcomponents separate core logic from GUI orchestration
- **Agent-ready documentation system**: repo docs now provide structured context for future coding agents

---

## What the software currently does

PorePythonPeople currently focuses on:

- **Search large databases** of nanopore experiment folders/files using inclusion and exclusion terms
- **Save curated experiment selections** as timestamped query folders containing `search_query.txt`
- **Load MATLAB-derived trace/event files** from selected experiment folders
- **Plot reduced traces and event overlays** in an interactive GUI
- **Navigate events and edit event quality values** for curated analysis

It is best understood as a **data selection and event curation toolkit**, not yet a full automated end-to-end sequencing pipeline.

---

## How to think about the runtime and agent layer

This repository also includes a local orchestrator/runtime layer for agent-assisted development work, but it should be understood in the right proportion.

The intended operating model is:

- **occasional use**, not continuous autonomous operation,
- **scoped feature/refactor/doc-sync work**, not broad unattended repository management,
- execution from a **dedicated local feature branch**,
- and **human-reviewed approvals/promotion** before changes are treated as real repository work.

In other words, the runtime is a **supervised development aid** for the main nanoporethon codebase—not the main product itself.

If you use the runtime, the recommended workflow is:

- run locally,
- keep the sandbox/promotion safeguards enabled,
- review generated edits like normal engineering changes,
- and merge through your usual branch and commit workflow.

For most users, the primary value of this repository is still the nanopore data workflow itself: search, reproducible experiment selection, trace inspection, and event-quality curation.

---

## Repository layout

Primary package location:

- `src/nanoporethon/`

Important documentation:

- `Docs/nanoporethon_textbook.md` — full user + agent handbook
- `Docs/components.md` — architecture and stable component contracts
- `Docs/UseCases.md` — major workflow use cases
- `Docs/UserPersonas.md` — who the software is for
- `Docs/technology_context.md` — scientific and engineering context
- `Docs/agent_context_index.md` — entry point for coding-agent context loading

---

## Installation

### Prerequisites

- Python 3
- `pip`

### Install from the project root

```bash
pip install -e .
```

This installs the package in editable mode so local changes are immediately reflected.

### Current declared dependencies

From `pyproject.toml`, the core dependencies currently include:

- `numpy`
- `matplotlib`
- `h5py`

Testing/development dependencies include:

- `pytest`
- `pytest-cov`

Optional note:

- `scipy` may be used by the MAT-loading layer when available for fallback MAT parsing, but it is not currently declared as a required dependency.

---

## Getting started

### Standard user workflow

1. Open **DataNaviGUI**
2. Select your database directory
3. Select your logs directory
4. Search by inclusion/exclusion terms
5. Manually refine the selection if needed
6. Confirm the selection to create a timestamped query log
7. Open **EventClassifierGUI**
8. Select the logs directory and a saved query
9. Load an experiment folder
10. Inspect traces, navigate events, and edit event quality as needed

---

## Running the GUIs

### Recommended: run as installed modules

From the project root:

```bash
python -m nanoporethon.data_navi_gui
python -m nanoporethon.event_classifier_gui
```

### Alternative: run source files directly

```bash
python src/nanoporethon/data_navi_gui.py
python src/nanoporethon/event_classifier_gui.py
```

---

## Data Navigator GUI

The Data Navigator GUI is the main entry point for selecting data.

### What it does

- browse and save a **database directory**
- browse and save a **logs directory**
- search using comma-separated inclusion and exclusion terms
- perform **cumulative** searches that add to the current selection
- allow manual file/folder selection toggling
- save a confirmed selection into a timestamped query folder

### Key workflow behavior

- Inclusion terms must all match
- Exclusion terms remove matches if any exclusion term is present
- Search results are added to the current selection rather than replacing it
- Clicking an item toggles selection
- Confirming a search writes `search_query.txt` and exits the GUI

### Practical usage guide

1. Launch `DataNaviGUI`
2. Select the database directory containing your experiment folders/files
3. Select the logs directory where search logs will be written
4. Enter inclusion terms, for example:
	 - `2NNN1, streptavidin, p180`
5. Enter exclusion terms if needed, for example:
	 - `control, broken, failed`
6. Click **Search**
7. Click items to add/remove them manually
8. Use **Select All** or **Clear Selection** if helpful
9. Click **Confirm Search** and enter a query name

### Output artifact

The result is a timestamped query folder containing `search_query.txt`, which records:

- source directory
- inclusion criteria
- exclusion criteria
- selected items

Important: this step logs references to the selected data; it does **not** copy the data itself.

---

## Event Classifier GUI

The Event Classifier GUI is used after a saved query already exists.

### What it does

- opens a logs directory containing saved query folders
- loads selected experiment folders from `search_query.txt`
- reads:
	- `reduced.mat`
	- `event.mat`
	- `meta.mat` (optional)
- plots reduced trace data and event overlays
- supports event-by-event navigation
- allows editing and saving event-quality values
- supports sampling-frequency override for x-axis conversion

### Current interactive features

- **Refresh Queries** button
- experiment list loading from saved queries
- interactive matplotlib plotting
- **Classify Events**, **Previous Event**, and **Next Event** buttons
- editable **Quality** field with **Save Quality** action
- keyboard shortcuts:
	- `←` / `p` — previous event
	- `→` / `n` — next event
	- `c` — start classify mode
	- `s` / `Enter` — save quality

### Practical usage guide

1. Launch `EventClassifierGUI`
2. Browse to your saved logs directory
3. Select a query from the dropdown
4. Select an experiment folder from the file list
5. Review the plotted reduced trace and event overlays
6. If needed, override sampling frequency and click **Apply Frequency**
7. Click **Classify Events** to jump into event navigation
8. Move between events and update the quality value as needed
9. Save quality to write the change back to `event.mat`

---

## Data expectations

### Search and query log expectations

Saved search folders are expected to include:

- `search_query.txt`

This file is used later by the Event Classifier, so its format is an important compatibility contract.

### Experiment folder expectations

Each selected experiment folder is expected to contain at least:

- `reduced.mat` — required for plotting
- `event.mat` — required for event overlays and quality editing
- `meta.mat` — optional source of sampling frequency

### Naming convention note

The Data Navigator performs substring matching on folder/file names. In practice, those names often encode metadata such as:

- date
- station
- pore identity
- pore number
- experimental conditions
- voltage
- run/file letter

The more consistent the naming scheme, the more useful the search workflow becomes.

---

## Example use cases

### Compare condition-dependent behavior

You might use Data Navigator to select all experiments matching:

- a pore type,
- an enzyme,
- a voltage,
- and a pH condition,

then exclude unwanted controls and open the final selection in Event Classifier.

### Validate a new enzyme variant

You might:

- search by variant name,
- exclude pilot or failed runs,
- save the curated set,
- and inspect event quality across all selected files.

### Re-open a previously curated set

Because selections are saved as query logs, you can later reopen the same experiment subset rather than rebuilding it manually.

---

## Example data

Example data can be found in:

- `tests/ExampleDataGit`

---

## Documentation map

For a deeper guide, see:

- `Docs/nanoporethon_textbook.md` — full user + agent handbook
- `Docs/components.md` — architecture and component contracts
- `Docs/UseCases.md` — workflow-driven use cases
- `Docs/UserPersonas.md` — user audience context
- `Docs/technology_context.md` — scientific/engineering context
- `Docs/agent_context_index.md` — agent context-loading entry point

---

## Screenshots

<img width="1470" height="917" alt="Screenshot 2026-03-12 at 4 03 30 PM" src="https://github.com/user-attachments/assets/1e9b6b72-5cee-48db-aa7a-eaa6eab9378a" />

<img width="1470" height="918" alt="Screenshot 2026-03-12 at 4 05 02 PM" src="https://github.com/user-attachments/assets/4d21f391-f171-4932-bd69-586ad21a3433" />

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'nanoporethon'`

Install the package from the project root with:

```bash
pip install -e .
```

### No files appear after search

- confirm the database directory is correct
- simplify the inclusion terms
- check whether exclusion terms are too broad
- verify the expected substrings are actually present in names

### Query loads but no experiments appear

- verify the query log references the correct source directory
- verify the referenced experiment folders still exist

### Plotting fails

- verify `reduced.mat` exists
- verify the selected experiment folder contains the expected MAT files
- inspect the GUI log for loading errors

### Events do not appear

- verify `event.mat` exists
- verify event-related arrays are present in the file
- confirm the selected file actually contains events recognized by the loader

### Time axis looks incorrect

- check whether sampling frequency was loaded automatically
- confirm whether downsampling may affect the conversion
- use the manual frequency override if needed

---

## Project intent

PorePythonPeople aims to provide an open, modifiable alternative to opaque nanopore analysis workflows, with emphasis on:

- reproducibility,
- transparency,
- extensibility,
- and shared lab/community development.

The agent/runtime tooling exists to support that goal safely and incrementally. It is intended to help with occasional development tasks under human supervision, not to replace normal engineering judgment or run the repository as an unattended autonomous system.

---

## Contributing

If you want to contribute or extend the project, review the docs in `Docs/` first so your changes stay aligned with the current workflows, contracts, and documentation expectations.

---

## License

See `LICENSE` for license details.

---

## Acknowledgments

This tool was built by the Gundlach Lab with input from collaborators and contributors working to standardize and modernize nanopore analysis workflows in Python.
