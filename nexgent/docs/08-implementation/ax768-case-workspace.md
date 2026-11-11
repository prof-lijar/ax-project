# AX768 case workspace

Date: 2026-11-04

## Member general-note Test case (2026-11-10)

The Test tab adds `member_note` (가입자 일반 사항 기록): member search and
explicit candidate selection, append to `general_notes` preserving existing
text, duplicate-line avoidance, and verified readback. It uses separate private
member-admin credentials and a dedicated read-only Compose mount. The device
workflow remains unchanged. Runtime capability gating prevents execution on an
older Agent Server. Login/live search succeeded; 475 affected tests, browser
checks, production build and Cargo check passed. All test writes were mocked.
Activation still requires a host rebuild because noninteractive sudo failed.
See [implementation and activation](../../agents/docs/ax768-member-general-note-test.md).

## AX768 Korean image input (2026-11-10)

The Workflow composer at `/agents/ax768` now enhances uploaded images locally,
extracts Korean text and fills editable 이름/주소/요청 fields. This is limited
to the AX768 page. Reviewed fields are converted into the existing text request
on explicit Run, so no Agent Server rebuild or API change is required. The
former requirement to manually transcribe and remove every image is superseded.

Actual Chromium OCR passed at `http://192.168.0.18:5173/agents/ax768` with
synthetic Korean images and mocked product APIs; no signal requests or AS writes
occurred. 74 focused tests and the frontend build passed. See
[implementation and limitations](../../agents/docs/ax768-korean-image-input.md).

## IMEI column mismatch resolved (2026-11-09)

The reported `699김   영호` input parsed correctly and matched 영덕 row 953.
Live read-only checks confirmed the actual IMEI headers are 울진 AA, 광명 W,
영덕 Z; the previously requested Z/V/Y columns contain S/N. The shared reader,
API/browser contracts and displayed column labels now follow those verified
headers. This resolves the historical column-clarification note below. The
exact input successfully read a valid IMEI from Z953 without a signal call or
AS write. 297 affected tests passed. Runtime rebuild remains necessary; the
attempt failed because sudo requires interactive authentication. See the
[correction evidence and activation command](../../agents/docs/device-adjustment-signal-gated-workflow.md).

## Signal-gated device adjustment (2026-11-09)

Unified workflow v4 resolves a name-only request's address from the latest AS
name row, finds the corresponding roster IMEI (울진 AA, 영덕 Z, 광명 W), checks
the installation-report signal API and updates AS only for a fresh connected
response. Reports expose separate signal and AS results; disconnected/failed
signals cause no AS mutation. The API blocks pre-v4 runtimes before dispatch.
See [implementation, acceptance checks and activation](../../agents/docs/device-adjustment-signal-gated-workflow.md).

Source is installed in the primary development checkout and the isolated
worktree. Agent Server rebuild/restart remains required; this session lacks
Docker socket/sudo access. No live subscriber records were mutated in tests.

## Agent display name (2026-11-09)

Renamed the displayed agent from AX768 to **운영시트에이젠트** in the agent
catalog, workspace heading, workspace accessible name, loading message and
sheet directory description. Korean translations and the existing loading-state
test expectation use the new name. Internal `ax768` IDs, URLs, graph names and
API routing are unchanged. Applied to the primary checkout serving port 5173
and the isolated worktree to avoid another source-copy mismatch.

Validation: frontend build and existing catalog, workspace and agent-list tests
passed. Repeat from `frontend/` with `npm run build` and
`npm test -- src/shared/api/agentCatalogClient.test.ts src/features/agents/Ax768WorkbenchPage.test.tsx src/features/agents/AgentsPage.test.tsx`.
No live workflow execution is needed for this display-only change.

## Compact workflow dropdown (2026-11-09)

The six radio cards are replaced by one native dropdown with an inline label
and required indicator. It is 36px high and at most 280px wide; the five
unavailable workflows appear only when opening the menu, disabled and marked
Coming soon. There is no default selection. The existing alert, focus handling,
in-flight lock, workflow_id API contract and current workflow remain unchanged.

