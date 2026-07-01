# AX Project Context

## Purpose

AX Project is a Nextor.ai initiative to identify and design practical ways to integrate AI and AI agents into existing projects, products, services, workflows, and microservice extensions.

The project should be treated as a requirements and design effort first, not as immediate implementation. The main output should be a realistic plan for where AI can add value, what systems it must connect to, and what governance is required before automation is allowed to act.

## Known Facts

- Company: Nextor.ai
- Project: AX Project
- Goal: apply AI and AI agents to existing applications, workflows, services, and internal operations.
- Preferred direction: local-first AI infrastructure with optional cloud model escalation.
- Current GPU resource noted: A6000 40GB x 3.
- Candidate interfaces shown in project material:
  - Slack bot
  - Telegram bot
  - Web dashboard
- Candidate outputs shown in project material:
  - Reports
  - Alerts
  - Code changes
  - Workflow execution
  - Analysis results
- Candidate data and infrastructure components:
  - GPU server
  - PostgreSQL with pgvector
  - Redis
  - Vector database
  - Internal tools
  - File storage
- Candidate agent architecture:
  - Orchestrator or master agent
  - Sub-agents or workers
  - State and memory store
  - Skills
  - Tools
  - Sandbox
  - MCP and external APIs

## Working Assumptions

- AX should begin with controlled assistance and workflow support before full automation.
- Sensitive company or customer data should remain local unless explicit approval allows cloud model use.
- Human approval is required for actions that affect production systems, customers, code, notifications, or external services.
- The first pilot should focus on a real existing service or workflow with measurable value.
- Frameworks such as LangGraph, LangChain, Google ADK, OpenAI Agents SDK, OpenClaw, Hermes Agent, and OpenHands should be evaluated as options, not treated as fixed defaults.

## Current Information Gaps

- Full list of existing company applications and services.
- Priority workflows for the first AX pilot.
- Available databases, APIs, message queues, and internal tools.
- Data access permissions and security requirements.
- Production deployment environment.
- Approval policy for AI-driven actions.
- Success metrics for the first pilot.
- Required languages and user roles for the dashboard and bots.

