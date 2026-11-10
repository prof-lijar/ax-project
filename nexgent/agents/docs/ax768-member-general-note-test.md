# AX768 member general-note Test case

Date: 2026-11-10

## Scope and input

The AX768 Test tab at `/agents/ax768` adds **가입자 일반 사항 기록** (`member_note`).
This separate case searches `https://admin.ansimk.com/members` through its own
API and replaces the entire **일반 사항** field with the entered dated text. It does not extend the device
adjustment Workflow or change Google Sheets, member status, devices, guardians,
or other member fields.

The editable example is exactly the operator's supplied example:

```text
이름: 이은경
일반 사항: 2026-10-28 [현지관리자 방문] 기기위치조정
```

`주소:` and `가입자 ID:` are optional disambiguation fields. The date is explicit,
not replaced with today's date. Input is one labeled request, one valid ISO date
and a note of at most 500 characters. Duplicate/unknown fields, missing names,
invalid IDs/dates and multiline notes are rejected before login.

The case saves directly when the supplied conditions identify one exact-name
member, or one partial-name member if no exact name matches. Supplied address
and ID constrain both paths; they are never ignored. Multiple matches return
candidates without writing. Selecting one fills its identity; run
**가입자 검색 및 일반 사항 교체** to update that member. No separate permission
step is required. Existing general notes are replaced, including other lines.

## Replacement update — 2026-11-10

The user clarified that the Test case must apply the update itself and replace
rather than append. Version 2 enforces this semantic change: both the graph and
product API reject version 1, so an old image cannot silently append. The UI
labels and description now state replacement. Only whole-field equality skips
a PUT; a matching line surrounded by other text must still replace the field.
No live replacement was performed during this implementation. An earlier,
separately authorized append was verified before this clarification.

## Verified API contract

Public runtime configuration identifies `https://api.ansimk.com` as the API.
The public member module and authenticated OpenAPI schema confirmed:

- Login: `POST /token/` with `username` and `password`; retain the access token
  in process memory only.
- Search: `GET /api/admin/wards/?search=...&page=...&pageSize=50`; response is
  `{data, totalItemCount, totalPages}`. Search can match fields other than the
  member name, so the workflow independently checks `full_name`.
- Detail: `GET /api/admin/wards/{id}/`; response is `{data: {...}}`.
- Update: `PUT /api/admin/wards/{id}/update/` accepts only fields to change.
  This adapter sends exactly `{"general_notes": "<entered text>"}`.
- The visible **일반 사항** field is `general_notes` with a 2,000-character limit.

Discovery was read-only apart from authentication. A live search for `이은경`
returned one partial-name candidate stored as `넥스터_이은경`. The live detail
endpoint was inspected for field shape, note length and concurrency headers;
existing note content was not printed or written to documentation. No ETag was
returned. These observations describe the verification run, not immutable
future membership data.

## Architecture and safeguards

`ax_integrations.ansimk_members.AnsimkMembersClient` owns fixed-origin HTTP and
credential loading. It never imports workflows. Redirects are disabled. Tokens,
passwords and raw error bodies are excluded from receipts. Requests have 20s
HTTP limits; the full case has a 120s bound. Search is bounded to 10 pages / 500
results and refuses incomplete, inconsistent or duplicated pagination. No write
request is automatically retried.

`workflows/ax768/member_note.py` owns parsing, constrained exact/partial name
selection, full-field replacement and readback verification. It reads the
selected member and compares the whole existing field with the entered value.
Equality returns `already_present` without a PUT. Otherwise it rereads identity
and notes immediately before one PUT; changes stop the write. A final GET must
match identity and the entire entered text. The parser limits input to 500
characters, within the upstream 2,000-character field limit.

Readback failure, mismatch, timeout or an unexpected error after PUT dispatch
returns `unknown`. Explicit 4xx rejection returns `failed`. No automatic retry
or rollback occurs.

The existing `ax768` graph handles this case before Google configuration and
model routing. The new input capability is `member_note_case_version: "2"`.
CLI `--case member_note` supplies it. The product API checks runtime support
before dispatch. Existing `case_policy: "search_only"` continues to govern the
old numbered/IMEI tests and is not sent for this explicitly mutating member case.
No new process, service, LLM, browser runtime dependency or package is required.

The admin/CSRF-protected product API validates a dedicated minimal receipt.
It allows `note_saved` only with verified identity, dated note and readback;
it strips unrelated member data. The frontend similarly validates receipts,
keeps history in the existing session store, shows member candidates and uses
a fixed `https://admin.ansimk.com/members` link. No credential enters browser
state or the frontend request.

## Credentials and activation

The operator created the private host file and set mode 600:

`/home/nextor-ai-02/.local/share/nexgent/ansimk-members-credentials.json`

Its JSON keys are `username` and `password`. Do not put values in Git, UI state,
logs or conversation messages. These are separate credentials from the
`dev-check.ansimk.com` signal-check code/session.

Compose mounts this file read-only at `/run/ax768/members-credentials.json` in
Agent Server and sets `AX768_MEMBERS_CREDENTIALS_FILE` accordingly. The host
path can be overridden by `AX768_MEMBERS_CREDENTIALS_HOST_FILE` in the Compose
environment. `create_host_path: false` prevents silently creating a directory
where a missing secret file should be. Other environments must create the
private file before starting the updated Compose service. Host CLI execution
uses the same private default or an explicit `AX768_MEMBERS_CREDENTIALS_FILE`.

