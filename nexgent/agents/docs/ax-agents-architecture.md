# AX Agents Architecture

## Information master-page address equivalence (2026-11-13)

Information-update member matching allows omission of known administrative
prefixes for the already-resolved roster region, while retaining exact name and
remaining address matching and a single-candidate requirement. Full member
identity is still reread around writes. This fixes county-prefixed master
addresses differing from 읍/면-prefixed roster addresses. Member failures now
report their phase and safe cause. Single-candidate address conflicts include
bounded candidate-ID/address evidence in the admin receipt, while conflicting
addresses still block and a new phone number cannot override that conflict.
Existing device/standalone member policy,
shared transport, graph version 2 and verified-write gates remain unchanged.
See [reproduction and checks](ax768-information-update-workflow.md).

## Bounded information-workflow roster reads (2026-11-13)

Information lookup scans names only, then rereads exact-match details in batches
of 20 rows. This avoids exceeding the existing 128 KB Sheets transport limit
when large rosters contain Korean addresses. Concurrency remains bounded at three;
failed/cancelled reads drain sibling tasks before the HTTP client closes. Identity
drift stops resolution. Roster receipts now identify the failing phase and safe
reason rather than replacing technical failures with input-correction guidance.
Version 2 and write gates are unchanged. See [reproduction and validation](ax768-information-update-workflow.md).

## Structured birthday input compatibility (2026-11-13)

The information-update planner recognizes reviewed `이름 · 생년월일: 값`
fields as update intent. A complete single-field request has a deterministic
parser; richer drafts retain the tool-free model step. Dotted birthdays are
calendar-validated, grounded against their literal source, then normalized to
compact strings without inferring a century. Version 2, roster/AS/member policy
and source grounding for other fields are unchanged. See the dated correction
in [the workflow contract](ax768-information-update-workflow.md).

## Information confirmation and update execution (2026-11-12)

The separately versioned `ax768_information_update` graph owns the authorized
information-update write path: tool-free grounded intent → one regional roster
row → all matching information-confirmation AS cases → appended master-page
notes. Version 2 removes region from input and searches 울진 → 광명 → 영덕
sequentially, stopping at the first uniquely resolved roster. No-match advances;
read errors and unresolved ambiguity stop. The resolved region is retained for
dependent-stage rechecks and returned as evidence. Roster identity
uses existing subscriber details, with exact-name AS fallback; new subscriber
and guardian numbers never substitute for old identity. Fixed live-verified
headers protect birthday/phone/guardian cells and existing formula columns.

The admin/CSRF endpoint `/api/ax768/workflow/information-runs` gates version 2,
validates ordered receipts and strips private snapshots. Each write rechecks and
reads back its target; unknown outcomes stop dependents without retries. AS absence
is a verified skip; other ambiguities block. Notes append and deduplicate while
preserving history. Existing device and extraction contracts are unchanged. No
new process or credential boundary is introduced. Agent Server rebuild remains
required. File-registered entrypoints use absolute workflow imports because the
server loads them without a package context; registration tests now cover both
information graphs. See [contract, tests and recovery](ax768-information-update-workflow.md).

## AX768 workflow-specific information extraction (2026-11-12)

`information_update` now has a dedicated tool-free extraction graph,
`ax768_information_extraction`, inside the existing AX768 module. It uses the
configured local model to discover arbitrary fields from supplied text and local
OCR output. Labels retain entity/relationship and old/new-value context. Every
value must be a literal substring of its identified source. This step has no
Sheets/member/device tools and performs no business-record updates.

The admin/CSRF endpoint `POST /api/ax768/workflow/extract` accepts only this
workflow, up to six 8,000-character sources, and checks extraction version 1
before stateless dispatch. Sources are chunked at at most 1,000 characters,
preferring line boundaries with overlap on long lines, to fit the deployed 8K
model context. At most two chunk calls run concurrently, with no transport
retry and a 100-second aggregate budget. Truncation, invalid grounding or any chunk failure
rejects the whole extraction. The API validates grounded output again.

The composer routes extraction by workflow. Device adjustment retains its
existing deterministic name/address/action parser; no selection retains raw
text. Information update auto-analyses image OCR and offers text-only analysis.
Drafts are editable with original sources retained. Workflow changes cancel the
browser request and invalidate late results. Images stay local; recognized text
is sent to the private agent/model. Agent Server registration requires a dev
image rebuild; no new process, credentials or model dependency is introduced.
See [implementation, validation and activation](ax768-information-extraction.md).

Chat screenshot correction (2026-11-12): extraction now distinguishes body
subjects from sender/reply headers, qualifies multi-person fields by subject,
preserves explicit names and add/change requests, and excludes interface/OCR
noise and chat-only timestamps. Meaningful uncertain text, literal identifiers,
business times and distinct device/signal observations remain. Successful empty
extractions no longer restore raw source text into the structured draft; the UI
shows a no-case-information status and retains the source internally for retry.
The version-1 field schema, grounding checks and no-write policy are unchanged.
A reply-header guard rejects assigning a known sender as subject unless the
source also explicitly identifies that person as a subject. Bounded source
context hints guide the model; one semantic correction attempt is allowed per
chunk within the same deadline, after which the whole result fails. Subject
names implied only in qualified labels become explicit name fields only with
matching body-name evidence. An opt-in anonymized live-model regression covers
these semantics.

## Device adjustment three-stage refactor (2026-11-11)

The version-5 AX768 workflow now routes by verified stage receipts and sends
every exit through a final result node with dependent-stage skip reasons.
Successful AS completion remains running until the member stage completes.
Name-only requests still resolve the bottom-most exact-name AS address before
the ordered roster/IMEI search; a missing AS row after successful signal
verification bypasses only the AS writer. Technical AS errors and uncertain
writes stop member processing. The UI groups receipts into three stages:
신호확인, AS 시트 반영, and 마스터페이지 일반사항. OCR preserves one recognized
action in canonical input, flags conflicting actions, and never invents one.
Existing write policy, version-5 schema, process boundaries, and credentials
remain unchanged. See [implementation and validation](device-adjustment-three-stage-refactor.md).

## Device adjustment member general notes (2026-11-10)

The unified AX768 workflow is now version 5. A final `member_note_step` follows
verified AS completion, or confirmed AS absence after a fresh connected signal.
It reuses the member replacement implementation with resolved roster name and
address. Explicit request action, otherwise verified AS completion type, selects
기기위치조정/전원연결. Missing/ambiguous action stops without guessing. Notes use
AS processing date or the current Asia/Seoul date when AS is absent.

State adds a nullable member receipt; both product boundaries require verified
member evidence for overall completion and preserve signal/AS results on member
failure. Failed/unknown AS or signal results never reach member writing. API and
browser timeouts increase to accommodate the 120s member step. The UI adds a
fifth result section. No process, credential or dependency boundary changes.
See [behavior, verification and activation](device-adjustment-member-note-step.md).


## AX768 member general-note Test case (2026-11-10)

The existing AX768 graph now has an explicit `member_note` case with capability
`member_note_case_version: "2"`. It bypasses Google/model setup, searches the
fixed member-admin API, prefers an exact name match and otherwise accepts one unique partial-name
match, always respecting supplied address/ID. It replaces only `general_notes`
with the entered text. Identical whole-field values are skipped; identity/notes are reread before PUT and verified
afterward. An uncertain dispatched write has an `unknown` receipt and is not
retried. The old tests retain their search-only policy; device workflow v4 is
unchanged. A shared fixed-origin adapter owns private JSON login and HTTP, while
the workflow owns member/replacement policy. Product API/browser boundaries validate
the new minimal receipt. Compose adds one dedicated read-only credential mount.
See [implementation, validation, activation and concurrency limits](ax768-member-general-note-test.md).

## AX768 image input preparation (2026-11-10)

Only the `/agents/ax768` Workflow composer now runs local Korean/English OCR
when images are added. Browser preprocessing and pinned same-origin OCR assets
produce editable name/address/request fields with raw text available for review.
The composer converts these fields into the existing canonical text request on
explicit Run; the agent graph, API schema and signal-before-AS policy stay the
same. No image or raw OCR instruction is sent to the workflow. Conflicts and
stale asynchronous results are handled in the composer, and other agents' image
paths are unaffected. See [scope, implementation and validation](ax768-korean-image-input.md).

## Device adjustment signal-gated completion (2026-11-09)

The unified `ax768_workflow` is version 4. Name-only input first resolves the
bottom-most exact-name AS row and its address. Both input modes then search the
ordered rosters by name/address, recheck the selected identity and read its
city-specific IMEI (울진 AA, 영덕 Z, 광명 W), and use the existing Ansimk signal
adapter. These columns were verified against live IMEI headers on 2026-11-09;
the earlier Z/Y/V mapping referred to S/N. Only a fresh connected result can reach the existing bounded AS
completion writer. Disconnection and unknown/failed signal checks never write
AS. Supplied-name/address requests resolve AS after the successful signal;
name-only requests retain and recheck their initially selected AS row.

The graph adds a bounded `signal` receipt and a `disconnected` outcome. The
product API requires version 4 before dispatch and validates signal evidence
before accepting an AS completion receipt. Reports preserve independent signal
and AS outcomes, including connected devices whose AS update is unknown. No
master-page notes are written. Shared IMEI reading remains inside the AX768
workflow module; the standalone IMEI test remains search-only. Existing graph
IDs, credentials and process boundaries are preserved. Stage budgets are
45s AS + 100s rosters + 20s IMEI + 60s signal + 40s update.

See [implementation, tests and required runtime activation](device-adjustment-signal-gated-workflow.md).

## AX768 IMEI signal Test case (2026-11-04)

`--case imei` is a deterministic case in the existing `ax768` graph and Test
workspace. It parses the person's name (and optional typed address), searches
the existing fixed rosters in 울진 → 광명 → 영덕 order, chooses the largest
matching row and rechecks name/address while reading the configured IMEI cell.
Invalid/missing IMEI stops at that person. It never edits Sheets, calls the AS
completion graph, chooses a different person to get an IMEI, or calls the LLM.

The workflow owns roster/column policy and the two required Korean messages.
The shared `ax_integrations.ansimk` adapter owns the fixed-origin admin login,
private cookie cache and signal API validation. Input uses the API's `sn` field
with a 15-digit IMEI; the response must contain that IMEI, a string serial number,
a boolean connection state and (for positives) fresh evidence. The user-facing
S/N comes from the response, preserving leading zeros. Other HTTP or auth errors
remain unknown/failed checks and never produce the disconnected-device message.
Raw device payloads, subscriber records, phone numbers, login codes and cookies
are excluded from the returned graph receipts.

A valid cached/seeded cookie is reused. One explicit HTTP 401 allows one login
and one resubmission; 403, timeout and server failures are not retried. Codes
remain in a private file; refreshed cookies are atomically saved with mode 600.
The dev container has read-only mounts for code and initial session plus a
private named volume for renewed sessions. Standard authenticated HTTPX access
works; no browser process or new Python dependency is required. Roster and
signal stages have 150s/75s bounds inside the existing product API timeout.

The existing `/api/ax768/runs` boundary adds case ID `imei`, requires the graph's
`imei_case_version: Literal["1"]`, validates source/IMEI/S/N/connection receipts
and only exposes bounded fields. The Test tab displays the requested Korean
message, city, row, source link, IMEI column/value, serial number and signal
strength, with separate connected, disconnected and failed outcomes. Existing
numbered cases and the unified AS completion workflow retain their contracts.

