# Agent Server service

Agent Server is supplied by the LangGraph CLI/runtime image rather than
implemented as a second custom HTTP server in this repository. Its graph
entrypoints are declared in the root `langgraph.json` file.

This directory is reserved for service-specific deployment metadata,
environment configuration, and future health/operations helpers.

`Dockerfile.dev` is the license-free development image used by the root
`compose.yaml`. It runs the same in-memory `langgraph dev` process used on the
host. The process binds `0.0.0.0:2024` inside the container; Docker restricts
the published host listener to `192.168.0.18:2024`.
