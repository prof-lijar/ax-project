# Chat 50 MiB upload limit

Date: 2026-10-30

Chat now accepts up to 50 MiB (52,428,800 bytes) per file, with a 50 MiB
combined limit per turn and a maximum of five attachments. Raising the combined
limit from 25 MiB allows a single 50 MiB upload. UI labels use MB, consistently
with the existing byte formatter. This supersedes the limits in earlier chat
attachment and persistent-history implementation records.

Updated frontend selection, composer and saved-file validation, English/Korean
messages, backend upload/normalized-reference validation, durable original reads,
and agent attachment contracts/readers. Existing extraction limits (100,000
characters), image pixel limits, accepted formats and DOCX expansion limits still
apply independently; a large file can fail content validation after passing size
validation.

Validation:

- Frontend attachment/API tests: 25 passed; TypeScript/Vite build passed.
- Live Vite module at 192.168.0.18:5173 serves the new 50 MB validation message
  and no longer serves the old 10 MB message.
- Backend attachment and saved-chat tests: 30 passed, 1 environment-dependent skip.
- Agent attachment/contract tests: 19 passed; scoped Ruff and diff checks passed.
- Boundary coverage accepts exactly 50 MiB, rejects one extra byte, and reads
  saved originals exceeding the former 10 MiB limit.
- Required desktop cargo check is blocked by a stale Tauri build-cache path
  pointing to workflow-helper/frontend/src-tauri/target. No Rust code changed.
- Required npm audit reports 8 existing dependency findings (4 low, 2 moderate,
  2 high). Dependency versions were not changed in this task.

Runtime rollout could not be completed: this account lacks Docker socket access
and sudo requires interactive authentication. Development frontend/backend use
source mounts, but Agent Server and chat-worker require rebuilt images. From
nexgent/, run:

```bash
sudo docker compose up -d --build --no-deps backend chat-worker agent-server
```

Refresh the chat page, upload a supported file between 10 and 50 MiB whose
extracted content fits the existing limits, and confirm it can be downloaded
and reused from saved files. A full live authenticated upload remains unverified.

