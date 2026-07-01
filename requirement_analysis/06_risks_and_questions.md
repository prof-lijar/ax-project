# AX Risks and Questions

## Key Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Undefined pilot scope | Delays and unclear success | Choose one workflow and define measurable outcomes |
| Unclear data permissions | Security and privacy exposure | Build a data access matrix before implementation |
| AI hallucination | Incorrect reports, guidance, or actions | Use RAG sources, confidence limits, and human approval |
| Over-automation too early | Production mistakes or customer impact | Start with drafts and recommendations only |
| Tool misuse | Data loss or unintended external actions | Separate read tools from write tools and require approval |
| Framework lock-in | Hard-to-change architecture | Keep governance and tool contracts custom and modular |
| Local hardware limits | Slow response or queue buildup | Use model routing, batching, and vLLM when needed |
| Weak observability | Hard to debug or audit | Log requests, tool calls, sources, approvals, and errors |
| Sensitive data leakage | Legal, customer, or business risk | Local-first policy and explicit cloud escalation approval |
| Poor document quality | Low answer accuracy | Curate source documents and add retrieval tests |

## Questions to Resolve Early

### Business and Product

- Which existing product or service should be the first AX pilot?
- What business outcome should AX improve first: time savings, service quality, alert handling, reporting, or support?
- Who are the first users: PM, operations, support, developers, management, or customers?
- What is the acceptable level of AI autonomy for the first pilot?

### Workflow

- Which workflows are repeated frequently and documented well enough to automate or assist?
- Which actions require human approval?
- Which actions are never allowed for AI in the first phase?
- What should happen when the AI is uncertain?

### Data

- What documents, databases, logs, files, and APIs can AX access?
- Which data is sensitive, personal, customer-related, or confidential?
- Can sensitive data be embedded into a vector database?
- What retention policy applies to prompts, outputs, logs, and retrieved context?

### Infrastructure

- Which machine will host the first AX runtime?
- How will the existing A6000 GPUs be allocated?
- Is Ubuntu the target operating system for the local AI server?
- Should early inference use Ollama, vLLM, or both?
- What monitoring and backup approach is required?

### Security and Governance

- Who approves cloud model escalation?
- Who approves production actions?
- What roles should exist in the AX permission model?
- What audit log fields are mandatory?
- Are there external compliance requirements for services such as smart care?

### Framework and Engineering

- Should the first orchestrator be LangGraph, a custom AX core, or a hybrid?
- Which agent patterns from Hermes Agent are useful enough to adapt?
- Which tools need sandbox execution?
- What internal APIs or MCP servers should be built first?
- What evaluation dataset will be used to test answer quality and workflow reliability?

## Suggested Immediate Next Decisions

1. Select the first pilot service or workflow.
2. Confirm available data sources and access permissions.
3. Define human approval rules.
4. Choose initial interface: web dashboard, Slack bot, Telegram bot, or internal API.
5. Build the first read-only RAG assistant before enabling action tools.

