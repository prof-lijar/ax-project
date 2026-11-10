# AX768

> Current behavior (2026-11-04): yellow highlighting is disabled for all numbered
> cases and the name shorthand. They return the latest matching row without
> changing values or formatting. The highlight descriptions and receipts below
> are historical; current commands use the same inputs and IDs for search only.
> Rebuild/restart Agent Server after updating. The browser blocks older versions
> before execution. Existing highlights are not removed.

AX768 is a local-LLM agent with Google Sheets as its first capability. It reuses
the workspace's `URL`/`MODEL`/`OPENAI_API_KEY` (or `OPENAI_BASE_URL`/
`OPENAI_MODEL`) settings and existing asynchronous model adapter. No cloud LLM
fallback is configured. The model must support JSON-schema structured output.
Google Sheets access still requires internet access to Google.

## Browser workspace

Administrators can open `/agents/ax768` from the Nexgent Agents page, select a
case, enter a message and run it. The form includes examples, a loading timer,
latest-row/city results, direct sheet links and a session-only recent history.
All seven cases search without changes. Existing formatting remains unchanged.

See the [workspace implementation and dev runtime setup](../../../docs/08-implementation/ax768-case-workspace.md).

## IMEI Test case

Choose **IMEI case** in the Test tab, enter `김순옥님 신호확인요.` and press
**Check signal**. The CLI uses the same deterministic path:

```bash
uv run python -m apps.ax768.run --case imei "김순옥님 신호확인요."
```

It searches 울진 → 광명 → 영덕, selects the bottom-most exact name match
(optionally also matching a typed address), rechecks the row and reads the
city's configured IMEI cell. A missing/invalid IMEI stops at that person;
it does not silently switch to an earlier row or another city's namesake.
Only then does it call 설치보고관리 with `{"sn": "<15-digit IMEI>"}`.
It never updates or highlights spreadsheet cells and does not run the AS
completion workflow.

The final message uses the **returned serial number**, preserving leading zeros:

- Connected: `S/N 0000 신호 확인되었습니다.`
- Disconnected: `S/N 0000 전원 연결 및 기기위치 확인해주세요.`

HTTP/authentication failures, missing identifiers, stale positive responses and
mismatched response IMEIs are failures, never proof of a disconnected device.
The UI includes city, row, source link, IMEI, S/N and signal strength. Raw
telemetry, account cookies and login codes are excluded from graph/browser output.

The integration reuses a private session cookie; an explicit HTTP 401 permits
one login and one resubmission. A timeout, 403 or server error is not retried.
Code and initial browser session paths are configured in `.env.example` as
file paths only. Local defaults are under `~/.local/share/nexgent/`:
`ansimk-admin-code`, optional seed `ansimk-admin-session.json`, and renewable
cache `ansimk-api-session.json`. New cache files use mode 600 and atomic replace.
The dev container mounts the code and seed read-only and stores renewed sessions
in its private `ax768_auth` volume. No browser dependency is needed; standard
HTTPX authenticated access was verified.

The product API requires `imei_case_version: Literal["1"]` in the running graph.
Rebuild Agent Server after installing the change. Roster reads are bounded to
150 seconds and login/ping to 75 seconds. The case uses fixed sheet/API targets
and no model-selected tools. A new run starts fresh and does not auto-replay an
uncertain device request.

## Unified workflow

Use the **Workflow** tab at `/agents/ax768`, or run from `agents/`:

```bash
uv run python -m apps.ax768.run --workflow "울진북로 164 김순옥님 신호확인요."
uv run python -m apps.ax768.run --workflow "김순옥님 신호확인요."
uv run python -m apps.ax768.run --workflow "지영희님 신호확인요 & 상밤터1길 59-4(사진)."
uv run python -m apps.ax768.run --workflow "왕피길83-15,정영자,기기위치조정 수신확인요~"
uv run python -m apps.ax768.run --workflow "영덕군 영덕읍 영덕대게로 699긴 영호,기기위치조정 수신확인요~"
```

