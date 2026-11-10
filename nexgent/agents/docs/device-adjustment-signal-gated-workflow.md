# Device adjustment: signal-gated AS completion

Date: 2026-11-09

The corrected 기기위치조정/전원연결 workflow accepts a Korean name, or name
and address. It confirms the device signal before changing AS. This supersedes
the earlier proposal to write master-page general notes; no such write is part
of this implementation.

## Verified IMEI column correction (2026-11-09)

The reported input `영덕군 영덕읍 영덕대게로 699김   영호,기기위치조정 수신확인요~`
already parses as name `김영호`, address `영덕대게로 699`, mode `name_address`.
No parser change was needed. The failure at 영덕 Y953 came from reading S/N
as a 15-digit IMEI. Live read-only inspection of all three configured tabs
confirmed these row-4 headers:

| Roster | S/N (old, incorrect mapping) | 단말 IMEI (실데이터) |
| --- | --- | --- |
| 울진 | Z | AA |
| 광명 | V | W |
| 영덕 | Y | Z |

The shared standalone/unified IMEI reader now uses AA/W/Z. API and browser
receipt validation enforce the same per-city mapping; the Test picker labels
also use the corrected columns. Columns remain explicit and there is no
adjacent-cell fallback. Invalid IMEI or changed identity still stops execution.

A live read-only run of the exact input through the parser, ordered roster
lookup and corrected IMEI reader found no 울진/광명 match, then selected 영덕
row 953 with the expected name/address and a valid 15-digit Z953 value. Y953
is six digits. No signal request or sheet write was made, and the actual IMEI
was excluded from diagnostic output.

The supplied-input fixture now fixes S/N and IMEI columns independently of
production constants, putting a six-digit S/N beside the valid IMEI. This
prevents tests from reproducing and concealing the configuration mistake.
The unnumbered reported input is included in connected/disconnected and
quoted/plain scenarios. API and frontend tests accept each corrected city
column and reject its S/N column, even with a valid-looking IMEI value.

Validation for this correction: 162 agent tests, 68 backend tests and 67
frontend tests passed (297 total). Agent Ruff check and the frontend production
build passed; the existing large-bundle warning remains. Commands:

```bash
# agents/
uv run pytest tests/unit/test_ax768_imei.py tests/unit/test_ax768_unified.py tests/unit/test_ax768_supplied_inputs.py tests/unit/test_ax768_as_update.py -q
uv run ruff check workflows/ax768/imei_case.py tests/unit/test_ax768_imei.py tests/unit/test_ax768_supplied_inputs.py
# backend/
.venv/bin/python -m pytest tests/test_ax768_workflow.py tests/test_ax768.py -q
# frontend/
npm test -- src/shared/api/ax768WorkflowClient.test.ts src/shared/api/ax768Client.test.ts src/features/agents/Ax768WorkbenchPage.test.tsx src/features/agents/Ax768WorkflowPanel.test.tsx src/shared/i18n/i18n.test.tsx
npm run build
```

Both source checkouts contain the correction. The image-backed Agent Server
must be rebuilt using the activation command below. Attempting that command
with `sudo -n` returned `interactive authentication is required`; activation
and a live signal/AS-update check remain unverified. Workflow schema version
remains 4 because this corrects column configuration without changing the
receipt structure. Do not interpret the live roster/IMEI read as evidence of
a connected device or completed AS update.

## Acceptance and execution

1. Parse one request, including bare `김순옥`, `김순옥님 신호확인요`, comma
   input, `699김영호`, and `김   영호` after an address.
2. For name-only input, search AS bottom-up for the latest exact name, read its
   address, and use that identity for roster lookup. Missing AS, blank address
   or a read failure stops before querying a device. An AS-derived identity is
   not automatically replaced with a similar name in a roster.
3. Search rosters sequentially in the established 울진 → 광명 → 영덕 order,
   advancing only on no match, stopping at the first same-row name/address
   match. Missing all rosters or a read failure stops. For supplied name/address
   input, existing address-grounded typo correction and confirmation remain.
4. Re-read the selected roster name/address together with its IMEI. Columns are
   exactly 울진 **AA**, 영덕 **Z**, 광명 **W**. IMEI must be 15 digits. Changed
   identity or invalid/missing IMEI stops; the workflow never substitutes a
   different row or column to obtain an IMEI.
