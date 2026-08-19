# Documentation map

- [AX agents architecture](ax-agents-architecture.md): authoritative modular
  package, runtime, API, security, deployment, and verification design.
- [AX agents module guide](ax-agents-module-guide.md): responsibilities,
  boundaries, interfaces, and current status of each package.
- [Scalable agent platform structure](scalable-agent-platform-structure.md):
  implemented apps/workflows/packages layout, dependency rules, performance
  decisions, validation, and extension guidance.
- [LangGraph environment setup](langgraph-environment-setup.md): greenfield
  Python/uv setup, graph-entry import requirements, local Agent Server
  validation, trusted-LAN binding, and production follow-up guidance. Read the
  architecture document before extending this setup.
- [OpenAI-compatible LLM integration](llm-integration.md): vLLM environment
  configuration, chat graph usage, retry behavior, and secret handling.
- [Chat response streaming](chat-response-streaming.md): provider-token to
  LangGraph custom-event contract, cancel-on-disconnect behavior, validation,
  and deployment.
- [Chat attachments](chat-attachments.md): transient reference contract,
  secure file reader, document/image provider payloads, safe errors, and
  runtime limits.
- [Reusable web research tools](web-research-tools.md): provider-neutral
  `web_search`/`web_fetch` contracts, private SearXNG deployment, reuse, source
  evidence, SSRF controls, and retrieval limits.
- [MCP development and integration](mcp-integrations.md): declarative remote
  server registry, environment-backed headers, discovery CLI, namespaced tool
  adapters, risk classification, and the configured read-only database MCP.
- [Ansimk weekly reporter](../workflows/weekly_report/README.md): private
  FastAPI/raw-PostgreSQL metadata source, deterministic current/prior metrics,
  warm Korean narrative generation, validation, and fallback behavior.
- [Ansimk weekly reporter implementation specification](ansimk-weekly-reporter-implementation.md):
  implemented FastAPI source boundary, calculation rules, LLM safety contract,
  configuration, and verification gates.
- [Frontend weekly reporter workbench](../../docs/08-implementation/weekly-reporter-test-route.md):
  live `/agents/1` execution with an operator-selected 1–25 report batch,
  first-report selection, safe report review, and the full Compose runtime path.
- [Outbound Slack messaging](slack-outbound-messaging.md): approved-channel
  configuration, reusable async delivery, safe failures, Slack app setup, and
  human-approved weekly-report verification.
- [Workspace README](../README.md#docker-development-server): license-free
  Docker development startup, parent Nexgent Compose integration, and
  trusted-LAN publishing.
