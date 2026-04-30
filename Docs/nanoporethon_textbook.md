# nanoporethon Textbook

This textbook is the primary user-facing and agent-facing guide to `nanoporethon`.

It is designed to answer four major questions clearly:

1. **What does nanoporethon do?**
2. **What kinds of nanopore work is it useful for?**
3. **How do the major components and important subcomponents fit together?**
4. **How should a new user actually use the GUIs to analyze data?**

This document complements, but does not replace:

- `Docs/components.md` for architecture and stable contracts
- `Docs/UseCases.md` for workflow-driven examples
- `Docs/UserPersonas.md` for audience needs
- `Docs/technology_context.md` for scientific and engineering context
- `Docs/agent_context_index.md` for cost-aware agent context loading
- `README.md` for high-level project overview

## Table of contents

- [1. What nanoporethon is](#1-what-nanoporethon-is)
- [2. What nanoporethon is used for](#2-what-nanoporethon-is-used-for)
- [3. What nanoporethon does not currently do](#3-what-nanoporethon-does-not-currently-do)
- [4. Who this textbook is for](#4-who-this-textbook-is-for)
- [5. The big-picture workflow](#5-the-big-picture-workflow)
- [6. Important concepts before using the software](#6-important-concepts-before-using-the-software)
- [7. Components and important subcomponents](#7-components-and-important-subcomponents)
- [8. Guide to using DataNaviGUI](#8-guide-to-using-datanavigui)
- [9. Guide to using EventClassifierGUI](#9-guide-to-using-eventclassifiergui)
- [10. Example user scenarios](#10-example-user-scenarios)
- [11. First analysis session walkthrough](#11-first-analysis-session-walkthrough)
- [12. MAT file schema reference](#12-mat-file-schema-reference)
- [13. Troubleshooting guide](#13-troubleshooting-guide)
- [14. How agents should use the documentation system](#14-how-agents-should-use-the-documentation-system)
- [15. True orchestrator runtime for specialist delegation](#15-true-orchestrator-runtime-for-specialist-delegation)
  - [15.11 Operator checklist (stage-by-stage runbook)](#1511-operator-checklist-stage-by-stage-runbook)
  - [15.14 Runtime entrypoint (usable now)](#1514-runtime-entrypoint-usable-now)
  - [15.15 Concrete Tier-2 feature delivery runbook (for daily use)](#1515-concrete-tier-2-feature-delivery-runbook-for-daily-use)
  - [15.16 Per-specialist model routing and context-window guidance](#1516-per-specialist-model-routing-and-context-window-guidance)
- [16. Guidance for developers extending nanoporethon](#16-guidance-for-developers-extending-nanoporethon)
- [17. Quick-start checklist for a new user](#17-quick-start-checklist-for-a-new-user)
- [18. Final summary](#18-final-summary)

---

## 1. What nanoporethon is

`nanoporethon` is a Python-based toolkit for nanopore data analysis built around a practical, reproducible workflow:

**search experiments → save the selected set → inspect traces/events → curate event quality**

It helps researchers work with large collections of nanopore experiments by making it easier to:

- search for experiments by conditions encoded in filenames or folder names,
- save a reproducible record of the selected experiment set,
- load those saved selections later,
- inspect reduced traces and event overlays,
- and edit per-event quality values in a structured way.

In plain language:

- the **Data Navigator GUI** helps you find the right experiments,
- and the **Event Classifier GUI** helps you inspect and annotate them.

---

## 2. What nanoporethon is used for

Based on the repository’s use cases and user personas, nanoporethon is designed for:

- **routine post-experiment review**,
- **comparison of experimental conditions**,
- **trace visualization and event inspection**,
- **curation of event quality labels**,
- **reproducible experiment selection from large archives**,
- and **future extension toward more advanced analysis pipelines**.

Examples of questions it helps answer:

- Which folders match this pore, enzyme, and voltage condition?
- What experiments were run under this pH or temperature?
- Which traces show events worth examining more closely?
- Which events look good, questionable, or bad?
- Can I save this exact subset of experiments and reopen it later?

---

## 3. What nanoporethon does **not** currently do

This software currently focuses on **selection, visualization, and event curation**.

It is **not yet** a complete automated nanopore basecalling or sequencing pipeline that:

- converts raw traces directly into final DNA/RNA/peptide sequence outputs,
- performs full consensus generation automatically,
- or replaces all downstream lab-specific analysis software.

Instead, nanoporethon provides a clear, extensible foundation for:

- finding the right datasets,
- inspecting event-rich traces,
- labeling event quality,
- and preparing data for future downstream analysis.

---

## 4. Who this textbook is for

This textbook is written for several types of readers.

### 4.1 New lab members

- a clear workflow,
- explanation of why steps matter,
- confidence that the software is being used correctly,
- and reduced dependence on trial-and-error.

### 4.2 Experienced nanopore users

- fast selection across many experiments,
- reproducible saved searches,
- trace comparison,
- and precise event review/editing.

### 4.3 Developers and coding agents

For developers and coding agents, this textbook provides:

- the user-facing meaning of the software,
- workflow expectations,
- where the important components fit,
- and how supporting context docs should be used together.

---

## 5. The big-picture workflow

nanoporethon is organized around two main stages.

### Stage 1: Find experiments with `DataNaviGUI`

You begin with a large database directory containing experiment folders or files.

You then:

1. choose the database directory,
2. search using inclusion and exclusion terms,
3. manually adjust the final selection,
4. and save that selection as a query log.

The output of Stage 1 is a timestamped query folder containing `search_query.txt`.

### Stage 2: Inspect experiments with `EventClassifierGUI`

You then:

1. open a saved query,
2. load the experiment folders listed in that query,
3. inspect reduced traces and event overlays,
4. navigate events,
5. and save event-quality edits back into `event.mat`.

This makes the workflow both **interactive** and **reproducible**.

---

## 6. Important concepts before using the software

### 6.1 Database directory

This is the top-level directory containing your experiment folders or files.

In practice, names often encode experiment metadata such as:

- date,
- pore type,
- pore number,
- enzyme,
- buffer,
- temperature,
- voltage,
- and other conditions.

The Data Navigator performs **substring-based matching** on these names.

### 6.2 Inclusion and exclusion terms

- **Inclusion terms**: an entry must contain **all** of them to match.
- **Exclusion terms**: an entry is removed if it contains **any** of them.

This makes the search behavior simple and predictable.

### 6.3 Query log

When you confirm a search, nanoporethon creates a query folder containing `search_query.txt`.

That log records:

- the source directory,
- the inclusion terms,
- the exclusion terms,
- and the selected files/directories.

Important: nanoporethon **does not copy the selected data** at this step. It saves a **reference log**, not a duplicate dataset.

### 6.4 Experiment folder expectations

For event inspection, a selected experiment folder is expected to contain:

- `reduced.mat` — required for plotting reduced trace data
- `event.mat` — required for event overlays and quality editing
- `meta.mat` — optional; may provide sampling frequency

### 6.5 Event quality

The Event Classifier allows the user to edit the `quality` values for events stored in `event.mat`.

This means the GUI is not only a viewer; it is also a curation tool.

---

## 7. Components and important subcomponents

This section explains the practical job of each major component.

For stable component contracts, see `Docs/components.md`.

### 7.1 `DataNaviGUI`

- **File**: `src/nanoporethon/data_navi_gui.py`
- **Role**: user-facing GUI for experiment search and selection

What it does:

- chooses the database directory,
- chooses the logs directory,
- accepts inclusion and exclusion terms,
- shows available files,
- allows manual selection and deselection,
- and confirms the final selection into a saved query log.

Important supporting subcomponents:

- `subcomponent_2_data_navigator.py`
  - filtering engine for inclusion/exclusion matching
- `subcomponent_3_data_navi_sub_directory.py`
  - writes the timestamped query folder and `search_query.txt`
- `subcomponent_4_config_manager.py`
  - stores saved directory preferences
- `subcomponent_5_directory_utilities.py`
  - shared directory browsing and validation helpers

### 7.2 `EventClassifierGUI`

- **File**: `src/nanoporethon/event_classifier_gui.py`
- **Role**: user-facing GUI for trace inspection and event-quality editing

What it does:

- loads saved queries,
- populates experiment selections from `search_query.txt`,
- loads `reduced.mat`, `event.mat`, and optionally `meta.mat`,
- plots traces and overlays event boundaries,
- supports event-by-event navigation,
- and saves edited quality values back into `event.mat`.

Important supporting subcomponents:

- `subcomponent_4_config_manager.py`
  - persistent path/config behavior
- `subcomponent_5_directory_utilities.py`
  - directory browsing helper
- `subcomponent_6_search_log_utilities.py`
  - query discovery and `search_query.txt` parsing
- `subcomponent_7_mat_file_loader.py`
  - MAT/HDF5 loading layer for reduced/event/meta data

### 7.3 Search filter engine

- **File**: `src/nanoporethon/subcomponent_2_data_navigator.py`

Behavior summary:

- matches directory entries by string content,
- requires all inclusion terms,
- rejects any exclusion term matches,
- returns matching names.

### 7.4 Query log writer

- **File**: `src/nanoporethon/subcomponent_3_data_navi_sub_directory.py`

Behavior summary:

- creates a timestamped query folder,
- writes a `search_query.txt` log,
- records criteria and selected items,
- preserves the markers required by the search log parser.

### 7.5 Search log parser

- **File**: `src/nanoporethon/subcomponent_6_search_log_utilities.py`

Behavior summary:

- finds saved query folders,
- parses `search_query.txt`,
- returns the original source directory and selected item list.

### 7.6 MAT file loading layer

- **File**: `src/nanoporethon/subcomponent_7_mat_file_loader.py`

Behavior summary:

- loads reduced trace arrays,
- loads event-related arrays,
- extracts sampling frequency when possible,
- supports fallback behavior for different MAT-file variants.

### 7.7 Config and directory helpers

- `subcomponent_4_config_manager.py`
- `subcomponent_5_directory_utilities.py`

These make the GUIs easier to use by persisting paths and centralizing directory selection behavior.

---

## 8. Guide to using `DataNaviGUI`

This section is written to help a new user move from “I have data” to “I have a saved experiment selection.”

### 8.1 What the Data Navigator is for

Use `DataNaviGUI` when you want to search a large repository and build a curated subset of experiments for later analysis.

### 8.2 What to prepare before opening it

Before starting:

- know where your database directory lives,
- know where you want saved query logs to go,
- and think of a few reliable substrings that identify your target experiments.

Examples of useful substrings:

- pore name,
- pore number,
- enzyme name,
- temperature,
- voltage,
- buffer concentration,
- pH,
- date fragments,
- orientation labels.

### 8.2.1 Filename anatomy and search-pattern guide

Many nanoporethon searches work best when users understand how information is encoded in experiment names.

Here are two real example folders from `tests/ExampleDataGit`:

- `240801e_2NNN1_t1&500mM500mM&ph7pt5&forwards&streptavidin5uM&anchorT5uM_p210l`
- `241004e_2NNN1_t1&500mM500mM&ph7pt5&forwards&streptavidin5uM&anchorT20uM&thermistor&tset22&Resistance34pt4kOhm_p150g`

These names are not parsed by a strict schema in code, but they usually contain reusable metadata fragments such as:

- **date**: `240801`, `241004`
- **station/run letter**: `e`
- **pore identity**: `2NNN1`
- **condition block**: strings separated by `&`
- **voltage fragment**: `p210`, `p150`
- **final run/file letter**: `l`, `g`

Recommended search strategy:

1. Start with one or two highly distinctive inclusion terms.
2. Add additional inclusion terms only when you want to narrow the set further.
3. Use exclusion terms to remove known unwanted categories.
4. Manually inspect and curate the final list before confirming the search.

Example search patterns that are likely to be useful:

- **By pore**: `2NNN1`
- **By pH**: `ph7pt5`
- **By direction/orientation**: `forwards`
- **By enzyme or binding partner**: `streptavidin5uM`
- **By anchor concentration**: `anchorT5uM`, `anchorT20uM`
- **By temperature setting**: `tset22`
- **By voltage**: `p210`, `p150`
- **By date**: `240801`, `241004`

Example combinations:

- To find streptavidin runs at pH 7.5:
  - inclusion: `streptavidin5uM, ph7pt5`
- To find forward runs on pore `2NNN1` at `p150`:
  - inclusion: `2NNN1, forwards, p150`
- To compare anchor concentrations while keeping the same pore and pH:
  - inclusion: `2NNN1, ph7pt5, streptavidin5uM`
  - then manually compare `anchorT5uM` and `anchorT20uM`

General tip: because the search engine uses substring matching, shorter terms are sometimes useful for broad discovery, while longer terms are better for precision.

### 8.3 How to launch it

A typical launch command is:

- `python -m nanoporethon.data_navi_gui`

### 8.4 What you will see

The GUI includes:

- a **Database Directory** field,
- a **Logs Directory** field,
- an **Inclusion Terms** box,
- an **Exclusion Terms** box,
- a file list,
- buttons for **Search**, **Clear Selection**, **Select All**, and **Confirm Search**,
- and a log window.

### 8.5 Step-by-step workflow

#### Step 1: Choose the database directory

Click **Browse** next to **Database Directory** and select the folder containing your experiment folders or files.

nanoporethon will:

- save that path for future sessions,
- load the directory contents,
- and display the entries in the file list.

#### Step 2: Choose the logs directory

Click **Browse** next to **Logs Directory** and choose the folder where confirmed searches should be saved.

#### Step 3: Enter inclusion terms

Type a comma-separated list such as:

- `2NNN1, streptavidin, p180`

This means an entry must contain **all three** substrings.

#### Step 4: Enter exclusion terms

Type any unwanted filters, for example:

- `control, bad, broken`

If a filename contains **any** exclusion term, it will be rejected.

#### Step 5: Click **Search**

The GUI runs the filter engine and **adds** matches to the current selection.

Important: searches are **cumulative**. Repeated searches can grow a curated set instead of replacing it.

#### Step 6: Manually adjust the selection

Click an item in the list to toggle its selected state.

Selected items appear first and are marked with a checkmark.

This is helpful when:

- a search is close but not perfect,
- or a few folders should be added/removed manually.

#### Step 7: Use quick actions if needed

- **Select All**: select all available files
- **Clear Selection**: remove all selected files

#### Step 8: Confirm the search

Click **Confirm Search**.

You will be prompted to name the query.

After confirmation, nanoporethon writes a timestamped query folder with `search_query.txt` and exits the GUI.

### 8.6 What gets saved

The saved query log contains:

- source directory,
- inclusion criteria,
- exclusion criteria,
- selected files/directories.

This saved query is later consumed by the Event Classifier.

### 8.7 Best practices for DataNaviGUI

- Use short, meaningful query names.
- Prefer stable metadata substrings over vague terms.
- Keep logs in a dedicated logs directory.
- Use cumulative search intentionally; clear selection when starting over.

---

## 9. Guide to using `EventClassifierGUI`

### 9.1 What the Event Classifier is for

Use `EventClassifierGUI` after you have already created a saved query with Data Navigator.

Its job is to reopen that curated selection and support trace and event review.

### 9.2 What to prepare before opening it

Before starting:

- make sure a search log already exists,
- make sure the selected experiment folders still exist,
- and make sure those folders contain the required MAT files.

### 9.3 How to launch it

A typical launch command is:

- `python -m nanoporethon.event_classifier_gui`

### 9.4 What you will see

The GUI includes:

- a **Search Logs Directory** selector,
- a **Search Query** dropdown,
- a **Files in Query** list,
- a plot area,
- a sampling-frequency override field,
- event navigation buttons,
- an event quality field,
- and a log window.

### 9.5 Step-by-step workflow

#### Step 1: Choose the search logs directory

Click **Browse** and select the folder that contains the saved query directories.

Use **Refresh Queries** if needed.

#### Step 2: Select a saved query

Choose a query from the dropdown.

nanoporethon will:

- read `search_query.txt`,
- recover the original source directory,
- and populate the file list with the selected experiment folders.

#### Step 3: Select an experiment folder

Click an entry in the file list.

The GUI attempts to load:

- `reduced.mat`
- `event.mat`
- `meta.mat` (optional)

If successful, the reduced trace is plotted and event overlays are drawn.

#### Step 4: Review the plot

The plot may show:

- reduced current trace,
- event boundaries,
- event numbers,
- quality-based shading,
- local IOS reference information.

The embedded matplotlib controls allow zooming and panning.

#### Step 5: Check or override the sampling frequency

If nanoporethon finds sampling frequency in `meta.mat` or `event.mat`, it can convert points to time.

If needed, enter a manual value in **Sampling Frequency (Hz, optional override)** and click **Apply Frequency**.

#### Step 6: Start event classification mode

Click **Classify Events** to jump to the first event and enter event-navigation workflow.

#### Step 7: Navigate between events

You can use:

- **Previous Event**
- **Next Event**

Or keyboard shortcuts:

- `←` or `p` for previous
- `→` or `n` for next
- `c` to begin classify mode
- `s` or `Enter` to save quality

#### Step 8: Edit event quality

Enter a numeric value in the **Quality** field and click **Save Quality**.

This writes the edited quality value back into `event.mat` for the currently selected event.

### 9.6 Best practices for EventClassifierGUI

- Confirm your saved query points to the experiments you expect.
- Check whether the x-axis is in points or seconds before interpreting timing.
- Save quality values intentionally because they affect downstream curation.
- Use the log window whenever loading or plotting fails.

---

## 10. Example user scenarios

### 10.1 Beginner user comparing a few conditions

Someone like Larry or Hannah may:

1. open DataNaviGUI,
2. search for a pore and enzyme,
3. exclude unwanted controls,
4. save the selection,
5. open EventClassifierGUI,
6. and inspect traces one by one.

### 10.2 Advanced user screening many conditions

Someone like Dave, Angela, or Tina may:

1. use cumulative searches,
2. build a larger curated query set,
3. compare traces across conditions,
4. and label event quality for downstream modeling or export.

### 10.3 Collaborator new to lab naming conventions

Someone like Grace or Maya may use this textbook plus `Docs/UseCases.md` to understand:

- what metadata is encoded in names,
- which search terms are likely to work,
- and how saved queries improve reproducibility.

---

## 11. First analysis session walkthrough

This walkthrough is intended for a brand-new user who wants one concrete example from search to event review.

### 11.1 Goal

Use the example dataset to:

1. create a saved search for streptavidin experiments,
2. open that search in Event Classifier,
3. load one experiment folder,
4. and inspect the plotted trace/events.

### 11.2 Recommended practice data

Use the folders in:

- `tests/ExampleDataGit`

The example folders currently include:

- `240801e_2NNN1_t1&500mM500mM&ph7pt5&forwards&streptavidin5uM&anchorT5uM_p210l`
- `241004e_2NNN1_t1&500mM500mM&ph7pt5&forwards&streptavidin5uM&anchorT20uM&thermistor&tset22&Resistance34pt4kOhm_p150g`

### 11.3 Part A: Build a search in DataNaviGUI

1. Launch `DataNaviGUI`.
2. Set the **Database Directory** to `tests/ExampleDataGit`.
3. Set the **Logs Directory** to a writable folder, for example `tests/Searches` or another dedicated logs folder.
4. In the inclusion box, try:
  - `2NNN1, streptavidin5uM`
5. Leave the exclusion box empty for the first pass.
6. Click **Search**.
7. Confirm that the two example experiment folders appear in the selection.
8. Optionally click one entry to deselect it if you want to inspect only one folder at first.
9. Click **Confirm Search**.
10. Enter a query name such as:
  - `StreptavidinIntro`

### 11.4 Part B: Understand what just got created

After confirmation, nanoporethon writes a query folder named like:

- `StreptavidinIntro_YYYYMMDD_HH:MM:SS`

Inside that folder is `search_query.txt`.

Its content follows a structure like:

- `DataNavi Search Query Log`
- `Timestamp: ...`
- `Source Directory: ...`
- `Destination Directory: ...`
- `Search Criteria:`
- `Inclusion Filter (Array_1):`
- `Exclusion Filter (Array_2):`
- `Selected Files/Directories:`

This file is what Event Classifier uses to recover your saved experiment selection.

For reference, the repository already contains example saved-query folders such as:

- `DEMO_20260305_14:53:08`
- `Streptavidin22C_20260305_14:01:16`

### 11.5 Part C: Open the search in EventClassifierGUI

1. Launch `EventClassifierGUI`.
2. Browse to the logs directory where you just created the query.
3. Click **Refresh Queries** if the query is not immediately listed.
4. Select the query you just created.
5. Click one experiment folder in the file list.

If loading succeeds, nanoporethon will attempt to:

- load `reduced.mat`,
- load `event.mat`,
- optionally use `meta.mat` for sampling frequency,
- plot the reduced trace,
- and overlay event boundaries when event data is available.

### 11.6 Part D: Try event navigation

1. Click **Classify Events**.
2. Move through events with:
  - **Previous Event** / **Next Event**
  - or keyboard shortcuts `p` / `n` and left/right arrow keys
3. If the quality field is populated, try changing it to a numeric value.
4. Click **Save Quality**.

This writes the updated quality value back to `event.mat` for the selected event.

### 11.7 What success looks like

By the end of this walkthrough, a new user should be able to:

- identify useful search substrings,
- create a saved query,
- understand what `search_query.txt` is for,
- load an experiment in Event Classifier,
- see a plotted trace,
- and navigate/save event quality.

---

## 12. MAT file schema reference

This section is especially useful for agents and developers, but it also helps advanced users understand what the GUIs are expecting.

### 12.1 `reduced.mat`

Primary loader:

- `subcomponent_7_mat_file_loader.load_reduced_mat(path)`

Expected structure:

- top-level group: `reduced`
- required datasets inside `reduced`:
  - `data`
  - `pt`
- optional downsample datasets or keys:
  - `downsampleFactor`
  - `downsample`
  - `dwnspl`
  - `ds`
  - `dsFactor`

Behavior notes:

- If `reduced.mat` is missing, loading fails for plotting.
- If `data` or `pt` is missing, `load_reduced_mat` returns `(None, None, None)`.
- If no downsample field is found, the loader defaults to `1.0`.

### 12.2 `event.mat`

Primary loader:

- `subcomponent_7_mat_file_loader.load_event_data(path)`

Expected event-related vectors include:

- `eventnum`
- `eventStartPt`
- `eventEndPt`
- `eventStartNdx`
- `eventEndNdx`
- `quality`
- `localIOS`

Behavior notes:

- The Event Classifier prefers `eventStartPt` / `eventEndPt` when available.
- If those are unavailable, it falls back to `eventStartNdx` / `eventEndNdx`.
- If `quality` exists, the GUI can display and edit current event quality.
- If `event.mat` is missing, the trace can still be plotted from `reduced.mat`, but event overlays and quality editing will not be available.

### 12.3 Sampling-frequency fields

Sampling frequency can be read from either `event.mat` or `meta.mat`.

Candidate field names include:

- `fsamp`
- `Fsamp`
- `f_samp`
- `samplingFrequency`
- `sampleRate`
- `fs`
- `Fs`

Behavior notes:

- Event Classifier prefers `meta.mat` when a valid positive sampling frequency is available there.
- If not found in `meta.mat`, it may use `event.mat`.
- If neither file provides valid sampling frequency, the GUI can still plot the trace, but the x-axis may remain in points rather than seconds.
- Users can manually override sampling frequency in the GUI.

### 12.4 MAT format compatibility

The loader supports two broad pathways:

- **HDF5-backed MATLAB v7.3 files** via `h5py`
- **older non-HDF5 MAT files** via `scipy.io.loadmat` when `scipy` is available

Agent/developer note:

- backward compatibility in this loader matters,
- field matching is deliberately tolerant,
- and normalized/case-insensitive lookup is part of the current behavior.

---

## 13. Troubleshooting guide

### Problem: No files appear after search

Check the following:

- Is the database directory correct?
- Are the inclusion terms too strict?
- Is an exclusion term removing everything?
- Are you using the right substrings and capitalization?

### Problem: Query loads but no usable experiments appear

Check the following:

- Does the query contain the expected items?
- Do those folders still exist under the source directory?
- Was the query created from the correct database?

### Problem: Plot does not appear

Check the following:

- Does the experiment folder contain `reduced.mat`?
- Is the file readable in a supported format?
- Does the log window report a MAT-loading error?

### Problem: Events do not appear

Check the following:

- Does the experiment folder contain `event.mat`?
- Does `event.mat` contain recognizable event boundary fields?
- Was the file loaded successfully but found to contain no events?

### Problem: Time axis looks wrong

Check the following:

- Was sampling frequency loaded from `meta.mat` or `event.mat`?
- Was the data downsampled?
- Should you use a manual frequency override?

### Problem: Saving quality does not work

Check the following:

- Is `event.mat` present?
- Does it contain a writable `quality` dataset?
- Is the entered quality value numeric?

---

## 14. How agents should use the documentation system

This section is important for future coding work.

### 14.1 Minimum agent reading order

Agents should begin with:

1. `Docs/agent_context_index.md`
2. `Docs/components.md`

Then add:

3. `Docs/UseCases.md`
4. `Docs/UserPersonas.md`
5. `Docs/technology_context.md`
6. this textbook

Then read only the relevant source files and tests.

### 14.2 Why this matters

This ordering helps agents:

- stay architecture-aware,
- avoid inventing workflows that conflict with the codebase,
- preserve data contracts such as `search_query.txt`,
- and understand who the software is for.

### 14.3 Which file answers which question

- `Docs/components.md`
  - “What are the stable components and contracts?”
- `Docs/UseCases.md`
  - “What real tasks should this software support?”
- `Docs/UserPersonas.md`
  - “Who is using this, and how technical are they?”
- `Docs/technology_context.md`
  - “What scientific and engineering assumptions matter?”
- `Docs/nanoporethon_textbook.md`
  - “How does a user actually operate the system?”

---

## 15. True orchestrator runtime for specialist delegation

This section documents the execution-plumbing model for users and developers who want the orchestrator to **actually delegate** work across specialist roles.

### 15.1 Why this runtime exists

The project supports specialist agent definitions (feature, refactor, doc sync), but chat-mode execution can still be constrained by host/runtime behavior.

A true orchestrator runtime is designed to solve this by making delegation explicit and executable:

- one request enters through the orchestrator,
- the runtime stages work,
- each stage is assigned to a specialist context,
- and stage gates control progression.

### 15.2 Runtime artifact locations

Current runtime-planning artifacts are in:

- `runtime/policies.yaml`
- `runtime/stage_templates.yaml`
- `runtime/orchestrator.py`
- `runtime/planner.py`
- `runtime/executor.py`
- `runtime/gates.py`
- `runtime/state.py`
- `runtime/adapters/ollama.py`
- `runtime/schemas/handoff_packet.schema.json`
- `runtime/schemas/stage_result.schema.json`
- `runtime/schemas/gate_result.schema.json`
- `runtime/schemas/run_state.schema.json`

Run-time execution artifacts are expected under:

- `.nanopore-runtime/runs/<run_id>/run.json`
- `.nanopore-runtime/runs/<run_id>/events.jsonl`
- `.nanopore-runtime/runs/<run_id>/artifacts/`

### 15.3 Delegation model (stage ownership)

Default stage sequence:

1. `triage_plan` — orchestrator
2. `implement` — feature builder specialist
3. `verify` — verifier specialist
4. `refactor_or_docsync` — orchestrator routing decision
5. `refactor` (conditional) — refactor specialist
6. `verify_after_refactor` (conditional) — verifier specialist
7. `doc_sync` — doc sync specialist
8. `memory_sync` — memory specialist
9. `closeout` — orchestrator

The routing intent is:

- if quality signals indicate structural cleanup is needed, run refactor path,
- otherwise proceed directly to doc sync.

### 15.4 Runtime architecture (lightweight)

The lightweight runtime is expected to implement these core roles:

- **Request ingestor**: captures user request and starts a `run_id`
- **Planner**: derives stage plan and acceptance criteria
- **Specialist executor**: runs specialist contexts with bounded prompts/tools
- **Gate engine**: enforces pass/fail/waived stage criteria
- **State store**: tracks run status and stage history
- **Repo adapter**: applies edits, runs checks, records outputs
- **Memory updater**: writes concise verified learnings to repo memory

### 15.5 Stage gates and quality controls

The runtime policy defines mandatory checks at stage boundaries.

Examples:

- planning gates: complexity classification + explicit acceptance criteria
- implementation gates: non-empty changeset or justified no-op
- verification gates: tests pass + no new errors + coverage policy
- documentation gates: component/textbook/log synchronization when required
- memory gates: repository memory update completed

Waivers are allowed only when explicitly recorded with:

- waiver id,
- gate id,
- reason,
- approver,
- scope.

### 15.6 Handoff contract between specialists

Each stage hands off structured output (schema-validated) rather than informal prose.

Core contract types:

- **HandoffPacket**
  - run id, from stage, to stage, summary, acceptance criteria, artifacts, quality signals
- **StageResult**
  - stage status, changed files, checks run, artifacts, timing
- **GateResult**
  - gate pass/fail/waived with evidence and optional waiver details
- **RunState**
  - resumable state for full run lifecycle

### 15.7 Repository memory update policy

The runtime should persist concise, verified lessons for future agent performance.

Current policy targets:

- `memories/repo/testing.md`
- `memories/repo/orchestrator-runtime.md`

Memory entries should be:

- short,
- factual,
- reproducible,
- and free of speculative claims.

### 15.8 Practical benefits of true runtime orchestration

Compared with convention-only routing, this runtime model provides:

- explicit specialist delegation,
- deterministic stage gating,
- reproducible run artifacts,
- cleaner traceability,
- and stronger long-term agent context building.

### 15.9 Will this always be done once true orchestrator runtime is running?

Usually yes, **if** the runtime is executed with its default gate policy and no waivers.

In practical terms, automatic end-to-end behavior is reliable when all of the following are true:

1. the request enters through the orchestrator runtime,
2. stage graph is enabled as defined in runtime policy,
3. gate checks are active,
4. no manual bypass/waiver skips required stages,
5. runtime has permission to edit files and run checks.

Important caveat:

- If a gate is waived, policies are changed, or execution is interrupted, the full sequence may not complete automatically.

So the correct guarantee is:

- **default behavior should be automatic and consistent**,
- **absolute behavior depends on policy settings, waivers, and runtime health**.

### 15.10 How users should invoke this workflow

For best results, user prompts should request full orchestration explicitly, for example:

- implement feature,
- run verification gates,
- refactor if required by quality signals,
- synchronize docs,
- update memory and request log,
- close out with run evidence.

This reduces ambiguity and makes pass/fail gating objective.

### 15.11 Operator checklist (stage-by-stage runbook)

Use this as a fast operational reference during a live runtime execution.

| Stage | Expected input | Expected output | Gate to pass | If gate fails |
|---|---|---|---|---|
| `triage_plan` | User request + startup docs (`agent_context_index`, `components`, relevant context) | Complexity class, staged plan, acceptance criteria, impacted components | Plan gate | Ask targeted clarification questions; tighten scope and acceptance criteria before proceeding |
| `implement` | Approved plan + acceptance criteria + impacted components | Code/test changes or justified no-op, changed file list, implementation summary | Build/implementation gate | Fix compilation/import issues, remove unresolved conflicts, or document no-op rationale |
| `verify` | Implementation changes + acceptance criteria | Test results, coverage evidence, quality signals (`require_refactor` true/false) | Verification gate | Resolve failing tests/errors first; if coverage policy fails, add relevant tests or request explicit waiver |
| `refactor` (conditional) | Quality signal requiring structural cleanup | Safer structure with preserved behavior, refactor summary | Post-refactor verification gate | Revert risky edits, reduce refactor scope, and re-run targeted verification |
| `doc_sync` | Verified behavior summary + contract/workflow change flags | Updated docs (`components`, textbook as needed) + request-log entry | Documentation gate | Patch missing docs, align with actual merged behavior, then re-check |
| `memory_sync` | Final run summary + verification evidence + pitfalls | Concise repo-memory updates (verified facts only) | Memory gate | Remove speculative notes, rewrite as short reproducible bullets, re-run memory gate |
| `closeout` | All prior stages passed or properly waived | Final run summary + artifact bundle + stage timeline | Closeout completeness check | Reopen missing stage artifact(s), regenerate summary from run state |

### 15.12 Operator pre-flight checklist

Before launching a run, verify:

- runtime policy file is present and readable (`runtime/policies.yaml`),
- stage templates and schemas are present,
- test environment is available,
- approved waiver operator is configured correctly,
- runtime has write permissions for source/docs/memory targets,
- waiver policy/approver path is defined,
- run artifact directory can be created (`.nanopore-runtime/runs/<run_id>/`).

### 15.13 Operator post-run checklist

After completion, verify:

- all required stages have `success` or explicit `waived` status,
- gate results include evidence,
- docs were synchronized when required,
- request log row was appended,
- repo memory update was written,
- run artifacts are complete and timestamped.

### 15.14 Runtime entrypoint (usable now)

The Tier-2 runtime now executes the policy-defined graph end-to-end:

- `triage_plan` → `implement` → `verify` → `refactor_or_docsync` →
  - `refactor` → `verify_after_refactor` (when required), or
  - `doc_sync` directly (when refactor is not required),
- then `memory_sync` → `closeout`

You can run it with:

- `python -m runtime.orchestrator --request "<your request>"`

Optional CLI output formatting:

- `--output json` (default)
- `--output summary` (human-readable run summary including context budget usage)
- `--output both` (summary first, then full JSON)

Live task-progress indicator:

- runtime now prints a compact one-line traffic-light status per stage while the run is executing,
- default is enabled via `--live-progress` (disable with `--no-live-progress`),
- indicator format includes stage id, estimated context usage, utilization %, gate pass/fail, and whether payload compaction occurred.

Operator approval mode:

- pass `--approval-mode per_stage` to pause between completed stages before the next stage begins,
- the runtime writes the handoff artifact first so the operator has something concrete to review,
- if the operator rejects or quits, the run is marked `blocked`/`cancelled` with `pending_approval` persisted in `run.json`,
- resuming with `--resume-run-id ... --resume-choice resume_from_last_completed` re-opens that pending transition instead of silently skipping it.

Current behavior:

- creates a new `run_id`,
- creates a sandbox copy of the repository under the run artifacts before implementation/doc-sync actions,
- writes `.nanopore-runtime/runs/<run_id>/run.json`,
- appends stage/gate events to `.nanopore-runtime/runs/<run_id>/events.jsonl`,
- emits stage-to-stage handoff artifacts in `.nanopore-runtime/runs/<run_id>/artifacts/handoffs/`,
- records approved waivers in `.nanopore-runtime/runs/<run_id>/artifacts/waivers.jsonl`,
- applies stage-specific context budgets from policy and compacts oversized payloads automatically,
- records per-stage context utilization in stage results and aggregate context metrics in `run.json`,
- writes repository memory updates directly into `memories/repo/` when memory sync runs,
- validates `HandoffPacket`, `StageResult`, `GateResult`, and `RunState` against runtime schemas,
- halts early if a required gate fails.

Operator-resume behavior:

- if a run is resumed, the operator must explicitly choose the resume mode,
- supported current modes are restarting from the beginning or resuming from the last completed stage.

Model-provider behavior:

- when `model_provider.adapter: ollama`, specialist stages load their `prompt_file`/`prompt_inline` and call local Ollama,
- specialists can optionally define `specialists.<owner>.model_provider` to override model/base_url per agent while inheriting unspecified global provider fields,
- when no adapter is configured, executor remains deterministic and local-test friendly.

Testing note:

- fixture-based runtime integration tests now live inside `tests/fixtures/runtime_fixture_repo/`,
- this keeps Tier-2 tests safely inside the main repository test tree.

### 15.15 Concrete Tier-2 feature delivery runbook (for daily use)

This is the practical, copyable workflow for adding new nanoporethon features with Tier-2 runtime orchestration.

#### 15.15.1 What this runbook is for

Use this runbook when you want to:

- add or change a feature,
- run specialist handoff stages in order,
- keep docs/tests/memory synchronized,
- and keep work auditable through run artifacts.

#### 15.15.2 Default operating mode for this repository

Current recommended defaults:

- sandbox-copy execution for implementation/doc-sync actions,
- waiver approval limited to the configured operator,
- explicit operator choice on resume,
- direct memory writes to `memories/repo/`,
- fixture-based integration tests under `tests/`.

#### 15.15.3 Pre-run checklist (2-minute version)

Before running a feature request:

1. Confirm `runtime/policies.yaml` is present.
2. Confirm runtime tests pass at least once in the current branch.
3. Confirm target feature scope is specific enough to test.
4. Confirm waiver approver identity is correct in policy.
5. Confirm `memories/repo/` exists and is writable.

#### 15.15.4 Standard run command

Use:

- `python -m runtime.orchestrator --request "<clear feature request>"`

Example request text (recommended style):

- "Add <feature>. Update nearest tests. If behavior/contracts change, sync components and textbook. Run verification gates and write run artifacts."

#### 15.15.5 Stage-by-stage user expectations

What you should expect:

1. **`triage_plan`**
  - outputs complexity, acceptance criteria, impacted components.
2. **`implement`**
  - applies changes in sandbox copy; records changed files.
3. **`verify`**
  - runs verification checks from policy.
4. **`refactor_or_docsync`**
  - routes by quality signal.
5. **`refactor` + `verify_after_refactor`** (when required)
  - structural cleanup and re-verification.
6. **`doc_sync`**
  - syncs user/architecture documentation expectations.
7. **`memory_sync`**
  - writes concise verified bullets to `memories/repo/`.
8. **`closeout`**
  - final run summary and artifact completeness.

#### 15.15.6 If a gate fails

Follow this order:

1. Fix the underlying issue and re-run.
2. If unavoidable, apply waiver only with approved operator.
3. Ensure waiver is recorded in run artifacts.
4. Re-check downstream stages before closing run.

#### 15.15.6a If approval mode is enabled

When running with `--approval-mode per_stage`, expect an explicit prompt before each stage transition.

Recommended operator behavior:

1. Review the just-written handoff artifact and `run.json`.
2. Approve when the stage output is good enough to continue.
3. Reject when you want to stop and inspect or patch the workflow.
4. Resume later with `--resume-run-id <run_id> --resume-choice resume_from_last_completed` once you are ready to continue.

This is the current terminal-runtime equivalent of a “keep changes and continue?” checkpoint.

#### 15.15.7 If execution is interrupted

Resume requires explicit operator choice.

Use one of:

- `--resume-choice restart_from_beginning`
- `--resume-choice resume_from_last_completed`

Recommended practice:

- use `resume_from_last_completed` only when artifact integrity is intact,
- otherwise restart cleanly.

#### 15.15.8 Where to inspect results

For run `<run_id>`, inspect:

- `.nanopore-runtime/runs/<run_id>/run.json`
- `.nanopore-runtime/runs/<run_id>/events.jsonl`
- `.nanopore-runtime/runs/<run_id>/artifacts/handoffs/`
- `.nanopore-runtime/runs/<run_id>/artifacts/waivers.jsonl` (if waivers used)

#### 15.15.9 Promotion checklist before merge

Do not promote unless all are true:

- required stages are `success` (or explicit approved `waived`),
- verification evidence exists,
- docs are synchronized if behavior/workflow changed,
- request log entry is appended,
- memory updates are present and factual,
- run artifacts are complete.

#### 15.15.10 Feature request template for users

Use this short template when asking for Tier-2 feature work:

- **Goal**: <what should change>
- **Why**: <user/lab value>
- **Acceptance checks**: <tests, outputs, edge cases>
- **Constraints**: <must not break X>
- **Docs impact**: <components/textbook expected or not>

This improves stage quality and reduces rework.

### 15.16 Per-specialist model routing and context-window guidance

This section defines the practical model map for local Tier-2 runs in this repository.

#### 15.16.1 Concrete model map (current recommended default)

- Global default model provider:
  - `qwen2.5-coder:14b`
- Specialist overrides:
  - `doc_sync` → `qwen2.5:7b`
  - `memory_sync` → `qwen2.5:7b`

Rationale:

- implementation/refactor/verification tasks keep stronger coding depth,
- documentation/memory summarization tasks use a smaller and faster local model,
- orchestrator and routing remain on the stronger global model unless explicitly overridden.

#### 15.16.2 Context-window estimates by specialist (operational guidance)

These values are practical planning estimates for local operation, not strict guarantees.

| Specialist | Typical work | Recommended effective context window | Runtime stage budget reference |
|---|---|---:|---:|
| `orchestrator` | triage, route decisions, closeout | 24k–32k | `triage_plan: 4000`, `refactor_or_docsync: 3000`, `closeout: 2000` |
| `feature_builder` | new/changed code | 32k–48k | `implement: 8000` |
| `verifier` | quality checks + test interpretation | 24k–32k | `verify: 6000`, `verify_after_refactor: 6000` |
| `refactor` | structural cleanup | 32k–48k | `refactor: 6000` |
| `doc_sync` | contract + workflow docs updates | 8k–16k | `doc_sync: 4000` |
| `memory_sync` | concise, factual memory notes | 8k–12k | `memory_sync: 2000` |

Important: the runtime stage budgets are intentional working limits and should usually be treated as the authoritative operating bound, even when model context capacity is larger.

#### 15.16.3 Pre-assigned context by specialist (what to load first)

Use this minimal context allocation to keep signal high and context growth controlled:

- `orchestrator`:
  - `Docs/agent_context_index.md`
  - `Docs/components.md`
  - `Docs/technology_context.md`
  - `Docs/nanoporethon_textbook.md` Section 15
- `feature_builder`:
  - Tier-0 docs, nearest source files, nearest tests
- `verifier`:
  - changed files + nearest tests + `runtime/policies.yaml` gate section
- `refactor`:
  - changed module(s), references/call sites, preservation tests
- `doc_sync`:
  - `Docs/components.md`, relevant textbook subsection(s), verified behavior summary
- `memory_sync`:
  - run artifacts (`run.json`, stage payload summaries), target memory files, request-log context

#### 15.16.4 Tuning order when context pressure rises

When you repeatedly observe high utilization or frequent compaction:

1. reduce unnecessary context inputs for that specialist,
2. tighten stage payload shape,
3. increase the specialist stage budget only if needed,
4. increase model context allocation only after policy-level tuning is insufficient.

---

## 16. Guidance for developers extending nanoporethon

When modifying or extending the codebase:

- keep GUI files orchestration-focused,
- prefer reusable logic in subcomponents,
- preserve query-log compatibility,
- preserve MAT-loading compatibility,
- update user documentation when workflows change,
- and append a request-log entry for meaningful changes.

If legacy MATLAB behavior conflicts with validated Python contracts/tests, Python is authoritative.

---

## 17. Quick-start checklist for a new user

Before your first real analysis session:

- [ ] Install the package and dependencies
- [ ] Identify your database directory
- [ ] Choose a logs directory
- [ ] Review typical filename substrings used in your lab
- [ ] Create a first search in DataNaviGUI
- [ ] Confirm that `search_query.txt` looks sensible
- [ ] Open the saved query in EventClassifierGUI
- [ ] Load one experiment and verify the trace plots correctly
- [ ] Check event navigation and quality editing on a test file before large-scale curation

---

## 18. Final summary

nanoporethon is a reproducible nanopore data-selection and event-inspection toolkit.

Its central promise is simple and powerful:

- **find the right experiments,**
- **save exactly what you selected,**
- **re-open that selection later,**
- **inspect traces and events,**
- **and curate event quality with a transparent Python workflow.**

That makes it useful not just for daily data analysis, but also for collaboration, teaching, and future agent-assisted development.
