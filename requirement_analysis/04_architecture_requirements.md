# AX Architecture Requirements

## Layer Overview

AX should be designed as a layered local-first agent platform.

```text
User Interfaces
- Web dashboard
- Slack bot
- Telegram bot
- Internal API

Agent Gateway
- Authentication
- Authorization
- API routing
- Rate limits
- Request logging

Governance Layer
- Human approval gate
- Role-based access control
- Audit log
- Policy guardrails
- Data sensitivity rules

Agent Orchestration Layer
- Orchestrator / master agent
- Workflow router
- Agent registry
- Task planner
- Result aggregation

Agent Layer
- PM agent
- QA agent
- Dev agent
- Ops agent
- Data agent
- Security agent
- Service-specific agents

Model Routing Layer
- Local SLLM for repeated/simple tasks
- Local LLM for reasoning and workflow support
- Optional cloud LLM for approved escalation

Execution and Tool Layer
- AX tools
- Sandbox
- MCP servers
- Internal APIs
- File processing
- Database access
- Git/code tools

Data and State Layer
- SQLite for lightweight state and execution history
- PostgreSQL + pgvector for structured data and embeddings
- Redis for queue/cache where needed
- Vector DB for retrieval
- File storage

Observability Layer
- Logs
- Metrics
- Traces
- Approval history
- Error tracking
```

## Component Requirements

### User Interfaces

- Provide simple request submission and result review.
- Show task status for long-running work.
- Support approval and rejection flows.
- Avoid exposing data that the user is not authorized to view.

### Agent Gateway

- Centralize authentication, permissions, and routing.
- Validate request type and user role before orchestration.
- Keep a request ID for traceability.

### Governance Layer

- Enforce approval before sensitive actions.
- Maintain policy rules for tool use, data access, and cloud escalation.
- Record who approved what, when, and from which source output.

### Orchestrator

- Analyze request intent.
- Break down work into tasks.
- Select workflow type.
- Assign tasks to agents or tools.
- Aggregate results and prepare final output.

### Sub-Agents

- Be specialized by role or service domain.
- Use only approved tools.
- Update state after each meaningful step.
- Return structured results to the orchestrator.

### State and Memory

- Store session state, workflow state, agent state, execution history, and memory context.
- Support restart and recovery for long-running tasks.
- Keep state separate from raw sensitive data where possible.

### Skills

- Define role, behavior rules, allowed tools, input/output expectations, and escalation rules.
- Be stored as version-controlled markdown or configuration files.
- Be reviewed before use in production workflows.

### Tools

- Use explicit schemas for inputs and outputs.
- Restrict write actions by permission.
- Log every tool call.
- Separate read-only tools from action tools.

### Sandbox

- Isolate code execution from the host system.
- Limit filesystem, network, process, and resource access.
- Use RPC-style execution only through approved interfaces.

### Model Router

- Route simple tasks to local SLLM where possible.
- Route reasoning-heavy work to local LLM.
- Use cloud LLM only for approved tasks and non-sensitive or approved data.
- Log model choice and reason.

## Framework Evaluation Requirements

Frameworks should be evaluated against AX needs rather than selected by popularity.

| Option | Fit to Evaluate | Main Tradeoff |
| --- | --- | --- |
| LangGraph | Stateful workflows, human approval, long-running tasks | More design and implementation effort |
| LangChain | RAG, tools, integrations | Better as support layer than full governance layer |
| Google ADK | Enterprise agent design reference | May pull architecture toward Google ecosystem |
| OpenAI Agents SDK | Tool calling, handoffs, guardrails, structured output | Cloud/hybrid orientation |
| Hermes Agent concepts | RPC execution, skill factory, low context cost | Needs security review and adaptation |
| OpenClaw / OpenHands | Local action and coding agent patterns | Requires strong sandbox and guardrails |
| Custom AX Core | Tight control, local-first governance | More internal engineering ownership |

## Suggested Architecture Direction

The first AX platform should combine:

- Custom AX governance and approval layer.
- LangGraph or a similar stateful workflow engine as an orchestration candidate.
- LangChain-style utilities for RAG and tool integrations where useful.
- Local model runtime through Ollama first, with vLLM as a scaling option.
- SQLite for early state management, with PostgreSQL/pgvector for shared production retrieval.
- Sandbox execution for generated scripts and code-related workflows.