The development server at `http://192.168.0.18:5173` serves the primary checkout
at `/home/nextor-ai-02/nextor_ai/ax-project`, not the isolated Codex worktree.
Earlier dropdown edits in the isolated worktree did not affect this server.
This change modifies only the picker markup and styles in the primary checkout
and preserves its existing workflow routing and other uncommitted changes.

Validation: production build, 35 focused frontend tests and offline Cargo check
passed in a temporary copy of the primary frontend. Mocked Chromium checks
covered the select element, absence of radio choices, five disabled options,
required-selection alert and focus with zero requests, workflow_id dispatch,
in-flight lock, candidate retry, tab persistence, reload and 1280/820/390px
layouts. No backend mutation or live AS write was performed. Existing npm audit
findings remain: four low, two moderate and two high; the large-bundle warning
also remains. Use the focused frontend command documented below, plus
`npm run build`, `cargo check --manifest-path src-tauri/Cargo.toml`, and
`npm audit --audit-level=moderate` from `frontend/` to repeat checks.

## Required workflow selection (2026-11-09)

Workflow now opens with six visible choices and no default selection. The
available workflow is **기기위치조정/전원연결** (`device_adjustment_power`).
정보확인&수정, 기기회수, 기기교체, 기기분실 and 가입자신규설치 are disabled and
marked **Coming soon**. Run without a selection shows an inline alert, focuses
the available choice and makes no request. Blank text also shows an alert.
Selection persists across tab switches and is locked during execution.

`POST /api/ax768/workflow/runs` requires `workflow_id` and accepts only
`device_adjustment_power`; missing, null, unknown and unavailable IDs return 422
before opening a runtime client. Responses echo the ID and the browser validates
it. The API strips this product routing field before calling the existing
`ax768_workflow` graph with version 3. The graph and CLI contract are unchanged.
Future choices need their own explicit API routing and workflow implementation
before they can be enabled. There is no fallback to the current workflow.

Validation: 35 focused frontend tests and 32 backend workflow tests passed;
production build and Rust check passed. Chromium verified no default, all six
choices, alerts without dispatch, loading locks, tab persistence, request/result
identity, Korean labels and a 780px layout using mocked API responses. Desktop
and narrow screenshots are under `/tmp/ax768-ui-artifacts/workflow-selection-*`.
No live AS update was executed. The existing large-bundle warning and eight
existing npm audit findings remain (four low, two moderate, two high).

Run focused checks from the respective directories:
`npm run test -- src/shared/api/ax768WorkflowClient.test.ts src/features/agents/Ax768WorkbenchPage.test.tsx`
and `.venv/bin/pytest tests/test_ax768_workflow.py -q`.
This update uses the backend/frontend development source reload; it does not
require a new Agent Server graph deployment.

## Workflow input copy cleanup (2026-11-09)

Removed the S/X/Y update explanation and roster search-order note beneath the
Workflow composer as requested. Also removed the introductory description about
finding and completing the latest AS row. The attachment-specific instruction still appears
when images prevent submission, with its accessible description attached only
while visible.

## IMEI signal Test case (2026-11-04)

**IMEI case** is available as an eighth option in Test, using the existing
case API and `ax768` graph. Input `김순옥님 신호확인요.` searches fixed rosters
울진 → 광명 → 영덕, selects the latest exact matching row, rechecks the person
and reads the configured IMEI cell. The API accepts the IMEI in its `sn` field;
the result message uses the returned serial number with leading zeros intact:

- `S/N 0000 신호 확인되었습니다.` for a verified connected response.
- `S/N 0000 전원 연결 및 기기위치 확인해주세요.` for a verified disconnected response.

