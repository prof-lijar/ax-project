# Agent Server service

Agent Server is supplied by the LangGraph CLI/runtime image rather than
implemented as a second custom HTTP server in this repository. Its graph
entrypoints are declared in the root `langgraph.json` file.

This directory is reserved for service-specific deployment metadata,
environment configuration, and future health/operations helpers.
