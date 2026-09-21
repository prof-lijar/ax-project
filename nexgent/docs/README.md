# AX Project Documentation

- [Weekly Reporter Selected-Ward Tests](08-implementation/weekly-reporter-selected-ward-tests.md): comma-separated ward selection, ZIP-only output, validation, and rollout.

- [Weekly Report Five-ZIP Retention](08-implementation/weekly-report-five-zip-retention.md): automatic ZIP cleanup, preserved report data, manual command, and rollout checks.

- [Weekly Reporter UI ZIP-only tests](08-implementation/weekly-reporter-ui-zip-only.md): export-only UI generation, preserved scheduled storage, validation, and rollout.

AX Project is a Linux desktop application built with Tauri. Its first stage is a human-in-the-loop command center for always-on agents: people approve, assign, inspect, redirect, and learn from agent work without losing control of execution.

This documentation set defines the product architecture before implementation begins.

## Document Map

- [Persistent AX Chat History](08-implementation/persistent-ax-chat-history.md): private per-user history, background replies, saved files, APIs, deployment, recovery and validation.

- [Password Length Policy](08-implementation/password-length-policy.md): 4–12 character creation/reset validation, existing-login compatibility, and verification.

- [Unified App Authentication](08-implementation/unified-app-authentication.md): current login gate, Settings administration, protected feature gateway, standard Compose startup and validation.

- [Backend PostgreSQL Docker Network](08-implementation/backend-postgresql-docker-network.md): database connection-refused fix, existing external network attachment, and runtime verification commands.

- [External PostgreSQL Configuration](08-implementation/external-postgresql-configuration.md): historical removal of the bundled account database; current startup is in Unified App Authentication.

- [Auth Database Schema](08-implementation/auth-database-schema.md): explicit `auth` table ownership, migration from `public`, data preservation and validation.

- [Simple Login and Access Control](08-implementation/simple-login-access-control.md): historical account foundation and eight-table RBAC implementation; superseded deployment integration.
- [Managed Account Foundation](08-implementation/managed-account-foundation.md): superseded historical record of the earlier Keycloak/session implementation.

- [Login and Access Architecture](03-architecture/identity-access-architecture-plan.md): simple local login, direct/group roles, permission enforcement and deployment boundaries.
- [Login and Access Database Schema](05-data/identity-access-database-plan.md): detailed columns, constraints, relationships, seed data and migration for the eight current tables.
- [Login and Access Backend and UI Plan](07-roadmap/identity-access-delivery-plan.md): implemented APIs, administration forms, verification steps and extension points.

- [Sumin Model-Directed File Search](08-implementation/sumin-model-directed-file-search.md): bounded metadata discovery, verified Slack attachments, migration, validation, and rollout checks.

- [Sumin Shared Agent Schema](08-implementation/sumin-shared-agent-schema.md): legacy table migration into `agent.sumin_*`, permissions, rollout, and validation limits.

- [Sumin Single-Workspace Channel Folders](08-implementation/sumin-single-workspace-channel-folders.md): channel-only archive paths, one-time database migration, rollout, and validation.

- [Sumin Unified Compose Startup](08-implementation/sumin-unified-compose-startup.md): standard root Docker startup, shared environment loading, migration ordering, and Socket Mode services.

- [Sumin Slack-to-Nextcloud Archive](08-implementation/sumin-slack-nextcloud-archive.md): durable Slack upload collection, channel-scoped discovery, operation, validation, and rollout checks.

- [RAG Knowledge Workspace Refinement](08-implementation/rag-knowledge-workspace-refinement.md): clearer upload/search flows, source passages, keyboard interactions, deletion safeguards, and validation.

- [Agents Co-worker Catalog Refinement](08-implementation/agents-coworker-catalog-refinement.md): clearer co-worker cards, local search, workspace/Chat actions, responsive states, and validation.