Errors, expired login, missing IMEI, mismatched identifiers, unverified fresh
positive responses and HTTP failures never become a disconnected-device claim.
This case performs no spreadsheet write/highlight and does not run AS completion.
The result includes source city/row/link, IMEI column/value, S/N and signal data.
The local LLM is not called. Old deployed graphs are blocked before execution
unless their input schema advertises `imei_case_version: Literal["1"]`.

Current column configuration follows the operator's requested mapping:
울진 Z, 영덕 Y, 광명 V. Live validation identified a discrepancy: on the supplied
tabs the actual `단말 IMEI (실데이터)` headers are 울진 AA4, 영덕 Z4 and 광명 W4.
The supplied example finds 울진 row 3084, where Z3084 is `3065` and AA3084 is the
15-digit IMEI `869016079754947`. The case correctly stopped before a signal call
because the configured cell was not a valid IMEI. A clarification is pending;
do not silently substitute a column or another same-name person.

`ax_integrations.ansimk` uses a normal HTTPX client with the fixed
`https://dev-check.ansimk.com` origin. A private browser-session seed or renewed
cache supplies the `device_check_session` cookie. One explicit 401 permits one
login using the saved admin code and one resubmission; 403, timeout and server
errors are not retried. Login failure text excludes secrets. New caches use mode
600 and atomic replacement. No cookie, code, raw telemetry, subscriber record or
phone number enters graph state or browser responses.

Local defaults: `~/.local/share/nexgent/ansimk-admin-code`,
`ansimk-admin-session.json` (optional seed), and `ansimk-api-session.json`
(renewable cache). `.env.example` documents path overrides. In Compose the code
and seed are narrowly mounted read-only and refreshed sessions use the private
`ax768_auth` volume. No browser dependency or new service is needed. Roster reads
have a 150s bound and authentication/ping a 75s bound.

Run from `agents/`:

```bash
uv run python -m apps.ax768.run --case imei "김순옥님 신호확인요."
```

Activate the graph capability and credential mounts from `nexgent/`:

```bash
docker compose -f compose.yaml up -d --build --no-deps agent-server
```

Validation: 254 AX768/integration/graph-entry checks, 49 backend case/workflow
checks and 26 frontend case/store/UI checks passed. Frontend build, Rust check,
Compose validation and Ruff passed. Mocked browser checks cover the eighth case,
example input, loading, source/IMEI/serial details, both Korean outcomes, history,
narrow layout and Korean labels. Live authenticated HTTP access and direct
code-based login/session persistence were verified without exposing secrets.
The full name-to-signal live run remains stopped by the column discrepancy above.
Existing npm audit findings (8) and the bundle warning remain. Docker activation
is still unavailable to this shell because of its socket permissions.

## AS completion step (2026-11-04)

The operator requested a third step after the AS lookup and confirmed
`S = 처리완료` and leaving Y unchanged for other C values. Unified workflow
version 3 now updates only the selected AS row:

| Column | Rule |
| --- | --- |
| S · 진행상태 | `처리완료` |
| X | Current Asia/Seoul date, stored as a date and displayed `yyyy-mm-dd` |
| Y | C = `기기위치 점검` → `위치점검완료`; C = `기기전원 연결` → `전원연결완료`; otherwise untouched |

The workflow validates the matched source against the configured AS client,
rechecks that row's name/address, reads C, sends one batch containing only S/X
and (when applicable) Y, and reads back identity/C and the changed values. X's
number format is the only formatting changed. No background highlighting,
other column write, device action or automatic retry is introduced. No match
or failed lookup skips the update. A failure before dispatch reports no write
sent; any unverified result after dispatch reports an unknown update rather than
completion, retaining the earlier roster and AS receipts.

The UI discloses the update before running and adds **3. AS row update**, with
verified values or unverified requested values, an explicit unchanged-Y note,
and a check-the-row message for uncertain writes. Completion requires verified
S/X/Y evidence through both the backend and browser adapters. The backend
requires graph version 3 before dispatch. The existing Test tab cases remain
search-only. Roster/AS/update time budgets are 150s/60s/40s inside the existing
270s API and 285s browser bounds.

