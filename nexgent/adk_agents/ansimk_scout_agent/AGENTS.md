# ansimk_scout_agent Working Guide

This standalone project was initialized from the agents-cli 1.4.1 ADK prototype
layout. It intentionally does not expose the generated raw ADK or A2A routes.

## Boundaries

- Keep all project files and runtime configuration inside this directory.
- Do not import from or modify Nexgent `agents/`, `backend/`, `frontend/`, RAG,
  Compose, shared model configuration, scheduling code, or Slack code.
- Keep model access behind ADK `LiteLlm` and the project-owned environment
  variables documented in `.env.example`.
- Keep exactly one ADK research Agent, `ansimk_scout_agent`, with only the
  bounded `web_search` and `web_fetch_and_extract` Function Tools.
- The Agent chooses when to search and which searched URLs to fetch. Per-run
  Python tool state owns budgets, searched-URL eligibility, fetch safety,
  successfully fetched URL tracking, and safe execution events.
- Deterministic application services own report validation, report persistence,
  and execution logging. Persistence must never become an Agent tool.
- Do not add Docker, browser automation, recursive crawling, scheduling, or
  notifications in this POC.

## Validation

Run Python commands with uv from this directory:

```bash
uv sync --all-groups
uv run pytest
uv run ruff check app tests
```

Run live model or internet checks at most once per requested smoke validation.
