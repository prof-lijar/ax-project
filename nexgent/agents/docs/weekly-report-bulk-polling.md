# Weekly-report bulk polling reliability

Date: 2026-09-08

The browser reported `net::ERR_NO_BUFFER_SPACE` while monitoring a 10,000-report
job. Inspection found an unbounded accumulation path: a two-second interval
started status fetches regardless of outstanding requests, and the HTTP client
had no deadline. This is a plausible contributor, not a confirmed live diagnosis
of the client operating system's socket-buffer exhaustion.

The frontend now uses `pollWeeklyReportJob` to await each status response before
scheduling another. Successful requests wait the server-advertised interval;
failures double that delay up to 30 seconds, and success resets it. Terminal
responses stop polling. Effect cleanup clears the timer, aborts the request,
and ignores late results. The effect depends on the active job identity so
intermediate status transitions do not create replacement polling loops.

Bulk JSON requests have a 30-second deadline covering headers and body reads,
forward caller cancellation, and remove timers/listeners on settlement. POSTs
are not automatically retried. The report limit, worker concurrency, and existing
page-lifecycle job cancellation behavior are unchanged.

Validation from `frontend/`:

- `npm test`: 216 tests passed across 21 files, including slow-response,
  exponential-backoff, terminal-state, cleanup, timeout, and cancellation cases.
- `npm run build`: TypeScript and Vite passed.
- `npm audit --audit-level=moderate`: zero vulnerabilities.
- `CARGO_TARGET_DIR=/tmp/bulk-poll-cargo cargo check --manifest-path src-tauri/Cargo.toml`: passed.

A live 10,000-report reproduction was not run. Remaining browser verification:
run `npm run dev -- --host 0.0.0.0`, open the Weekly Reporter, and observe a
user-approved bulk run with DevTools Network throttling. Verify that only one
status GET remains pending per panel, failures increase the retry interval,
and terminal completion stops GETs. Existing navigation/refresh behavior cancels
an active run, so do not reload the page merely to investigate a running job.
