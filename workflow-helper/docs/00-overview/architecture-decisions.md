# Architecture Decisions

This file records early decisions that should guide implementation. Update it when a decision changes.

## ADR-001: Local-First Desktop Shell

Decision: AX Project starts as a local-first Tauri app.

Reasoning:

- The first users need speed, file-system proximity, and durable local state.
- Agent integrations may touch local repositories, commands, and credentials.
- Local event storage makes audit and recovery simpler before cloud sync exists.

Implications:

- The frontend must tolerate offline operation.
- Background work should be supervised by the Tauri backend, not by hidden browser timers.
- Data schemas should be sync-ready but not sync-dependent.

## ADR-002: Event Log as Source of Truth for Audit

Decision: Tasks, approvals, assignments, and agent state changes emit append-only events.

Reasoning:

- Human-agent systems require accountability.
- Reconstructing timeline and causality is difficult if only current rows are stored.
- Event history gives future analytics and debugging a stable foundation.

Implications:

- Current task state may be stored as projections for speed.
- Event writes should be atomic with state updates.
- Events must include actor, timestamp, target, type, payload, and correlation id.

## ADR-003: Approvals Are Domain Objects

Decision: Approval requests are persisted objects with state, policy, evidence, and decision records.

Reasoning:

- Approval is the main human control point.
- Treating approvals as transient UI dialogs would make audit and delegation weak.

Implications:

- Approvals can be queued, assigned, escalated, expired, and reviewed.
- Agent actions that require permission must reference an approval policy.

## ADR-004: Agent Runtime Is Behind a Command Boundary

Decision: The app shell talks to agents through a stable backend command interface.

Reasoning:

- The first implementation may use mock agents, local processes, or remote APIs.
- The UI should not know agent transport details.

Implications:

- Define commands around product concepts: create task, assign task, request approval, pause agent.
- Avoid leaking provider-specific API shapes into UI state.

## ADR-005: React Stack for First Desktop Build

Decision: The first Tauri frontend uses React, TypeScript, TanStack Query, Zustand, and CSS modules.

Reasoning:

- React keeps hiring, testing, component libraries, and Tauri examples straightforward.
- TanStack Query separates backend-owned domain state from frontend rendering concerns.
- Zustand is sufficient for compact UI state such as selection, panels, filters, and layout.
- CSS modules with plain design tokens keep styling explicit without committing the product to a heavy design framework.

Implications:

- Avoid introducing a second styling system in the first build.
- Keep domain mutations behind typed Tauri commands.
- Keep critical workflow state out of frontend-only stores.
