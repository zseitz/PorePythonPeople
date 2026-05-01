# nanoporethon Use Cases

This document summarizes the real workflow problems nanoporethon is intended to support.

It helps both humans and coding agents understand **why** the software exists, not just **how** it is implemented.

Important framing: the primary product is the nanopore data workflow itself (search, selection, inspection, and curation). The local runtime/agent tooling is supporting infrastructure for occasional, human-supervised development work—not an unattended autonomous platform.

---

## 1. Core operational use case

### Use Case 1: Search a large historical experiment database

Users need to pull a focused subset of experiments from a large directory of files/folders whose names encode experimental conditions.

Typical goals:

- find all experiments for a specific pore,
- find all runs at a specific voltage,
- compare specific enzymes or buffer conditions,
- exclude broken controls or irrelevant runs,
- manually curate the final selection,
- and save that selection reproducibly for later analysis.

This use case maps directly to:

- `DataNaviGUI`,
- the search filter engine,
- and query-log generation.

---

## 2. Scientific analysis use cases

### Use Case 2: Compare experimental conditions across many runs

Researchers want to compare nanopore behavior across variables such as:

- pore identity,
- motor enzyme,
- ATP concentration,
- pH,
- temperature,
- salt concentration,
- orientation/direction,
- voltage,
- and other experiment labels encoded in names.

This often begins with Data Navigator and continues into trace inspection with Event Classifier.

### Use Case 3: Review and curate event quality

Users need to visualize traces and assess whether events appear good, bad, ambiguous, noisy, or otherwise noteworthy.

This use case maps directly to:

- trace plotting,
- event overlays,
- event navigation,
- and saving quality values back to `event.mat`.

### Use Case 4: Support sequencing-oriented nanopore experiments

Users may work on DNA, RNA, peptide, or other analyte workflows where event structure and trace quality help evaluate:

- enzyme performance,
- read quality,
- pore behavior,
- and candidate sequencing conditions.

nanoporethon does not yet perform full automated sequence calling, but it supports the selection and inspection steps needed before or alongside those pipelines.

### Use Case 5: Support non-enzymatic or noncanonical experiments

nanoporethon should also support broader nanopore workflows such as:

- sensing experiments,
- pore opening/closing studies,
- bond-rupture experiments,
- mechanistic event characterization,
- and exploratory experiments that do not fit a strict sequencing template.

---

## 3. Collaboration and reproducibility use cases

### Use Case 6: Re-open and share a saved experiment subset

Users often need to:

- save the exact selection they used,
- revisit it later,
- share it with a collaborator,
- or use the same set for a later round of analysis.

This is why the query-log folder and `search_query.txt` contract matter so much.

### Use Case 7: Standardize workflows across users with different skill levels

nanoporethon must work for:

- brand-new undergraduates,
- experienced graduate students,
- postdocs,
- collaborators outside the lab,
- and developers who want to extend the software.

That means:

- GUI workflows should be clear,
- documentation should be explicit,
- and internal contracts should be stable enough for agents to maintain.

---

## 4. Future-facing use cases

### Use Case 8: Prepare data for downstream modeling or ML

Curated selections and event-quality annotations can support future workflows such as:

- classifier training,
- model benchmarking,
- consensus alignment studies,
- or deterministic preprocessing pipelines.

These are best understood as downstream or adjacent workflows. They do not change the current operating model of this repository, which remains centered on supervised data review and human-reviewed development changes.

### Use Case 9: Extend to broader nanopore platforms and analytes

The project should stay flexible enough that future users can adapt it to:

- different pores,
- different enzymes,
- new analytes,
- or new experiment naming conventions,

as long as stable data contracts are preserved where required.

That flexibility goal refers to scientific adaptability of the data workflow, not to turning the repository into a fully autonomous analysis or software-management platform.

---

## 5. Summary

In short, nanoporethon is meant to support:

- **finding experiments**,
- **saving selections reproducibly**,
- **plotting and comparing traces**,
- **curating event quality**,
- and **providing an extensible, open workflow** for nanopore data analysis.

Any agent/runtime assistance should be read in service of those goals, with normal human review and branch-based engineering practices still in place.