Google's [batch request documentation](https://developers.google.com/workspace/sheets/api/guides/batch)
confirms that the included cell updates are validated and applied atomically.
The date uses Google's documented [date serial and formatting model](https://developers.google.com/workspace/sheets/api/guides/formats).
The preceding identity check is not a conditional transaction: concurrent row
changes can still race it. A failed verification does not roll back saved values,
and server checkpoint recovery is not an exactly-once write guarantee. Inspect
an uncertain row before manually rerunning.

Use the existing Workflow Run button or `uv run python -m apps.ax768.run
--workflow "<request>"` from `agents/`. This now writes the completion cells;
the seven `--case` commands retain read-only behavior. Rebuild from `nexgent/`:

```bash
docker compose -f compose.yaml up -d --build --no-deps agent-server
```

Validation: the full AX768 unit/graph-entry suite passed, including mocked
Sheets tests for both C rules, unknown/blank C preserving Y, exact column/row
bounds, literal status strings, a real date value, Korea midnight, changed
identity, wrong target, timeout, changed C and failed readback without retry.
Backend workflow/case checks (41) and frontend workflow/workbench checks (24)
passed. Production build and Rust check passed. Chromium with mocked receipts
verified all three saved values, unchanged Y, uncertain-write presentation,
retained lookup evidence, Korean labels and narrow layout. No live AS rows were
modified during these tests. Existing audit findings (8) and bundle warnings
remain. This shell lacks Docker socket access, so runtime activation still
requires the rebuild command above.

## Automatic region from the roster (2026-11-04)

Manual region selection was removed at the operator's request. Every text request
now searches 울진 → 광명 → 영덕 until the first match and reports its source city
and row. Name-only requests now follow this order too, then use the latest exact
name match in AS. Requests with an address still use both fields. No roster match
means AS is skipped; a read error stops fallback. AS receipts label the source
roster's city; a name-only AS match is not independently validated by region.

The frontend, API and CLI have no region parameter. The product boundary requires
workflow schema version 2 and blocks version 1, preventing the old name-only skip
behavior. The previous section's optional region selector is superseded. The
new runtime must be rebuilt with the command below from `nexgent/`:

```bash
docker compose -f compose.yaml up -d --build --no-deps agent-server
```

Validation passed: 60 agent/parser/CLI/graph-entry checks, 13 workflow API
checks, 21 frontend checks, production build and Rust check. Browser checks
confirmed no region selector, name-only submission without a region field, source
city display, Korean copy and narrow layout. Live read-only execution of
`김순옥님 신호확인요.` found 울진 roster row 3084, then AS row 899.
Regression coverage includes matches in each roster, no match, errors stopping
fallback, name-only AS handoff and rejection of the older runtime.
Existing dependency-audit findings and this shell's Docker socket limitation
remain as documented below.

## Unified roster and AS workflow (2026-11-04)

The Workflow tab now executes text requests through the versioned
`ax768_workflow` graph and `POST /api/ax768/workflow/runs`. It shows an elapsed
loading indicator, ordered roster attempts, separate roster/AS receipts with
city, sheet, row and direct links, and retains a roster match if AS fails.
Editing text or region clears the previous result; switching tabs preserves
input and a pending run. Duplicate submission is blocked. Drafts/results remain
in page memory and disappear on refresh/navigation/account change.

Accepted formats include name-only `김순옥님 신호확인요.`, address/name with
honorifics, typed photo addresses, comma-separated service requests, numbered
prefixes and spaces inside names. Name/address requests search 울진 → 광명 →
영덕, advancing only on no match, then search AS by both fields from the bottom.
Name-only requests skip the rosters and find the latest exact AS name. Optional
울진/광명/영덕 selection records KakaoTalk room context without inferring a city
or filtering the AS result. No KakaoTalk connection is implied.

