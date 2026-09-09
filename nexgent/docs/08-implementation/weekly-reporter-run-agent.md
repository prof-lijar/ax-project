# Weekly Reporter Run Agent

Date: 2026-09-08

## Implementation

Weekly Reporter (`/agents/1`) now offers **Run Agent** using the existing bulk
API adapter. The default limit is 10,000: all eligible reports up to the API's
per-job maximum. The operator can lower the limit and must still select the
existing live-run approval checkbox. Submission and the selected active run
prevent duplicate starts; switching to another recent run is disabled while
that run is active.

The status indicator spins through queueing, discovery, generation, packaging,
and cancellation, then changes to a completed or attention indicator. Text
labels and reduced-motion styling supplement color and animation.

Elapsed time updates once per second while the selected job is active. Terminal
states use server `updated_at` minus `created_at`, so the duration remains fixed
when viewed later. The API does not expose a separate completion timestamp;
expiry or another later terminal-state update can change the recorded duration.
Progress uses the discovered count once discovery ends, so a source smaller
than the requested limit can reach 100%. Truncated selections explicitly state
that additional wards were excluded.

## Architecture and operational limits

This extends the existing shared HTTP product adapter; no shell, filesystem,
credentials, Tauri permissions, or backend changes were added. Existing behavior
still cancels the selected active run on navigation, page close, or Stop & refresh.
The server API limit remains 10,000; this does not implement unlimited batches
or continuation beyond that limit. Polling errors leave the last known state
visible and the timer running until the server confirms a terminal state.

## Validation

- `npm run build`: passed.
- `npm test`: 211 tests passed, including frozen terminal durations, discovered
  report progress, partial failures, and packaging indicators.
- `cargo check --manifest-path src-tauri/Cargo.toml`: stale build metadata
  referenced the former workflow-helper path and failed.
- `CARGO_TARGET_DIR=/tmp/nexgent-cargo-check cargo check --manifest-path src-tauri/Cargo.toml`:
  passed using a separate target directory.
- `npm audit --audit-level=moderate`: blocked by npm registry DNS failure
  (`EAI_AGAIN`). Run that exact command again with registry access.

Live report generation was not executed: it invokes the private model and
processes live care data. Remaining interactive verification command from
`frontend/`:

```bash
npm run dev -- --host 127.0.0.1
```

Open `/agents/1`, choose the report week, check the existing live-run approval,
and select Run Agent. Verify status transitions and exported reports, and confirm
elapsed time stops after completion or cancellation. This requires the configured
bulk API, job database, and worker to be available.
