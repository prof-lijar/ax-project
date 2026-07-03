# Desktop App Status

Date: 2026-07-03

## Summary

The first Linux desktop implementation has been added under `frontend/`. It provides a Tauri 2 desktop shell, a React + TypeScript operator UI, and a secure Rust command boundary with sample workflow data.

The app is usable as a web preview and builds successfully as a Debian package.

## What Is Done

- Created `frontend/` as a Tauri 2 + React + TypeScript + Vite project.
- Added a simplified Mission Control first screen with:
  - one primary decision area
  - current work
  - co-worker presence
  - recent activity
- Added secondary views for Tasks, Approvals, Team, Activity, and Settings.
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
- CSP is restricted to local bundled assets and IPC/local development endpoints.
- Credentials are not stored in frontend state.
- Approval and task data are sample data only; destructive actions are not implemented.
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
frontend/src-tauri/target/release/bundle/deb/Workflow Helper_0.1.0_amd64.deb
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
- Nextcloud backend integration is not wired into the desktop UI yet.
- Approval decisions are visible in the UI but do not mutate persistent state yet.
- AppImage bundling is not enabled by default because it failed in this environment with a read-only filesystem error.
- The Tauri icon is a generated placeholder and should be replaced with a proper product icon.
- Event streaming is represented in the architecture but not implemented yet.

## Next Work

1. Add SQLite persistence behind Rust commands.
2. Implement approval decision commands and audit events.
3. Connect the existing FastAPI backend health/integration state.
4. Replace seed data with persisted task, approval, agent, and activity records.
5. Add focused frontend tests for approval controls, task status rendering, and event reconciliation.