- [Chat Session UI Upgrade](08-implementation/chat-session-ui-upgrade.md): session conversations, composer and transcript UX, background replies across menus, HTTP-compatible copy actions, and validation.

- [Workspace Top Bar Removal](08-implementation/workspace-top-bar-removal.md): shared search/Pause header removal, full-height content layout, Settings placeholder, and validation limits.

- [Weekly Report Ward/Week Uniqueness](08-implementation/weekly-report-ward-week-uniqueness.md): existing update-on-conflict behavior, PostgreSQL regression coverage, and remaining database verification.
- [Weekly Reporter 01:00 KST Schedule](08-implementation/weekly-reporter-schedule-0100-kst.md): Monday scheduler time change from 03:00 to 01:00 Asia/Seoul and rollout commands.

- [Weekly Reporter Run Agent](08-implementation/weekly-reporter-run-agent.md): bulk run action, status indicator, fixed completion timing, validation, and report limits.

- [Scout ADK Compose Integration](scout-adk-compose-integration.md): automatic Scout startup, same-origin frontend proxy, environment configuration, persistence, and migration limits.

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
- [Docker Production Server Stack](08-implementation/docker-production-stack.md): separate stable server for tested releases, non-conflicting ports, immutable frontend/backend images, shared temporary credential values, operations, validation, and runtime boundaries.
- [Dashboard Content Scrolling](08-implementation/dashboard-content-scrolling.md): app-shell sizing fix that keeps left-navigation section content scrollable within the desktop window.
- [Frontend Section Routing](08-implementation/frontend-section-routing.md): stable URL paths, direct-load behavior, and browser-history synchronization for sidebar sections.
- [Agent Server Chat](08-implementation/agent-server-chat.md): Workspace replacement, streamed AX chatbot client, session transcript, networking, and validation.
- [RAG Chat Agent](../agents/docs/rag-chat-agent.md): dedicated Chat-page agent,
  read-only Top-5 grounding, streamed OpenAI-compatible generation,
  deterministic sources, completed Phase 1 live validation, and current limits.
- [Chat File Attachments](08-implementation/chat-file-attachments.md): transient multi-file upload, document extraction, multimodal model input, security boundaries, and validation.
- [Agents Management Interface](08-implementation/agents-management-interface.md): agent catalog, bulk-only Weekly Reporter entry, inspector UX, routing, and integration boundaries.
- [AnsimK Scout Agent Frontend POC](08-implementation/ansimk-scout-agent-frontend-poc.md): Agents-page workbench, direct browser-to-standalone-Scout API routing, authoritative run timing, exact-origin CORS, validated report rendering, and operational network limits.
- [Weekly Reporter Frontend Workbench](08-implementation/weekly-reporter-test-route.md): bulk-only `/agents/1` job submission, throughput monitoring, cancellation, verified export, fixed Monday 03:00 KST cron submission with a local-only schedule editor preview, private runtime path, and the retired Quick Preview boundary.
- [RAG UI Integration](../RAG/docs/rag-ui-integration.md): sidebar and `/rag` page integration, direct browser-to-RAG API routing, RAG Chat validation, and the systemd-managed host RAG lifecycle.

- [RAG Knowledge Search Workspace](08-implementation/rag-knowledge-search-workspace.md): search-first RAG redesign, source drawer, passage inspector, API boundaries, and validation.

## Stage-One Definition

Stage one does not need full autonomous execution. It needs the durable product foundation:

1. A clear desktop workspace where a human can see agent status, queue health, pending approvals, assigned work, and current risk.
2. A task and approval model that can support future integrations without being redesigned.
3. A local-first Tauri architecture that keeps the UI responsive while agents run continuously in background processes or remote services.
4. A traceable event model so every agent recommendation, human decision, task transition, and failure can be audited.

## Default Product Stance

AX Project should feel like a calm co-worker workspace, not a chatbot, system monitor, or generic task board. Chat can exist, but the primary interface is command: current work, co-worker focus, decisions, evidence, responsibility, and follow-up.
