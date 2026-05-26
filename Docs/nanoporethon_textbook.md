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
  - [15.6 Operator checklist (with example prompt)](#156-operator-checklist-with-example-prompt)
  - [15.7 Runtime entrypoint (usable now)](#157-runtime-entrypoint-usable-now)
  - [15.8 Per-specialist model routing and context-window guidance](#158-per-specialist-model-routing-and-context-window-guidance)
    - [15.8A Plain-language note on quants and current model map](#158a-plain-language-note-on-quants-and-current-model-map)
  - [15.9 Local operator assistant GUI (Option B)](#159-local-operator-assistant-gui-option-b)
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
- the **Event Classifier GUI** helps you inspect and annotate them,
- and the **Consensus Maker GUI** provides a sequence-to-expected-signal utility for quick consensus previews.

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

Optional utility stage:

- **Sequence design preview with `SequenceDesignerGUI`**
  - enter a DNA sequence in 5'→3' order,
  - choose k-mer size, feeding orientation, pore orientation, display order, and phase shift,
  - optionally edit at a specific N-position with A/C/G/T, delete, or random mutation controls,
  - optionally toggle Hel308 mode and save/export generated outputs,
  - generate a deterministic expected normalized current trace.

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

### 7.8 `SequenceDesignerGUI`

- **File**: `src/nanoporethon/sequence_designer_gui.py`
- **Role**: sequence-to-signal design GUI aligned to MATLAB Sequence Designer controls.

What it does:

- validates DNA input (A/C/G/T) entered in 5'→3',
- computes a deterministic k-mer-based expected signal,
- exposes feeding orientation (5'/3'), pore orientation (forwards/backwards), display order (5'→3'/3'→5'), and phase shift (0..1),
- adds MATLAB-style edit-at-position controls (position slider/index plus A/C/G/T/delete/random actions),
- includes Hel308 toggle plus save-figure and export-levels actions,
- displays the result as a step trace in normalized $I/I_0$-style units.

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

- `StreptavidinIntro_YYYYMMDD_HHMMSS`

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

- `DEMO_20260305_145308`
- `Streptavidin22C_20260305_140116`

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

This section describes the current executable model for delegation in `nanoporethon`.

### 15.1 What makes this a **true orchestrator runtime**

This runtime is considered “true orchestration” (not convention-only routing) because it enforces all of the following:

- one request enters through a single orchestrator entrypoint,
- work executes through a policy-defined stage graph,
- each stage has explicit specialist ownership,
- gates must pass (or be explicitly waived with evidence),
- stage handoffs are schema-validated,
- run artifacts are persisted for replay/audit,
- and closeout includes documentation + memory synchronization.

### 15.2 Runtime artifacts and source of truth

Policy, templates, runtime code, and schemas live in:

- `runtime/policies.yaml`
- `runtime/stage_templates.yaml`
- `runtime/orchestrator.py`, `runtime/planner.py`, `runtime/executor.py`, `runtime/gates.py`, `runtime/state.py`
- `runtime/adapters/ollama.py`
- `runtime/schemas/handoff_packet.schema.json`
- `runtime/schemas/stage_result.schema.json`
- `runtime/schemas/gate_result.schema.json`
- `runtime/schemas/run_state.schema.json`

Per-run artifacts are written under:

- `.nanopore-runtime/runs/<run_id>/run.json`
- `.nanopore-runtime/runs/<run_id>/events.jsonl`
- `.nanopore-runtime/runs/<run_id>/artifacts/`

Ollama adapter behavior (current implementation):

- `runtime/adapters/ollama.py` is a minimal local-model transport wrapper.
- It sends HTTP POST requests to Ollama's `/api/chat` endpoint (default `http://localhost:11434`).
- It provides two modes:
  - `chat(...)` for normal text responses
  - `chat_json(...)` for JSON-structured responses (via Ollama `format: "json"`)
- It returns the model's `message.content` text to callers and surfaces connectivity failures with actionable runtime errors.
- This path is plain Ollama HTTP API usage (not Model Context Protocol / MCP transport).

### 15.3 Delegation model (stage ownership and routing)

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

Routing behavior:

- if quality signals require structural cleanup, run `refactor` then `verify_after_refactor`,
- otherwise route directly from `refactor_or_docsync` to `doc_sync`.

### 15.4 Runtime architecture (lightweight, current scope)

The current runtime is intentionally lightweight and local-first. Core roles:

- **Request ingestor**: starts `run_id` and captures request.
- **Planner**: generates scoped plan + acceptance criteria.
- **Specialist executor**: runs stage owners with bounded context.
- **Gate engine**: enforces pass/fail/waived decisions.
- **State store**: records run + stage lifecycle.
- **Repo adapter**: applies edits/checks in the active feature-branch workspace and controls promotion.
- **Memory updater**: writes concise verified learnings.

### 15.4A Intended operating model (important reality check)

This runtime should be understood as a **human-supervised feature-work assistant**, not as an always-on autonomous platform.

In practical terms, the intended operating model is:

- run it **occasionally**, not continuously,
- use it primarily for **scoped implementation/refactor/doc-sync tasks**,
- launch it from a **dedicated local feature branch**,
- keep a **human operator in the loop** for review, approvals, and promotion,
- and treat the runtime as **supporting infrastructure** for nanoporethon development rather than the main product itself.

What this means operationally:

- The runtime is **not meant to run unattended**.
- Promotion should be treated as a **normal reviewed workflow**, not as blind auto-merge.
- Strong guardrails are useful, but they should stay proportional to this repo's real use case.
- The primary value remains the nanopore analysis and curation code; the runtime exists to make occasional development work safer and more repeatable.

If multiple people use the runtime, the preferred pattern is still the same: each operator runs locally, on their own branch, with normal git review habits preserved.

### 15.5 Gates, contracts, and guarantees

Gate categories include planning, implementation, verification, documentation, and memory completion.

Waivers are valid only when explicitly recorded with approver and reason.

Structured handoff contracts:

- **HandoffPacket** (stage-to-stage payload)
- **StageResult** (stage outcome)
- **GateResult** (gate evidence + decision)
- **RunState** (full resumable lifecycle)

Operational guarantee:

- default behavior is automatic and consistent under active policy/gates,
- absolute completion still depends on waivers, policy changes, and runtime health.

### 15.6 Operator checklist (with example prompt)

Use this checklist for day-to-day operation.

- **Pre-flight**
  - Work from a dedicated feature branch.
  - Ensure clean git working tree.
  - Confirm `runtime/policies.yaml` + schemas exist.
  - Confirm tests/environment are available.
  - Confirm the request is appropriately scoped for a supervised feature-work run, not a broad autonomous repo rewrite.

For assistant-triggered runs (Option B), pre-flight is now policy-enforced before launch:

- clean working tree requirement (policy-controlled), and
- feature-branch requirement (policy-controlled; `main`/`master` and detached HEAD are blocked).
- **Submit request**
  - Run the orchestrator with a clear scoped request.
  - Prefer acceptance checks in the request itself.
- **Monitor stages and gates**
  - Confirm expected stage progression.
  - If approval mode is enabled, review each handoff before approving.
  - Review generated edits as normal engineering work; the runtime is an assistant, not a substitute for judgment.
- **Handle failures correctly**
  - Fix and rerun first.
  - Use waivers only when approved and recorded.
- **Closeout checks**
  - Verify required stages are `success` or approved `waived`.
  - Verify docs + request log are updated when behavior changed.
  - Verify memory updates are factual and concise.
  - Verify run artifacts are complete.
  - Promote only the files you are comfortable reviewing and owning on your branch.

Example prompt for a feature run:

- "Add <feature>. Update nearest tests. If behavior/contracts change, sync `Docs/components.md` and relevant textbook sections. Run verification gates, record artifacts, and complete memory + closeout stages."

### 15.7 Runtime entrypoint (usable now)

Run with:

- `python -m runtime.orchestrator --request "<your request>"`

Helpful options:

- `--output json|summary|both`
- `--live-progress` / `--no-live-progress`
- `--approval-mode per_stage`
- `--resume-run-id <run_id> --resume-choice restart_from_beginning|resume_from_last_completed`

Current runtime behavior includes in-place branch edits, policy-driven verification commands, schema validation with deterministic fallback handling (including explicit output-target precedence, syntax-safe generic Python scaffold emission for missing/invalid implement payloads), absolute local file-context ingestion (including `.mlapp` extraction from `matlab/document.xml`), approval-aware resume flow, and optional operator-gated promotion.

Recommended usage pattern:

- use this runtime for **targeted feature work, runtime experiments, docs sync, and bounded refactors**,
- avoid treating it like a hands-off background service,
- and keep standard branch review/commit discipline even when the runtime completes successfully.

### 15.8 Per-specialist model routing and context-window guidance

Current recommended model map:

- global default: `qwen2.5:3b` (Ollama, speed-first)
- specialist overrides:
  - `feature_builder` → `qwen3:4b`
  - `refactor` → `qwen3:4b`
  - `doc_sync` → `qwen2.5:3b`
  - `memory_sync` → `qwen2.5:3b`

Operator-assistant classifier recommendation remains separate from specialist generation routing:

- `assistant_scope.intent_classifier.model` → `mistral:7b` (kept for strict JSON routing stability)

Recommended context planning (operational estimates):

| Specialist | Recommended effective context window | Stage budget reference |
|---|---:|---:|
| `orchestrator` | 24k–32k | `triage_plan: 4000`, `refactor_or_docsync: 3000`, `closeout: 2000` |
| `feature_builder` | 32k–48k | `implement: 8000` |
| `verifier` | 24k–32k | `verify: 6000`, `verify_after_refactor: 6000` |
| `refactor` | 32k–48k | `refactor: 6000` |
| `doc_sync` | 8k–16k | `doc_sync: 4000` |
| `memory_sync` | 8k–12k | `memory_sync: 2000` |

When context pressure rises: reduce unnecessary inputs first, then tighten payload shape, then raise stage budgets only if needed.

### 15.8A Plain-language note on quants and current model map

Many future `nanoporethon` developers will come from biophysics, chemistry, molecular engineering, or related experimental backgrounds rather than machine-learning engineering. Because of that, it is worth defining one common local-LLM term very plainly:

- **quantization** is the process of storing a model in a lower-precision, more compact numerical format,
- and a **quant** is informal shorthand for a **quantized model variant**.

In everyday usage, when someone says “use a quant,” they usually mean:

- “use the quantized version of the model,”
- not “use a single quantized number,”
- and not “use a separate special algorithm.”

An intuitive way to think about this is:

- a full-precision model is like carrying the whole lab bench everywhere,
- while a quantized model is more like packing the same essential tools into a compact field kit.

The compact kit may lose a little fidelity, but it is often much easier to carry and much faster to deploy.

For local attended agent workflows, quantized models are useful because they usually:

- use less RAM,
- load faster,
- respond faster on ordinary laptops or desktops,
- and still perform well enough for planning, drafting, routing, and structured-output tasks.

This matches the design of the `nanoporethon` runtime well, because model output is helpful but **not** the final source of truth. The real source of truth remains:

- repository code,
- tests,
- policy,
- gates,
- and operator review.

That means `nanoporethon` can often benefit from faster quantized local models without giving up safety, because gate evidence and verification results still decide whether a run passes.

Current configured agent/model ownership in `runtime/policies.yaml` is:

- **Operator-assistant intent classifier** → `mistral:7b`
- **Orchestrator runtime global default** → `qwen2.5:3b`
- **Specialists inheriting the global default**:
  - `orchestrator`
  - `verifier`
- **Specialists with explicit model entries**:
  - `feature_builder` → `qwen3:4b`
  - `refactor` → `qwen3:4b`
  - `doc_sync` → `qwen2.5:3b`
  - `memory_sync` → `qwen2.5:3b`

As checked against the local Ollama metadata during documentation review on **2026-05-08**, the currently installed model variants reported:

- `mistral:7b` → `Q4_K_M`
- `qwen2.5:3b` → `Q4_K_M`
- `qwen3:4b` → `Q4_K_M`

So, on the machine used for this update, the effective current map is:

| Agent / role | Configured model | Reported quant |
|---|---|---|
| Operator-assistant intent classifier | `mistral:7b` | `Q4_K_M` |
| `orchestrator` specialist | `qwen2.5:3b` | `Q4_K_M` |
| `feature_builder` specialist | `qwen3:4b` | `Q4_K_M` |
| `refactor` specialist | `qwen3:4b` | `Q4_K_M` |
| `verifier` specialist | `qwen2.5:3b` | `Q4_K_M` |
| `doc_sync` specialist | `qwen2.5:3b` | `Q4_K_M` |
| `memory_sync` specialist | `qwen2.5:3b` | `Q4_K_M` |

Important caveat: the **model name** in policy and the **quant installed on a particular machine** are related but not identical ideas.

- `runtime/policies.yaml` says which model names the runtime should use.
- The local Ollama installation determines which exact quantized artifact is actually present for that model name.
- If another developer pulls a different build of `mistral:7b`, `qwen2.5:3b`, or `qwen3:4b`, the reported quant could differ on their machine.

Practical recommendation for the default policy:

- keep the **intent classifier** on `mistral:7b Q4_K_M` for routing stability,
- keep the **global runtime default** on `qwen2.5:3b Q4_K_M` for portability,
- upgrade the code-heavy **`feature_builder`** and **`refactor`** specialists to `qwen3:4b Q4_K_M`,
- and keep **`doc_sync`**, **`memory_sync`**, **`orchestrator`**, and **`verifier`** on lighter models unless real usage shows a quality bottleneck.

This is intended as a **balanced 16 GB-friendly profile**: most machines should still be able to run the attended operator-assistant/runtime workflow locally, while the two stages that benefit most from stronger coding ability get a modest model upgrade.

When in doubt, the authoritative local check is Ollama model metadata (for example the `/api/show` response used by `runtime/orchestrator.py` startup checks), not guesswork based on the model name alone.

### 15.9 Local operator assistant GUI (Option B)

`nanoporethon` now includes a local operator assistant interface for attended runtime usage:

- launch with `python -m nanoporethon.operator_assistant_gui`
- use chat for in-scope repo/runtime questions and request drafting
- answer follow-up questions only when the assistant needs more precision
- review the generated runtime request preview
- run attended runtime directly from the GUI
- monitor stage/gate/promotion progress from streamed event updates

Important guardrail behavior:

- The assistant is domain-scoped to nanoporethon/runtime/repository workflows.
- Off-topic requests are deterministically refused (for example: cooking recipes, medical advice, political advice, investment advice, legal advice, general lifestyle counseling).
- Scope checks occur before runtime execution so out-of-scope prompts cannot trigger implementation actions.

Operationally, this keeps Option B interactive while preserving the project’s intended model:

- local-only assistance,
- branch-local change flow,
- and human-supervised attended operation.

Chat-first request guidance:

- Start by describing the feature/task naturally in one or two sentences.
- Intent and request-type understanding are inferred semantically by the local LLM (feature work vs question vs docs/help), not by hard-coded keyword checks.
- Strict semantic routing can use a primary classifier plus an optional fallback classifier from policy; both must produce valid structured JSON outputs.
- Local model calls for this flow use the Ollama HTTP adapter (`runtime/adapters/ollama.py`) against `/api/chat`; this assistant path is not MCP-server based.
- Classifier availability is mandatory at startup in strict mode; if local classifier initialization fails, the GUI shows an explicit startup error and disables message routing until fixed.
- Classifier prompts include recent chat/session context so runtime follow-up questions after a run are interpreted in conversation context (not as isolated messages).
- Use the **Health Check** button to validate strict-mode prerequisites (classifier enabled in policy, Ollama reachable, model installed, and valid JSON classifier output contract).
- Common runtime timeline terms (like `promotion_disabled`) are answered directly in-assistant so users can ask immediate post-run questions without switching workflows.
- For code-edit requests, verification is expected by default (automated tests + behavior checks) and is included in the runtime request guardrails without requiring testing keywords.
- Generated runtime request packets now include an explicit anti-hallucination quality rubric for each assistant-produced change:
  - Contract-safe (schema/policy/gate compatible)
  - Evidence-first (deterministic tests + behavior checks)
  - Surface-consistent (`Docs/components.md` + textbook sync when behavior changes)
  - Traceable (`Docs/agent_logs/REQUEST_LOG.md` row appended)
  - Scoped (minimal relevant diffs)
  - Operator-supervised (branch-local, human-reviewed flow)
- The assistant will ask targeted clarifying questions only when needed for missing behavior details or boundaries.
- If a prompt references a likely-mistyped source filename (for example requesting `SequenceDesigner.m` when `SequenceDesigner.mlapp` exists in the referenced folder), the assistant asks a single near-match confirmation question instead of launching a likely no-op run.
- When implement-stage model output is unavailable or invalid, runtime deterministic fallback can now scaffold explicitly requested GUI Python targets instead of always completing as a no-op.
- Runtime deterministic scaffolds are now runtime-generic (not tied to any specific generated app module), preserving architecture independence from application-specific code.
- Runtime request-file context discovery avoids hardcoded local folder assumptions and relies on explicit referenced paths plus discovered absolute roots.
- You do not need to pre-fill a long static intake form before getting useful help.

Core-component protection rule:

- Protected files are policy-configured in `runtime/policies.yaml` (repository defaults include `src/nanoporethon/data_navi_gui.py` and `src/nanoporethon/event_classifier_gui.py`).
- They should only be modified when the user explicitly authorizes such changes.

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