Version 4 checks device connectivity before AS completion. Name-only requests
first find the bottom-most exact-name AS row and take its address. Both input
modes search 울진 → 광명 → 영덕 rosters sequentially using name and address,
then recheck the selected identity while reading IMEI: 울진 AA, 영덕 Z, 광명 W.
No matching AS address for name-only input, no roster match, invalid IMEI, or a
failed signal request stops without an AS write.

The existing installation-report admin API checks the IMEI. It returns the
actual S/N, preserving leading zeros. Connected returns
`S/N 0000 신호 확인되었습니다.`; disconnected returns
`S/N 0000 전원 연결 및 기기위치 확인해주세요.`. Only a fresh connected response
can update the selected AS row. Supplied-name/address requests find the latest
AS name/address match after the signal; name-only requests keep their original
AS row and recheck it before updating.

| Column | Saved value after confirmed connection |
| --- | --- |
| S · 진행상태 | 처리완료 |
| X | Today's Asia/Seoul date, displayed as `yyyy-mm-dd` |
| Y | `위치점검완료` for C = `기기위치 점검`; `전원연결완료` for C = `기기전원 연결`; otherwise unchanged |

Name spacing is ignored. Supplied-name/address requests retain address-grounded
unique typo correction and explicit candidate confirmation; AS-derived
name-only identities require exact roster matching. The report includes roster,
IMEI/S/N/signal, AS match and verified or unknown AS update evidence. Missing AS
after a positive signal retains the signal result without claiming an update.
Unknown mutation results require checking the row before rerunning; there is no
automatic write retry or rollback. Latest means largest row number.

The product API requires workflow version 4, so rebuild Agent Server before
using the new workflow. `completed` requires a verified connected signal and AS
readback; `disconnected`, `not_found`, `needs_confirmation`, `blocked`, and
`failed` retain evidence and exit CLI with code 1. Images still require typed
transcription and removal before running. No master-page note is written.
See [full contract, verification and activation](../../docs/device-adjustment-signal-gated-workflow.md).

## Setup and run

1. Run `uv sync` from the workspace root.
2. In Google Cloud project `nexgent-513207`, enable **Google Sheets API**.
3. Configure **Google Auth Platform → Branding / Audience**. For an External
   app in Testing, add the Google account you will sign in with as a test user.
   Under **Data Access**, add `https://www.googleapis.com/auth/spreadsheets`.
4. Under **Clients**, create an OAuth client with application type **Desktop app**
   and download its JSON file. A service-account key is a different credential.
5. Store the downloaded client JSON privately on the Linux server outside the
   repository. In the existing **agents/.env**, set absolute paths:

   ```dotenv
   AX768_GOOGLE_AUTH_MODE=oauth
   AX768_GOOGLE_OAUTH_CLIENT_FILE=/private/ax768/oauth-client.json
   AX768_GOOGLE_OAUTH_TOKEN_FILE=/private/ax768/oauth-token.json
   AX768_SPREADSHEET=https://docs.google.com/spreadsheets/d/YOUR_ID/edit
   ```

   The provided sheet link is already saved in the local .env. The login command
   creates the token file; do not download or invent its contents. Keep the client
   JSON and generated refresh token out of Git and chat. Explicit environment
   variables take precedence over .env.
6. From your **laptop terminal**, establish an SSH tunnel to the agent server:

   ```bash
   ssh -L 8767:127.0.0.1:8767 YOUR_LINUX_USER@YOUR_SERVER
   ```

   In that SSH session, change to the `agents/` workspace and run:

   ```bash
   uv run python -m apps.ax768.oauth_login
   ```

   Open the printed Google authorization URL in your **laptop browser**. Sign in
   with the Google account that has Editor access to the sheet and grant the
   requested access. Keep SSH connected through the callback. The login listener
   binds only to server loopback and waits up to five minutes. The tunnel forwards
   the browser's loopback redirect to it; no public callback or browser on the
   server is needed. If port 8767 is occupied, use a matching tunnel and `--port`.
7. Once the command reports success, run a task:

   ```bash
   uv run python -m apps.ax768.run "Read the headers in 'Sales'!A1:D1"
   ```

