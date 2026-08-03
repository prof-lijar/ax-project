# Frontend Agent Guide

This file keeps future Codex work in `frontend/` consistent. Treat it as the local working agreement for the Tauri desktop UI.

## Project Shape

- Desktop shell: Tauri 2.
- UI stack: React, TypeScript, Vite.
- State and data access:
  - TanStack Query for command-backed domain data.
  - Zustand for ephemeral UI state.
  - Rust commands as the product boundary.
- Keep the existing layout:
  - `src/app` for shell, providers, routes.
  - `src/features` for product surfaces.
  - `src/shared/api` for command/mock API adapters.
  - `src/shared/components` for reusable UI.
  - `src/shared/state`, `src/shared/types`, `src/styles`.
  - `src-tauri/src` for Rust commands, domain models, and app setup.

## UX Direction

- The main screen should feel like a simple co-worker workspace, not a dense dashboard.
- Agents should be presented in visible UI as co-workers, team members, or collaborators.
- Prefer "Team", "Co-workers", "Focus", "Decision", and "Current work" over infrastructure-heavy labels.
- Avoid defaulting to tables or tabs for co-workers. Use presence cards or simple workspace views.
- Keep the first screen focused on:
  - one clear next decision
  - current work
  - co-worker presence
  - recent activity
- Use restrained colors, clear spacing, and compact controls. Do not add decorative panels, marketing hero sections, or busy status grids.

## Security Rules

- Frontend code must not execute shell commands.
- Frontend code must not access filesystem, process, or OS APIs directly.
- Use Tauri Rust commands for product operations.
- Do not add Tauri plugins or capabilities unless the task requires them and the permission is narrowly scoped.
- Keep credentials out of frontend state, local storage, and mock data.
- Preserve the strict CSP in `src-tauri/tauri.conf.json`; do not add remote script/style sources.

## UI Implementation Rules

- Use `lucide-react` for icons.
- Prefer existing CSS modules and design tokens over new styling systems.
- Keep cards at `8px` radius or less.
- Avoid nested cards.
- Keep text short and operational.
- Ensure layouts work at narrow desktop widths and do not rely on viewport-scaled font sizes.
- When adding product copy, match the co-worker workspace language in `docs/02-design/ux-system.md`.

## Data Boundary

- UI components should depend on `src/shared/api/queries.ts` or the shared API adapter, not direct mock imports.
- Mock data is acceptable for preview, but keep it behind `src/shared/api`.
- Tauri commands should expose product operations, not raw database tables.
- Approval, task, team, and activity changes should eventually become auditable Rust command operations.

## Validation

Run from `frontend/` after code changes:

```bash
npm run build
cargo check --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
```

Preview locally:

```bash
npm run dev -- --host 127.0.0.1
```

Preview from another PC on the same LAN:

```bash
npm run dev -- --host 0.0.0.0
```

## Source Of Truth

- Product and UX direction: `../docs/02-design/ux-system.md`.
- Frontend architecture: `../docs/03-architecture/frontend-architecture.md`.
- Current implementation status: `../docs/08-implementation/desktop-app-status.md`.

If these docs conflict with existing code, preserve working behavior first, then update the smallest surface needed and document the mismatch.
