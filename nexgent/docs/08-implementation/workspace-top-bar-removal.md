# Workspace Top Bar Removal

Date: 2026-09-10

Removed the shared workspace search and Pause header from AppShell for every route. The main grid now has one full-height content row, reclaiming the former 64px header space. Removed unused header styles, icons, and search subscriptions. Sidebar navigation and page-specific controls remain available; Chat retains its existing content overflow behavior.

Settings now displays only “Coming Soon”.

## Validation

- `npm run build`: passed.
- `git diff --check`: passed for the UI changes.
- `cargo check --manifest-path src-tauri/Cargo.toml`: blocked by a missing generated Tauri app_hide.toml permissions file referenced under the workflow-helper build directory.
- `npm audit --audit-level=moderate`: blocked by registry.npmjs.org DNS resolution (EAI_AGAIN).

## Remaining verification

Run commands from `frontend/`. After repairing the Rust build environment, rerun `cargo check --manifest-path src-tauri/Cargo.toml`. With registry connectivity, rerun `npm audit --audit-level=moderate`.

Interactive desktop/browser validation was not performed in this change. Run `npm run dev -- --host 127.0.0.1` and visit each sidebar page at wide and narrow desktop widths to verify scrolling and the absence of the shared top bar.