OAuth uses the signed-in user's existing spreadsheet permissions. The Sheets
scope can authorize access to all spreadsheets available to that user; AX768's
fixed spreadsheet setting restricts its tools to the selected file. Sheets
scope authorization does not override file sharing or protected ranges.
The runtime refreshes expired access tokens and atomically saves them with mode
0600 under a cross-process file lock. Revoked or expired refresh tokens require
running the login command again. External apps in Testing generally receive
refresh tokens that expire after seven days for this scope; use the appropriate
Google publishing/verification process for longer-term operation.

For containers, mount the token **directory** writable by the agent process so
atomic token replacement and locking work; keep it private. The OAuth client
file is needed only during interactive login, not ordinary graph runs. No browser
login starts inside a graph node. With OAuth, service-account sharing is unused.
The previous service-account path remains available only when explicitly setting
`AX768_GOOGLE_AUTH_MODE=service_account` and `AX768_GOOGLE_CREDENTIALS_FILE`.

The `ax768` graph is also registered for the private Agent Server. Submit input
`{"message":"your task"}` using existing thread/run APIs. Server-backed threads
retain checkpoints; the manual CLI is a single stateless invocation. The product
chat API does not automatically route messages to this new agent.

## Contract and skills

### Name search and yellow highlight

Date: 2026-11-03

Case **1.1** takes the text `김순옥님 신호확인요.`, searches for `김순옥` in
the chosen tab and sets the bottom-most matching name cell's background to yellow. It does not check
device telemetry or infer a person's health. Matching uses the entire displayed
cell text after trimming surrounding whitespace and Unicode NFC normalization.
If multiple cells match, only the one with the largest row number is highlighted.
Same-row ties select the leftmost match. Earlier matches are left unchanged. A missing name returns a clear
not-found response without a write. Longer strings such as `김순옥 (보호자)` or
`김순옥님` in a cell are not exact matches for `김순옥`.

The user's requested target is configured in the local unified .env:

```dotenv
AX768_SPREADSHEET=https://docs.google.com/spreadsheets/d/1n8XFAPB66eCUxVqUobzcNDJuK6-b_rhtwjBuhqcPjV0/edit
AX768_NAME_SEARCH_SHEET_ID=2142794645
```

From the `agents/` directory:

```bash
uv run python -m apps.ax768.run --case 1.1 "김순옥님 신호확인요."
```

Replace the name for another person. `--case` selects the registered workflow;
`1.1`, `2.2`, `2.3`, `4.2`, `4.3`, `6.2` and `6.3` are currently implemented. Unknown cases and text that does not match
the case are rejected before Google/model calls. Without `--case`, existing
general mode and shorthand behavior remain available. Graph API input can include
`"case_id": "1.1"`; send `"case_id": null` to clear it on a reused thread.
The fixed shorthand takes a deterministic
path through AX768; other requests continue using the configured local LLM.
The `find_and_highlight_name` tool owns paged search and readback, so the model
does not need the roster. It only changes background color; values, formulas,
text formatting and other cells are preserved. Readback must confirm both stored
and effective yellow; a conditional-format override yields a verification error.
Scanning is capped at 100,000 grid cells in 2000-cell pages and 100 matches,
failing without partial search writes. Results include `total_match_count`,
`selected_row`, and the single selected cell in `matched_cells`. Latest means
row position; the agent does not compare dates or infer identity from similar names.

The service account must have Editor access to this new spreadsheet separately
from the original A81 test spreadsheet. Reload/restart any existing Agent Server
process after changing its environment; the CLI loads .env on every invocation.

Validation: 44 focused tests passed, including explicit case routing and rejection,
pagination, exact versus partial matches, bottom-most duplicate selection,
no-match behavior, a changed cell before writing, background-only
field masks, conditional-format verification failure and Korean shorthand routing.
Live attempt on 2026-11-03: the configured service account
`nexgent@nama-ai-455515.iam.gserviceaccount.com` received HTTP 403
`PERMISSION_DENIED` for this new spreadsheet while the original A81-test
spreadsheet returned HTTP 200 with the same credentials. No live highlighting
occurred. Verify the new file's sharing for that exact email, then rerun the
command above; real name locations and formatting remain unverified.

