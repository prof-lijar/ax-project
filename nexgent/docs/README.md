# AX Project Documentation

AX Project is a Linux desktop application built with Tauri. Its first stage is a human-in-the-loop command center for always-on agents: people approve, assign, inspect, redirect, and learn from agent work without losing control of execution.

This documentation set defines the product architecture before implementation begins.

## Document Map

- [Vision](00-overview/vision.md): product intent, operating principles, and stage-one scope.
- [Architecture Decisions](00-overview/architecture-decisions.md): early technical decisions and tradeoffs.
- [Product Requirements](01-product/product-requirements.md): personas, jobs, features, and non-goals.
- [Human-Agent Workflow](01-product/human-agent-workflow.md): core operating loops and user journeys.
- [UX System](02-design/ux-system.md): desktop information architecture, screens, layout, and interaction principles.
- [Frontend Architecture](03-architecture/frontend-architecture.md): Tauri, frontend layers, app shell, state, commands, and packaging.
- [Agent Orchestration](04-agents/agent-orchestration.md): agent registry, runtime model, task routing, approvals, and supervision.
- [Data Model](05-data/data-model.md): local-first entities, event log, persistence, and sync-ready boundaries.
- [Algorithms](06-algorithms/core-algorithms.md): scheduling, assignment, approval gating, notification, and context selection algorithms.
- [Roadmap](07-roadmap/implementation-roadmap.md): phased plan from docs to first usable desktop app.
- [Desktop App Status](08-implementation/desktop-app-status.md): implementation state, run commands, validation, and known gaps.
- [Document Viewer](08-implementation/document-viewer.md): NextCloud file preview behavior, supported formats, LibreOffice setup, and validation.
- [Docker Development Stack](08-implementation/docker-development-stack.md): dated implementation record for the FastAPI and Vite Compose stack, configuration, operation, validation, and remaining runtime check.
- [Dashboard Content Scrolling](08-implementation/dashboard-content-scrolling.md): app-shell sizing fix that keeps left-navigation section content scrollable within the desktop window.
- [Frontend Section Routing](08-implementation/frontend-section-routing.md): stable URL paths, direct-load behavior, and browser-history synchronization for sidebar sections.
- [Agent Server Chat](08-implementation/agent-server-chat.md): Workspace replacement, streamed AX chatbot client, session transcript, networking, and validation.
- [Chat File Attachments](08-implementation/chat-file-attachments.md): transient multi-file upload, document extraction, multimodal model input, security boundaries, and validation.
- [Agents Management Interface](08-implementation/agents-management-interface.md): read-only LangGraph agent catalog, Weekly Reporter preview, inspector UX, routing, and integration boundary.
- [Weekly Reporter Frontend Workbench](08-implementation/weekly-reporter-test-route.md): live `/agents/1` configurable 1–25 report runner, first-report selection, private source runtime path, contract validation, and operator UX.

## Stage-One Definition

Stage one does not need full autonomous execution. It needs the durable product foundation:

1. A clear desktop workspace where a human can see agent status, queue health, pending approvals, assigned work, and current risk.
2. A task and approval model that can support future integrations without being redesigned.
3. A local-first Tauri architecture that keeps the UI responsive while agents run continuously in background processes or remote services.
4. A traceable event model so every agent recommendation, human decision, task transition, and failure can be audited.

## Default Product Stance

AX Project should feel like a calm co-worker workspace, not a chatbot, system monitor, or generic task board. Chat can exist, but the primary interface is command: current work, co-worker focus, decisions, evidence, responsibility, and follow-up.