Exact roster matches take priority over close candidates in earlier rosters.
If no exact match exists and there is one unique, complete, address-matched
candidate whose 3–5 syllable Korean name differs by one syllable, it is re-read
and automatically used for AS. The original/corrected names are shown. Multiple
candidates require choosing a name; a new run rechecks that name and address
using the same roster priority. No fuzzy matching occurs in AS. The helper reads
at most 100,000 configured cells per target in 2000-cell pages, rechecks matched
cells, and performs only GET requests. It never formats or changes a sheet.

The service-request suffix is not an instruction to manipulate devices. This
version processes text only: attached images are local previews, and a visible
instruction asks the operator to transcribe the address and remove attachments
before execution. No image is uploaded or silently ignored.

The backend requires admin and CSRF access, accepts only bounded text, region
and an optional selected name, validates the graph's `workflow_version` schema,
and returns bounded source receipts instead of raw state. Missing or stale
graphs return 409 before a run. The roster stage has a 180s budget and AS 60s;
API/browser budgets are 270s/285s. No automatic retry follows a transport failure.
The existing service account, AS configuration and runtime process are reused.

Run immediately from `agents/`:

```bash
uv run python -m apps.ax768.run --workflow "울진북로 164 김순옥님 신호확인요."
uv run python -m apps.ax768.run --workflow --region uljin "김순옥님 신호확인요."
```

Enable the new graph in the running web stack from `nexgent/`:

```bash
docker compose -f compose.yaml up -d --build --no-deps agent-server
```

Validation: 180 AX768/graph-entry Python checks, 93 backend AX768/integration
checks and 31 frontend AX768 checks passed. Frontend production build and Rust
check passed. Chromium checks with mocked API responses covered enabled submit,
loading, duplicate prevention, tab retention, row links, optional region,
ambiguous-name selection, partial failure, stale-runtime messages, images,
narrow layout and Korean labels. A live service-account read of
`울진북로 164 김순옥님 신호확인요.` found 울진 roster row 44 and AS row 689.
The supplied typo example `영덕대게로 699긴 영호` also completed: unique
address-matched `김영호`, 영덕 roster row 953, AS row 960, with a visible
correction notice. The graph schema advertises version 1. No live sheet write
was made.

Known environment issues: Agent Server rebuild is blocked by this shell's Docker
socket permissions, so the deployed browser-to-new-graph path still needs the
command above. `npm audit` reports 8 existing findings (4 low, 2 moderate, 2 high);
no dependencies were changed. A broader unrelated contract run also found the
two pre-existing weekly-report scheduler environment-mount assertions in
`test_weekly_report_notification_deployment.py`; this workflow does not alter
those scheduler deployments. The existing frontend bundle-size warning remains.

## Sheets directory tab (2026-11-04)

A third **Sheets** tab lists the operator-approved AS, uljin-users,
gwangmyeon-users and yeongdeok-users spreadsheets, with readable names, aliases
and related case IDs. The operator requested links only. Each row opens the
correct spreadsheet and numeric tab (`gid`) in a new browser tab using
`noopener noreferrer`; access is through the user's Google account. This does
not fetch sheet contents, use service-account credentials in the browser, or
modify Google Sheets.

The directory lives in `frontend/src/shared/api/ax768Sheets.ts`. The four URLs
were checked against the configured AS/address targets and the workflow's fixed
city-roster registry. It is a static directory, not a live availability check;
update it when those targets change. All three tabs support arrows, Home/End,
linked accessibility panels and preservation of the mounted Workflow draft.

Validation: frontend build, 10 existing component tests, Rust check and Chromium
checks passed. Browser checks verified all four spreadsheet/tab links, new-tab
attributes, keyboard wraparound, retained Workflow input, narrow layout and Korean
labels. Existing dependency audit findings are unchanged. Screenshot:
`/tmp/ax768-ui-artifacts/sheets-tab.png`.

