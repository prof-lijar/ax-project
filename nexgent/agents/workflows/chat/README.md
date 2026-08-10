# Chat workflow

This workflow performs one LLM-backed chat-completion turn. It accepts a
non-empty `message` and returns `response`. Provider configuration and HTTP
behavior remain in `ax-integrations`; this module owns only the workflow state
and graph topology.

The workflow uses asynchronous model I/O and is registered as `chat` in
`langgraph.json`. The deterministic `smoke` workflow remains available for
health checks that must not depend on model availability.