### Address row search

Case **2.2** searches for an address fragment and returns matching row numbers
and address cells, ordered from the bottom row upward. It highlights only the
bottom-most matching row yellow, across every existing column (A:AU in this tab).
From the `agents/` directory:

```bash
uv run python -m apps.ax768.run --case 2.2 "후포로 158"
```

This case has its own target in the local .env and uses the existing credentials:

```dotenv
AX768_CASE_2_2_SPREADSHEET=https://docs.google.com/spreadsheets/d/1Md868AWFklkeLfvgkbc8AAHmxiPmxf5EkFxp-dZJ7uU/edit
AX768_CASE_2_2_SHEET_ID=177570717
AX768_CASE_2_2_ADDRESS_COLUMNS=G:H
```

Graph input is `{"case_id":"2.2","message":"후포로 158"}`. This fixed case
bypasses the model. Matching ignores whitespace and normalizes Unicode, so
`후포로158` and a full address containing `후포로 158` match. Numeric boundaries
exclude `후포로 1580`. It is a literal fragment search, so suffixes such as
`후포로 158-1` also match. Fragments must occur in a single cell. Columns G:H
contain the formula-adjusted and entered road addresses in this tab. The optional
column span is validated against the tab dimensions; omitting it scans all
columns subject to the same limit. It scans only the specified tab/columns,
up to 100,000 grid cells in 2000-cell pages and 100 matched
cells; failures stop without reporting partial results as complete. Results
include `matches`, `match_count` (rows) and `selected_row` (bottom-most row),
with address text capped at 1000 characters and a `truncated` flag per cell.
The `find_and_highlight_address_row` action rechecks the selected address, changes
only the row background, and verifies stored and effective yellow for every cell.
Values, formulas, other formatting and earlier matching rows are preserved.
No match causes no write. Results include `highlighted_range` and `verified`;
missing stored yellow fails the run, even when Google accepted the write.
Stored yellow across the row with visible overrides completes with a warning: the
tool returns `highlighted_with_warnings`, `stored_verified: true`, `verified: false`.
Here `verified` retains its meaning of visibly yellow across the row.
Row formatting is bounded to 2000 columns. Concurrent edits may race the recheck;
inspect the row after uncertain failures before rerunning. The original
`search_address` action remains read-only for previously recorded decisions.

Live verification on 2026-11-03 succeeded with
`nexgent@nama-ai-455515.iam.gserviceaccount.com` after an initial access failure.
The supplied address matched eight rows: 3998, 3900, 3811, 3309, 3155, 3098,
3087 and 3064. The selected bottom-most row was 3998 in the initial read-only run.
The subsequent highlight run verified yellow across `A3998:AU3998`, with eight
candidate rows and only row 3998 highlighted. All 68 focused AX768 and contract
tests passed; scoped Ruff checks passed.
Editor access is required for case 2.2 highlighting. Reload an existing Agent Server
after changing its environment; the CLI loads .env on each invocation.

### AS Sheet name and address search

Case **2.3** searches the AS Sheet from the bottom for a row whose name and
address both match, then highlights that entire row yellow. Run:

```bash
uv run python -m apps.ax768.run --case 2.3 "후포로 158 김동명"
```

The final word is the Korean name (2–10 Hangul characters); the preceding text
is the address fragment and must include a number. Name matching uses the entire
trimmed, NFC-normalized cell. Address matching ignores whitespace and excludes
numeric continuations such as 1580 for 158. Both fields must match on the same
row. Latest means largest row number, not a date comparison. The agent stops
at the first qualifying row from the bottom; `match_count` is 0 or 1 and does
not count earlier matching rows. A missing match causes no write.

The configured AS Sheet is:

```dotenv
AX768_CASE_2_3_SPREADSHEET=https://docs.google.com/spreadsheets/d/1n8XFAPB66eCUxVqUobzcNDJuK6-b_rhtwjBuhqcPjV0/edit
AX768_CASE_2_3_SHEET_ID=2142794645
AX768_CASE_2_3_NAME_COLUMN=I
AX768_CASE_2_3_ADDRESS_COLUMN=H
AX768_CASE_2_3_START_ROW=7
```

These columns were checked against the `AS 관리` headers (가입자 and 주소).
The search skips dashboard/header rows. It scans at most 100,000 cells in pages
of up to 2000 cells. Both fields are rechecked before one background-only write
across A:AJ in the live tab. Values and formulas are preserved. Stored and
visible yellow are checked across the whole row. Saved yellow with a visible
override completes with a warning; missing stored yellow still fails. The same credentials require Editor access.
Concurrent edits may race the recheck; inspect formatting after uncertain failures.

Graph input: `{"case_id":"2.3","message":"후포로 158 김동명"}`.
No LLM call is needed for this fixed case. Restart an existing Agent Server to
load the new code/environment; each CLI invocation loads the current .env.

Live run on 2026-11-03: no row matched both `김동명` and `후포로 158`; the
operation returned `not_found` and made no changes. Live case 2.3 highlighting
therefore remains unverified for a matching person. The shared formatting helper
was live-verified in case 2.2, and 80 focused AX768/contract tests pass, including
case 2.3 matching/highlighting fixtures. Scoped Ruff and diff checks pass.

Subsequent completion-policy retest: `오봉길 24 주정수` returned `completed`,
selected row 985, and verified saved yellow across A985:AJ985. C985 and O985 have
visible formatting overrides, reported as warnings. All 85 focused AX768/contract
tests pass with this policy.

### Ordered user-sheet lookup

Case **4.2** searches the three user rosters sequentially and returns the city
and bottom-most row where both name and address match. It performs no edits,
highlighting or device signal checks. From `agents/`:

```bash
uv run python -m apps.ax768.run --case 4.2 "울진북로 164 김순옥님 신호확인요."
```

Input may also be plain `울진북로 164 김순옥`. The final Korean name and the
optional signal-check suffix are separated from the preceding address. Matching
uses the entire trimmed/NFC-normalized name cell and the existing address
fragment matcher (ignores whitespace, rejects numeric continuations).

| Order | Sheet alias | City | Tab ID | Name / address | First data row |
| --- | --- | --- | --- | --- | --- |
| 1 | uljin-users | 울진군 | 177570717 | C / H | 6 |
| 2 | gwangmyeon-users | 광명시 | 1895743441 | D / G | 5 |
| 3 | yeongdeok-users | 영덕군 | 2024273886 | C / H | 6 |

The approved file IDs and layout are held in [city_search.py](city_search.py).
`gwangmyeon-users` preserves the user's alias; its actual sheet is 광명시.
The listed user rosters are searched, rather than the AS sheet from case 2.3.
Case 4.2 uses the existing auth settings and does not require `AX768_SPREADSHEET`
or new target environment variables. Viewer access to each target is sufficient.

The next sheet is searched only after no match in the previous one. On a match,
the search stops and returns `city`, `sheet_alias`, `selected_row`, `sheet_url`,
and ordered `attempts`. An unreadable sheet stops the run with a failed attempt;
it is never treated as not-found. If all three searches finish without a match,
the command completes with a clear not-found response. Latest means largest row
number within the first matching sheet, not a comparison of dates or row numbers
across cities. Both matched cells are rechecked before returning the result.

Graph input: `{"case_id":"4.2","message":"울진북로 164 김순옥님 신호확인요."}`.
The fixed path makes no model calls. Existing Agent Server processes need a restart
to load the code; the CLI uses current code on each invocation.

Live run on 2026-11-03 found **울진군 / uljin-users, row 44** for the supplied
example and stopped before later targets. All three tabs' access and headers
were verified. No cells were changed.
Validation: 99 focused AX768/contract tests passed; scoped Ruff and diff checks passed.

### AS signal-request lookup

Case **4.3** finds the bottom-most AS row matching both the name and address,
then highlights that entire row yellow:

```bash
uv run python -m apps.ax768.run --case 4.3 "울진북로 164 김순옥님 신호확인요."
```

This parses name `김순옥` and address fragment `울진북로 164`. Plain
`울진북로 164 김순옥` also works. It uses the same AS Sheet and configuration
as case 2.3 (`AX768_CASE_2_3_*`): tab `AS 관리` (2142794645), name column I,
address column H, starting at row 7. No additional environment variables are
needed. Both fields must match on one row; largest row number means latest.
Matching and limits are identical to case 2.3. Earlier rows remain unchanged,
and a missing match performs no write. Saved yellow with visible formatting
overrides returns `completed` with a warning; missing saved yellow still fails.

This case performs an AS spreadsheet lookup/highlight, not a device signal
check. It does not call case 4.2 or search the city rosters. Graph input:
`{"case_id":"4.3","message":"울진북로 164 김순옥님 신호확인요."}`.
Restart an existing Agent Server to load the code; the CLI loads it each run.

Live case 4.3 verification on 2026-11-03 selected row 689 for the supplied
example and confirmed saved yellow across `AS 관리!A689:AJ689`. The result was
`completed` / `highlighted_with_warnings` because existing formatting overrides
the visible colors. All 104 focused AX768/contract tests and scoped Ruff checks
passed.

### Comma-separated roster lookup

Case **6.2** finds the correct user row across the same three user rosters as
case 4.2. Run:

```bash
uv run python -m apps.ax768.run --case 6.2 "왕피길83-15,정영자,기기위치조정 수신확인요~"
```

Input format is `주소,이름,요청내용`. All three fields must be nonempty. The
first two commas separate the fields; later commas remain in the request text.
The example searches address `왕피길83-15` and name `정영자`. Surrounding
whitespace and an optional `님` suffix on the name are accepted. The request
text stays in the original input but is not used as a search key or executed.

The agent searches **울진군 (uljin-users) → 광명시 (gwangmyeon-users) → 영덕군
(yeongdeok-users)**. Both name and address must match on the same row; the
bottom-most row wins within the first matching sheet. It stops on a match or
error, advancing only after a genuine not-found result. Results include city,
sheet alias, row, source link and search attempts. If all three sheets have no
match, it completes with a not-found response.

This case performs only lookup: no highlighting, data edits, device-position
adjustment or reception/signal checks. It reuses case 4.2's target map, bounds
and auth; no new environment variables are needed. Graph input:
`{"case_id":"6.2","message":"왕피길83-15,정영자,기기위치조정 수신확인요~"}`.
Restart an existing Agent Server to load the code; each CLI invocation uses the
current code.

Live case 6.2 verification on 2026-11-03 found **울진군 / uljin-users, row 369**
for `정영자 / 왕피길83-15` and stopped before the later sheets. No cells were
changed. All 122 focused AX768/contract tests, scoped Ruff and diff checks passed.

### Comma-separated AS lookup

Case **6.3** finds the bottom-most AS row matching both address and name, then
applies yellow background across the row:

```bash
uv run python -m apps.ax768.run --case 6.3 "왕피길83-15,정영자,기기위치조정 수신확인요~"
```

Input follows case 6.2's `주소,이름,요청내용` format. The example searches
address `왕피길83-15` and name `정영자`. All fields must be nonempty; only the
first two are used for matching. The request text does not trigger device actions
or reception checks. It uses the AS Sheet configuration shared with cases
2.3/4.3 (`AX768_CASE_2_3_*`, `AS 관리`, name I, address H, data from row 7).

Both fields must match on the same row, with the largest row number selected.
The action rechecks the match before applying background-only formatting. No
match means no write. Confirmed stored yellow completes with warnings if existing
formatting overrides the visible colors; missing saved yellow fails. Values,
formulas and earlier matching rows are preserved. Existing conditional-format
rules are unchanged, so yellow may be stored without appearing on screen.

Graph input: `{"case_id":"6.3","message":"왕피길83-15,정영자,기기위치조정 수신확인요~"}`.
No new credentials or environment variables are needed. Restart an existing
Agent Server to load the code; the CLI uses current code each run.