Both the primary development checkout and isolated worktree contain the change.
Existing layout differences between those copies were preserved. Backend and
frontend use source reload. Agent Server is image-backed and needs rebuilding:

```bash
cd /home/nextor-ai-02/nextor_ai/ax-project/nexgent
sudo docker compose -f compose.yaml up -d --build --no-deps agent-server
sudo docker compose -f compose.yaml logs --tail=80 agent-server
```

The attempted `sudo -n` activation failed with `interactive authentication is
required`. Direct Docker activation also failed with socket permission denied.
`docker compose -f compose.yaml config --services` passed without sudo.
Runtime activation remains unverified; until rebuilt the API returns
409 for this case before any member operation.

After rebuilding, open AX768 → Test → 가입자 일반 사항 기록 → 예시 입력.
Run once to replace the uniquely identified member's general notes. Multiple
matches require member selection and another Run. This is a real mutation. Do not run the example
against a real person merely to test a deployment unless that note is intended.

## Replacement validation — 2026-11-10

- 32 workflow tests passed: exact and unique partial-name selection, multiple
  partial matches, explicit address/ID constraints, replacement of all old lines
  (including an already-matching line), whole-field equality, repeat execution,
  concurrent change detection, denied writes and uncertain readback. Version 1
  cannot dispatch a replacement.
- 39 backend tests passed, including rejection of the old append capability and
  dispatch of version 2 only. 46 frontend tests passed.
- Ruff and `git diff --check` passed. Production build and offline Cargo check
  passed. Required npm audit still reports 8 existing vulnerabilities (4 low,
  2 moderate, 2 high); no dependencies changed.
- Chromium smoke passed on `http://192.168.0.18:5173/agents/ax768` with product
  APIs mocked: direct unique-member success, disambiguation of multiple members,
  equality/unknown receipts and 390px layout. No live replacement was made.
- Updated sources are in both checkouts. Activation was attempted again: sudo
  requires interactive authentication and direct Docker access is denied. The
  rebuild command above remains required; version gating blocks stale runtime
  execution until then.

## Initial append-version validation (historical)

- 343 affected agent/integration tests passed, including 24 new member-note
  tests. They cover input validation, preserved existing text, duplicate
  avoidance, partial/multiple/missing matches, explicit IDs, changed identity,
  concurrent preflight changes, size limits, denied writes, transport uncertainty,
  readback failure/mismatch, private credential mode and full pagination.
- 82 backend tests passed, including new capability, admin/CSRF, public-receipt
  sanitization and rejection of unverified save evidence.
- 50 frontend tests passed. TypeScript/production build and offline Cargo check
  passed. Existing large-bundle warning remains. Required npm audit reports the
  existing 8 findings (4 low, 2 moderate, 2 high); dependencies were not changed.
- Chromium smoke test passed at the actual development AX768 URL with mocked
  product APIs: nine cases, candidate selection without automatic saving,
  selected member input, confirmed save, already-present and unknown outcomes,
  and a 390px layout. Screenshots are under `/tmp/ax768-member-note-artifacts/`.
- Real credentials authenticated successfully and the account endpoint confirmed
  admin access. The implemented case returned the partial-name candidate from
  a live search using a verification transport that forbids member writes.
- That initial validation did not write live notes; a separately authorized
  append was subsequently saved and verified before the replacement request.

Repeat tests from `agents/`:

```bash
uv run pytest tests/unit/test_ax768*.py tests/unit/test_ansimk.py -q
uv run ruff check packages/integrations/src/ax_integrations/ansimk_members.py workflows/ax768/member_note.py tests/unit/test_ax768_member_note.py workflows/ax768/cases.py workflows/ax768/graph.py apps/ax768/run.py
```

From `backend/`:

```bash
.venv/bin/python -m pytest tests/test_ax768_member_note.py tests/test_ax768.py tests/test_ax768_workflow.py -q
```

From `frontend/`:

```bash
npm test -- src/shared/api/ax768Client.test.ts src/shared/api/ax768MemberNote.test.ts src/features/agents/Ax768WorkbenchPage.test.tsx src/features/agents/Ax768MemberNote.test.tsx src/shared/state/useAx768Store.test.ts src/shared/i18n/i18n.test.tsx
npm run build
cargo check --offline --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
AX768_TEST_URL=http://192.168.0.18:5173 node scripts/ax768-member-note-smoke.mjs
```

The optional browser script accepts `PLAYWRIGHT_MODULE`,
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` and `AX768_TEST_ARTIFACTS` overrides. It mocks all
product API calls and never writes a real member.

## Remaining limitations

The upstream update endpoint does not advertise an atomic conditional update or
compare-and-set contract, and live detail responses lacked ETag. An external
edit between the final GET and PUT can race the replacement; rereads/readback reduce
uncertainty but cannot eliminate that race or guarantee exactly-once delivery
across processes/crashes. Inspect uncertain outcomes before rerunning. The
case does not resolve unrelated AS lookup failures in the device workflow.
