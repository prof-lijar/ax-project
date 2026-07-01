# AX Implementation Phases

## Phase 0: Discovery and Inventory

Goal: identify what AX can safely integrate with first.

Activities:

- List existing products, services, applications, and microservices.
- Identify available documents, databases, APIs, logs, files, and manuals.
- Map high-value workflows and repeated operational tasks.
- Identify user roles and approval owners.
- Classify data sensitivity.
- Select one pilot workflow.

Deliverables:

- Application and service inventory.
- Workflow shortlist.
- Data access matrix.
- First pilot decision.

## Phase 1: Knowledge and RAG Foundation

Goal: build a controlled assistant that can answer from approved material.

Activities:

- Collect approved source documents.
- Build document ingestion and indexing flow.
- Add source citation and retrieval trace.
- Create web dashboard or internal bot interface.
- Add basic auth and request logging.

Deliverables:

- Internal knowledge assistant.
- Document ingestion process.
- Retrieval quality test set.
- Basic audit log.

## Phase 2: Workflow Assistant

Goal: move from Q&A to guided work without autonomous production actions.

Activities:

- Define orchestrator workflow types: sequence, loop, parallel.
- Create first service-specific agent.
- Add report generation.
- Add alert triage or operational status summarization.
- Add human approval flow.

Deliverables:

- AX workflow assistant.
- Approval gate.
- First service-specific workflow.
- Operator review process.

## Phase 3: Tool and API Integration

Goal: connect AX to real systems with controlled permissions.

Activities:

- Build read-only tools for selected databases and APIs.
- Add write-capable tools only after approval rules are defined.
- Add MCP server or internal API integration where useful.
- Add sandbox execution for scripts and data processing.
- Improve observability and error handling.

Deliverables:

- Approved tool catalog.
- Tool permission model.
- MCP/API integration prototype.
- Sandbox execution policy.

## Phase 4: Pilot Operation

Goal: operate AX on one real workflow with measurable value.

Candidate pilot:

- `안심지키미` operations assistant, if service data and documents are available.

Pilot scope:

- Knowledge Q&A.
- Alert guidance draft.
- Exception management support.
- Monthly report draft.
- Human-approved notifications or action recommendations.

Metrics:

- Time saved per workflow.
- Reduction in repeated manual work.
- Retrieval accuracy.
- Report preparation time.
- Approval acceptance rate.
- Number of corrected or rejected AI outputs.
- Operator satisfaction.

## Phase 5: Expansion

Goal: extend AX to more services and deeper automation.

Activities:

- Add more service-specific agents.
- Add batch and parallel processing.
- Add model routing policies.
- Add advanced monitoring and evaluation.
- Add controlled write actions after pilot validation.

Deliverables:

- Multi-service AX platform.
- Evaluation dashboard.
- Governance playbook.
- Production operation guide.

