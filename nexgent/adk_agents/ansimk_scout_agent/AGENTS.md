# ansimk_scout_agent Working Guide

This standalone project was initialized from the agents-cli 1.4.1 ADK prototype
layout. It intentionally does not expose the generated raw ADK or A2A routes.

## Boundaries

- Keep all project files and runtime configuration inside this directory.
- Do not import from or modify Nexgent `agents/`, `backend/`, `frontend/`, RAG,
  Compose, shared model configuration, scheduling code, or Slack code.
- Keep model access behind ADK `LiteLlm` and the project-owned environment
  variables documented in `.env.example`.
- Both ADK LLM stages must remain tool-free. Deterministic application services
  own DDGS search, HTTPX fetch, Trafilatura extraction, report persistence, and
  execution logging.
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
