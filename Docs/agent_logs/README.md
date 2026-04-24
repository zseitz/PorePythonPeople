# Agent Task Logging

This folder keeps a lightweight paper trail of agent requests and outcomes.

## Files

- `REQUEST_LOG.md`: append-only index of task requests and outcomes.

## Logging format

Each entry should include:

- date (YYYY-MM-DD)
- requester (person or "team")
- objective (short)
- agent used
- files changed (or `none`)
- status (`completed`, `blocked`, `superseded`)
- notes (1-2 lines)

## Policy

- Add one log row per meaningful request.
- Keep entries concise.
- Do not include secrets or sensitive data paths.
