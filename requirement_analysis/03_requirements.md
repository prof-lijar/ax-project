# AX Project Requirements

## Functional Requirements

### FR-01 Request Intake

The system shall accept user requests through approved interfaces such as web dashboard, Slack bot, Telegram bot, or internal API.

### FR-02 Authentication and Authorization

The system shall verify user identity and permissions before allowing access to tools, data, workflows, or model actions.

### FR-03 Task Planning

The system shall analyze each request, identify the goal, decompose it into tasks, and select an appropriate workflow.

### FR-04 Agent Orchestration

The system shall support a master orchestrator that routes work to specialized sub-agents or workers.

### FR-05 Workflow Types

The system shall support at least three workflow patterns:

- Sequence workflow for step-by-step tasks.
- Loop workflow for retry, validation, and quality improvement.
- Parallel workflow for independent research, extraction, or analysis tasks.

### FR-06 RAG and Knowledge Search

The system shall retrieve information from approved project documents, files, internal knowledge bases, and vector indexes.

### FR-07 Tool Use

The system shall allow agents to use approved tools for file processing, search, database lookup, reporting, code support, and internal service integration.

### FR-08 State and Memory

The system shall store session state, workflow state, execution history, and reusable memory in a persistent state layer.

### FR-09 Human Approval

The system shall require human approval before sensitive actions, including customer-facing messages, production changes, code modification, external API writes, and cloud model escalation for sensitive data.

### FR-10 Audit Logging

The system shall log user request, selected workflow, agent actions, tool calls, data sources, model used, output, approval decision, and errors.

### FR-11 Model Routing

The system shall route tasks between local SLLM, local LLM, and optional cloud LLM based on task complexity, sensitivity, cost, and approval policy.

### FR-12 Report Generation

The system shall generate reports from approved source material, including summaries, operational status, satisfaction results, risks, and next actions.

### FR-13 Alert Triage

The system should classify alerts, summarize context, suggest response guidance, and prepare human-reviewed notifications.

### FR-14 Exception Management

For service operations such as smart care, the system should help identify and manage exceptions such as long absence, hospital admission, or unusual status patterns if the required data is available.

### FR-15 Sandbox Execution

The system shall execute generated scripts or code only in an isolated sandbox with controlled resource access.

### FR-16 MCP and API Integration

The system shall support controlled integration with MCP servers, internal APIs, SaaS platforms, and service databases.

## Non-Functional Requirements

### NFR-01 Local-First Operation

The default deployment should keep sensitive data and routine inference local.

### NFR-02 Security

The system shall enforce least privilege access, role-based permissions, data access boundaries, and tool restrictions.

### NFR-03 Reliability

The system should support long-running tasks, recovery from worker failures, and persisted workflow state.

### NFR-04 Observability

The system shall provide logs, task status, tool traces, approval history, and error reports for operators.

### NFR-05 Maintainability

Agent roles, skills, tools, and workflows should be modular and version-controlled.

### NFR-06 Scalability

The system should support batch and parallel execution where workloads are independent and hardware capacity allows.

### NFR-07 Cost Control

The system should minimize unnecessary model calls through state reuse, retrieval, routing, and programmatic tool execution where appropriate.

### NFR-08 Privacy

The system shall avoid exposing sensitive personal, customer, or company data to external models unless policy and approval allow it.

### NFR-09 Explainability

The system should show sources, assumptions, confidence limits, and recommended next actions for important outputs.

### NFR-10 Extensibility

The system should allow new service-specific agents, tools, and workflows to be added without redesigning the full platform.

