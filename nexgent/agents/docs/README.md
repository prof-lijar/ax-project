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
- [Reusable web research tools](web-research-tools.md): provider-neutral
  `web_search`/`web_fetch` contracts, private SearXNG deployment, reuse, source
  evidence, SSRF controls, and retrieval limits.
- [MCP development and integration](mcp-integrations.md): declarative remote
  server registry, environment-backed headers, discovery CLI, namespaced tool
  adapters, risk classification, and the configured read-only database MCP.
- [Ward-risk weekly reporter](../workflows/weekly_report/README.md): database
  MCP-backed danger-day input, deterministic comparisons, Korean narrative
  generation, bounded demo selection, and template fallback behavior.
- [Workspace README](../README.md#docker-development-server): license-free
  Docker development startup, parent Nexgent Compose integration, and
  trusted-LAN publishing.
