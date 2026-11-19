# Device adjustment workflow member general-note replacement

Date: 2026-11-10

## Update — 2026-11-19

The device workflow now **appends** to the last line and preserves history,
matching both name and address. The replacement behavior below describes the
original implementation. See [current policy and activation](device-workflow-append-general-notes.md).

## Implemented behavior

Only the AX768 `기기위치조정/전원연결` workflow gains a final member-admin
step. After resolving the roster identity and verifying a fresh connected
signal, it updates the matching AS row if present, then replaces the entire
member **일반 사항** field and verifies readback. It uses the existing private
member credentials and fixed `https://api.ansimk.com` adapter, backing
`https://admin.ansimk.com/members`.

The note format is one of:

```text
YYYY-MM-DD [현지관리자 방문] 기기위치조정
YYYY-MM-DD [현지관리자 방문] 전원연결
```

The supplied example date is a format example, not a constant. With an AS
update, the note uses its verified processing date (Asia/Seoul). Without an AS
row, it uses the current Asia/Seoul date when the member step runs. An explicit
request action wins; for a signal-only request, the verified AS Y completion
value supplies the action (`위치점검완료` or `전원연결완료`). If neither identifies
the action, member writing stops with an actionable message. Both actions in
one request are rejected before I/O. No action is guessed.

A confirmed missing AS row skips the AS mutation and permits the member step
when roster identity, signal and action are available. Failed AS lookup or a
failed/uncertain AS update stops before member access. Name-only requests still
need an AS address before roster/device resolution, so missing AS in that path
stops before any device or member write. Disconnected/stale/unverified signal
results cannot reach either writer.

## Contracts and implementation

- `workflow_member_note.py` owns action selection, note construction, the
  signal/AS gate and member-stage outcome. `unified_graph.py` sequences the new
  `member_note_step` after verified AS completion or confirmed AS absence.
- The existing replacement implementation searches with the resolved roster
  name **and address**, including corrected names. A unique exact match, or
  unique partial name when no exact match exists, saves directly. Address
  equality ignores Unicode normalization/spacing only. No name-only fallback
  discards the known address. Multiple members are reported without writing.
- Only `general_notes` is written. The old value is replaced, including all
  other lines. Whole-field equality skips the PUT; reads before and after the
  write validate identity and text. Writes are not retried automatically.
- Workflow version is **5**. The product API rejects earlier runtime schemas.
  An explicitly supplied older graph version also stops before I/O. Direct
  in-process callers omitting a version use current behavior.
- `member_note` is `null` when not executed, otherwise the bounded existing
  member receipt. Backend and browser validate identity against the roster,
  allowed note format, date agreement, stage ordering and readback evidence.
  Completion requires verified member replacement or existing identical text.
  The signal and AS receipts survive member failures/uncertain writes.
- The UI adds **5. 가입자 일반 사항**, showing saved/requested text, member
  identity, outcome, and the fixed member-admin link. The completed label also
  applies when AS was absent. No new permission step is introduced.
- API timeout becomes 420s and browser timeout 435s to cover the existing stages
  plus the bounded 120s member step. No new process, dependency or secret mount.

## Validation and activation

- 166 agent tests passed across unified routing, the supplied Korean requests,
  member-step policies and the existing replacement implementation. Synthetic
  HTTP exercises the full signal → AS write/readback → member replacement/
  readback sequence. The 100 graph/member-step tests were rerun after the final
  skipped-AS explanation change and passed.
- 92 backend tests and 62 frontend tests passed (320 distinct focused tests).
  They include version-4 rejection, missing/invalid member completion evidence,
  no-AS completion, and preserved AS evidence after uncertain member writes.
- TypeScript/Vite production build, offline Cargo check, Ruff and
  `git diff --check` passed. The existing bundle-size warning remains. Required
  npm audit reports the existing 8 findings (4 low, 2 moderate, 2 high); no
  dependencies changed.
- Chromium smoke passed at the actual LAN AX768 URL, with mocked product APIs:
  adjustment, power connection without AS, uncertain member result,
  disconnected/skipped member step, and 390px layout. Screenshots are in
  `/tmp/ax768-workflow-member-note-artifacts/`.
- No real AS/member mutation was made. Source changes are in both the worktree
  and serving primary checkout. The activation attempt failed because
  `sudo -n` requires interactive authentication; version 5 runtime activation
  remains pending. Run the exact rebuild command below before a real workflow.


Repeat from `agents/`:

```bash
uv run pytest tests/unit/test_ax768_unified.py tests/unit/test_ax768_supplied_inputs.py tests/unit/test_ax768_workflow_member_note.py tests/unit/test_ax768_member_note.py -q
```

From `backend/`:

```bash
.venv/bin/python -m pytest tests/test_ax768_workflow.py tests/test_ax768_member_note.py tests/test_ax768.py -q
```

From `frontend/`:

```bash
npm test -- src/shared/api/ax768WorkflowClient.test.ts src/shared/api/ax768MemberNote.test.ts src/features/agents/Ax768WorkflowPanel.test.tsx src/shared/i18n/i18n.test.tsx
npm run build
cargo check --offline --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
AX768_TEST_URL=http://192.168.0.18:5173 node scripts/ax768-workflow-member-note-smoke.mjs
```

The image-backed Agent Server requires activation from the primary `nexgent/`
checkout; frontend/backend use source reload:

```bash
cd /home/nextor-ai-02/nextor_ai/ax-project/nexgent
sudo docker compose -f compose.yaml up -d --build --no-deps agent-server
sudo docker compose -f compose.yaml logs --tail=80 agent-server
```

## Limits

AS and member writes are separate remote operations, without a transaction or
rollback. An AS update may remain saved if the member operation fails. A
concurrent external member edit can still race the final preflight GET/PUT,
since the upstream exposes no conditional update contract. Inspect both records
after an uncertain overall result. A member with a differently formatted address
beyond whitespace/Unicode normalization will not be silently matched. Ambiguous
members are shown for resolution; this workflow does not accept a member-ID
override. The standalone member Test case retains that separate capability.