5. Use the existing authenticated fixed-origin Ansimk adapter to call
   `https://dev-check.ansimk.com/api/admin/ping` with the IMEI in its `sn` input
   field. The returned serial number is distinct from that input and preserves
   leading zeros. A valid response must echo the IMEI and a boolean connection
   result; positive connection also requires `fresh: true`.
6. Disconnected: return `S/N 0000 전원 연결 및 기기위치 확인해주세요.` with
   the returned serial number. Skip AS mutation. Transport/authentication,
   timeout, malformed and stale-positive results are failures, never invented
   disconnection results.
7. Connected: return `S/N 0000 신호 확인되었습니다.` with the returned serial
   number. Resolve the latest matching AS name/address row if it was not already
   selected for name-only input. Recheck and update the selected row using the
   existing completion writer, then verify readback. Missing AS means no write
   while retaining the successful signal result.

AS changes remain S=`처리완료`, X=today in Asia/Seoul, and Y=`위치점검완료`
when C=`기기위치 점검`, or `전원연결완료` when C=`기기전원 연결`; other C
values leave Y unchanged. Name-only input retains the initially selected AS row
and rechecks that row before writing. There is no automatic mutation retry or
rollback. Unknown write results remain unknown and require inspecting the row
before manually rerunning.

## Contract and report

`ax768_workflow` now advertises `workflow_version: Literal["4"]`. The product
API refuses older runtimes before dispatch. The public `workflow_id` stays
`device_adjustment_power`; the route and agent IDs stay unchanged.

State adds a small `signal` receipt with status, IMEI column/value, returned S/N,
connection/freshness, signal label/RSSI and failure reason. The API exposes only
those bounded fields. The graph update node, API normalization and frontend
validation all require a verified connected signal for an updated AS receipt.
The new `disconnected` outcome has no AS update. Existing `failed`, `not_found`,
`blocked` and `needs_confirmation` outcomes retain available stage evidence.
Each new invocation clears previous signal/update receipts.

The result screen presents roster evidence, signal evidence, latest AS match
and AS update/readback. A connected signal remains visible if AS lookup or
updating subsequently fails; an unknown AS write is never presented as saved.
Input selection remains a required compact dropdown.

The existing IMEI test case reuses the extracted `read_roster_imei` helper and
keeps its search-only/no-AS-write policy. Name-only resolution from AS applies
to the unified Workflow, not to the separate IMEI Test case.

Maximum stage budgets are AS lookup 45s (once per run), ordered rosters 100s,
IMEI recheck 20s, signal 60s, and AS update 40s, within the existing 270s product
API / 285s browser timeout. Ansimk authentication retains the existing private
cookie cache and single explicit-401 reauthentication policy. Credentials,
cookies and raw device payloads never enter reports.

## Validation

### Exact operator-input acceptance update (2026-11-09)

`tests/unit/test_ax768_supplied_inputs.py` now has 34 passing checks for the eight
exact supplied examples. Each is run both as plain text and wrapped in double
quotes, with both connected and disconnected responses (32 checks). The suite
uses the real graph, Sheets lookup, roster IMEI recheck, Ansimk response
validation, and AS update/readback code with synthetic HTTP services. Every HTTP
request is intercepted; names and addresses below are test inputs, not claims
about the live subscriber records. Synthetic roster assignments exercise AA/W/Z.

| Input form | Parsed identity | Address handling |
| --- | --- | --- |
| 김순옥님 신호확인요. | 김순옥 | Latest AS name row supplies address before roster lookup |
| 울진북로 164 김순옥님 신호확인요. | 김순옥 | 울진북로 164 |
| 지영희님 신호확인요 & 상밤터1길 59-4(사진). | 지영희 | 상밤터1길 59-4; `(사진)` is text, not OCR |
| 왕피길83-15,정영자,기기위치조정 수신확인요~ | 정영자 | 왕피길 83-15 |
| ① 영덕군 영덕읍 영덕대게로 699김영호,기기위치조정 수신확인요~ | 김영호 | 영덕대게로 699 |
| ② 영덕군 영덕읍 영덕대게로 699김   영호,기기위치조정 수신확인요~ | 김영호 | 영덕대게로 699 |
| 영덕군 영덕읍 영덕대게로 699김   영호,기기위치조정 수신확인요~ | 김영호 | 영덕대게로 699; exact reported failure |
| 3 영덕군 영덕읍 영덕대게로 699긴 영호,기기위치조정 수신확인요~ | 긴영호 | Same-address unique candidate 김영호 is rechecked before use |

