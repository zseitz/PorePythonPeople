# operator-assistant-routing skill

Purpose: keep chat routing semantic, strict, and operator-safe.

## Routing heuristics

- Treat feature follow-up replies as session continuation when a feature session is active.
- Ask clarification questions only when execution is truly blocked.
- Ask at most one blocking follow-up question per turn.

## Protection policy

- Protected files (`data_navi_gui.py`, `event_classifier_gui.py`) require explicit authorization when implicated.
- Authorization prompts should name specific files and planned reason.

## Strict mode

- Classifier availability and structured JSON output are mandatory for strict routes.
- No coarse non-LLM fallback for strict classification/session-analysis paths.