## Unified Workflow composer (2026-11-04)

The operator clarified that text and images must share one visual input component.
The separate textarea border and image drop area are replaced by one composer:
borderless text entry, image thumbnails with remove controls, and an integrated
bottom toolbar with Add images, character count and Run workflow. The entire
composer accepts dropped files, including drops over the text entry. A shared
focus outline and drag overlay identify it as one input. File limits, local draft
behavior and the right-side status/results layout are unchanged. Execution still
awaits the operator's workflow definition.

Validation: frontend build, 10 existing component tests and Rust check passed.
Chromium verified the shared component contains both text and images, its toolbar
opens the file picker, drops on text attach images, validation/removal/clear still
work, tab switching preserves the draft, and narrow/Korean layouts work without
page errors or network writes. Existing dependency-audit findings remain.
Desktop preview: `/tmp/ax768-ui-artifacts/workflow-composer.png`.

## Workflow text and image interface (2026-11-04)

The Workflow tab now has two columns. On the left, one request contains text
(up to 8,000 characters) and attached images together, with a single Run workflow
button. Images can be selected through the file picker or dropped onto the upload
area. PNG, JPEG and WebP are accepted, up to five images and 50 MiB combined.
Empty/unsupported/oversized files are rejected with inline messages. Duplicate
attachments are ignored. Each image has a local preview, filename, size and remove
control; Clear input resets both text and images.

On the right, Workflow status reports Not started and summarizes the current
text/images; the result area reserves space for workflow output and completion
status. Execution is explicitly disabled until the operator supplies workflow
steps. There is no simulated run, OCR, sheet operation, network upload, or
backend integration for this tab yet. The existing search-only Test tab is retained.

`Ax768WorkflowPanel.tsx` owns this page-local draft. Switching tabs preserves text
and files because the panels remain mounted. Navigating away, refreshing, logout
or losing workspace access discards the draft. Blob preview URLs are revoked
when images are removed, cleared or the component unmounts. The responsive layout
stacks input above status/results on narrow screens. English and Korean copy are
provided.

Validation: production build, 14 existing component/store tests and Rust check
passed. Chromium checks covered combined text/images, picker upload, drag/drop,
local preview rendering, type/count/size limits, removal, clear, preserved tab
state, narrow layout and Korean copy; no network writes or page errors occurred.
The dependency audit still reports the eight pre-existing findings. Screenshot
artifacts are `/tmp/ax768-ui-artifacts/workflow-input.png` and
`/tmp/ax768-ui-artifacts/workflow-input-narrow.png`.

## Test and Workflow tabs (2026-11-04)

The existing case runner is now under the default **Test** tab. The adjacent
**Workflow** tab is a placeholder awaiting the operator's workflow details.
Switching panels preserves input drafts, selected case, results and pending runs;
a spinner on the Test tab remains visible during execution. Tabs expose selected
state and linked panels, support Left/Right and Home/End keyboard navigation,
and keep hidden panel controls out of keyboard and accessibility navigation.
No workflow execution, new API or persistence is introduced by this UI change.

Validation: frontend build, 14 existing component/store tests, Rust check and
Chromium checks passed. Browser checks covered both tabs, keyboard selection,
preserved input, loading during a tab switch and results after switching back.
The dependency audit still reports the eight existing findings documented below.

## Search-only update (2026-11-04)

The operator has disabled yellow highlighting. All seven numbered cases now
return search results without modifying values or formatting. Name-only requests
also search without highlighting. Existing colors are preserved. UI case titles,
descriptions, capability labels and buttons now describe lookup only; inputs,
loading, row/city links and session history remain.

The shared action contract adds `search_name` and `search_person_row`; address
lookup reuses `search_address`. AX768 rejects legacy `find_and_highlight_*`
decisions before creating a Sheets client. Shared formatting adapters remain
available for other consumers and retain their tests. General explicitly requested
cell editing remains a separate CLI capability; it is not exposed by this UI.

