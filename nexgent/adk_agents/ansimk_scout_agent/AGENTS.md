# ansimk_scout_agent Working Guide

This standalone project was initialized from the agents-cli 1.4.1 ADK prototype
layout. It intentionally does not expose the generated raw ADK or A2A routes.

## Boundaries

- Keep Scout application and source files inside this directory. Host
  deployment/runtime configuration, such as systemd `EnvironmentFile` files
  under `/etc/nexgent/`, may live outside this directory but must remain
  untracked and secret-safe.
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
- Slack delivery is an optional deterministic application service after a
  successful persisted run, authorized on 2026-09-07. It must not become an
  Agent tool, and delivery failures must not fail completed research.
- Docker packaging and Nexgent Compose integration are authorized as of
  2026-09-07. Keep secrets out of images and reports in persistent storage.
- Do not add browser automation, recursive crawling, or internal
  scheduling in this POC. The standalone Scheduling API remains a separate
  component; it is not a Scout Agent tool or an internal Scout scheduling
  implementation.

## Validation

Run Python commands with uv from this directory:

```bash
uv sync --all-groups
uv run pytest
uv run ruff check app tests
```

Run live model or internet checks at most once per requested smoke validation.