Two additional checks verify that multiple typo candidates require confirmation
without signal/write activity, and that all three numbered lines pasted together
are blocked before any I/O. This is still a one-person-per-run workflow. The
tests assert bottom-most row selection, signal-before-write ordering, exact S/N
messages, one verified AS write for connected devices, and zero AS writes for
disconnected devices. No production behavior change was needed for these inputs.

Repeat from `agents/`:
`uv run pytest tests/unit/test_ax768_supplied_inputs.py -q`.
Ruff lint/format checks passed. These checks do not verify live sheet contents,
current device connectivity or runtime deployment; the activation caveat below
still applies.

### Implementation regression checks

- 285 agent/adapter regression tests passed, including the exact text formats,
  AS-first address handoff, all roster positions, IMEI city columns, stale or
  incorrect signal evidence, disconnected/API-error paths without AS writes,
  missing/blank AS address, fresh state, and uncertain AS-update reports.
- 65 backend tests passed, including version-3 rejection, permissions,
  disconnected reports, and rejection of unverified completion evidence.
- 55 frontend tests passed; production build and offline Cargo check passed.
  Vite retains its existing large-bundle warning.
- Chromium with synthetic intercepted API responses verified required
  selection, connected completion, disconnected/no-update, signal failure,
  connected/unknown-AS-write, and a 390px layout. Screenshots and check script:
  `/tmp/device-signal-workflow/`. The served module at the actual development
  URL was also checked and contains the new signal-result UI.
- Agent Python Ruff lint and format checks passed. Existing Python 3.14 pytest
  deprecation warnings remain. Dependency versions are unchanged; the previously
  observed npm audit findings remain separate maintenance work (4 low, 2 moderate,
  2 high, confirmed again during this change).

Repeat from `agents/`:

```bash
uv run pytest tests/unit/test_ax768*.py tests/unit/test_ansimk.py -q
uv run ruff check workflows/ax768/unified_graph.py workflows/ax768/imei_case.py workflows/ax768/request_parser.py apps/ax768/run.py tests/unit/test_ax768_unified.py
```

From `backend/`: `.venv/bin/python -m pytest tests/test_ax768_workflow.py tests/test_ax768.py -q`.
From `frontend/`: `npm run build` and
`npm test -- src/shared/api/ax768WorkflowClient.test.ts src/features/agents/Ax768WorkbenchPage.test.tsx src/features/agents/Ax768WorkflowPanel.test.tsx src/shared/i18n/i18n.test.tsx`.

## Activation and remaining live verification

The development UI at `http://192.168.0.18:5173/agents/ax768` serves the primary
checkout `/home/nextor-ai-02/nextor_ai/ax-project`. Apply code there and to the
isolated worktree; preserve the primary checkout's existing uncommitted routing
and UI changes. Backend and frontend use development source reload. Agent Server
is image-backed with `--no-reload`, so source changes alone do not activate v4.

This session cannot rebuild the container: Docker socket access is denied and
`sudo -n` requires interactive authentication. On the host, run:

```bash
cd /home/nextor-ai-02/nextor_ai/ax-project/nexgent
sudo docker compose -f compose.yaml up -d --build --no-deps agent-server
sudo docker compose -f compose.yaml logs --tail=80 agent-server
```

After activation, open the Workflow tab and run an operator-approved test
record. A connected response will update its AS row. For an explicit CLI live
check (also writes AS when connected), run from the primary `agents/` directory:

```bash
uv run python -m apps.ax768.run --workflow '<approved name and address>'
```

No live subscriber signal requests or AS writes were executed during validation.
The 2026-11-09 column correction below revalidated live headers and the reported
영덕 row read-only. Columns are fixed to the verified IMEI headers; invalid
values still fail closed.
Update 2026-11-10: the AX768 page now prepares text from images locally; see
[Korean image input](ax768-korean-image-input.md). The execution graph still
receives text only. KakaoTalk ingestion remains outside this workflow. Sheets offers no compare-and-set transaction across
the identity recheck and write, so concurrent edits remain an existing limitation.