Before a web run, the backend reads the registered AX768 assistant's schema and
requires the `case_policy` constant `search_only`. An older image receives no run:
the API returns 409 and the UI asks for an Agent Server restart. The default
assistant UUID uses the installed Agent Server graph namespace, verified against
a temporary local server with a successful HTTP 200 schema request and a real
API-to-Agent-Server round trip using invalid input rejected before Google access. This is a
compatibility guard, not a client option to re-enable highlighting.

Validation: 155 AX768 and contract checks passed, including full graph-to-mocked-
Google tests asserting GET-only requests and latest-row selection. The frontend
build, 22 focused tests, Chromium search-only/navigation/loading/result/409 checks,
and Rust check passed. API tests pass, including refusing an older graph before
run submission. Dependency audit findings remain the eight previously documented
issues. A real AS case 2.3 attempt failed with a Google transport error; no
formatting writes were made. Live matched-result verification is therefore not
claimed for this update.

Docker socket access is still denied in the coding shell. From `nexgent/`, rebuild
and restart the development Agent Server to load this update:

```bash
docker compose -f compose.yaml up -d --build --no-deps agent-server
```

The frontend/backend development mounts reload changed source. Reload the page
and run a search after the server is healthy. The earlier delivery record below
describes the superseded highlighting behavior and initial validation.

---

Date: 2026-11-04

## Delivered behavior

AX768 appears in `/agents` and opens an administrator-only workspace at
`/agents/ax768`. Operators choose one of the existing cases (1.1, 2.2, 2.3,
4.2, 4.3, 6.2, 6.3), enter or edit Korean request text, optionally load a case
example, and submit. The page explains the search target and whether the case
writes yellow formatting. Cases 4.2 and 6.2 only search; the others preserve
their existing highlight behavior. Latest means the largest matching row number.

During execution the form is disabled, a spinner and elapsed seconds are shown,
and repeated clicks cannot submit another run. Progress does not claim a
percentage or an unobserved internal stage. The operator can navigate within
the app and return while the request continues. Results show the outcome, latest
row, city, sheet, name/address, direct Google row link, and expandable details.
Saved yellow and visible yellow are separate confirmations. Existing conditional
formatting is preserved; overrides produce a warning instead of falsely reporting
failure or guaranteed visible yellow.

The last 20 attempts and per-case drafts are memory-only. Refresh, logout,
account change or lost administrator access clears them. Late responses from a
previous account are ignored. Refresh/disconnect does not cancel an upstream
sheet write; on an uncertain result inspect the sheet before resubmitting.
There is no durable run history, cancellation, automatic retry or general-purpose
agent prompt in this workspace.

## Boundaries

- `frontend/src/shared/api/ax768Client.ts` owns case metadata, validated API
  responses and safe Google links. The page uses this shared adapter and an
  ephemeral Zustand store. This follows the existing authenticated browser
  boundary; AuthGate already excludes Tauri sessions.
- `POST /api/ax768/runs` accepts only `case_id` and `message` (1–8,000 characters),
  requires an authenticated administrator and CSRF token, and calls the private
  Agent Server `/runs/wait` with fixed assistant `ax768`. Requests cannot choose
  another graph, raw tool arguments or arbitrary spreadsheet targets.
- `backend/app/ax768.py` normalizes existing workflow receipts and strips raw
  metadata/observations. It bounds the returned result and returns HTTP 502 with
  `ax768_outcome_unknown` after transport, timeout or malformed-output failures.
  It does not retry. The request deadline is 270 seconds (browser 285 seconds).
- Raw `/agent-server/*` proxy access now requires admin permission, except
  authenticated `GET`/`HEAD /agent-server/ok`. Regular users still access chat
  through the product `/api/chat` boundary. This closes the alternative route
  to invoke AX768 or inspect arbitrary agent threads.
- The existing workflow, case parser, deterministic matching, local-model
  configuration and Google tools remain authoritative. No shared package imports
  application code and no new runtime, database table or dependency is added.