Live case 6.3 run on 2026-11-03 found no AS row matching both `정영자` and
`왕피길83-15`; it returned `not_found` and changed no cells. Live highlighting
for this particular input remains unverified. All 136 focused AX768/contract
tests and scoped Ruff/diff checks passed.

### General tool contract

Input: a natural-language `message` of 1–8000 characters. Output: `status`,
`response`, and ordered `observations` with tool arguments and Google receipts.
Status is `completed`, `blocked` (missing sheet/auth configuration), or `failed`.
A completed response can ask for clarification without performing an edit.
Runtime instructions live in [skills/google_sheets.md](skills/google_sheets.md)
and are loaded into the model's system prompt. They are agent capabilities,
not global Codex configuration.

Supported tools read/write cells, append rows, clear values, add/rename/delete
tabs, and delete rows/columns. Ordinary cell writes keep formatting. RAW writes
are the default; formulas require explicit USER_ENTERED actions. There is no
unrestricted API, filesystem, shell, web, Drive-file deletion or sharing tool.
Actions target the operator-configured spreadsheet for the selected case;
case 2.2 uses its separate search/highlight target and case 4.2 uses the three
approved user rosters in order. Model output cannot supply another
spreadsheet ID. Formatting design, spreadsheet creation,
and additional workflows can be added as separate capabilities when needed.

Limits: ten actions per run, 2000 cells per explicit rectangle/write, 200 rows/
columns per deletion, bounded prompt/tool payloads, 30-second Google HTTP timeout.
Append uses Google's table detection and may write beyond its search rectangle.
There is no automatic tool retry. Metadata identifies sheet IDs and is refreshed
after structural changes. Instructions require reading before edits and checking
results; semantic correctness of the model's selections still needs live evaluation.

## Recovery and verification

Formatting verification requests only stored/effective background colors. This
fixes the oversized readback for `상밤터1길 59-4`: the previous request returned
128,726 bytes for row 3548 despite a successful address search. The transport
limit remains 128,000 bytes; this failure did not require smaller search pages.
Because readback follows the write, the earlier failed run may already have
applied yellow. Repeating this background-only action is idempotent, subject to
the usual recheck of the selected address.
Live retest reduced readback to 38,524 bytes. Row 3548 received yellow stored
backgrounds, but C3548 and E3548 remained visibly blue. This is reported as
`highlighted_with_warnings` with top-level `status: completed`, and
`overridden_cells` (up to 20) and
`overridden_cell_count` identifying background overrides. Existing conditional
formatting is not changed by this tool.

Each graph node records its result in Agent Server checkpoints. CLI output shows
partial completion too. Tool errors stop the loop; a timeout can mean Google
committed the mutation without returning its receipt. Inspect actual cells and
recorded observations before issuing a new task. Do not automatically replay
append/delete actions or resume a pending mutation after a crash: a Google write
and a LangGraph checkpoint are not one transaction. Concurrent edits are not
serialized and cross-action rollback/exactly-once execution is not provided.
This initial manual workflow is not an unattended job runner.

Acceptance checks cover fixed target isolation, schema rejection, bounded ranges,
read/update/verify completion, failed mutation without retry, missing configuration,
and correct Sheets request semantics. The configured local model passed a live
structured-action check using synthetic metadata, selecting the requested read
range correctly. End-to-end Google evaluation is pending the OAuth client file and user consent. No real spreadsheet was modified during implementation.

References: [Sheets value operations](https://developers.google.com/workspace/sheets/api/guides/values),
[structural requests](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request),
[service account authentication](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.service_account.html).

OAuth references: [Google Desktop/CLI OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[refresh token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).

Validation on 2026-10-30: 28 OAuth/workflow/dependency-boundary/graph-entry tests passed; scoped Ruff and LangGraph validation passed. OAuth tests cover private token storage, refresh persistence, revoked grants, missing scopes/offline permission and loopback/PKCE configuration. Real Google consent and row 81 writing await the user login.