See [case usage and credential setup](../workflows/ax768/README.md#imei-test-case).

## AX768 AS completion update (2026-11-04)

Unified workflow version 3 adds `as_update_step` after a successful AS lookup.
Only the selected AS row changes: S is `처리완료`, X is the current Asia/Seoul
date, and Y is `위치점검완료` when C is `기기위치 점검` or `전원연결완료`
when C is `기기전원 연결`. Other C values leave Y untouched. The seven numbered
Test cases remain search-only. No background highlighting or device action occurs.

Workflow-owned `as_update.py` validates the selected spreadsheet/tab/row against
the configured AS client, refreshes metadata and rechecks name/address on that
row before reading C. It submits one `spreadsheets.batchUpdate` with two or three
single-cell UpdateCells requests, then reads back identity/C and changed values.
X uses a numeric Sheets date with only its number format set to `yyyy-mm-dd`;
S/Y use literal strings. Value fields and X's number format are the only write
masks. Other values, formulas and background formatting are excluded.

The update receipt records target row, Korea date, requested S/X/Y values,
Y unchanged/updated policy and readback verification. Completion requires a
verified update, not just a successful lookup. Pre-dispatch failure reports no
write sent. After-dispatch errors, timeout, identity/C changes or readback
mismatch report an unknown update and retain roster/AS evidence. No automatic
mutation retries are configured. Sheets offers no conditional compare-and-set
for these cells; concurrent row changes can race the recheck, and failed
readback does not roll back a write. An uncertain result must be inspected
before manually rerunning. Existing server checkpoints do not provide an
exactly-once guarantee after a process crash.

Rosters have a 150s budget, AS lookup 60s and update 40s, within the existing
270s API / 285s browser limits. The admin API requires workflow version 3,
validates exact S/X/Y receipts and returns a third stage to the UI. Browser
copy discloses the write before Run, shows verified versus requested values,
and preserves lookup receipts when the update fails. No new input parameter,
credential or process is added. See
[implementation and checks](../../docs/08-implementation/ax768-case-workspace.md#as-completion-step-2026-11-04).

## AX768 automatic region from ordered rosters (2026-11-04)

The operator removed manual region selection. Unified workflow version 2 accepts
text and an optional confirmed candidate name only; the UI, API and CLI no longer
accept a region. Every request, including name-only, searches 울진 → 광명 → 영덕
and stops at the first matching roster, returning that roster's city and latest
row. A missing match advances to the next roster; a read failure stops. If none
matches, AS is skipped. Name-only requests then search AS by name only, selecting
the bottom-most exact name; name/address requests keep both fields. The reported
city is the roster source, not a separate assertion about the AS row's address.

The product API requires `workflow_version: Literal["2"]` so an old version that
skips rosters for name-only input is blocked before execution. No credential,
write policy, target order or process boundary changed. This supersedes the
manual-region and name-only skipping behavior documented in version 1 below.

## AX768 unified roster and AS workflow (2026-11-04)

`ax768_workflow` is a separate versioned graph in the existing AX768 capability.
It parses one text request deterministically, then searches fixed rosters in order
울진 → 광명 → 영덕 and hands the matched name/address to the bottom-up AS lookup.
Name-only requests skip rosters; an optional user-selected KakaoTalk room region
is recorded as context, never inferred from a same-name person or used as an AS
filter. The seven Test cases keep their existing contracts.

The shared GET-only `sheets_lookup` helper normalizes internal name whitespace,
requires name/address on the same row, selects the largest row number, and
rechecks the selected cells. It preserves the 100,000-cell target bound, 2000-cell
pages and existing response cap. The workflow prefers an exact match in any
roster over earlier suggestions. When no exact match exists, exactly one complete,
address-matched suggestion differing by one Korean syllable (3–5 syllable names)
is re-read and automatically used for AS; the correction is disclosed. Multiple
candidates or truncated suggestions require a name selection and a fresh lookup.
No AS fuzzy matching, LLM name invention, sheet writes or device operations occur.

The admin/CSRF product boundary `POST /api/ax768/workflow/runs` accepts only text,
optional region and an explicitly selected candidate name. It checks the private
assistant's `workflow_version: Literal["1"]` schema before dispatch, normalizes
bounded stage receipts and generates safe row links. Missing/older runtime returns
409. Roster failures stop fallback; AS failures retain the earlier roster receipt.
Rosters have a 180-second budget, AS 60 seconds, API 270 seconds and browser 285
seconds. No automatic retry follows an uncertain transport result. Web runs are
stateless and deleted on completion; browser drafts/results live only in component
memory and survive tab switches, not page/account changes. There is no job store.

The Workflow tab has combined input, optional region, elapsed loading and two
result stages with source city/sheet/row. Images remain local previews; execution
requires text and no attachments, with an explicit transcription instruction.
Actual OCR and KakaoTalk integration remain future work. Deployment requires
rebuilding Agent Server to register the new graph. See
[workflow behavior and validation](../../docs/08-implementation/ax768-case-workspace.md#unified-roster-and-as-workflow-2026-11-04).

## AX768 searches without highlighting (2026-11-04)

The operator disabled yellow highlighting. All seven numbered cases now perform
read-only lookup; case 1.1 and the name shorthand use `search_name`, case 2.2 uses
`search_address`, and AS cases 2.3/4.3/6.3 use `search_person_row`. Ordered roster
cases 4.2/6.2 are unchanged. Latest-row selection, target configuration and result
links remain. New read-only shared actions reuse existing bounded matching;
shared highlight tools remain for compatibility but AX768 rejects their execution,
including stale saved decisions. Existing sheet formatting is left untouched.

The graph input schema advertises `case_policy: Literal["search_only"]`. Before
submitting a web run the product API checks the private assistant schema for that
policy; an older graph receives no run and the browser reports that Agent Server
needs a restart. This prevents a live old image from highlighting after the UI
has switched to search-only labels. No general-purpose write capability is
exposed through the numbered-case API.

See [search-only rollout and checks](../../docs/08-implementation/ax768-case-workspace.md#search-only-update-2026-11-04).

## AX768 browser case workspace (2026-11-04)

The Nexgent frontend exposes an admin-only `/agents/ax768` case runner for the
seven existing deterministic workflows. The product backend accepts only an
explicit case ID and text at `POST /api/ax768/runs`, checks admin/CSRF permissions,
and invokes private Agent Server assistant `ax768`. It returns bounded,
normalized receipts instead of raw graph state. The workflow remains the owner
of parsing, target configuration, latest-row selection and highlight verification.
No new graph, shared-package dependency, persistent job store or general prompt
execution path is introduced.

Raw Agent Server proxy endpoints require admin access, except authenticated
GET/HEAD `/ok`; normal chat retains its product API boundary. The dev Agent Server
receives the existing service-account key through a read-only file mount.
Browser drafts/results are session memory only (last 20 runs), cleared on refresh
or identity/access changes. Loading uses elapsed time, not inferred stage progress.
A timeout yields an unknown outcome and no automatic retry. Stored yellow with
conditional-formatting overrides completes with a visible warning.

See [implementation, validation and pending runtime restart](../../docs/08-implementation/ax768-case-workspace.md).

## AX768 comma-separated AS lookup, case 6.3 (2026-11-03)

`--case 6.3 "왕피길83-15,정영자,기기위치조정 수신확인요~"` uses case 6.2's
comma-separated address/name/request parser and the existing AS person-row
highlight action. It reuses `AX768_CASE_2_3_*` configuration and the same bounded
bottom-up search, same-row matching, recheck and background-only write as cases
2.3/4.3. The request text is retained in the input but not executed or matched.
No match causes no write; saved yellow with visible overrides completes with a
warning, while missing stored yellow fails. No city-roster search, signal check
or device operation occurs. Tests cover parsing, AS target isolation, action
restrictions and completion with warnings. Existing checkpoint/retry semantics
are unchanged; no new contract or target configuration was introduced.
The supplied live case 6.3 input returned `not_found` with no write; 136 focused
AX768/contract tests passed.

## AX768 comma-separated roster lookup, case 6.2 (2026-11-03)

`--case 6.2 "왕피길83-15,정영자,기기위치조정 수신확인요~"` splits the first
two commas into address, name and request text. Nonempty fields, a numbered
address and a Korean name are required. Surrounding whitespace and optional
`님` on the name are removed; commas after the second remain part of the request.
The original message retains that request in state, but only name/address enter
the existing typed `search_user_sheets` action. No device operation or receipt
check is performed.

Case 6.2 shares case 4.2's fixed targets, auth and deterministic read-only path:
울진 → 광명 → 영덕, advancing only after no match, stopping on the first
bottom-most same-row match or on an error. It returns city, alias, row, source
link and ordered attempts. It neither highlights nor edits. Existing bounds,
checkpoints and retry policy apply; no new schema or target configuration was
needed. Tests cover comma parsing, malformed inputs, request-text isolation,
all target positions, missing matches, failures and mutation rejection.
The supplied live example found 울진군 row 369 without writes. All 122 focused
AX768/contract tests passed.

## AX768 AS signal-request lookup, case 4.3 (2026-11-03)

`--case 4.3 "울진북로 164 김순옥님 신호확인요."` uses case 4.2's optional
signal-request suffix parsing and case 2.3's AS lookup/highlight operation.
It emits the existing `find_and_highlight_person_row` action and uses the same
`AX768_CASE_2_3_*` target settings: AS 관리, name I, address H, data from row 7.
No new integration, credentials or duplicate target configuration is needed.
It searches bottom-up for both fields on one row, rechecks them and highlights
only that row. Missing matches cause no write. Saved yellow across the row
completes with warnings for visible overrides; missing saved yellow still fails.
It neither searches city rosters nor checks device signals. The graph restricts
this case to the AS action, with existing bounds, checkpoints and no automatic
write retry. Tests cover CLI/suffix parsing, AS target isolation, forbidden
actions, and completion with warnings.
Live execution selected AS row 689 and confirmed saved yellow across A689:AJ689;
the run completed with visible-format override warnings. All 104 focused
AX768/contract tests passed.

## AX768 ordered user-sheet lookup, case 4.2 (2026-11-03)

`--case 4.2 "울진북로 164 김순옥님 신호확인요."` parses the address and name
into a typed `search_user_sheets` action. The workflow-owned `city_search.py`
holds the three approved targets and their order: uljin-users (울진군),
gwangmyeon-users (광명시), yeongdeok-users (영덕군). These are the supplied user
rosters, not the AS tab used by case 2.3. No input/model output can substitute
another spreadsheet. Existing auth is reused; no separate target env vars are
needed. The fixed case bypasses the model and performs no writes or signal checks.

The shared `search_person` integration is extracted from case 2.3's search path.
It finds and rechecks the bottom-most row where name and address match together,
without formatting it. Case 2.3 wraps that search with its existing highlight.
Case 4.2 tries targets sequentially, advances only on `not_found`, and stops on
the first match or any read/auth/configuration failure. A failure remains a
failure, with prior attempts recorded; it never implies a city was searched
successfully. A match returns city, configured alias, spreadsheet/tab IDs, row,
matched address cell, name cell and a direct sheet/row URL. Earlier sheets have
priority; row numbers are compared only within each sheet.

Verified layouts: 울진 C/H from row 6, 광명 D/G from row 5, 영덕 C/H from row 6
(name/address columns). The same 100,000-cell per-target bound, 2000-cell page
bound, 128,000-byte response cap, timeout and no-automatic-retry behavior apply.
Only matched fields and compact attempt receipts enter graph state. Case 4.2
rejects mutation actions; its tool is unavailable in other modes. Existing
server checkpoints retain the result; the CLI remains stateless.

The supplied live example found 울진군 row 44 and stopped before accessing later
targets. All three target tabs and headers were read successfully. Tests cover
ordered second/third-sheet fallback, all-not-found, same-row matching, bottom-most
selection, early stop, read failures, parsing, case isolation and no writes.
See [command and target map](../workflows/ax768/README.md#ordered-user-sheet-lookup).

## AX768 saved-highlight completion with warnings (2026-11-03)

Cases 2.2/2.3 now separate saved background verification (`stored_verified`)
from visible yellow verification (`verified`, retaining its existing meaning).
When every existing cell has saved yellow but some display another color, the
tool returns `highlighted_with_warnings`; the graph reports `completed` and the
CLI exits successfully. The response identifies overridden cells without claiming
the whole row appears yellow. Missing stored yellow or incomplete row readback
still fails. Case 1.1 retains its existing strict name-cell verification policy.
This changes only completion semantics, not spreadsheet conditional formatting.
Regression checks cover both cases, true missing-format failures, incomplete
readback and the normal visible-yellow path.
Live retest of `오봉길 24 주정수` completed at row 985 with saved yellow across
A985:AJ985 and warnings for C985/O985. All 85 focused AX768/contract tests pass.

## AX768 formatting readback size fix (2026-11-03)

Case 2.2 address `상밤터1길 59-4` selected row 3548, but requesting all stored
and effective formatting returned 128,726 bytes, exceeding the transport's
128,000-byte limit. Address search pages themselves were below the limit.
Row verification (cases 2.2/2.3) and name-cell verification (case 1.1) now request
only `backgroundColor` and `backgroundColorStyle` inside both format objects;
name verification also retains `formattedValue`. This preserves stored/visible
yellow checks while excluding irrelevant borders, text styles and other formats.
The response limit, search page sizes, mutation masks and no-write-retry policy
are unchanged. A large-format regression fixture exercises the real byte guard.
Live readback dropped to 38,524 bytes. Row 3548's stored backgrounds are yellow,
but C3548 and E3548 remain effectively blue. The initial strict visibility
policy reported failure; the saved-background policy below now treats this as
completion with a warning. Results now report up to 20 `overridden_cells` and the full
`overridden_cell_count`; user responses identify these cells without modifying
existing conditional-format rules.

## AX768 AS Sheet name/address matching, case 2.3 (2026-11-03)

`--case 2.3 "후포로 158 김동명"` deterministically parses the final whitespace-
separated Korean name and preceding address into `find_and_highlight_person_row`.
Malformed input is rejected before external access. This case has its own
`AX768_CASE_2_3_*` spreadsheet, numeric tab ID, name/address column and first-data-row
settings. The live AS Sheet uses tab `AS 관리` (2142794645), column I for 가입자,
H for 주소 and data beginning at row 7. Other cases keep their targets and behavior.

The integration reads at most 100,000 configured grid cells in pages of at most
2000 cells, visiting pages and rows bottom-up. The entire name cell must match
after NFC normalization and trimming; the address uses the existing literal
fragment matcher with whitespace normalization and numeric boundaries. Both must
match on one row. It stops at the first qualifying row (largest row number),
rechecks both cells, and highlights only that row across all existing columns
(up to 2000). Shared background-only formatting verifies stored and effective
yellow for every cell. Saved yellow across the row is sufficient for completion;
visible overrides produce a warning. No match performs no write. `match_count` is 0 or 1,
describing the selected row, not a total of earlier matches. No model is called.

The graph rejects unrelated actions in case 2.3 and this case's action in other
modes. Read/write failures stop without automatic retry; concurrent edits may
still race the recheck. Existing checkpoint and partial-write recovery semantics
apply. Tests cover same-row requirements, numeric false positives, descending
pagination, latest selection, no match, changed name/address, read failure,
conditional-format verification and case isolation. See
[configuration and command](../workflows/ax768/README.md#as-sheet-name-and-address-search).
Live execution of the supplied name/address returned `not_found` without writes.
All 80 focused AX768/contract tests passed; live highlighting for a case 2.3
match remains unverified.

## AX768 address search, case 2.2 (2026-11-03)

`--case 2.2 "후포로 158"` selects a deterministic `find_and_highlight_address_row`
action. The workflow selects `AX768_CASE_2_2_SPREADSHEET` and
`AX768_CASE_2_2_SHEET_ID` using the existing auth provider; optional
`AX768_CASE_2_2_ADDRESS_COLUMNS` restricts the search to a column span. Case 1.1 and general
mode retain their existing target. The shared typed action cannot supply a
spreadsheet ID. Execution permits only address search and row highlighting in
case 2.2 and rejects these tools outside that case before opening a Sheets client.
The old `search_address` action remains read-only for existing recorded decisions.

The integration scans the configured tab/column span in pages of at most 2000 cells,
capped at 100,000 scanned grid cells and 100 matched cells. The live target uses
G:H, identified from its road-address headers; its full 47-column grid exceeds
the scan limit. Matching is a literal substring
after NFC normalization, whitespace removal and case folding, with numeric
boundaries to avoid matching 1580 for 158. Each address must occur within one
cell; adjacent cells are not combined. Results contain matching row numbers and
address cells, sorted by descending row number, with `selected_row` identifying
the bottom-most match. The selected row's matching addresses are rechecked before
a single background-only repeatCell batch colors the entire row yellow, from A
through the tab's last column (up to 2000 cells). No match means no write. Both
stored and effective colors are checked for every cell. Missing stored yellow
fails verification; stored yellow with visible overrides completes with a warning. No model calls occur. Search failures precede
any write. Concurrent changes can still race the recheck; no automatic write
retry occurs. The CLI has no persistent checkpoint;
server runs use existing graph checkpoints.

Acceptance checks cover normalized and bounded-number matching, pagination,
bottom-first grouping, no matches, read failures, target isolation, CLI routing
and unrelated-mutation rejection, changed addresses, conditional-format overrides,
and write failures. Live search verification succeeded with the configured service
account: the supplied address matched eight rows, with 3998 bottom-most. The
subsequent live highlight verified yellow across `A3998:AU3998`; 68 focused
AX768/contract tests passed. See
[configuration and command](../workflows/ax768/README.md#address-row-search).

## AX768 Korean name highlight (2026-11-03)

AX768 maps the explicit Korean shorthand `<name>님 신호확인요.` to a typed
`find_and_highlight_name` action. This fixed request uses deterministic parsing
and executes one constrained operation, while other requests retain the local
LLM decision loop. It means a spreadsheet name highlight, not a device signal
check. The runtime skill also exposes the action for model-directed requests.

The CLI now selects this workflow with `--case 1.1 "<request text>"`.
`workflows/ax768/cases.py` owns registered case IDs; the CLI and graph validate
unknown cases or mismatched text before calling external services. Case IDs
remain strings (1.10 is not 1.1). The graph records `case_id` in state/results.
Omitting the flag preserves general mode and the existing shorthand behavior;
threaded API callers send `case_id: null` to clear a prior case selection.

The operator sets `AX768_SPREADSHEET` and `AX768_NAME_SEARCH_SHEET_ID` in the
unified .env. The shared integration scans only that numeric tab ID in bounded
2000-cell pages, matches NFC-normalized trimmed whole-cell text, and changes only
the bottom-most matched cell background color to yellow with repeatCell.
The largest row number defines latest; same-row ties choose the leftmost match.
Only that one name cell is highlighted, with the total candidate count and selected
row reported; earlier matches, unrelated names and cell values remain
unchanged. No match produces no write. At most 100,000 grid cells and 100 matches
are permitted; exceeding limits or failing any search read stops before writes.
Only match addresses and receipts enter graph state, not the scanned roster.

Targets are re-read before a single formatting batch. Readback checks both
stored and effective color so conditional-format overrides cannot be reported
as verified yellow. Search and write are not transactional against concurrent
sheet edits. A verification failure may follow an applied batch; uncertain HTTP
outcomes retain the existing no-automatic-retry policy. Repeat yellow formatting
is idempotent, but recheck the selected names before replay after an interruption.
See [configuration and command](../workflows/ax768/README.md#name-search-and-yellow-highlight).

## October 26 saved-count correction tool (2026-11-02)

`playground/fix-oct26-previous-counts/run.sh` previews or applies a fixed-week
repair for all saved October 26–November 1 reports. It copies each ward's
October 19–25 actual motion and remote-control totals into the newer report's
previous counts, then updates comparison percentages and displays. Current
counts, classifications, narrative, scores and guardian actions are preserved.
Local archive and production are separately selectable and default to both;
each reads its own prior saved report. The live preview confirmed identical
plans for both targets. This is an operator tool, not a scheduler or graph hook.

Writes use separate repeatable-read transactions, row locks, private flushed
backups, original-JSON checks and full patched-JSON verification before commit.
Missing baselines or invalid reports are skipped explicitly. Local commits
first; cross-database atomicity is not promised. Rerun preview after partial
failure and retry the failed target. Exports are not rewritten. Tests cover
scope, date/identity validation, field preservation, idempotence, missing/null/
zero/invalid values, backup failure, conflict rollback, readback failure and
partial-target cleanup. Applied and verified on 2026-11-02: each database
updated 5,571 reports, retained 717 already-matching reports and skipped nine
missing baselines. Post-commit previews showed zero eligible updates, and
before/after comparisons verified preservation of baseline and unrelated
fields. The 27 correction tests passed. See [commands, execution receipts and recovery](../playground/fix-oct26-previous-counts/README.md).


## Saved previous-week activity counts (2026-11-02)

The source API now copies previous motion and remote-control totals from the
same ward's saved report in local `archive.resources_ward_weekly_report` for
exactly the preceding Monday–Sunday. It reads
`living_activity.activity_detection.metrics.current_week` and
`living_activity.remote_control_usage.metrics.current_week`; it never
recalculates these two comparison totals from historical daily summaries.
Current-week totals still come from `ansimk.analysis_devicedailysummary`.
Percentages, classifications, narrative facts and guardian guidance use the
copied comparison totals through the existing deterministic policy.

The bounded, parameterized read uses the source API's `ANSIMK_DATABASE_DSN`
and requires SELECT on the local archive report table. This database must
contain the reports committed by the bulk writer (including when a separate
storage DSN is configured). Raw observations remain exclusively in `ansimk`;
this saved-report read is the explicit archive exception. Both interactive
and bulk generation share the source API. No full report JSON enters graph
state, and no new write path, connection setting or public schema is added.

Missing prior reports, missing/null fields and malformed, negative or
non-finite counts produce unavailable comparison values and the source warning
`ward-<id>: previous_activity_counts_unavailable`. Valid signals are copied
independently. Zero remains zero and retains the unavailable-ratio policy.
There is no raw-count fallback or lookup of an older report. A database read
failure follows the existing source error/retry path. Other previous-week
metrics, including risk events and compatibility activity averages, retain
their existing source calculations.

Acceptance: changing historical daily counts cannot change either saved
comparison total; current counts and risk metrics stay source-derived; exact
ward/week selection, null/zero/invalid counts and source failure are tested.
The regression reproduces the observed 2,278/1,123 saved counts versus
3,002/1,606 refreshed source totals with synthetic ward IDs.

Rollout: rebuild/recreate the source API between jobs and verify its archive
SELECT access. Start fresh jobs; already-staged bulk metrics and completed
reports retain their original values. Historical changes require explicit
regeneration, earliest week first when regenerating adjacent weeks, followed
by normal migration. Production-only manual corrections are not mirrored into
local archive reports, so reconcile the local baseline before expecting those
corrections to carry forward. Correcting incomplete current-week source data is
a separate concern; copying prior counts intentionally preserves the saved
report's value. Implementation does not deploy or rewrite stored reports.

Validation: 162 targeted source, graph, renderer, activity-policy, API and
quality tests passed. The PostgreSQL selection test passed with synthetic
inline rows in a read-only transaction. A read-only source-service check for
ward 13554 returned current 2,710/1,967 and copied previous 2,278/1,123, with
no warnings. Changed-file Ruff, LangGraph validation, local Compose rendering
and the weekly-reporter skill validator passed. Full-suite validation remains
incomplete: two existing notification deployment contracts fail against parent
Compose configuration, and broad runs stalled (including the existing bulk
source-timeout test). Whole-tree Ruff also reports existing ordering issues in
`packages/integrations/src/ax_integrations/__init__.py` and
`tests/unit/test_rag_chat_graph.py`. No parent Compose files were modified.

## Scheduled daily risk copy to production (2026-11-02)

The existing parent production Compose service now selects
`DAILY_RISK_SYNC_TARGET=both`. After the previous Seoul day's archive commit,
the scheduler copies the processed month to live dev, then live production,
using isolated `LIVE_DEV_*` and `LIVE_PROD_*` SSH/database settings and schema
`ansimk`. Production TLS defaults to `require`. The existing workflow-owned
copy preserves month scoping, staged validation, missing-ward skips,
idempotent upserts and destination verification. No new service is introduced.

Completion and success notification require every selected commit. Failure
stops subsequent copies, identifies the destination, and retains earlier
commits. Per-destination completion events and `live_targets` receipts expose
progress; `live` retains its previous dev receipt meaning. Replaying the same
date reconciles locally and retries both copies. Cross-database atomicity,
automatic retry and missed-run catch-up are not provided. Preview remains
local-only; `local`, `dev`, and `prod` modes remain individually selectable.

Tests cover commit ordering, dev/prod failure and replay, preview isolation,
local failure gating, settings isolation, schema/identity guards and month
scoping. Rebuild/recreate the scheduler to activate the new configuration.
See [daily risk operations](../apps/daily_risk_scheduler/README.md).

## Manual monthly risk copy to production (2026-11-02)

The operator CLI `playground/migrate/run.sh -target prod` previews the full
local archive risk table against production; `--migrate-to-live` commits.
It loads unified `agents/.env`, selects only `LIVE_PROD_*` destination settings,
and defaults production TLS to `require`. The workflow-owned copy implementation
retains staging validation, missing-parent skips, idempotent upserts, verification,
and one atomic destination commit. The scheduler now supports both live
destinations as described above.
See [commands and recovery](../playground/migrate/README.md).

## AX768 Google user OAuth (2026-10-30)

AX768 now defaults to user OAuth, selected explicitly in the unified local .env.
`ax_integrations.google_oauth` owns token loading, refresh, file locking, and
atomic mode-0600 token replacement; `apps.ax768.oauth_login` owns one-time consent.
Google's installed-app library handles PKCE and OAuth state. A Desktop OAuth
client plus an SSH-forwarded loopback listener permits login from a laptop
browser while the agent stays on the terminal-only Linux server. Consent waits
up to five minutes; no interactive authorization runs in a graph node.

The graph selects exactly one authentication mode, with no fallback to another
identity. Service-account mode remains an explicit option. User OAuth inherits
the user's file permissions and requests the Sheets scope; the fixed configured
spreadsheet still bounds tool execution. Token material stays outside graph
state, model prompts and results. Token directories must support writes for
refresh and locking; revoked grants require login again. Google external Testing
mode can expire these refresh tokens after seven days. Live consent and row 81
verification remain pending the user's Desktop client file and browser sign-in.
See [headless OAuth setup](../workflows/ax768/README.md).

## Chat upload limit increased to 50 MiB (2026-10-30)

Chat now permits 50 MiB per file and 50 MiB combined per turn, retaining the
five-file cap. Frontend selection and saved-file checks, backend upload and
reference validation, durable-file reads, and agent contracts/readers use the
same byte limits. Extraction and image pixel limits remain independent.
Deployment requires rebuilding the Agent Server and chat worker images; the
development frontend/backend source mounts can reload their local changes.
See [validation and rollout](../../docs/08-implementation/chat-upload-50-mib-limit.md).

## AX768 local-model spreadsheet agent (2026-10-30)

`workflows/ax768` introduces the private `ax768` graph, initially serving manual
Google Sheets tasks. It reuses the workspace OpenAI-compatible local model
settings and has no cloud fallback. Runtime skill instructions are workflow-local;
the decision schema is in `ax_contracts.sheets` and the async Sheets v4 transport
and service-account token adapter are in `ax_integrations.google_sheets`.
`apps/ax768/run.py` provides a manual CLI using the unified `agents/.env`.
The product chat API routing is unchanged.

An operator fixes one spreadsheet link/ID and private credentials path in
configuration. The model cannot change the target or issue arbitrary API calls.
Strict typed actions cover bounded cell reads/writes/appends/clears, tab changes,
and row/column deletion. The graph initializes metadata, then checkpoints each
decision/tool step independently, capped at ten actions. Observations preserve
arguments and Google receipts, structural writes refresh metadata, and failures
stop immediately with partial progress available. Reads and verification are
required by runtime instructions; model semantic correctness remains subject to
live evaluation. Missing sheet/auth configuration returns blocked without calls.

Tools have no automatic retries. Google writes and graph checkpoints are not
atomic; uncertain append/delete results require inspection before replay. The
CLI has no durable checkpoint, and this first workflow does not promise unattended
recovery, rollback, serialized concurrent editing, or exactly-once writes. Agent
Server remains responsible for thread persistence. See [AX768 setup, contract,
limits and acceptance criteria](../workflows/ax768/README.md). A live local-model
structured-action check passed with synthetic metadata. End-to-end Google
evaluation awaits the user's sheet link and service-account access.

## Production daily risk copy to live dev (2026-10-30)

Historical checkpoint: superseded by the November 2 dual-destination update above.

The production `daily-risk-scheduler` explicitly sets `DAILY_RISK_SYNC_TARGET=dev`.
After committing the previous Seoul day's local reconciliation, it copies the
selected month's stored rows to `LIVE_DEV_DB_*`, schema `ansimk`, through the
existing `LIVE_DEV_SSH_*` tunnel. This destination is intentional even though
the scheduler runs in the production container. Development retains local-only
behavior unless explicitly configured. The image now includes SSH and sshpass.

The workflow owns the copy implementation, shared with the manual migration.
It stages and validates a bounded stream, skips wards absent from dev, upserts
source-owned counts, arrays and timestamps, verifies eligible keys, and commits
one atomic destination transaction. Other destination months are untouched.
Historical dates in the selected month come from the archive snapshot. Monthly
historical initialization still requires the manual archive migration.

Success/completion follows both commits; live-copy failure exits nonzero and
reports that the local archive already committed. No cross-database transaction
or automatic retry is implied. Replaying the date reconciles locally again and
retries the idempotent month copy. Preview remains local-only and sends no
notification. Production database credentials are never selected for this copy.
Runtime recreation and replay are required to repair the previously reported
local-only success. See [daily risk operations](../apps/daily_risk_scheduler/README.md).

## Approved daily-risk environment mount (2026-10-28)

The production `daily-risk-scheduler` now mounts unified `agents/.env` read-only
at `/app/.env`, replacing the old backend notification-settings mount. This is
an explicitly approved deployment correction for the existing notification
reader; cron, database calculations, and Slack payloads are unchanged. Compose
validation passed. Runtime recreation remains an operator step because sudo
requires interactive authentication. Other parent scheduler changes remain
pending; the reviewed patch was refreshed to exclude this applied change.

## Unified workspace environment (2026-10-27)

The operator consolidated configuration into `agents/.env` for every process
and tool under this workspace. This supersedes older sections requiring
playground env files, mounted backend `prod.env`, and a separate external sync
env. Existing environment consumers retain their typed settings and validation;
LangGraph and Compose inject the unified file, and migration scripts resolve it
from their workspace root. Cron notification readers use `/app/.env` instead of
the backend settings mount. Backend services outside `agents/` retain their own
configuration; their service token and destination mappings must match clients.

Production migration and correction tools now use the unified `LIVE_PROD_*`
connection keys. SSH routing reads the remote database host/port from those keys
instead of hardcoding an endpoint; Python connects through a loopback tunnel.
Development migration retains `LIVE_DEV_*`. No business SQL, delivery policy,
schedule, retry, or checkpoint semantics change. The optional production sync
overlay uses the unified file but retains its explicit production enable gates.
External key/known-hosts/CA artifacts remain files with paths in configuration.

The parent scheduler Compose patch is prepared but unapplied after automatic
approval review rejected changing secret mounts. Runtime adoption requires
that patch and scheduler/monitor recreation. See [configuration, precedence,
and rollout checkpoint](unified-environment.md).

## Daily risk-count Slack status (2026-10-27)

Applied daily-risk runs now submit English completion/failure status
through `ax_integrations.notifications` to the backend's durable Slack queue.
The shared `BackendNotificationSettings` loads only mounted backend `prod.env`;
the weekly reporter retains its existing settings interface and behavior using
this shared parser. The production daily scheduler mounts the same file read-only
and uses its existing host network to reach the published backend loopback port
(`PROD_BACKEND_PORT`, default 8001). Development has no production secrets mount.
The existing backend enable flag and service token are reused. Daily alerts use
the dedicated `daily_risk` destination mapped to `C0C24T2124E` in backend
`NEXGENT_SLACK_CHANNELS`, leaving the weekly reporter's `default` mapping intact.
There is no fallback to `default` if the daily destination is missing. Recreate
the backend and notification worker after changing their environment mapping.

Workflow-local notification copy contains exactly status (`Success`/`Fail`),
title (`Daily Risk Count`), actual run start/end timestamps in KST, and message.
Success says `Successfully done!`; failures identify the failed database stage
and direct operators to sanitized logs. Counts and archive storage details are
omitted. Exception bodies, credentials and ward data are excluded. The app submits after
reconciliation and connection cleanup, never from inside the DB transaction.
Cleanup errors cannot relabel a confirmed commit as failed. Preview runs never
submit. Configuration or submission failure is logged independently and does
not change the database outcome or cause automatic database retries.

Each invocation uses a unique request key; bounded transport retries keep its
payload and key unchanged. Backend acceptance delegates durable Slack delivery
and retries to the existing worker. No local outbox is added: submission failure
before acceptance is best effort, with operator replay required. Replays report
their own counts and send a fresh message. Missed starts and terminated processes
remain outside this completion hook. See [configuration and recovery](../apps/daily_risk_scheduler/README.md#slack-status-notifications).

## Daily risk-count agent (2026-10-26)

`workflows/daily_risk_counts` reconciles the full previous Asia/Seoul calendar
day into `archive.resources_ward_monthly_risk_count`, reading only archive ward
and evaluation tables. `apps/daily_risk_scheduler` runs this deterministic,
model-free workflow daily at 05:15 (`15 5 * * *`), independently of weekly-report
generation and the operator history migration. The operator confirmed a
midnight-to-midnight window, including all of 23:59.

Each ward's selected day is replaced in the monthly danger/recovery arrays;
other day memberships and months are preserved. Recovery requires a strictly
later same-date STABLE. Counts derive from sorted distinct arrays. A single
repeatable-read transaction, serialized with the manual migration's target
table lock, makes reruns and uncertain commits recoverable without increments.
The committed business rows are the checkpoint; completion logs follow commit.
New rows include only the selected date, so historical initialization still
uses the manual migration. No live database copy, model call, schema change,
or automatic missed-run catch-up is added. The scheduler is declared directly
in root `compose.yaml` (development `scheduled` profile) and `compose.prod.yaml`
(normal production startup), with no separate Compose file. Start or recreate
the environment service to activate scheduling. See [operations and recovery](../apps/daily_risk_scheduler/README.md).

Date: 2026-09-01

Status: **Authoritative implementation specification**

## Weekly-report schedule moved to 04:00 KST (2026-10-26)

The fixed Monday cron now starts at 04:00 Asia/Seoul (`0 4 * * 1`),
following the operator's backup/restore schedule change. The independent
monitor uses the same start time and detects missed starts from 04:15 KST.
The reporting period remains the previous completed Monday–Sunday week.
Rebuild/recreate both scheduler and monitor between jobs to activate this change;
see [scheduler deployment](../apps/weekly_report_scheduler/README.md#production-rollout-and-recovery).

## Local database for completion coverage (2026-10-26)

Completion notification coverage now reads only the local database configured
by `WEEKLY_REPORT_STORAGE_DATABASE_DSN` or `ANSIMK_DATABASE_DSN` in the process
environment/`agents/.env`. The local connection reads `ansimk` roster and device
links plus `archive.resources_ward_weekly_report`. Coverage export bypasses SSH,
playground target configuration and `SOURCE_DATABASE_DSN`. Migration still uses
its separate production target and must commit before notification submission.
The Slack footer labels success as local DB storage; it does not claim verified
production coverage. Existing frozen notification payloads and accepted receipts
retain their idempotency behavior. See [local notification coverage](../../docs/08-implementation/weekly-report-local-notification-coverage.md).

## Weekly-report generation progress logs (2026-10-26)

Scheduled and manual regeneration waits now poll bulk status every five seconds
and write flushed `weekly_report_schedule_progress` JSON events containing only
job identity, reporting week, status, counters, and producer completion.
Transient polling errors retain last observed counts; HTTP request time adds to
the interval. Migration keeps existing script output and start/end events.
The 24-hour deadline, migration gates, receipts and notification behavior are
unchanged. See [progress logging](../../docs/08-implementation/weekly-report-five-second-progress-logs.md).

## Device relationship correction (2026-10-26)

The October 23 sections below incorrectly described `has_device` as a physical
ward column. The source schema has no such column. Current eligibility uses
`resources_device.location_id -> resources_location.id` and
`resources_location.ward_id -> resources_ward.id`, all in `ansimk`.
A shared `EXISTS` predicate filters discovery, derives `has_device` for explicit
requests, and determines completion coverage skips. Multiple devices/locations
do not duplicate wards. Offline but linked devices remain eligible; wards
without a linked device are skipped. This supersedes the earlier null-flag rule.
See [device relationship fix](../../docs/08-implementation/weekly-report-device-relationship-fix.md)
for validation, permissions, deployment, and failed-week recovery.

## Weekly-report skipped-device completion counts (2026-10-23)

Completion coverage snapshots now use version 2 and retain regional `skipped`
counts for production wards with `has_device=false`, alongside eligible totals
and successes. The same read-only snapshot covers both weeks; excluded wards
remain skipped even when historical reports exist. Null flags remain eligible.
Slack shows the overall skipped count in its summary and fallback text, plus
an eighth regional table column, `기기 미연결·제외(명)`. Missing rates continue
to use only eligible wards. Both weeks use the current production roster and
current device flags, rather than historical connection state or worker logs.

Version 1 snapshots retain their existing seven-column format. Frozen pending
payloads and accepted receipts are unchanged; no resend or new idempotency key
is introduced. Rebuild the scheduler for new snapshots and messages.

## Weekly-report device eligibility (2026-10-23)

Wards with `ansimk.resources_ward.has_device = false` are excluded before
metrics or narrative generation. Discovery filters them before applying the
page limit; explicit requests return `SkippedWard(reason="no_device")` and
bulk selection accepts that intentional exclusion. Missing wards and other
source skips still fail bulk completeness validation. Eligible wards without
observations continue to receive no-data reports. Null device flags retain
existing eligibility; only explicit false is excluded.

Production completion coverage uses the same exclusion for both reporting
weeks, so intentionally excluded wards do not count as missing reports.
Existing stored reports, staged bulk inputs, and scheduler receipts are not
rewritten. Rebuild the source API, worker, and scheduler together between jobs;
use fresh jobs to apply the new selection policy.

## Operator monthly risk migration (2026-10-22)

The operator-only `playground/migrate` tools recalculate archived monthly danger
and same-day recovery day counts, then optionally copy stored rows to live dev.
Local reads and writes stay in `archive`; dev copies target the configured
schema (default `ansimk`) through the `LIVE_DEV_*` SSH/database settings.
Danger and recovery days are deduplicated by local date and stored as sorted
integer arrays with matching counts. Recovery requires a strictly later STABLE
evaluation on the same local date; weekly columns are no longer referenced.

Local apply commits by month. Dev apply stages a full local snapshot, excludes
rows for missing destination wards with explicit skip counts, validates all
eligible data, and verifies the upsert before a single destination commit.
Previews do not change business rows; reruns are idempotent. These manual tools
add no graph nodes, scheduler hooks, deployment services, or notification paths.
Their PostgreSQL tests use synthetic temporary data. The real dev preview passed;
live dev apply remains an operator step. See [implementation and validation](../../docs/08-implementation/monthly-risk-count-migration.md)
and [operator commands](../playground/migrate/README.md).

## Saved guardian template ID migration (2026-10-19)

The operator-only `playground/migrate-guardian-template-ids` program previews or
updates legacy non-`GUI_` guardian-action item IDs independently in local
`archive.resources_ward_weekly_report` and live
`ansimk.resources_ward_weekly_report`. Normal generation and migration share
`select_guardian_guides`; raw-metric assessment and normal selection behavior
remain unchanged. Migration recalculates activity from saved totals, resolves
saved environment/device conditions against current policy labels, and requires
card semantics to match a selected guide. Historical JSON lacks the daily counts
needed to recompute environment/device assessments from raw facts.

Only verified legacy item IDs and row `updated_at` are changed. Existing GUI
IDs, valid no-data nulls, parent IDs, report text, and metrics are preserved.
Preview uses read-only snapshots; write mode requires an explicit flag, durable
private before/after artifacts, row locks, and original-JSON comparisons. Any
blocked report or update conflict prevents that target's changes. Local and live
commits are independent; reruns are idempotent. Existing generation, scheduler,
copy, and outbox boundaries are unchanged. See [operator commands and recovery](../playground/migrate-guardian-template-ids/README.md).

## Explicit weekly-report regeneration command (2026-10-17)

The scheduler CLI accepts `--week-start YYYY-MM-DD --regenerate RUN_KEY` to
regenerate a completed reporting week and then run the existing production
migration. The bounded run key creates a separate stable bulk idempotency
namespace, including cursor hashes for continuation batches, and a success
receipt under `regenerations/<RUN_KEY>/<Monday>.json`. Repeating the key reuses
jobs and resumes migration; a completed regeneration skips both stages. Original
cron receipts and default scheduler keys are preserved.

The existing global pipeline lock, heartbeat/failure tracking, all-batch storage
checks, 24-hour generation deadline and production migration gate remain in
force. No successful regeneration receipt is written before migration succeeds.
A terminal failed generation requires correction and a new run key; a failed
migration can reuse its completed jobs with the same key. Existing per-week
completion notification receipts are reused without a new correction message.
Rebuild the scheduler image before using the new option; no live generation,
production writes or deployment were performed while implementing the CLI.
See [scheduler commands](../apps/weekly_report_scheduler/README.md).

## Weekly-report source restored to ansimk (2026-10-17)

Per operator instruction, all five source queries now explicitly read
`ansimk.resources_ward`, `ansimk.analysis_devicedailysummary`,
`ansimk.analysis_wardevaluation`, and `ansimk.dispatch_dispatchrequest`.
This supersedes only the source-read portion of the October 6 archive decision.
The connection remains `ANSIMK_DATABASE_DSN`; no search-path fallback is used.

Investigation of October 5–11 found archive daily summaries with seven dates
but partial-day counts. For the investigated ward, each summary matched exactly
the raw measurements before 04:00 KST (48 samples/day), while raw measurements
continued through approximately 23:58 (287 samples/day). The archive weekly
activity/remote totals were 530/268; full-day raw totals and ansimk daily totals
were 8,193/3,175. Date coverage alone does not establish full-day completeness.
The upstream archive synchronization cause remains unconfirmed.

Local report storage and recovery remain in `archive.resources_ward_weekly_report`;
production migration/delivery and the optional outbox retain their existing
boundaries. Source wards therefore still need archive ward parents for local
storage. A read-only check found all 6,656 ansimk wards had archive parents.
No database schema, credentials, calculation rules, or report content are changed
by this source switch itself.

Rebuild/recreate the source API between jobs and use fresh jobs so staged
archive snapshots are not reused. Existing reports and scheduler success
receipts are unchanged; affected weeks require explicit regeneration and
migration. Regression tests bind each query to ansimk and exercise roster
selection with a competing archive roster.

## Guardian-action template catalog correction (2026-10-16)

Guardian-action cards now use the operator-approved `GUI_` template IDs:
`GUI_ACT_RISK_01`–`04`, `GUI_ENV_CAUTION_01`–`04`, `GUI_ENV_RISK_05`–`08`,
`GUI_DEV_POWER_01`, and `GUI_DEV_POS_01`; stable cards retain `GUI_GOOD_01`.
Activity-decrease and device-position descriptions match the supplied catalog.
The separate complete-reception-absence card retains no template ID because
the supplied catalog assigns none to that case. Selection rules and internal
variant numbers remain unchanged. JSON and Markdown expose the corrected IDs;
previously stored reports require regeneration to adopt them.

## Weekly-report shared production notification configuration (2026-10-06)

The operator requires backend `prod.env` to be the only notification settings
source. Production scheduler and monitor now mount `backend/prod.env` read-only
at `/run/ax-notifications/prod.env`. `NEXGENT_SLACK_ENABLED=true` enables both
completion and failure notifications automatically, using the same
`NEXGENT_NOTIFICATION_SERVICE_TOKEN` as the backend and the `default` alias
from `NEXGENT_SLACK_CHANNELS`. The internal API is fixed to
`http://backend:8000`; the backend notification worker remains the Slack sender.

All `WEEKLY_REPORT_NOTIFICATION_*` settings are retired. Notification loading
ignores agent `.env` and process overrides, including dotenv interpolation, so
cron and monitor use the same file. Missing mounts leave non-production
notification clients disabled; production bind mounts reject missing host files.
Development stacks do not mount production notification credentials. Source DB
settings still use the separate agent `.env`. Existing success gates, immutable
pending requests, accepted receipts, retry policy, and production DB schema are
unchanged. No message is sent as part of implementation verification.

## Weekly-report local archive schema (2026-10-06)

Per operator request, all weekly-report source queries now explicitly read
`archive.resources_ward`, `archive.analysis_devicedailysummary`,
`archive.analysis_wardevaluation`, and `archive.dispatch_dispatchrequest`.
This supersedes the August 19 source-schema decision and the September 21
reference to the `ansimk` ward roster. All-ward discovery now pages the archive
roster, including wards without observations. The database connection remains
`ANSIMK_DATABASE_DSN`; no search-path override or database rename is involved.
Production database schema, report delivery, and coverage queries retain
`ansimk` per explicit operator instruction. Source calculations, paging,
read-only transactions, and model boundaries are unchanged.

The operator also approved local report storage in
`archive.resources_ward_weekly_report`. Its ward foreign key stays within
`archive`, avoiding missing-ward failures for archive-only identities. The
local-only `004_create_archive_ward_weekly_report.sql` supports new installs
without changing an existing archive table. The scheduler's migration now
reads local archive reports while continuing to write production `ansimk`.
Recovery uses the same archive writer. The optional operational outbox remains
`ansimk.weekly_report_sync_outbox` in the same local database, preserving pending
deliveries and transactional enqueue. Job tables and historical reports are
unchanged; no production DDL or historical report copy is part of this switch.

Live read-only verification confirmed matching source columns, all five source
queries, a one-ward source request, and the existing archive report table's
ward foreign key and ward/week unique key. The archive roster had 6,646 wards,
34 absent from the local `ansimk` roster. Deployment requires coordinated
source API, worker, and scheduler rebuilds between jobs. Start fresh jobs after
the switch; old partial jobs and scheduler receipts are not reset automatically.

## Weekly-report failure monitoring (2026-09-29)

The scheduler persists a UUID-scoped attempt record after obtaining its existing
pipeline lock, with configuration/submission/generation/migration/notification
stages, safe job status/counts and a 30-second heartbeat. Caught exceptions and
termination persist failure before best-effort backend notification submission.
An independent `apps.weekly_report_scheduler.monitor` process observes the same
durable volume and detects failed attempts, five-minute heartbeat loss,
27-hour runtime overruns and missed Monday 04:00 KST starts after 15 minutes.
The monitor has no bulk API/scheduler dependency or production DB access.

Failure events retain immutable Korean native blocks and one idempotency key
per attempt (or missed week). A file lock coordinates scheduler/monitor outbox
creation and submission, with bounded backend attempts and persistent backoff.
Monitoring and alert retry never regenerate reports or rerun migration. The
first monitor activation establishes the missed-schedule baseline; restarts
retain it. Backend acceptance still delegates actual Slack delivery to the
backend worker. Same-host failure monitoring requires the monitor, state volume
and backend to remain available; whole-host coverage needs an external observer.
See [deployment, limitations and recovery](weekly-report-failure-notification.md).

## Weekly-report production completion notification (2026-09-29)

The scheduler now has an opt-in operational notification stage after its
production migration receipt. Workflow-owned deterministic SQL reads both
reporting weeks in one read-only target snapshot through the existing SSH
migration script's new coverage-only mode. The current production subscriber
roster supplies identical denominators for both weeks. Address municipality
tokens partition 울진, 영덕, 광명 and 기타; 전체 is their sum. Report existence
defines success, absence defines failure, and the message includes missing
rates for both weeks and the change in missing counts, with the current-roster limitation.

A shared `ax-integrations.notifications` adapter submits aggregate-only
messages to the backend's durable Slack API using a service token, configured
destination alias and stable per-week idempotency key. Persisted snapshots and
immutable request/acceptance receipts separate retries from generation and DB
migration. Backend acceptance is not proof of Slack delivery; its worker owns
delivery retries/status. Failed generation/migration never announces completion.
No new database tables, process boundaries or automatic cron catch-up are added.

The backend now validates native header, section, context, divider and table
blocks. The producer uses seven blocks with a full seven-column regional table
and retains every count, rate, percentage-point change and calculation note.
Plain-text table cells and escaped/verbatim Markdown preserve mention safety.
Complete accessible fallbacks and unchanged legacy idempotency fingerprints
are required. See [backend native-block contract](../../docs/08-implementation/slack-notification-native-blocks.md).

The scheduler image installs frozen workspace dependencies and cron uses the
virtualenv Python. Notification settings come from the existing agent `.env`
mount. This operational aggregate notification is authorized by the feature
request; existing report-content delivery approval remains intact. See
[configuration, acceptance criteria and recovery](weekly-report-completion-notification.md).

## Weekly-report source retries and diagnostics (2026-09-28)

The workflow-owned read-only source client now retries transient timeouts,
network errors and HTTP 408/429/5xx up to three attempts with 2/4-second backoff.
Each whole HTTP attempt is bounded by the configured source timeout (30 seconds
by default, finite and at most 120). Validation and permanent HTTP failures do
not retry; cancellation propagates. Retries reuse the page within the existing
job before staging, preserving completed work and weekly idempotency.

The worker uses an allowlisted JSON formatter from `ax-observability`; source
events carry task-local job correlation, timing, attempts and safe error types.
Stage failures retain source diagnostics instead of losing structured fields.
The scheduler logs timestamped failed-job identity and counts. No new persistence,
job restart, catch-up, migration retry, or notification boundary is introduced.
See [retry policy, diagnostics and rollout](weekly-report-retries-and-diagnostics.md).

## Missing production wards in weekly-report delivery (2026-09-21)

Per operator instruction, a report whose ward does not exist in the production
ward table is skipped. The scheduled pipeline already invokes the shared
`playground/weekly-reporter/migrate.sh`; that command prints skipped ward IDs
and weeks, counts skipped reports, and commits the remaining reports.

The optional outbox delivery worker now records terminal `skipped` entries
with reason `missing_ward`, no delivery timestamp, and no automatic retry.
Dry-run and delivery output identify the ward and week. Status counts skips
separately and excludes them from outstanding work. Explicit retry revalidates
a skipped entry after the ward is restored. Local migration
`003_weekly_report_sync_skipped.sql` adds the status without changing existing
blocked deliveries; readiness checks require it. Missing reports for existing
wards still insert, and content conflicts and other database errors retain
their existing failure behavior. Generation and local storage completeness
remain unchanged; this exception applies to missing production target wards.
See [production delivery](weekly-report-production-sync.md) for rollout.

## Persistent product AX chat history (2026-09-21)

The authenticated product backend now owns private per-user AX conversations,
messages, attachment metadata and execution jobs in the application PostgreSQL
`chat` schema. An independent backend `chat-worker` consumes leased jobs and
persists assistant output independently of browser connections. Development and
production use separate deployment namespaces because their account DB is shared.

The worker invokes the existing `chat` graph through stateless Agent Server runs,
supplying the recent successful pairs from the product database (20 turns/32,000
characters). It uses custom response events and temporary-thread deletion. The
graph does not open database connections or instantiate a checkpointer. Existing
graph history and attachment contracts remain unchanged; public clients cannot
submit historical context or arbitrary upstream thread identifiers. This supersedes
the ephemeral product-UI/thread coupling in the September 14 record below.

Original and normalized attachments persist in a private API/worker volume; the
worker stages only selected normalized copies for Agent Server. Users explicitly
reuse files. Browser disconnection detaches the viewer; explicit Stop cancels the
worker's upstream connection and retains partial output. Worker loss marks the run
interrupted after lease expiry without automatic model retries. Reopening a completed
chat remains possible after Agent Server restarts. RAG remains session-only.

Deletion immediately revokes access and queues file/record cleanup after cancellation.
Migration, HTTP contracts, operational commands, isolated PostgreSQL and browser
validation, and remaining real-model rollout checks are recorded in
[Persistent AX chat history](../../docs/08-implementation/persistent-ax-chat-history.md).

This document is the required starting point for any material change to AX
agent runtime, graph orchestration, tools, APIs, persistence, deployment,
security, or evaluation. `AGENTS.md` requires contributors and agents to read
it before implementation and update it when architecture changes.

## All-ward weekly-report completeness (2026-09-21)

The operator now requires one weekly report for every row in
`ansimk.resources_ward`, including wards without weekly records. This supersedes
record-based candidate discovery and successful partial generation below.
The source pages the ordered ward table; missing observations remain null or
explicitly unavailable under the existing deterministic presentation rules.

Every staged ward must have a verified, correctly identified report before a
bulk batch can commit report storage or complete. Missing explicit selections,
skipped source wards, and exhausted artifact/data failures fail the batch;
successful artifacts remain recoverable. Cancelled batches retain export
behavior but do not persist a subset. Model exceptions, invalid text and
timeouts use deterministic fallback. If fallback prose itself fails validation,
a fixed neutral summary points to the deterministic detail sections without
inventing observations or dropping the ward. Cancellation still propagates.

The scheduled pipeline follows continuation cursors across bounded jobs until
the ward table is exhausted, validates completed/discovered counts, and only
then migrates the week. `partial` no longer permits migration. A shared 24-hour
generation deadline bounds continuation and polling. Policy-versioned keys and
receipts avoid reusing legacy record-only completion; receipts contain batch
IDs and the report count. Existing per-job 10,000 and per-source-page 100 limits
remain. Discovery observes the live ward roster as pages are read, rather than
introducing a transaction spanning source calls; changes to the roster during
a run require reconciliation. No schema or process boundary is added.

Per explicit operator instruction, generated Markdown and frontend JSON no
longer display fallback implementation notices. `generation_notice` stays null
for schema compatibility; report-level generation metadata retains the mode
and reason. Existing saved reports need regeneration to adopt these changes.
See [completeness rollout and verification](weekly-report-completeness.md).

## Update: selective database recovery (2026-09-08)

Operator recovery supports `--write --skip-not-null`: bounded batch savepoints
fall back to individual row savepoints only for NOT NULL violations (23502).
Valid rows commit together; other errors still roll back. Output identifies
skipped ward IDs and columns; exit code 2 indicates skipped rows, including
all-skipped runs. Regular bulk finalization retains atomic storage. See
[database recovery](weekly-report-database-recovery.md) for commands and status
semantics. No source/model calls or queue status changes occur in recovery.

## Implementation status

The baseline described here is implemented as of 2026-08-05:

- `uv` workspace with deployable `apps/`, self-contained `workflows/`, and
  shared `packages/` for contracts, runtime, tools, integrations, persistence,
  observability, and evaluations;
- versioned Pydantic contracts with strict unknown-field rejection;
- runtime context, execution limits, normalized errors, and LangGraph config
  helpers;
- deterministic compiled graph exported from `workflows/smoke` and configured in
  `langgraph.json`;
- capability/risk-based tool authorization policy;
- reusable authorized `web_search` and SSRF-safe `web_fetch` tools backed by a
  private no-provider-key SearXNG deployment;
- declarative remote MCP registry, environment-backed Streamable HTTP client,
  discovery CLI, and policy-enforced namespaced MCP tool adapters;
- Agent Server adapter port and FastAPI gateway with health, submit, status,
  SSE events, and interrupt-resume route contracts;
- self-hosted PostgreSQL/Redis/Agent Server Compose baseline;
- pooled asynchronous OpenAI-compatible model adapter and one-turn chat graph;
- dedicated one-turn `rag_chat` graph with read-only RAG Top-5 grounding,
  deterministic empty-context handling, and code-owned source provenance;
- transient document/image attachment references, secure local artifact reads,
  and opt-in multimodal chat content;
- architecture governance in `AGENTS.md` and this document.

Validation completed:

```text
ruff check apps workflows packages tests -> passed
python -m pytest -q                  -> 13 passed
langgraph validate                  -> valid, 1 graph found
docker compose config               -> valid with .env.example
langgraph dev + POST /runs/stream   -> streamed ack: hello
```

The real Agent Server adapter, authentication provider, durable production
database, and business-specific write tools remain intentionally unimplemented.
Compose image build, PostgreSQL/Redis integration tests, and a live model
readiness check are the next deployment verification gates.

## RAG Chat orchestration (2026-08-25)

The Chat page now has a real `RAG Agent` execution path through the dedicated
`POST /api/rag/chat/stream` backend endpoint. The backend reuses its existing
Agent Server SSE relay but selects only the registered `rag_chat` graph for
this route. Normal `/api/chat/stream`, preview agents, and Weekly Reporter
routing are unchanged.

`rag_chat` calls the existing read-only `GET /rag/v1/search` endpoint with the
exact current question and fixed `top_k=5`. It preserves returned order and
provenance, treats all retrieved text as untrusted evidence in one user
message, and keeps its grounding policy in a separate system message. Zero
results deterministically return an insufficient-context response and skip
model generation. With results, the graph reuses the same pooled
OpenAI-compatible `/v1/chat/completions` adapter, environment-driven model/base
URL/auth path, retry policy, streaming, and safe errors as normal Chat. It then
appends Markdown-escaped sources in code, including a null-provenance legacy
fallback.

The graph remains a one-turn, text-only Phase 1 workflow. Attachments are
disabled in the RAG Agent UI and rejected by the strict JSON API contract.
Production search remains vector-only; the lexical/RRF experiment was not
enabled and the RAG retrieval implementation, schema, chunking, embeddings,
OCR, and DOCX paths were not changed.

`RAG_SERVER_BASE_URL` configures the server-side read-only RAG origin and must
be reachable from the Agent Server runtime without embedded credentials. The
live Agent Server reaches the systemd-managed host RAG API through
`http://host.docker.internal:8765`; a narrowly scoped host network policy allows
TCP 8765 for that runtime. The host service is enabled through
`multi-user.target`; its PostgreSQL container lifecycle remains separate. The
registered `rag_chat` graph, deterministic
empty-corpus branch, populated retrieval/generation path, backend SSE relay,
and browser rendering were live-validated on 2026-08-25. The pre-empty
test-data backup was deliberately not restored; one synthetic Direct Text
source was added only for the populated-path validation. Phase 1 remains
one-turn and text-only, with no Chat attachment ingestion, conversation memory,
Nextcloud link, deduplication/versioning, or production Hybrid retrieval. See
[RAG Chat Agent](rag-chat-agent.md) for the endpoint, prompt, sources, evidence,
and deployment details.

## Weekly-report bulk execution (2026-08-20)

Database recovery update on 2026-09-08: an operator-only recovery command reads
a terminal job and checksum-verified completed artifacts, then reuses the
existing atomic report writer without source/model calls or queue-state changes.
See [database recovery](weekly-report-database-recovery.md) for guards and commands.


Browser polling reliability update on 2026-09-08: the bulk panel awaits each
status request before scheduling another, backs off failures to 30 seconds,
and stops on terminal status or cleanup. Bulk JSON requests have a 30-second
deadline with caller cancellation. See [polling reliability](weekly-report-bulk-polling.md)
for implementation and validation.


The manual `ansimk_weekly_reporter` LangGraph remains the compatibility path
for interactive batches of at most twenty-five reports. High-volume generation
is a separate workflow-owned execution path in `workflows/weekly_report/bulk`.
It does not create one graph branch or one agent per ward and does not place
thousands of reports in LangGraph state.

An operator submits an idempotent job for at most 10,000 reports. One leased
producer consumes the existing private source API in ordered pages of at most
one hundred and stages each validated metric snapshot exactly once. Bounded
asynchronous consumers claim independent wards from PostgreSQL with
`FOR UPDATE SKIP LOCKED`, call the existing reporter specialist, and atomically
write report artifacts. Producer, item, and finalizer leases can be reclaimed
after process loss. A worker process admits up to four distinct jobs by default,
oldest first. All active jobs share the same process-wide item-concurrency
ceiling, so admitting another job does not multiply simultaneous model calls.
Additional worker processes or containers add bounded consumer capacity while
the PostgreSQL leases prevent duplicate item completion.

The separate bulk-job PostgreSQL contains only job metadata, opaque cursors,
artifact references, checksums, attempt counts, leases, and safe error codes.
Input snapshots, rendered reports, and the ZIP export live on a private
persistent volume with owner-only permissions and atomic replacement. The
terminal ZIP contains
`manifest.json`, `reports.jsonl`, deterministic `reports/<ward_id>.md`
Markdown files, and frontend-ready `json/<ward_id>.json` template files.
Artifacts expire after seven days; long-term report history, a public bulk API,
editable schedule persistence, and bulk Slack delivery are deliberately out of
scope. Slack remains a separate human-approved side-effect boundary.

The model path is LLM-first for every report. OpenAI-compatible servers receive
the dedicated weekly-summary system prompt plus validated report-facing data
and return one plain-text Korean paragraph; the existing single correction and
disclosed deterministic fallback policy is unchanged. Python owns all metrics,
section statuses, and rendering. Worker concurrency is async and
bounded—Python threads and process-local sub-agent fan-out are not the scaling
boundary.

Weekly Reporter structured-template update on 2026-09-02: every
`WardWeeklyReport` retains its `markdown` field and additionally returns
`template_data`, now versioned as `weekly-report-v5`. Stable keys cover basic
information, the LLM-authored summary, the combined living-activity section,
the remaining deterministic detail sections, and guardian actions. Raw numeric values and approved display
strings are both present, avoiding client-side parsing and duplicated product
logic. Interactive responses and existing report JSON/JSONL artifacts carry
the new field. The bulk finalizer also persists that frontend object to the
dedicated report table described below. ZIP downloads
also expose each `template_data` object as `json/<ward_id>.json` while keeping
all existing entries and Markdown paths intact.

Weekly Reporter activity-format update on 2026-09-02: the former sibling
`생활 활동` and `생활 패턴` sections are combined under one `생활 활동` parent.
Its children are `활동감지` and `리모컨 이용`; child descriptions and summaries
are removed. The parent renders the two available descriptions, collapses two
unavailable comparisons into one approved data-limitation sentence, and shows
one `태그` selected by `RISK`, `CAUTION`, unavailable, then `GOOD` severity.
Equal statuses prefer `활동감지`. Calculation bands and the LLM summary inputs
remain unchanged.

Weekly Reporter missing-metric display update on 2026-09-02: indoor-environment
rendering now distinguishes temperature-only, humidity-only, and combined data
limitations with approved Korean copy and displays unavailable metrics as `-`.
Count-based device metrics without source values display `0`. Structured raw
values remain null in both cases, and neither display fallback changes status
calculation or the LLM fact package.

Weekly Reporter tag-contract update on 2026-09-02: all deterministic detail
sections render the label `태그` rather than `요약`. The frontend template
renames indoor-environment and device-status `summary` keys to `tag`, requiring
the `weekly-report-v4` version. When no CAUTION/RISK guardian action is selected,
the stable GOOD card outputs `GUI_GOOD_01` as its template ID. Markdown remains
available alongside the structured JSON. If no card is selected, the empty
state exposes the same code through `template_id` in both JSON and Markdown.

Weekly Reporter device-day display update on 2026-09-02: `정보 수신` now uses
the current covered-day count, while `전원 확인` is the selected seven-day
period minus that count. The v5 frontend keys are `normal_reception_days` and
`power_check_days`. The source-derived power-pattern occurrence count remains
internal to the backward-compatible device status policy and is no longer
rendered as the power metric.

Weekly Reporter report-storage update on 2026-09-03: the workflow-owned
`ansimk.ward_weekly_report` table is the durable frontend JSON target. After
generating verified JSONL and ZIP artifacts, the bulk worker streams completed
report artifacts through a dedicated writer DSN into bounded 500-row upsert
batches inside one transaction. `report_data` contains `template_data` only;
score and status are copied to queryable columns, and `week_end_date` is the
inclusive Sunday shown to the guardian. The ward/week unique key makes a
reclaimed or repeated finalization idempotent. Any write or count mismatch
rolls back storage and fails the job. The private source service and interactive
preview remain non-writing, while bulk-job metadata storage stays separate.

Weekly Reporter storage-table rename on 2026-09-04: the approved durable target
is now `ansimk.resources_ward_weekly_report`, superseding the original table
name in the 2026-09-03 record above. The schema remains `ansimk`; the columns,
foreign key to `ansimk.resources_ward`, unique ward/week key, atomic upsert
behavior, and writer configuration are unchanged.

Weekly Reporter concurrent bulk-job update on 2026-09-04: the durable worker no
longer awaits one entire job before admitting the next. It runs up to
`WEEKLY_REPORT_ACTIVE_JOB_LIMIT` distinct jobs per process (default four),
selects unadmitted jobs oldest first, and isolates task failure and cancellation
by job. All admitted jobs share one `WEEKLY_REPORT_WORKER_CONCURRENCY` semaphore
per process. This keeps aggregate report/model work bounded at the existing
limit rather than multiplying it by the number of active jobs. Producer, item,
and finalizer leases retain restart and multi-process recovery behavior.

Weekly Reporter frontend simplification on 2026-09-04: `/agents/1` is now a
bulk-only operator surface. The Quick Preview mode, its per-report review UI,
the Chat-triggered Weekly Reporter run, and the frontend `/runs/stream` parser
and report contracts were removed. Weekly Reporter is no longer marked as
Chat-capable in the frontend catalog. The retired `/test-agent` path normalizes
to `/agents/1`, and its sidebar entry is gone. The durable bulk control client,
status polling, cancellation, recent jobs, and verified ZIP download remain.
The registered interactive graph remains a backend compatibility boundary; it
has no first-party frontend caller.

Weekly Reporter cron scheduling update on 2026-09-04: the independently
deployable `apps/weekly_report_scheduler` service runs BusyBox cron at
`0 4 * * 1` with the container clock fixed to `Asia/Seoul`. Each invocation
calculates the previous fully completed Monday-through-Sunday period and
submits up to 10,000 reports through the private bulk control API. It never
accesses PostgreSQL or the model directly. A period-derived idempotency key
prevents retry duplicates, transient delivery retries are bounded, responses
are size-limited and validated, and logs contain only schedule/job metadata.
The production Compose topology (`../compose.prod.yaml`) starts the service
by default and is the
single automatic schedule owner. Agent-only and root development Compose keep
the same service behind the opt-in `scheduled` profile so concurrently running
environments avoid duplicate work against shared external systems. Keep the
`scheduled` profile disabled in development when production scheduling is enabled. Every
enabled scheduler depends on bulk-API readiness.

The `/agents/1` schedule card now identifies the configured server cron while
retaining local-only weekday/time previews for the future editable-schedule
experience. UI changes and the disabled save action do not reconfigure cron.
There is no schedule database, schedule-management API, missed-run catch-up,
or automatic Slack delivery. Manual durable bulk controls remain available.

Release capacity is measured end to end against a representative private-model
deployment. The hard gate is 10,000 reports in at most two hours (at least
1.389 reports/second); the healthy target is ninety minutes (at least 1.852
reports/second). Operators increase worker concurrency only until model or
source saturation, then add private inference replicas. vLLM prefix caching,
continuous batching, and structured output may be enabled at the inference
deployment, but replica count is derived from the observed benchmark rather
than fixed in application code.

Bulk operator API and UI update on 2026-08-20: the existing durable worker is
now reachable from the Weekly Reporter page through a separate private
`apps/weekly_report_bulk_api` control process. Its strict endpoints submit an
idempotent job, list and inspect content-free progress, request cooperative
cancellation, and stream only checksum-verified terminal ZIPs. Recent-job
listing was added to the generic bulk store so browser refresh does not lose
operator visibility. The control API and worker share the job database and
private artifact volume but remain separate deployment and ownership
boundaries; the API never executes model calls.

The default development Compose topology starts the bulk PostgreSQL queue,
worker, and control API. The control API has no host port and is reachable in
the browser only through the existing Vite development proxy. The `/agents/1`
workbench exposes only durable bulk generation for up to 10,000 reports. It
does not call the interactive LangGraph reporter. The bulk view displays source
discovery in 100-item pages, active consumer count,
queued/completed/fallback/failed counts, observed throughput, projected finish,
recent jobs, cancellation, and ZIP download. Submission requires explicit
acknowledgement that allowlisted care-derived facts will reach the configured
private model and that a shared model endpoint may slow Chat.

This is an observable execution path, not evidence that the two-hour SLA has
been achieved. A real PostgreSQL-backed run and representative 10,000-report
private-model benchmark remain release gates. Production exposure also requires
an authenticated gateway; the Vite proxy is trusted-development plumbing only.

Bulk cancellation and paging update on 2026-08-24: durable bulk source pages
now contain at most one hundred wards, while the interactive compatibility
graph remains capped at twenty-five. A persisted cancellation request is
watched during execution; the worker cancels in-flight async model calls,
marks pending and leased items cancelled, and exports only reports that had
already completed. The operator UI sends the same cancellation request for
Cancel, stop-and-refresh, page refresh, navigation, and unmount. Browser
keepalive delivery is best-effort, while the explicit Cancel response remains
the confirmed control path.

Weekly Reporter bulk recovery update on 2026-08-26: production-like history
showed normal forty-report jobs completing in roughly 27–47 seconds, but one
oldest active job remained non-terminal for about 31 minutes and queued later
jobs behind it. The runner now converts producer, consumer, and finalizer
exceptions into persisted terminal job failures, cancels unfinished items,
and lets the durable worker continue polling. Each narrative generation has a
configurable 60-second default deadline and degrades to the deterministic
grounded fallback on timeout. Verified ZIP responses are sent in bounded
chunks with the verified artifact byte size advertised as `Content-Length`.
Regression tests cover producer failure, an indefinitely slow model item, and
the non-zero ZIP response length so these failure modes cannot silently return.

Architecture update on 2026-08-05: workflow modules moved from `graphs/` to
`workflows/`; `apps/workers`, `packages/persistence`, and
`packages/observability` were added as explicit scaling boundaries; shared
tests were grouped by intent. Ruff, 13 tests, direct smoke execution, and
`langgraph validate` passed after the move.

Architecture update on 2026-08-10: `ax-integrations` gained a provider-neutral
chat-model port and a concrete OpenAI-compatible streaming adapter. The new
`workflows/chat` graph provides a minimal async LLM path while `workflows/smoke`
remains deterministic. Model settings are loaded only in the integration layer,
connections are pooled, retries are bounded, and credentials stay outside
graph state. Ruff, 24 tests, and `langgraph validate` with two registered graphs
passed for this change; the live private endpoint check remains deployment-owned.

Runtime compatibility update on 2026-08-10: LangGraph API 0.12.0 loads graph
entries configured as Python file paths without package context. Graph
entrypoints therefore use absolute workflow imports, while package-internal
modules may continue using relative imports. A contract test now loads every
`langgraph.json` entry using the runtime's file-versus-module behavior so
validation cannot pass while development startup fails.

Development network update on 2026-08-10: the documented local Agent Server
command binds specifically to `192.168.0.18:2024` so trusted LAN peers can use
it. This is an in-memory, noop-auth development listener only. Port 2024 must
remain restricted to the trusted network; production traffic still terminates
at the authenticated gateway, with Agent Server kept private.

Containerized development update on 2026-08-10: the root `compose.yaml` builds
a license-free development image that runs `langgraph dev` automatically. The
process binds `0.0.0.0:2024` inside its container and Docker publishes it only
as `192.168.0.18:2024`; model settings are injected from the ignored root
`.env`. This in-memory, noop-auth path is separate from the licensed standalone
deployment baseline under `infra/compose` and is restricted to trusted-LAN
development.

Parent stack update on 2026-08-10: `/nexgent/compose.yaml` now composes this
development Agent Server with the existing backend and frontend. Its build
context remains `/nexgent/agents`, the frontend proxy resolves the container as
`http://agent-server:2024`, and the published listener remains
`192.168.0.18:2024`. Running `docker compose up --build` from `/nexgent` starts
all three development services.

Root production-server update on 2026-09-03: `/nexgent/compose.prod.yaml` adds
an isolated `nexgent-prod` Compose project for the separate stable server used
by the designated user group after application testing. It has separate host
ports and volumes, an immutable backend container, and a compiled frontend
served through Nginx. In this operational naming, `production` distinguishes
the stable user server from the new-feature development server; it does not
mean a LangSmith-hosted deployment. The stable server intentionally reuses the
current environment values and tested in-memory Agent Server implementation
for now. References to a `production-grade Agent Server` elsewhere in this
document describe a separate future hardening milestone and are outside the
current two-server separation scope.

Chat streaming update on 2026-08-10: the chat workflow now consumes the
provider adapter's asynchronous token iterator directly and emits only text
deltas through LangGraph's `custom` stream mode. It still returns the assembled
response in graph state, so clients request both `custom` and `values`: custom
events provide immediate display updates and the final values event verifies
the completed response. Provider URLs, credentials, and raw provider events
remain inside the integration boundary and are never included in graph stream
payloads. Full Ruff validation and all 26 agent tests passed after this change.
The chat workflow's bounded output budget is 2,048 tokens, increased from the
initial 500-token prototype limit to support detailed operational answers.

Chat cancellation update on 2026-08-10: the stateless frontend run request now
sets Agent Server's `on_disconnect` policy to `cancel`. Aborting the response
stream therefore cancels graph execution and propagates async cancellation to
the OpenAI-compatible provider stream, rather than leaving model generation
running after the UI stops. This uses Agent Server's run lifecycle contract and
does not add provider-specific cancellation logic or durable chat threads.

Web research tools update on 2026-08-12: `ax-contracts` now defines strict,
versioned search, source, and fetched-page schemas. `ax-tools` exposes
workflow-neutral `web_search` and `web_fetch` factories with injected executors,
read-risk authorization, deterministic idempotency keys, structured artifacts,
and safe retry-classified failures. `ax-integrations` provides pooled SearXNG
search and public-page fetch adapters; page retrieval pins validated DNS
addresses, rejects non-public destinations and unsafe redirects, bounds
content, and extracts readable text with Trafilatura. SearXNG is digest-pinned
and private in every Compose topology. The current chat graph is unchanged.
Ruff, 52 deterministic tests, two LangGraph entrypoints, the smoke graph, and
all three Compose configurations passed. The opt-in live quality evaluation was
skipped as designed; live container startup still requires operator Docker
access on the host.

Weekly reporter update on 2026-08-12: `ansimk_weekly_reporter` is the first
business-specific graph. A manually triggered coordinator loads a stable
three-user mock work-activity window and uses bounded LangGraph fan-out into an
isolated per-user calculation, Korean narrative, and Markdown composition
subgraph. Python owns every numeric calculation; the OpenAI-compatible model
may produce only validated, grounded prose. The initial narrative contract was
digit-free; the later structured-summary policy allowlists only meaningful
verified values. Model configuration, request,
empty-output, and narrative-validation failures yield disclosed deterministic
fallback reports without failing the batch. Strict weekly-report contracts and
deterministic evaluator gates cover ordering, Korean structure,
personalization, numeric grounding, and fallback disclosure. The workflow is
registered in `langgraph.json`; scheduling, real database access, report
persistence, authentication, and delivery remain deferred integration work.
Ruff, all 70 deterministic tests, and LangGraph validation with three graph
entries passed; the opt-in live web-quality evaluation remained skipped as
designed.

MCP integration update on 2026-08-13: `ax-integrations` now uses the official
MCP Python SDK behind a strict JSON server registry. HTTP headers resolve only
from environment variables, clients reuse bounded connection pools, failures
are normalized without credentials, and `ax-mcp inspect` performs non-secret
server/tool discovery. `ax-tools` converts discovered definitions into
namespaced LangChain tools, validates remote JSON Schemas locally, rejects
unclassified risks, and applies the existing per-call authorization policy.
The first configured endpoint, `db_mcp_server`, negotiated protocol
`2025-11-25` with server version `1.29.0`; its ten advertised read-only tools
are classified as `read` but are not automatically granted to any workflow.
Ruff, 84 tests with one opt-in live evaluation skipped, LangGraph validation
with three graph entries, both in-scope Compose configurations, live discovery,
and one allowlisted `server_info` call passed.

Weekly reporter MCP update on 2026-08-13: the production
`ansimk_weekly_reporter` repository now loads its fourteen-day activity window
through `db_mcp_server`. Its workflow-local gateway exposes only the classified
read tools `find_columns` and `query_data`; it never grants the remaining MCP
surface. A strict canonical row contract covers user identity, activity date,
task counts, focus minutes, and blocker counts. Operators may configure an
explicit schema, table, and canonical-to-physical column mapping; otherwise,
exact-name discovery must identify one common table or view. Retrieval selects
only required columns, uses half-open date filters and deterministic sorting,
pages by one hundred rows, caps the batch at fourteen hundred rows, validates
all untrusted output, and fails closed without a production mock fallback. The
stable mock repository is test-only. The MCP protocol and tool schemas were
verified live, while end-to-end data readiness remains blocked by the remote
server's rejected backing PostgreSQL credential. Ruff passed, 89 tests passed
with one opt-in live evaluation skipped, all three LangGraph entries validated,
and both Compose configurations rendered successfully.

Ward-risk prototype update on 2026-08-14: live schema inspection showed that
the Ansimk database does not contain the generic task/focus/blocker contract and
that `analysis_wardperiodreport` is currently empty. The weekly graph now uses
the populated `ansimk.analysis_warddangerdaily` source for a deliberately small
end-to-end validation slice. Its repository grants only `query_data`, scans one
bounded identity page for the requested fourteen-day window, selects three
sorted wards by default, and re-queries those identities for complete daily
histories. Python computes current and previous danger-day counts and their
delta; an isolated branch generates validated Korean narrative and grounded
Markdown for each ward. Output warns when source selection is truncated, all
MCP data remains untrusted until validated, and no write occurs. A live cycle
for 2026-08-03 completed through MCP, the OpenAI-compatible model, LangGraph,
and terminal rendering with three AI-narrated reports. This is a validation
prototype, not an approved production interpretation of risk data. Ruff
passed, 86 tests passed with one opt-in live evaluation skipped, all three
LangGraph entries validated, and both Compose configurations rendered.

Weekly reporter production-path update on 2026-08-18: the danger-day MCP
prototype was replaced by a private `apps/weekly_report_api` FastAPI process.
A reusable `asyncpg` integration owns pooled read-only PostgreSQL transactions;
workflow-owned parameterized queries calculate current and prior raw seven-day
environment, activity, sleep, risk, danger-day, and dispatch metadata. The
graph consumes versioned snapshots through a private-network workflow-local
HTTP client and preserves the registered graph ID plus compatibility
`danger_days` fields. Python converts verified metrics into qualitative facts
before a workflow-local reporter specialist writes warm Korean prose. The
model sees no raw rows, free-text notes, or numeric values; structured output
receives one validation retry and then a disclosed deterministic fallback.
Automatic ward discovery is ordered, cursor-paged, and capped at twenty-five;
explicit IDs return missing wards as skipped. Scheduling, delivery, and report
persistence remain deferred.

Outbound Slack integration update on 2026-08-18: `ax-integrations` now owns a
reusable async adapter over the official Slack SDK and `chat.postMessage`.
Environment configuration defines the default channel and an allowlist of
logical destinations; runtime or model-generated channel IDs cannot expand
that allowlist. The adapter supports text, Block Kit, and thread replies with
bounded timeouts, one `Retry-After` rate-limit retry, sanitized result objects,
and content-free structured delivery logs. The weekly reporter adds an
explicit post-generation sender for an approved configured destination. It is
kept outside graph execution and requires human confirmation before sending
care-related content, preventing graph retries from duplicating Slack side
effects. No inbound Slack capability was introduced.

Weekly reporter source-schema correction on 2026-08-19: live execution against
the configured archive database showed that unqualified relation names resolve
through a deployment-specific `search_path`, while matching tables exist in
`ansimk`, `ansimk_clone`, and `archive`. All weekly-report SQL now explicitly
qualifies the approved `ansimk` schema. Clone and archive relations cannot be
selected implicitly, and a regression test enforces that source binding.

Weekly Reporter frontend integration update on 2026-08-19 (superseded on
2026-09-04): at that time, the catalog route `/agents/1` owned the interactive
workbench, while `/test-agent` remained an alias for isolated testing. An
operator-triggered request sent an explicit limit of
1–25 selected in the UI through the existing Agent Server SSE boundary; the
default is three, and no query or model call occurs merely by opening the page.
The Agent Server run configuration caps graph concurrency at four so a larger
batch does not fan out without a bound. The frontend validates the expanded weekly
metric, narrative, generation, skip, and cursor contract, selects the first
ordered report by default, and renders only useful indicators plus safe
Markdown rather than exposing raw report JSON. The root development Compose
stack now includes the private weekly-report FastAPI service and gates Agent
Server startup on its database-backed readiness endpoint.
The read-only source path was verified with an actual three-item batch. A live
model-backed batch remains an explicit approval gate because even the
allowlisted qualitative fact package is ward-derived care information.

Weekly Reporter progress correction on 2026-08-19: the frontend Agent Server
request enables subgraph streaming because `ward_report_ready` is emitted from
each isolated per-ward branch. The SSE client accepts namespaced `custom|...`
events as validated progress while continuing to accept the terminal report
only from the top-level `values` event. This prevents completed batches from
displaying a stale zero-of-requested report count without weakening result parsing.

Weekly Reporter environment-policy update on 2026-08-26, superseded by the
2026-08-27 spreadsheet-template policy below: a product-approved,
deterministic presentation rule classifies daily indoor maxima using inclusive
year-round recommended ranges: `15℃ ≤ temperature ≤ 31℃` and
`30% ≤ humidity ≤ 70%`. Python converts below/above-bound measurements into
cold/hot or dry/humid qualitative facts.
The reporter receives only qualitative evidence, and validation enforces every
material environment issue without exposing numeric thresholds to the model.

Weekly Reporter grounded-summary correction on 2026-08-25: `한주 총평` now
scales from one to six sentences according to the available qualitative facts,
with no minimum character count. Available observations take precedence over
coverage metadata. Prompt validation rejects missing-data apologies,
unsupported health reassurance, future-report promises, and guardian
pleasantries, while the deterministic fallback concatenates only verified
facts and may return a single short observation.

Weekly Reporter insight-summary refinement on 2026-08-25: the versioned prompt
now asks for a formal, guardian-facing weekly insight rather than a flat fact
list. Normal device reception may establish observation reliability, related
movement and remote-control facts are synthesized into the overall activity
flow, and material exceptions follow with a natural contrast. Headline and
analysis validation requires warm `합니다체`; the deterministic fallback mirrors
the same ordering, synthesis, and formal register without adding unverified
interpretation.

Weekly Reporter evaluatable-area summary policy on 2026-08-25: workflow-owned Python
now derives `valid_days` from current covered dates and derives data quality
from valid-day coverage plus approved device power/position status. It selects
`ALL_GOOD`, `MIXED`, `RISK`, `LOW_DATA`, or `PARTIAL_DEVICE` before the model
call and produces a semantic INTRO/LIFE/ENV/SAFE/CLOSE outline. All evaluatable
activity, environment, and device items are provided as evidence; the later
valuable-insight policy makes only material issue topics mandatory and allows
low-value GOOD facts to be omitted. Unavailable items are omitted entirely
rather than rendered as insufficient-data or cannot-compare filler. The LLM may
only synthesize the supplied grounded evidence; the renderer owns the integrated
CLOSE action.
Narrative validation admits only significant numeric tokens already present in
the outline and rejects invented counts. This policy supersedes the earlier sparse single-observation layout for
production fact packages; direct compatibility packages without an outline
retain the shorter fallback behavior.

Weekly Reporter topic-removal update on 2026-08-25: sleep and dispatch are no
longer report topics. They are excluded from the semantic outline, model fact
package, generated headline and analysis, observations, suggestions, and all
rendered Markdown sections. The summary now covers only evaluatable activity,
indoor environment, and device reception. The detail sections retain
risk-event detection/resolution under risk management
without rendering dispatch data. Private source-contract compatibility fields
remain temporarily available upstream but cannot cross the reporting boundary.
When all three report topics are unavailable, an empty available-item list is
preserved as empty rather than expanded to default topics. The narrative uses
the grounded coverage headline with empty analysis and observations, and the
renderer completes the report without indexing nonexistent evidence. This
zero-block path is an explicit terminal fallback state rather than a failed
Agent Server stream.

Weekly Reporter environment RISK correction on 2026-08-25: directional RISK
classification now uses daily maximum extrema and requires the same extreme on
four or more dates. The strict thresholds are maximum humidity below 30% or
above 70%, and maximum temperature below 15℃ or above 31℃. Exact boundary
values do not count as extreme days. Recommended-range temperature and humidity
departures still drive GOOD and CAUTION, while combined departure on four or
more dates selects RISK 5. Python owns all daily aggregation, boundary checks,
counts, precedence, and rendered status; the model receives qualitative copy
only.

Weekly Reporter valuable-insight summary update on 2026-08-26: the model no
longer follows a fixed LIFE/ENV/SAFE order or emits one sentence for every
available report area. Python still supplies the complete allowlisted
qualitative evidence and owns all calculations, statuses, issue detection, and
suggested actions. The narrative must cover every material CAUTION or RISK
topic, but may omit low-value GOOD facts and combine related evidence into one
to four connected weekly insights. Unavailable items remain fully excluded;
sleep and dispatch remain excluded from the entire report. Validation retains
topic allowlisting, material-issue coverage, numeric grounding, formal Korean,
safety filters, and the terminal zero-evaluable-item path.

Weekly Reporter spreadsheet-template policy update on 2026-08-27: the product
owner promoted spreadsheet `1tOuquKA_QrsWfWI6JlVTQ2z_pS2C5O9j5r8u6ZEo6QM`,
sheet `1395281680`, as the versioned classification, copy, and guardian-guide
policy. Prompt version `weekly-korean-sheet-template-v16` follows the approved
all-GOOD sequence: activity, indoor environment, and device reception, joined
by `구체적으로`, `이와 함께`, and `또한`. A byte-for-byte golden test locks the
full Markdown example, while deterministic Python continues to own arithmetic,
statuses, copy selection, guide priority, and rendering. The promoted rules
also make 150% activity `CAUTION`, include exact environment range boundaries,
use daily maxima for environment classification, and prioritize device issues
before activity, environment, and the general check-in.

Weekly Reporter risk-score presentation update on 2026-08-25: the deterministic
renderer now exposes the already-calculated current-week average `risk_score`.
Python rounds the average to a whole point using half-up rounding and classifies
it with the product-approved statuses `76–100 GOOD`, `26–75 CAUTION`, and
`0–25 RISK`. The report shows the grounded score, uppercase status, and exact
Korean guidance; missing or invalid source scores remain explicitly
unavailable. The score and classification stay outside model-authored prose.

Weekly Reporter activity presentation update on 2026-08-25: the source
contract now carries weekly totals calculated directly from non-null
`movement_count` and `remote_control_count` rows. Workflow-owned Python compares
each current total with its previous-week total, assigns the product-approved
`GOOD`, `CAUTION`, or `RISK` status, and renders the exact Korean guidance and
short summary. Missing totals and zero previous totals fail closed as an
unavailable comparison. Only the qualitative guidance may enter the reporter
prompt; totals, percentages, and thresholds remain deterministic report data.

Weekly Reporter activity layout update on 2026-08-31: the shared numbered
`활동량` wrapper was removed. Movement now renders as the sibling `생활 활동`
section and remote-control use as `생활 패턴`; each owns a flat `지표` list for
the current total, comparison total, and percentage. Calculation and copy
selection remain deterministic and unchanged.

Weekly Reporter risk-management layout update on 2026-08-31: the renderer no
longer emits the empty `위험 관리 기록` subsection or its unavailable-detail
placeholder. The section retains only the verified risk detection and normal
resolution counts; no source or calculation contract changed.

Weekly Reporter section-heading update on 2026-08-31: all main headings below
`주요 내용` are unnumbered. This applies to `생활 활동`, `생활 패턴`,
`실내 환경`, `기기 데이터 수신`, and `위험 관리`; guardian action-card list
numbering remains separate and unchanged.

Weekly Reporter living-activity copy update on 2026-08-31: the existing
movement ratio bands remain unchanged, while deterministic description and
summary copy now uses the approved `평소 수준`, `조금 감소`, `조금 증가`,
`많이 감소`, and `많이 증가` language.

Weekly Reporter living-pattern copy update on 2026-08-31: the same existing
ratio bands now map remote-control use to approved `TV 이용 등 일상적인 생활
패턴` descriptions and the summaries `평소 수준`, `조금 감소`, `조금 증가`,
`많이 감소`, and `많이 증가`. The living-activity copy is unchanged.

Weekly Reporter combined activity-summary update on 2026-08-31: Python now
maps the nine approved movement-plus-remote combinations to exact warm Korean
copy for the opening activity block in `한주 총평`. Prompt version
`weekly-korean-sheet-template-v16` requires the model to place that block first
after one connector without paraphrasing; validation enforces the same
contract and permits 해요체 only inside this Python-owned block. The block may
contain two sentences. Relevant indoor-environment and device findings remain
connected afterward, and the renderer still owns the separate closing action,
so the summary is not collapsed into a single activity sentence.

Weekly Reporter indoor-environment copy and boundary update on 2026-08-31:
all seventeen GOOD, CAUTION, and RISK variants now render the revised exact
guardian-facing description and short summary. Combined classification matches
the stated directional counters directly instead of inferring a direction
from aggregate departure days. The private source snapshot adds optional daily
maximum counters for temperature below 18℃ and humidity at or above 70%, used
only by cool-humid CAUTION and cold-humid RISK respectively. Older snapshots
without those fields fall back to the ordinary below-15℃ and above-70%
directional counters; raw source calculation and current fixtures provide the
new counters explicitly.

Weekly Reporter device-status copy update on 2026-08-31: the rendered
`기기 데이터 수신` heading is now `기기 상태`. Existing deterministic row
classification remains good, power, then position, with power-first weekly
precedence and two-occurrence CAUTION thresholds. GOOD, power-check, and
position-check results now render the newly approved exact descriptions and
summaries. Prompt version `weekly-korean-sheet-template-v17` uses `기기 상태`
as the model-visible topic label so generated summaries do not reintroduce the
retired section name.

Weekly Reporter guardian-action metadata update on 2026-08-31: deterministic
guardian guides now own an approved description, tag, and optional template
ID in addition to condition, status, and title. The increase actions apply to
movement and remote-control `CAUTION`; increase `RISK` no longer reuses them.
Rendered action cards contain only deterministic guides because model-authored
suggestions cannot supply an approved tag or template ID. Device issues remain
first, output remains capped at three cards, and the stable GOOD card requires
a GOOD weekly risk score with no CAUTION/RISK area state or detected risk
event. Prompt version `weekly-korean-sheet-template-v18` carries the expanded
candidate metadata but leaves selection and rendering in Python.

Weekly Reporter human-summary refinement on 2026-08-31: prompt version
`weekly-korean-sheet-template-v19` treats `한주 총평` as the primary guardian
customer explanation. The exact Python-selected movement-plus-TV block remains
first and byte-for-byte unchanged. When indoor-environment or device evidence
is available, validation now requires at least one supporting insight after
that block. The model prioritizes material changes, cross-area relationships,
observation reliability, and useful stable context, may combine related facts,
and is explicitly prevented from using numbered recitals or process-oriented
report filler. The deterministic fallback follows the same multi-insight rule.

Weekly Reporter natural-support summary update on 2026-08-31: prompt version
`weekly-korean-sheet-template-v20` adopts warm 해요체 for the entire structured
headline and analysis and rejects stiff administrative 합니다체. The exact
Python-owned activity block now begins the analysis directly without a forced
connector; the opposing CAUTION decrease/increase pair uses the approved
`활동은 조금 줄어든 모습이었지만...` wording. For valid data, the
personalized opening follows the deterministic weekly risk-score status, with
GOOD rendered as `전반적으로 평소와 비슷한 생활 흐름을 이어가셨어요`.
Normal device reception may establish observation reliability before a
material environment finding and its practical check. The renderer no longer
adds a separate generic CLOSE paragraph because guidance now stays beside the
finding that supports it. Deterministic fallback and validation mirror this
same structure without changing numeric calculations or status rules.

Weekly Reporter free-summary composition update on 2026-08-31: prompt version
`weekly-korean-free-summary-v21` replaces the normal-path Python summary mode,
headline, and exact activity-combination block with one LLM-authored paragraph.
The model receives only subscriber identity and deterministic report-facing
results for overall state, living activity, living pattern, indoor environment,
device status, risk management, and approved actions. It receives no raw rows,
totals, ratios, thresholds, dates, measurements, sleep/dispatch fields,
`summary_outline`, or prewritten summary sentence. The plain-text response must
be one body-only paragraph in warm 해요체 and is rejected if it contains digits,
`움직임`, `리모컨`, English status values, Markdown, formal administrative
endings, excluded topics, unsupported claims, or an omitted material issue.
Python splits the validated first sentence only to satisfy the existing
`WeeklyNarrative` contract, then the renderer rejoins it unchanged. Detail
sections and guardian actions remain deterministic; one correction and the
disclosed validated fallback remain reliability boundaries.

Weekly Reporter summary-quality guardrail update on 2026-09-01: prompt version
`weekly-korean-free-summary-v22` incorporates production feedback for sparse
and attention-heavy reports without changing deterministic calculations or
section classifications. The model synthesizes related findings rather than
copying section descriptions, states each fact once, and consolidates
same-purpose actions. Overall score-band and device-reception results cannot be
expanded into subscriber safety claims. An absent risk-detection record is
normally omitted and never means a dangerous situation did not occur; a
present record is mandatory but may be described only as a record, without
cause or severity inference. Material changes, device checks, and present risk
records prohibit a contradictory generic stable close. Validation rejects
repeated sentences or check-in intent, unsupported safety reassurance, omitted
present risk records, and stable closes that conflict with attention signals;
the single corrective retry receives a specific safe instruction. The
deterministic fallback strips section-local action repetition, combines the two
living-pattern trends, and appends at most one grounded action before passing
the same validator.

Weekly Reporter calm-record wording update on 2026-09-01: prompt version
`weekly-korean-free-summary-v23` keeps all deterministic record calculations,
detail-section labels, and classifications unchanged while removing categorical
or alarm-amplifying language from `한주 총평`. An absent separate record is no
longer included in the model payload; a present record is exposed only through
neutral `별도 확인 기록` data and summarized with calm observation wording.
Summary validation rejects `위험`, rushed or alarming words, and exclamation
marks, while still requiring a neutral mention when a record exists. Correction
feedback and deterministic fallback use the same unhurried language.

Weekly Reporter sparse-reception personalization update on 2026-09-01: prompt
version `weekly-korean-free-summary-v24` requires a usable supplied subscriber
name in the summary opening and rejects generic substitute honorifics in later
direct references. For deterministic complete lifestyle-information reception
absence (`기기 상태: 자료 없음`), the model payload is reduced to the subscriber,
one neutral reception-absence fact, and the approved power check. The summary
contains only the two grounded sentences `생활 정보가 들어오지 않은 날이
있었어요` and `기기 전원이 잘 연결되어 있는지 확인해 주세요`; unrelated
overall, activity, environment, and record interpretation are omitted.
Correction feedback and deterministic fallback enforce the same boundary.

Weekly Reporter guardian-persona and closing-order update on 2026-09-01:
prompt version `weekly-korean-free-summary-v25` removes risk-management and
separate-record data from the `한주 총평` model payload and forbids mentioning
or implying those records in the generated paragraph. This does not change the
deterministic `위험 관리` detail section. The summary persona is an experienced
customer-support adviser describing a parent who lives alone to an adult child
who lives apart. Activity evidence uses `활동` and `TV 이용 등 일상적인 생활
패턴`, never the unsupported duration phrase `TV 이용 시간`. All observations
must precede one consolidated final action sentence; validation rejects action
requests before the last sentence, new facts after an action, repeated actions,
and emotional-attitude directions such as `다정하게` or `따뜻하게`. Correction
feedback, the deterministic fallback, tests, and project-local skill references
share this boundary.

Weekly Reporter natural-flow and basic-information boundary update on
2026-09-01: prompt version `weekly-korean-free-summary-v26` removes overall
score-band and every other `기본 정보` value from the `한주 총평` payload. The
subscriber display name remains only as the identity required by the fixed
`지난 한 주 [이름]님은` opening. That first sentence now carries the core
activity and everyday lifestyle-pattern flow instead of repeating generic
overall copy. Normal summaries contain two to four sentences, join related
findings with natural Korean connective endings, and combine stable
activity/pattern and device/environment observations instead of reciting one
short sentence per section. A summary-only underscore immediately after a
bracketed service label is normalized to a space; stored identity and the
deterministic basic-information section remain unchanged. Risk-management
exclusion, non-duration TV wording, final-action ordering, correction, and
fallback boundaries from v25 remain in force.

Weekly Reporter opening-particle update on 2026-09-01: prompt version
`weekly-korean-free-summary-v27` prevents the fixed `지난 한 주 [이름]님은`
opening from immediately repeating the Korean topic particle with `활동은`,
`생활 활동은`, or `생활 패턴은`. The first clause uses an `이/가` subject form
such as `활동이` or restructures the phrase, while later contrastive `은/는`
remains valid. Deterministic validation triggers one specific corrective retry,
and the fallback applies the same grammar normalization. No calculation,
payload, rendering, or report-section boundary changes.

Weekly Reporter guardian-card title and environment-eligibility update on
2026-09-01: deterministic guardian cards now use observation-style titles for
stable, activity, everyday-pattern, environment, and device states while
preserving the approved descriptions, tags, and template IDs. Directional
environment variants one through four select `ENV_CAUTION_01` through
`ENV_CAUTION_04` for either CAUTION or RISK; combined variants five through
eight remain RISK-only. Prompt version `weekly-korean-free-summary-v28` labels
these values as guardian-card titles rather than closing action sentences.
Summary closing checks and deterministic fallback actions are grounded in the
verified section descriptions. Card priority, the three-card cap, stable-card
eligibility, and the zero-source device safeguard are unchanged.

Weekly Reporter environment day-count update on 2026-08-25, superseded by the
2026-08-27 spreadsheet-template policy above: the source service collapses
device summaries by date and deterministically counts departures from the
approved year-round temperature and humidity ranges using each date's maximum
values. The validated snapshot carries observed,
temperature, humidity, combined, and directional day counts. Workflow policy
assigns the approved uppercase status, exact Korean description, and short
summary with explicit precedence. The unspecified `반복` boundary is normalized
to four days, matching the explicit combined RISK duration; duplicated GOOD
copy maps to zero-day and one-day variants. The model receives only the chosen
qualitative description, while Python owns counts, status, ranges, and output.

Weekly Reporter device-reception update on 2026-08-27: the source service now
classifies each raw device-daily-summary row into validated good, power, and
weak-position occurrence counts. GOOD requires non-null/non-zero temperature,
humidity, light, and movement counts but ignores remote-control usage. Power
requires null temperature, humidity, and light counts regardless of activity
values. Position continues to inspect all five count fields after good and
power are excluded. Row classification is mutually exclusive in good, power,
then position order; workflow policy uses the approved two-occurrence threshold and
power-first weekly precedence to select `CAUTION`, then selects `GOOD` when at
least one good occurrence remains. Good occurrences do not need to equal every
source row. Unmatched rows are shown as a neutral `기타 수신 패턴` count and do
not override a matched weekly status. Received rows matching no weekly rule are
`판정 불가` and never create a false missing-data or power-check claim. Python
owns all raw comparisons, counts, precedence, status, and rendering; only
qualitative section assessments may reach the model.

Weekly Reporter zero-reception guidance update on 2026-08-26: a current period
with no device-daily-summary rows remains internally unavailable and does not
create a synthetic power occurrence, but its deterministic device-section
description asks the guardian to verify that device power is connected. Since
the status remains unavailable, the absence stays out of model-authored
insights and is not interpreted as a health or safety event.

Weekly Reporter guardian-guide update on 2026-08-26, superseded by the
2026-08-27 spreadsheet-template policy above: workflow-owned Python maps
validated activity changes, promoted environment conditions, and device
CAUTION results to a
product-approved internal condition, displayed title, and analysis sentence.
The renderer hides the internal condition and displays the title plus analysis,
orders device problems, activity changes, environment, then the general
check-in, caps output at three,
places deterministic guides before model suggestions, and closes `한주 총평`
with the first deterministic title. Hot and cold environment guides map by
semantic condition rather than internal variant number. The model may receive
approved titles as qualitative suggestions and fill remaining slots, but it
does not select, reorder, or rewrite deterministic guide content.

Weekly Reporter personalization and sensor-evidence update on 2026-08-26: the
Python-owned summary outline now creates the personalized first sentence from
the validated ward display name, and the renderer uses that headline directly.
The model prompt identifies the 안심지키미 expert-report role and receives
qualitative assessments for movement, remote control, temperature, humidity,
and device reception together with exact deterministic guardian candidates;
raw sensor rows, totals, and thresholds remain outside model state. Device-row
reception classification is mutually exclusive in good, power, then position
order, while weekly power and position CAUTION still require two occurrences.

Weekly Reporter template refinement on 2026-08-24: the weekly narrative heading
is now `한주 총평`, and its closing sentence repeats the first validated,
highest-priority guardian suggestion to keep the assessment warm and actionable.
The separate detailed action section remains. The score-band legend is no longer
rendered. The later topic-removal policy supersedes the original conditional
sleep-section behavior and excludes sleep from every report.

Frontend launch integration update on 2026-08-14 (superseded on 2026-09-04):
the Agents catalog marked `ansimk_weekly_reporter` as the single live-data
entry. Both of its **Run in Chat** actions created a one-shot run intent in UI
state and navigated to Chat. Chat consumed that intent once and chose the most
recent completed Monday in
the local calendar with `Asia/Seoul`, and calls the existing Agent Server SSE
boundary with cancellation enabled. Custom workflow events drive a live
four-stage trace; the completed per-ward Markdown reports and any warnings are
rendered in the transcript. Frontend parsing mirrors the ward danger-day
contract and rejects malformed events or results. The browser stores no MCP
endpoint or credential. Other preview agents still have no live runner.

Concurrent Chat/Weekly Reporter update on 2026-08-20 (superseded on
2026-09-04): the shared Chat workspace owned independent `chat` and
`weekly-report` request lanes. Each lane permitted one request, owned its own
abort controller and UI state, and could be cancelled
without affecting the other. Weekly Reporter remains visible as background
work while the normal Chat composer stays available. This removes a frontend
serialization bottleneck; the two requests may still compete for a shared
inference endpoint, so deployment capacity and latency remain separate release
concerns.

Agent Server concurrency correction on 2026-08-20: the development image starts
`langgraph dev` with `--n-jobs-per-worker 4`. The installed in-memory runtime's
implicit single-job default serialized otherwise-independent graph runs, so a
Chat run could not begin until the interactive Weekly Reporter run ended.
Operator-facing Weekly Reporter callers now use graph `max_concurrency: 1` to
avoid placing a four-report fan-out ahead of Chat at the shared model endpoint.
The four Agent Server slots are run admission capacity, not four guaranteed LLM
slots. Bulk workers remain a separate process boundary and require dedicated or
explicitly reserved inference capacity before production activation.

Repository validation for this correction passed the complete agent test suite
(one environment-dependent skip), full Ruff checks, three-graph LangGraph
validation, 97 frontend tests, the frontend production build, Tauri `cargo
check`, npm audit with zero vulnerabilities, and root Compose configuration.
The running stack was not replaced because the current account cannot access
the host Docker socket; deployment and the live overlapping-run browser check
remain explicit operator gates.

Weekly Reporter detail integration update on 2026-08-14 (superseded on
2026-09-04): the stable catalog route `/agents/1` rendered the live
`ansimk_weekly_reporter` workbench directly. Operators could select a reporting
Monday and timezone, observe
validated custom progress events, cancel the active Agent Server run, and
inspect per-ward Markdown and metrics without leaving the agent detail route.
The former `/test-agent` route reused the same workbench in test-oriented
presentation, while all other agent detail routes retained their preview UI.

Chat attachment runtime update on 2026-08-14: `ax-contracts` defines strict
references for gateway-normalized transient chat artifacts and safe attachment
error payloads. The chat graph accepts at most five references while keeping
file bytes and extracted document text outside graph state and stream events.
`ax-integrations` resolves only absolute `file://` paths below
`AX_CHAT_ARTIFACT_ROOT`, rejects traversal and symlinks, opens every path
component with no-follow semantics, and verifies regular-file type, size,
stability, and SHA-256 before constructing provider content. Documents become
delimited untrusted text parts; normalized PNG, JPEG, and WebP files become
base64 `image_url` parts only when `OPENAI_SUPPORTS_VISION=true`. Vision remains
disabled by default and must be enabled only after a live capability check.
The product backend requests only LangGraph `custom` stream mode for attachment
runs, preventing the runtime's initial values event from echoing private file
references; a terminal `response_complete` custom event verifies the assembled
answer. Text-only chat retains the existing `custom` plus `values` contract.

## 1. Design goals and constraints

The system must be clean, maintainable, fast, modular, secure, and suitable
for production workloads. The architecture therefore favors:

- explicit package boundaries and stable contracts;
- compiled LangGraph graphs with small, typed state;
- durable execution delegated to Agent Server and PostgreSQL;
- side effects isolated behind capability-scoped tools and integrations;
- a private Agent Server behind an authenticated product API gateway;
- deterministic tests and separate quality evaluations;
- bounded retries, timeouts, cancellation, and resumable interruptions;
- provider-neutral ports where changing model or infrastructure vendors does
  not change graph topology.

LangGraph is the orchestration runtime, not the entire application framework.
LangChain integrations may be used inside adapters, while LangSmith remains an
optional tracing and evaluation backend. [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)

## 2. Runtime topology

```text
Client
  |
  v
API Gateway (public boundary)
  |  AuthN/AuthZ, tenant policy, limits, audit, API contracts
  v
Agent Server (private)
  |  assistants, threads, runs, streaming, task queue
  +--> PostgreSQL (durable resources, checkpoints, long-term store)
  +--> Redis (ephemeral queue signaling, cancellation, pub/sub)
  +--> SearXNG (private, no-provider-key web discovery)
  |
  v
Compiled LangGraph graphs
  +--> supervisor/coordinator nodes
  +--> specialist subgraphs
  +--> capability-scoped tool adapters
  +--> model and external-service integrations
```

The first production target is self-hosted Agent Server on Docker Compose or
a VM. Compose is the local/integration baseline; the container boundaries and
configuration must remain portable to Kubernetes. LangChain documents
PostgreSQL and Redis as required standalone-server backing services and
recommends Kubernetes for production-grade scaling, but this project selects
Compose/VM as its initial operational target. [Standalone deployment](https://docs.langchain.com/langsmith/deploy-standalone-server)

Agent Server is not publicly exposed. The gateway translates the product API
into Agent Server calls and owns user-facing security policy. This prevents
clients from coupling to LangGraph-specific API details.

## 3. Repository and package structure

```text
apps/
  gateway/                   # public API service
  agent_server/              # Agent Server deployment metadata
  workers/                   # independently scalable async execution boundary
  weekly_report_scheduler/   # fixed private cron-to-bulk-API submission
workflows/
  orchestrator/              # optional cross-workflow dynamic delegation
  smoke/                     # deterministic example graph
  risk_monitoring/           # business workflow graph
  weekly_report/
  call_recommendation/
  device_management/
packages/
  contracts/                 # versioned Pydantic boundary models
  runtime/                   # execution context, limits, normalized errors
  tools/                     # tool policies and capability contracts
  integrations/              # model, Agent Server, storage, HTTP ports
  persistence/               # durable storage ports and adapters
  observability/             # logs, metrics, traces, and audit boundaries
  evals/                     # datasets, evaluators, release gates
infra/
  compose/                   # local and VM Agent Server topology
tests/
  unit/                      # isolated deterministic behavior
  contract/                  # schema and boundary compatibility
  integration/               # PostgreSQL, Redis, Agent Server containers
  evals/                     # quality and trajectory regression cases
docs/
```

The root is a `uv` workspace. Each package has its own `pyproject.toml`,
editable workspace dependency, focused tests, and minimal runtime dependencies.
Dependencies may flow only in the following direction:

```text
apps -> workflows -> packages
apps ----------------> packages

packages/runtime --------> packages/contracts
packages/tools ----------> packages/contracts
packages/integrations ---> packages/contracts
packages/persistence ----> packages/contracts
packages/observability --> packages/contracts
packages/evals ----------> packages/contracts
```

Shared packages never import from `apps/` or `workflows/`. Apps may compose
workflows and packages. Workflow-local prompts, state, nodes, specialists, and
topology stay in `workflows/<name>/`; provider clients stay in
`packages/integrations`; reusable capability policy stays in
`packages/tools`; external request handling stays in `apps/gateway`.

This is a modular monolith, not a service per workflow. Split an application
or worker deployment only when ownership, isolation, load, or availability
measurements justify the operational cost.

## 4. Contracts and state

`ax-contracts` is the only source of cross-boundary schemas. Models reject
unknown fields and carry `schema_version` so persisted or replayed results can
be migrated deliberately.

Required contracts are:

- `TaskEnvelope`: objective, context, priority, task identity, requester;
- `RunContext`: tenant, thread, run, correlation identity, deadline, attempt;
- `AgentInput` / `AgentOutput`: validated graph boundary and evidence;
- `ToolRequest` / `ToolResult`: capability, arguments, idempotency, risk, and
  retry classification;
- `Handoff`: source/target ownership, objective, artifacts, evidence, and stop
  conditions;
- `ArtifactRef`: URI, type, version, and optional checksum;
- `ChatAttachmentRef`: transient attachment identity, safe filename, kind,
  normalized media type, local file URI, byte size, and SHA-256;
- `ChatErrorPayload`: safe attachment/capability error code, message, and
  optional affected filename for custom stream events and terminal chat state;
- `EvaluationResult`: criterion, status, severity, score, evidence, and
  recommendation.
- `WeeklyReportRequest`, `WardWeeklyMetricSnapshot`, `WardWeeklyMetricDelta`,
  `WardWeeklyMetrics`, `WardWeeklyReport`, and `WardWeeklyReportBatchResult`:
  the versioned selection input, full current/prior ward metadata, grounded
  narrative, Markdown output, and ordered batch result for
  `ansimk_weekly_reporter`. `WeeklyReportSourceResponse` is the private
  FastAPI-to-workflow snapshot boundary. Earlier
  personal-work contracts remain temporarily exported for compatibility.

LangGraph state should contain only the minimum working state needed by the
graph. Durable state must be associated with a stable `thread_id`; checkpoint
history and task writes are relied on for resumption and failure recovery.
[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

## 5. Graph and agent design

- Export compiled graphs from `workflows/`; use factories only when a run needs
  graph customization.
- Keep nodes small and testable. Nodes decide and transform state; tools perform
  controlled side effects.
- Use explicit edges, bounded loops, maximum step/tool-call limits, and terminal
  states (`completed`, `blocked`, `failed`).
- Use a supervisor graph only when work spans multiple specialists. Each
  specialist has a responsibility, authority, inputs, outputs, tools,
  stop-conditions, and escalation rule.
- Require handoffs to carry structured output, artifacts, evidence, and the
  next action; never hand off an unbounded transcript as the only contract.
- Use `interrupt()` for approval or missing human input. A persistent
  checkpointer and stable thread ID are mandatory for resumable interrupts; use
  a production checkpointer rather than in-memory storage. [Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- Do not instantiate production checkpointers or stores inside graph modules;
  Agent Server injects those resources at deployment time. [Agent Server persistence](https://docs.langchain.com/langsmith/agent-server)
- `ansimk_weekly_reporter` uses a coordinator plus isolated per-ward subgraph.
  The coordinator calls only its private-network source API and `Send`
  fans out after source and reporting-window validation. Branches transform
  verified metrics into report-facing section results, request one Korean
  summary paragraph,
  validate or replace it, and return finalized reports through reducers.
  Source selection accepts explicit ward IDs or an opaque validated cursor and
  is capped at twenty-five. Operator-facing callers execute one branch at a
  time to preserve interactive model capacity; isolated tests may raise that
  bound, while the separate bulk worker owns high-throughput concurrency.

## 6. Gateway API

The public API is versioned and intentionally independent of Agent Server wire
schemas:

| Endpoint | Behavior |
| --- | --- |
| `POST /v1/runs` | Validate and submit a task; return run identity and status. |
| `GET /v1/runs/{run_id}` | Return normalized status, output, errors, and evidence. |
| `GET /v1/runs/{run_id}/events` | Stream progress and terminal events. |
| `POST /v1/threads/{thread_id}/resume` | Resume a durable interrupt with a validated command. |
| `GET /healthz` / `GET /readyz` | Liveness and dependency readiness. |

Gateway responsibilities include authentication, authorization, tenant
isolation, request size/rate limits, idempotency keys, correlation IDs, audit
events, input/output redaction, and mapping internal errors to safe public
responses. The gateway must not expose provider credentials, raw stack traces,
raw prompts, or unrestricted tool arguments.

## 7. Tools and integrations

Tools are registered by capability and risk (`read`, `write`, `destructive`).
Every call is checked against a tenant-aware allowlist before execution.

Tool adapters must define:

- typed arguments and results;
- timeout and cancellation behavior;
- idempotency strategy;
- retryable versus permanent error mapping;
- audit metadata;
- network and credential scope.

Secrets remain in the executor/integration layer and are never inserted into
prompts or agent-visible state. External input and model output are untrusted
until validated.

The OpenAI-compatible model adapter accepts `URL`, `MODEL`, and
`OPENAI_API_KEY`, with `OPENAI_BASE_URL` and `OPENAI_MODEL` as preferred aliases
for shared environments. It normalizes server, `/v1`, and full completion URLs;
uses streamed SSE responses; reuses a bounded async connection pool; and
retries transient failures only before any response content has been emitted.
Provider errors must not expose credentials or unrestricted response bodies.
Its provider-neutral message contract accepts either text or validated
OpenAI-compatible text/image content parts. Remote image URLs are rejected;
image inputs use data URLs assembled transiently from verified normalized
artifacts. `OPENAI_SUPPORTS_VISION` defaults to false and is a deployment
capability assertion, not automatic model detection.

The transient chat attachment reader is an integration boundary because it
owns filesystem access and provider-payload assembly. The gateway passes only
`ChatAttachmentRef` objects. The reader enforces five files, 50 MiB per file,
50 MiB combined, and 100,000 extracted document characters. It accepts
normalized UTF-8 plain/Markdown/CSV text and normalized PNG/JPEG/WebP bytes.
Every attachment and original filename is explicitly labeled untrusted in the
model request so multi-file prompts can still refer to files by name.

Reusable web research is split into discovery and evidence retrieval.
`web_search` calls an injected provider-neutral executor; the initial adapter
uses a private SearXNG JSON API and returns normalized, deduplicated source
metadata. `web_fetch` opens one selected public HTTP(S) source and returns
bounded readable text marked as untrusted. Both tools are read-risk operations,
require explicit allowlisting, produce deterministic idempotency keys, preserve
stable source IDs and URLs for citations, and propagate cancellation.

Page retrieval must resolve and pin public destinations, reject any DNS answer
set containing a non-global address, revalidate redirects, disable ambient
proxy configuration, omit user credentials and cookies, restrict content
types, and cap redirects, downloaded bytes, and extracted text. Search snippets
are discovery data only; workflows fetch selected pages before using
substantive claims as evidence. Retrieved content never changes permissions or
tool policy.

Remote MCP servers are declared in `config/mcp_servers.json`. Checked-in
configuration may name a secret environment variable and a non-secret prefix,
but may not contain a static credential. Discovered tools are namespaced by
server, validated against their advertised input JSON Schema, explicitly
classified by risk, and separately allowlisted by each consuming workflow.
Unclassified tools fail closed. Remote descriptions and results are untrusted;
they never modify permissions. MCP tool calls are not retried automatically
because remote idempotency cannot be assumed.

Reusable PostgreSQL access is exposed by `ax-integrations` as a bounded
`asyncpg` pool. It accepts only application-owned parameterized query strings,
runs each fetch in a read-only transaction, maps provider failures to safe
errors, and keeps DSNs out of graph state. The weekly reporter is the first
consumer through its private FastAPI process; it does not expose a
model-callable SQL tool.

Outbound Slack messaging is also exposed by `ax-integrations`, using the
official async Slack Web API client. Only channel IDs loaded from
`SLACK_DEFAULT_CHANNEL_ID` or `SLACK_CHANNEL_<NAME>` are authorized. Callers
receive a typed success/failure result; provider exceptions, tokens, message
text, blocks, and caller metadata are excluded from logs and normalized errors.
Slack rate-limit handling is bounded, `chat.postMessage` requests have a
configurable timeout, and tests inject a fake client. Business workflows must
call this service instead of importing the Slack SDK. Sensitive outbound
notifications retain their workflow-specific human-approval gate.

## 8. Persistence, reliability, and performance

- PostgreSQL is the durable system of record for Agent Server resources,
  checkpoints, thread state, and long-term memory.
- Redis stores ephemeral queue signaling, cancellation, and streaming pub/sub;
  no irreplaceable state may depend on Redis.
- Use bounded retries with explicit retry reasons, exponential backoff, and
  idempotent writes.
- Persist enough state to resume after worker interruption without rerunning
  completed side effects.
- Use deadlines, per-node/tool timeouts, cancellation, graceful shutdown, and
  duplicate-submission handling.
- Prefer compiled graphs, async I/O, small state payloads, bounded concurrency,
  and parallel fan-out only for independent work.
- Store large documents and generated artifacts outside graph state and pass
  typed references across nodes and handoffs.
- Chat attachments remain in a private shared transient volume. The graph reads
  them only for the active model call; normalized bytes, extracted text, and
  image data URLs are never returned in state or custom events. Attachment
  references are cleared from terminal state after success or safe failure.
- Reuse bounded HTTP and database connection pools in adapters; never create a
  client per node invocation.
- Track queue delay separately from graph execution time and model/tool latency.

Agent Server supports single-host and split API/queue modes. Begin with the
single-host Compose baseline, then separate API and queue workers when load
requires independent scaling. [Agent Server runtime architecture](https://docs.langchain.com/langsmith/agent-server)

## 9. Security and observability

- Authenticate every public request and authorize every tenant/resource action.
- Keep gateway and Agent Server on private network segments; use TLS at the
  ingress boundary.
- Load secrets from deployment secret stores; never commit `.env` secrets,
  bake them into images, or print them.
- Redact sensitive inputs, outputs, metadata, and tool arguments before tracing;
  disable tracing for data classes that cannot be safely retained. [Trace masking](https://docs.langchain.com/langsmith/mask-inputs-outputs)
- Emit structured events for request, assignment, node start/end, tool call,
  retry, interrupt, resume, evaluation, and completion.
- Include correlation, tenant, thread, run, graph, node, and version metadata
  without including secrets or unrestricted user content.
- Measure latency, queue time, throughput, errors, retries, token usage, cost,
  checkpoint failures, and evaluation scores.

## 10. Verification and release gates

Every package must have unit tests. Shared behavior additionally requires:

- contract tests rejecting malformed or unknown fields;
- graph tests for happy path, bounded loops, failure, and interrupt/resume;
- tool-policy tests for allow, deny, timeout, and destructive actions;
- gateway tests for auth boundary, validation, idempotency, and safe errors;
- container integration tests with PostgreSQL, Redis, and Agent Server;
- recovery tests for worker restart, duplicate work, stale resume, and partial
  writes;
- curated evaluation datasets for task success, tool selection, argument
  correctness, safety, cost, latency, and trajectory quality.

CI must run formatting, linting, type checks, dependency/security audit,
contract/unit tests, integration tests, and evaluation thresholds before image
publication. LangSmith evaluations may be used for offline, online, and CI
quality gates while keeping evaluator interfaces provider-neutral. [Evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)

## 11. Implementation order

1. Keep `ax-contracts` and package dependency checks stable.
2. Add runtime context, error, limit, and retry primitives.
3. Add graph package conventions and one deterministic compiled graph.
4. Add tool policy and one fake integration for contract tests.
5. Add gateway adapter and public API tests.
6. Add PostgreSQL/Redis Compose integration and Agent Server image build.
7. Add persistence recovery, interrupt/resume, observability, and security
   checks.
8. Add and mock-test real model/tool integrations as workflows require them;
   require the preceding deployment gates plus live readiness checks before
   production release.

## 12. Known limitations and decisions deferred

- The weekly reporter now calculates broad raw weekly metadata and produces
  validated warm Korean summaries. Manual submission remains available, and a
  fixed Compose cron service submits the previous completed week every Monday
  at 04:00 `Asia/Seoul`. Cron has bounded request retries but no durable
  missed-run catch-up or editable schedule record. Durable bulk finalization
  persists rendered frontend JSON; interactive compatibility runs remain
  non-writing. An operator can explicitly deliver a completed batch to an
  approved Slack destination; delivery is not an automatic graph side effect.
  Weekly-average risk-score bands and indoor
  environment ranges are product-approved deterministic presentation rules;
  the weekly-summary model receives neither numeric score nor report-facing
  overall/basic-information values. The
  model-backed chat workflow now supports bounded per-thread session history
  (see the 2026-09-14 update) and does not yet compose the reusable web research
  tools. Chat
  attachments are transient and cannot be referenced by later turns;
  scanned-PDF OCR and durable or multi-host artifact storage remain outside the
  agent runtime.
- MCP registry, discovery, and authorized tool adapters are implemented. The
  weekly reporter no longer grants an MCP tool; other workflows receive
  no MCP capabilities unless they define their own minimal allowlist and
  tool-use behavior.
- No-key SearXNG engines may be throttled, challenged by CAPTCHAs, or change
  without notice. Their live quality is monitored separately from deterministic
  CI and is not equivalent to a paid search-provider availability contract.
- `apps/workers`, `packages/persistence`, and `packages/observability` are
  explicit extension boundaries; their production implementations remain
  intentionally deferred until requirements and load measurements exist.
- Compose/VM is the selected first production posture; Kubernetes remains the
  scale-out migration target.
- LangSmith tracing/evaluation is optional and must be configured only after
  data-retention and redaction policy is approved.
- Concrete tenant model, identity provider, database HA strategy, and model
  vendor remain application decisions, but must not violate these boundaries.

## Explicit insert timestamps (2026-09-08)

Production recovery identified `created_at` NOT NULL failures for all 6,437
reports. The writer now supplies `NOW()` for both `created_at` and `updated_at`
on INSERT, without depending on table defaults. Conflicting ward/week updates
preserve `created_at` and refresh `updated_at`. This applies to regular bulk
finalization and recovery, and requires rebuilding the worker image. No table
alteration or report regeneration is required. Retry recovery with `--write`
after rebuilding; `--skip-not-null` remains optional for other rejected rows.


## UI report exports without report-table writes (2026-09-09)

The bulk request now carries a strict `persist_reports` boolean, defaulting
to true for existing scheduled/CLI requests and older jobs. The frontend
submission adapter always sends false for UI test generation. The control API
stores the flag with the job; finalization checks it before report-table
UPSERTs while always producing the ZIP. Job tracking and private artifact
retention are unchanged. See [implementation and validation](../../docs/08-implementation/weekly-reporter-ui-zip-only.md).


## Weekly Report ZIP retention (2026-09-09)

The weekly report worker retains the five latest published terminal ZIPs per
shared store, ordered by completion timestamp and job ID. A generic job-store
query selects older terminal exports; a job-scoped artifact deletion removes
only `weekly-reports.zip`, then clears the download URI/checksum without
changing outcome or completion time. Terminal failed-job orphan ZIPs are also
removed. Active jobs, report-table rows, and report recovery artifacts remain.
Cleanup runs after execution and every 30 seconds in the worker admission loop,
including startup. Failures are retried without failing generation. The manual
`cleanup-exports` command shares this policy. No schema migration is needed.
See [implementation and verification limits](../../docs/08-implementation/weekly-report-five-zip-retention.md).


## Selected-ward ZIP-only tests (2026-09-09)

The bulk request optionally carries up to 25 unique positive `ward_ids`. It
normalizes the report count to the selection and requires report persistence
to be disabled and the cursor omitted. The UI exposes this as an optional
comma-separated field. The worker uses the existing source explicit-ID path,
validates result membership, and resumes only unstaged IDs. Missing IDs become
source warnings without substituting other wards. Existing bulk discovery,
scheduled storage, job tracking, and five-ZIP retention remain in place.
See [selected-ward implementation and validation](../../docs/08-implementation/weekly-reporter-selected-ward-tests.md).

## Production weekly-report delivery (2026-09-11)

An opt-in production Compose overlay adds a deterministic sync worker and an
SSH forwarding container. The production report writer atomically saves an
immutable, checksummed delivery payload to a local report-database outbox in
the same transaction as report storage. Explicit production enqueue flags
exclude default development writers; ZIP-only UI requests remain non-writing.
The separate bulk-job database and graph state do not carry delivery payloads.

A leased per-report worker inserts into the private target database, accepts
identical replays, and blocks conflicting content without overwrites. Bounded
retries, lease-token acknowledgements, and target-commit-before-local-ack ordering
recover process and network failures independently of generation. Delivery is
at-least-once and per-report atomic, not a whole-week distributed transaction.
Same ward identity was operator-confirmed. Local migration, scoped credentials,
verified SSH forwarding and target TLS are required before activation. See
[production delivery](weekly-report-production-sync.md) for deployment,
permissions, status/dry-run/retry commands, and verification limits.

Read-only sync readiness checks now validate both database connections, outbox
columns, target tables, and the immediate ward/week unique index. The `check`
command and every `dry-run` perform this validation even with an empty queue;
no probe rows or lease mutations are used. Target write permissions remain a
deployment verification step.


## Operator historical report migration (2026-09-11)

`playground/weekly-reporter/migrate.sh` provides an explicit local-to-production
report copy, separate from outbox delivery. Preview uses read-only transactions;
`--write` upserts by ward/week in one target transaction with a report-table
write lock. Source snapshots are read-only; target IDs and existing creation
timestamps are preserved, every matching row is updated (including identical
content) with a refreshed `updated_at`, and missing target
wards are logged and skipped. All weeks are selected unless `--week-start` is set.
The original manual entry point leaves the outbox unchanged. See the [operator instructions](../playground/weekly-reporter/README.md).
Seven isolated unit cases and shell/lint checks pass; live database behavior
and SSH connectivity have not been verified.

## Scheduled post-storage migration (2026-09-13)

The Monday 04:00 Asia/Seoul scheduler now owns submission, bounded status
polling, and a subsequent invocation of the existing playground migration
script. It waits for `completed` or `partial`, which follow local report
storage commit, then passes `--write --week-start` with the original report
week's Monday. Failed/cancelled jobs never trigger migration. This changes
the scheduler's deployment boundary: its image includes SSH and database
client dependencies, while the production Compose file mounts local source and
migration settings read-only plus durable receipt and known-host volumes.

A file lock serializes migration invocations sharing the tunnel port. A
per-week receipt suppresses completed reruns; absent receipts reuse the
existing bulk idempotency key. Polling is bounded to 24 hours and migration
to one hour. Operator resume accepts an explicit reporting Monday. Process
interruption after target commit but before receipt persistence can repeat
upserts; no automatic catch-up is promised. Generation status stays independent
of migration failure, and the separate outbox overlay must not deliver the
same reports concurrently. See [scheduler operations](../apps/weekly_report_scheduler/README.md).


## Chat session memory (2026-09-14)

Normal Chat conversations now carry random UUID session IDs from the ephemeral
frontend store through the backend's validated multipart `session_id` field.
The backend creates/reuses Agent Server threads with `if_not_exists=create`,
rejects concurrent runs on the same thread, and preserves disconnect
cancellation. Requests without a session and the RAG Chat path remain stateless.

Agent Server owns checkpointing. The Chat graph retains only a bounded recent
suffix of successful user/assistant text pairs (20 turns, 32,000 characters),
then includes them before the current model input. Failed/cancelled node calls
do not append history. Every session input resets transient response, error,
and attachment fields; custom-only streams and unconditional completion events
prevent prior checkpoint values from appearing as a new reply. Attachment
content is not retained in history.

The current UI does not restore sessions after refresh or purge server
checkpoints when deleting a conversation. Runtime storage/retention and the
existing trusted-LAN access boundary remain deployment responsibilities;
public thread access requires authenticated ownership checks. No production
database or cross-session personal memory is added. See
[Chat session memory](chat-session-memory.md) for contracts, limits, validation,
and rollout requirements.


## Sumin Slack file archive and discovery (2026-09-14)

`workflows/sumin` owns a deterministic worker-injected LangGraph for file
collection and mention-driven discovery. Its strict, versioned `SuminTask`
contract lives in `ax-contracts`; reusable Slack file reads, signature checking,
bounded HTTP transfers, and Nextcloud WebDAV operations live in
`ax-integrations`. Existing outbound Slack policy remains the reply boundary.
No model, cross-workflow supervisor, or generic Chat run registration is added.

The separate `apps/sumin` ingress isolates the publicly routable Slack-signed
callback from private Agent Server and operator APIs. It verifies signatures
and request age, restricts workspace/channels, normalizes events, and commits
them to a workflow-owned PostgreSQL inbox before acknowledging Slack.
`apps/workers/sumin.py` independently consumes one task at a time, using
exclusive 360-second leases, token-fenced completion, a 300-second execution
deadline, and five attempts. An opt-in `compose.sumin.yaml` deploys API, worker,
and schema migration against an explicitly configured external PostgreSQL.
All configuration uses `SUMIN_*` keys from `agents/.env`.

Uploads create `<root>/<team-id>/<channel-name>/<file-id>--<filename>` plus
per-event context JSON containing upload text and Slack provenance IDs.
PostgreSQL preserves channel/file path mappings and searchable upload text;
file bytes remain outside graph state in Nextcloud. Conditional uploads verify
identical replays instead of overwriting collisions. Existing channels retain
their original folder after rename; reused channel names fail closed.

Mention searches match filenames and upload-message keywords within the
requesting channel, intersect context matches with live bounded Nextcloud
listings, and return at most ten authenticated Nextcloud file URLs in the
original Slack thread. Nextcloud ACL provisioning is operator-owned; the agent
does not publish shares or copy Slack membership. Historical backfill, file
content/OCR indexing, cross-channel search, deletion synchronization, and
automatic retention cleanup remain outside this capability. Archive replay is
idempotent; Slack replies can repeat after a send/ack crash.

Offline graph, ingress, integration-adapter, and authority tests are provided,
with an opt-in PostgreSQL concurrency/recovery test. Live credentials are
deferred by the user. Database/container and Slack/Nextcloud end-to-end checks
remain deployment gates. See [Sumin](../workflows/sumin/README.md) for the
contract, limits, acceptance criteria, commands, and operational checkpoints.


## Sumin channel membership and discovered identity (2026-09-15)

Sumin now follows bot membership in its configured token's workspace rather
than a static channel allowlist. API and worker discover validated workspace
and bot identity with bounded `auth.test` calls at startup. Identity failure
prevents startup; unsigned requests and other-workspace events remain rejected.
The `SUMIN_SLACK_TEAM_ID`, `SUMIN_SLACK_BOT_USER_ID`, and
`SUMIN_SLACK_CHANNEL_IDS` inputs are retired. Existing and future channels
become eligible when the bot is invited, without restart or configuration edits.

Signed channel events are committed promptly; the worker validates current
`conversations.info` membership before archive/search execution, so removal
blocks queued work. A separate reusable member-aware outbound adapter checks
membership again before each reply and delegates to a request-scoped existing
Slack sender with a reused client. Static outbound policies for other workflows
are unchanged. DMs and group DMs are excluded, and membership is not cached.
Stored workspace/channel identifiers and folder mappings are unchanged; no
database migration is needed. Tests cover discovery, startup readiness, newly
joined channels, revoked membership, and safe replies. Live Slack validation
remains pending operator credentials. See [Sumin operations](../workflows/sumin/README.md).


## Shared agent database configuration (2026-09-15)

Sumin's API, worker, and migration/status/retry CLI now read the shared
`AGENT_DATABASE_DSN` from `agents/.env`. `SUMIN_DATABASE_DSN` is retired with
no fallback, keeping connection selection unambiguous. Agent-specific Slack
and Nextcloud settings retain the `SUMIN_*` prefix. This configuration rename
does not move existing tables or change the database schema; future agents
may reuse the shared connection with their own table ownership. The isolated
`SUMIN_TEST_DATABASE_DSN` remains opt-in for disposable integration tests and
never falls back to the shared runtime database.


## Sumin host-local deployment and Nextcloud trust (2026-09-15)

The opt-in Sumin Compose stack uses Linux host networking to reach the existing
loopback-published PostgreSQL through `AGENT_DATABASE_DSN`. Its HTTP ingress
binds only 127.0.0.1:8093 and still requires a publicly reachable, Slack-signed
callback route. The main default Compose stack does not launch Sumin.

The worker now uses separate Slack and Nextcloud HTTP pools. Optional
`SUMIN_NEXTCLOUD_CA_BUNDLE` selects a trusted PEM file for Nextcloud only; Compose
mounts it read-only (defaulting to the host system CA bundle). Certificate and
hostname verification stay enabled. This supports privately issued certificates
without inheriting the product backend's disabled verification setting.
See [Sumin troubleshooting](../workflows/sumin/README.md#startup-troubleshooting).


## Sumin Socket Mode transport (2026-09-15)

The default Sumin deployment now runs `sumin-events` (`apps.sumin.socket`)
instead of the HTTP API. It authenticates an outbound WebSocket connection
using `SUMIN_SLACK_APP_TOKEN` (`xapp-`, `connections:write`); the existing bot
token still owns identity, file access, and replies. The manifest enables
Socket Mode and no longer declares a callback URL. Event subscriptions remain
required. `SUMIN_SLACK_SIGNING_SECRET` is needed only for the retained optional
HTTP adapter, whose startup rejects a missing secret. No inbound ports are
exposed in the standalone Compose stack.

`ax-integrations.slack_socket` owns the SDK, bounded receive queue, at most four
ingress handlers, post-commit acknowledgements, scrubbed transport logs, and
connection lifecycle. The application injects workflow normalization and
durable enqueue; provider code never imports workflows. Queue failures and
overload remain unacknowledged; existing idempotent task keys handle replay.
Initial connection and disconnected recovery have 30/60-second deadlines;
Compose restarts failed listeners. The worker, channel membership checks, and
archive/search policy remain separate from the transport.

The configured database's missing Sumin tables were initialized with the
idempotent migration. Live checks validated the bot token and host database
connection. Upload validation remains blocked on listener deployment/app-token
setup and a valid Nextcloud certificate: the current local self-signed Nginx
certificate has a hostname mismatch for the configured Tailscale URL.


## Sumin unified root Compose startup (2026-09-15)

The default `nexgent/compose.yaml` includes `agents/compose.sumin.yaml` with
`agents/.env` as the explicit interpolation environment. The standard root
`sudo docker compose up --build -d` now starts Sumin's migration, Socket Mode
listener, and worker under the same `nexgent` project, without additional
files or profiles. Both consumers depend on migration success. Relative build
and service env-file paths resolve against the included agents directory;
shared DSN and Nextcloud CA settings remain in `agents/.env`. Existing Linux
host networking and no-inbound-port behavior are unchanged.

Rendered Compose verification confirmed all three default services, root
project identity, correct build/env paths, and migration dependencies. The
separately selected production Compose file is unchanged. Live Docker startup
still requires operator daemon access, and Slack/Nextcloud setup requirements
remain in force. See [unified startup](../../docs/08-implementation/sumin-unified-compose-startup.md).


## Sumin explicit Nextcloud TLS setting (2026-09-15)

`SUMIN_NEXTCLOUD_VERIFY_SSL` defaults to `true` and accepts only `true` or
`false` (case insensitive). When false, the worker disables certificate and
hostname verification only for its Nextcloud HTTP client and ignores the CA
bundle. Slack retains its separate verified client. The operator requested
`false` in the local `agents/.env`; the example keeps the verified default.
The unified Compose env-file supplies this setting on container recreation.
No database or process boundaries change.


## Sumin editable Markdown archives (2026-09-15)

The archive workflow accepts non-external `snippet` files in addition to
`hosted` files. Both use the existing authenticated, bounded download and
immutable Nextcloud archive path; snippet preview text is never used as file
content. Posts, external files, unknown modes, and mismatched file IDs remain
rejected. This corrects the hosted-only gate for editable text uploads without
changing persistence or deployment boundaries. Regression cases cover UTF-8
Markdown, both download URL fields, duplicate graph execution, and rejected
metadata. Failed events require operator retry after worker deployment.


## Sumin single-workspace folder layout (2026-09-15)

Archive paths now use `<root>/<channel-name>/<file-id>--<filename>` for the
operator's single Slack workspace. Workspace IDs remain in event authorization
and database keys. A transactionally recorded `channel-folders-v2` migration
removes the legacy workspace segment from existing channel and file mappings,
preserving roots and stable channel names. It runs only once; conflicting
unique paths abort the transaction. No Nextcloud objects are moved or deleted,
and completed events are not reset. The operator will clear the old archive
with consumers stopped before deploying. See Sumin's rollout instructions.


## Sumin tables in shared agent schema (2026-09-15)

Sumin persistence moves from `sumin.{events,channels,files,contexts,migrations}`
to `agent.sumin_{events,channels,files,contexts,migrations}` using the unchanged
shared DSN. All runtime, readiness and management queries use the new names.
The startup migration takes a transaction-level advisory lock, rejects
coexisting source/destination tables, prefixes legacy index names, and moves
existing tables in place. Rows, grants, constraints, queue statuses and migration
history are retained; the empty legacy schema is not dropped. Fresh installs
create only the shared-schema tables. Consumers must be stopped during upgrade.
The migration role needs table ownership and CREATE on `agent`; runtime roles
need schema USAGE plus table permissions. Other agent tables and Nextcloud
objects are unchanged. PostgreSQL regression cases cover preservation,
idempotence and conflicts; execution requires an isolated test database.


## Sumin mention-search file attachments (2026-09-16)

Mention search now delivers up to ten matching archived files as Slack
attachments in the original request thread, plus source links. Matching remains
channel-scoped filename/upload-message keywords against live WebDAV results.
A bounded Nextcloud download reads each file sequentially, and the member-aware
Slack adapter checks channel membership before `files_upload_v2`. The manifest
adds `files:write`; operator reinstall and deployment are required. Original
file bytes are retained and archive ID prefixes removed from attachment names.
No content indexing, new persistence, or deletion sync is added. Own-bot events
remain excluded. Upload failure leaves work retryable; partial delivery may
repeat on retry, consistent with existing at-least-once Slack replies.


## Sumin Korean briefing keyword matching (2026-09-16)

The deterministic query parser normalizes Unicode, ignores common Korean
request filler, and expands explicit CEO/briefing Korean-English concepts,
including known Korean particles. Up to eight source tokens expand to at most
24 search terms used for filename and upload-message matching. Quoted phrases
remain literal; channel boundaries and live Nextcloud listing remain unchanged.
No model call, content indexing or temporal filtering is introduced. Regression
cases cover the reported CEO briefing filename, bot-mention removal, ranking,
thread delivery and exclusion of another channel's files.


## Sumin model-directed discovery (2026-09-16)

Superseding deterministic keyword selection and the bilingual alias patch,
Sumin now uses the shared OpenAI-compatible model adapter with a workflow-owned
search skill and validated structured actions. Up to eight actions browse/search
channel metadata, inspect candidates, verify their live Nextcloud availability,
and select attachments or ask for clarification. Tools never accept model-owned
SQL, channels or URLs; only inspected and verified IDs may reach delivery.
The archive path stays deterministic and model-free. Search metadata includes
original filenames, upload-message excerpts, uploader IDs and Slack upload times;
legacy files use clearly labeled first-receipt timestamps where available.
The migration adds nullable metadata columns without fabricating upload times.

Model calls have 20-second deadlines within the existing 300-second task budget.
Results are paginated and bounded; invalid actions consume the same finite budget.
Provider/tool failures are sanitized and use durable retries; no keyword fallback
hides model failure. Request-scoped search state is rebuilt on retry, preserving
the existing at-least-once delivery limitation. No conversational memory, file
content indexing, deletion sync, or additional agent supervisor is introduced.
Metadata is disclosed only to the configured model endpoint; file bytes and
credentials are excluded. Tests cover action gating, query scope, temporal
metadata, missing files, and ambiguous queries. An opt-in synthetic real-model
evaluation measures Korean/English recent-file selection without Slack writes.