## Development runtime

The dev Compose Agent Server mounts the existing key read-only at
`/run/ax768/service-account.json` and sets `AX768_GOOGLE_CREDENTIALS_FILE` to that
container path. The host source defaults to
`/home/nextor-ai-02/.local/share/nexgent/nexgent-service-account.json`; override
`AX768_SERVICE_ACCOUNT_HOST_FILE` when needed. `create_host_path: false` fails
clearly on a missing key. The private key is neither copied into the image nor
sent to the browser. Existing `agents/.env` selects service-account auth and
spreadsheet scope. No production Compose change was made.

From the Nexgent project root, with Docker access:

```bash
docker compose -f compose.yaml up -d --build --no-deps agent-server
docker compose -f compose.yaml ps agent-server
```

Backend and frontend dev source mounts already reload changed source. If their
watchers do not reload, restart just those services:

```bash
docker compose -f compose.yaml restart backend frontend
```

Then sign in as an administrator, open
`http://192.168.0.18:5173/agents/ax768`, select 4.2, load the example, and Search.
The example currently returns 울진군, row 44. For an authorized write test choose
an AS highlight case and verify both saved and visible formatting receipts.

## Verification and checkpoint

- Frontend production build passed; existing bundle-size warning remains.
- 33 focused frontend tests passed (API, store, component, catalog and routes).
- 102 backend API, access-control, proxy, chat and RAG regression tests passed.
- Nine deployment, dependency-boundary and graph-entry contract checks passed.
- `cargo check` passed with `CARGO_TARGET_DIR=/tmp/ax768-cargo-target`; the default
  target cache refers to an older checkout and fails before compiling this app.
- `npm audit --audit-level=moderate` reports eight existing findings (four low,
  two moderate, two high). This change adds no dependencies or lockfile updates.
  Dependency remediation remains separate work.
- A real service-account CLI case 4.2 lookup completed, and the new API normalizer
  converted its receipt to `found`, 울진군, row 44, 실시간 가입자 명부. It made no
  Google writes.
- Chromium checks passed against the running Vite frontend with isolated test
  authentication and API fixtures, including the normalized real read-only
  receipt: all seven cases, editable examples, blank-input guard, loading,
  disabled controls, navigation during a pending request, row/link results,
  formatting warnings, no-match, unknown-outcome, refresh clearing and member
  access denial. Desktop and 780px-wide screenshots were inspected; no horizontal
  overflow or JavaScript page errors. Fixtures for write cases made no sheet writes.
  Temporary screenshots are in `/tmp/ax768-ui-artifacts`; the browser verification
  harness is `/tmp/ax768-browser/check.cjs`.

Remaining deployment verification: this execution shell cannot access the Docker
socket and passwordless sudo is unavailable. The Agent Server rebuild/restart
above has not been performed. A complete authenticated browser → running backend
→ rebuilt Agent Server → Google execution therefore remains to be checked after
that restart. No production services or Google formatting were changed by UI tests.


## Member-note replacement update — 2026-11-10

The Test case now replaces the entire 일반 사항 field with the supplied text.
A unique exact-name match, or one unique partial-name match when no exact match
exists, saves directly. Address/ID constraints are always respected. Multiple
matches still require selecting the intended member. Version 2 rejects the old
append runtime; rebuild Agent Server before using the changed UI. See
`../../agents/docs/ax768-member-general-note-test.md` for validation and commands.


## Device workflow general notes — 2026-11-10

Version 5 adds member general-note replacement after verified AS completion,
or after confirming AS is absent. Signal verification remains required. The
request action, otherwise AS completion type, determines 기기위치조정/전원연결;
the date follows Asia/Seoul processing. The fifth result section keeps member
outcomes separate from AS results. See
`../../agents/docs/device-adjustment-member-note-step.md` for policy, tests and
the required Agent Server rebuild.
