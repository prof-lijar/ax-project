# Desktop App Status

Date: 2026-07-03

## Summary

The first Linux desktop implementation has been added under `frontend/`. It provides a Tauri 2 desktop shell, a React + TypeScript operator UI, and a secure Rust command boundary with sample workflow data.

The app is usable as a web preview and builds successfully as a Debian package.

## Update: Retired Tasks, Approvals, and Activity UI

Date: 2026-09-03

The Tasks, Approvals, and Activity menu items and pages were removed from the
React frontend. Their route identifiers, rendering branches, query hooks,
browser mock data, frontend domain types, dedicated table styling, status/risk
badge helpers, and progress component were removed with them. The related
placeholder command-strip actions for Policy, Notifications, and Create task
were also removed; global search and Pause remain available on non-Chat pages.

Direct visits to `/tasks`, `/approvals`, or `/activity` now follow the existing
unknown-route behavior and are replaced with `/chat`. The Tauri command modules
and Rust domain models remain in place because this change removes frontend
surfaces only and does not retire backend capabilities.

Validation performed from `frontend/`:

```bash
npm test
npm run build
CARGO_TARGET_DIR=/tmp/nexgent-cargo-check cargo check --manifest-path src-tauri/Cargo.toml
git diff --check
```

All four checks passed. `npm audit --audit-level=moderate` could not be
completed because this execution environment denied access to the external npm
registry. Run that exact command from `frontend/` in an authorized network
environment to complete the dependency audit.

## Update: Agent Server Chat

Date: 2026-08-10

The Workspace/Mission Control section and its unused workspace command, models,
and sample data were removed. Chat is now the default section at `/chat` and
connects to the AX Agent Server through a reusable streaming client. The page
checks `/ok`, sends one stateless message per `/runs/stream` request, safely
parses chunked SSE responses, retains the visible transcript for the current
frontend session, and supports cancellation and explicit failure feedback.

Browser development and preview use a same-origin Vite proxy. Packaged Tauri
builds connect directly to the configured LAN endpoint under a narrowly scoped
CSP rule. See [Agent Server Chat](agent-server-chat.md) for configuration,
validation, security constraints, and remaining live-server verification.

## Update: Simplified Sidebar Status

Date: 2026-08-03

The sidebar footer now presents one product-level status line instead of the
technical `Local shell` label and `healthy` badge. It displays `Status: Good`
when the system health query reports healthy, and `Status: Bad` when it reports
degraded or fails. While the initial health request is loading, the existing
healthy default is preserved to avoid a false bad-state flash.

Validation performed from `frontend/`:

```bash
npm run build
CARGO_TARGET_DIR=/tmp/nexgent-cargo-check cargo check --manifest-path src-tauri/Cargo.toml
```

Both commands passed. The current health source remains command-backed sample
data, so live degraded/error transitions still require verification after a
runtime health integration is available.

## Update: Nexgent Sidebar Brand

Date: 2026-08-03

The sidebar brand mark and product label now use `N` and `Nexgent` instead of
`W` and `Workflow`. The workspace label remains `AX Project` (or the
command-provided workspace name when available).

Validation performed from `frontend/`:

```bash
npm run build
```

## What Is Done

- Created `frontend/` as a Tauri 2 + React + TypeScript + Vite project.
- Added an AX chatbot as the first screen with streamed responses, cancellation,
  session-only transcript state, and Agent Server availability reporting.
- Added secondary views for Agents, NextCloud, RAG, Test agent, and Settings.
- Added a NextCloud Drive surface for read-first file browsing through the local backend.
- Added a NextCloud document viewer for PDF, Markdown, text, images, DOCX, PPTX, and XLSX.
  - Office files are converted to PDF by LibreOffice on the backend machine.
  - See [Document Viewer](document-viewer.md).
- Organized frontend code into maintainable modules:
  - `src/app`
  - `src/features`
  - `src/shared/api`
  - `src/shared/components`
  - `src/shared/state`
  - `src/shared/types`
- Added Rust command modules under `frontend/src-tauri/src/commands`.
- Added typed domain models and seed data under `frontend/src-tauri/src/domain`.
- Added a frontend API adapter that uses Tauri commands in desktop mode and mock data in browser preview mode.
- Added Linux Debian bundle output through Tauri.

## Security Posture

- No Tauri shell, process, or filesystem plugins are enabled.
- Default Tauri capability has no broad permissions.
- Frontend actions go through product-level Rust commands, not raw database or system APIs.
- CSP is restricted to local bundled assets, IPC, local development endpoints, and the local backend.
- Document preview uses backend-proxied bytes and scoped `blob:` rendering for PDF/image previews.
- Markdown is rendered as React nodes with limited safe support for details blocks and safe links.
- Credentials are not stored in frontend state.
- Retired task, approval, and activity operations remain enforced behind the
  Tauri command boundary and are not exposed by the current React UI.
- UI icons use `lucide-react`, an open-source icon package with React and TypeScript support.

## Validation

Completed successfully:

```bash
npm run build
npm audit --audit-level=moderate
cargo check --manifest-path frontend/src-tauri/Cargo.toml
npm run tauri:build
```

Current package output:

```text
frontend/src-tauri/target/release/bundle/deb/Nexgent_0.1.0_amd64.deb
```

## Run Commands

Local web preview:

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

LAN web preview from another PC:

```bash
cd frontend
npm run dev -- --host 0.0.0.0
```

Open:

```text
http://192.168.0.18:5173/
```

If another PC times out, allow inbound traffic on the Linux machine:

```bash
sudo ufw allow from 192.168.0.0/24 to any port 5173 proto tcp
sudo ufw reload
```

Desktop development:

```bash
cd frontend
npm run tauri:dev
```

Linux package build:

```bash
cd frontend
npm run tauri:build
```

## Known Gaps

- Data is currently command-backed sample data, not SQLite.
- NextCloud Drive integration is read-first; upload, write, delete, copy, and move are intentionally not exposed yet.
- DOCX, PPTX, and XLSX previews require LibreOffice packages on the backend host.
- The desktop app expects the FastAPI backend to run separately; it does not supervise the backend process yet.
- Task, approval, and activity command handlers remain sample-data backed and
  have no current React UI.
- AppImage bundling is not enabled by default because it failed in this environment with a read-only filesystem error.
- The Tauri icon is a generated placeholder and should be replaced with a proper product icon.
- Agent chat streaming is implemented; general domain event streaming is not.

## Next Work

1. Add SQLite persistence behind Rust commands.
2. Connect the existing FastAPI backend health/integration state beyond the read-first Drive view.
3. Replace remaining command-backed sample data when the associated product
   surfaces are prioritized again.
