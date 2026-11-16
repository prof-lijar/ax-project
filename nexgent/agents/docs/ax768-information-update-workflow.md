# AX768 information-confirmation and update workflow

Date: 2026-11-12

## Contract and acceptance criteria

`정보확인&수정` now runs independently of the device/signal workflow. The
operator reviews/edits the extracted text and clicks Run. Version 2 searches
울진 → 광명 → 영덕 sequentially, with no region input or selector. The first
uniquely resolved roster supplies the region for subsequent stages and results.
No-match advances; read failure or unresolved same-name ambiguity stops.

User-confirmed scope: update subscriber birthday, subscriber phone and guardian
information. The multiple-row rule applies only to AS: the roster must resolve
to exactly one row in the first matching roster; all `정보확인` AS rows for the identified subscriber are
completed. No signal check is part of this workflow.

Acceptance criteria:

- Old subscriber phone, new subscriber phone and guardian phone remain distinct.
- Name/address/current phone resolve one row through ordered regional roster lookup.
  If insufficient, exact-name `정보확인` AS evidence supplies address/phone to
  disambiguate within that roster. Multiple unresolved roster candidates block all writes; they are not skipped to select someone in a later region.
- For multiple same-name AS cases, match the roster's **pre-update** subscriber
  phone and complete every matching row. AS lookup filters AS구분 and name,
  not the AS region cell: missing region metadata must not drop a matching case.
- A unique AS case can match exact address, provided its nonblank phone does not
  contradict the roster. Clearly different same-name subscribers are skipped;
  unresolved blank/conflicting identity evidence blocks before roster changes.
- Preserve birthday leading zeros and formula columns. Guardian add selects a
  wholly empty slot; it never overwrites another guardian. Replacement requires
  one uniquely matched old guardian phone. Name/relationship-only replacement
  retains the explicitly supplied old phone. An existing identical added phone
  is idempotent; differing relationship/name requires correction.
- AS writes only 진행상태=`처리완료`, 처리결과=`정보확인완료`, and
  처리완료일=today in Asia/Seoul. Confirmed AS absence is a verified skip and
  still permits the member note.
- Master-page lookup requires exactly one exact name/address identity after
  removing only known, whitespace-separated administrative prefixes belonging
  to the resolved roster region. Remaining road/building/unit text must match. Append
  `YYYY-MM-DD [현지관리자 방문] 정보확인/생년월일 380215로 수정` (with phone/
  guardian changes and optional source excerpt). Use an explicit visit date if
  supplied, otherwise today. Preserve existing notes and skip an identical line.
- Recheck identities and edited cells before writes; read back every write.
  A dispatched write with an unverified result is `unknown`, with no automatic
  retry and no dependent-stage execution. Earlier verified receipts remain.

## Implementation boundaries

`information_policy.py` owns a strict, source-grounded one-subscriber change
plan. The existing local model gets no business tools, credentials or sheet
contents. It must reject conflicting/multiple subjects, unsupported edits and
mere observations. All values are literal source substrings; formats and phone
roles are validated. One 90s model call, no retries, 95s outer budget. The
message limit is 8,000 characters; oversized/malformed/truncated responses fail
closed. Extraction still discovers arbitrary fields; execution accepts only the
supported explicit edits. Multiple subscribers must be run separately.

`information_sheets.py` owns fixed layouts, header guards, bounded exact-name
search and cell changes. `information_update.py` registers the version-2 graph
`ax768_information_update`: prepare → roster → AS → member. Node state carries
the validated plan, selected identity, bounded snapshots and independent
receipts. It does not reuse the device workflow's latest-row selection, signal
check, or replacement-note policy. No shared integration or other graph changed.

Live read-only verification on 2026-11-12 confirmed:

| Roster | Birthday | Subscriber phone | Guardian name/phone/relation |
| --- | --- | --- | --- |
| 울진 | E | O | R/S/T, U/V/W |
| 영덕 | E | O | Q/R/S, T/U/V |
| 광명 | E | H | J/K/L, M/N/O, P/Q/R, S/T/U |

The AS sheet's actual date header is **처리완료일** (X), alongside C=AS구분,
I=가입자, K=전화번호, S=진행상태 and Y=처리결과. Every run checks the exact
header coordinates; column drift stops execution. Formula-adjusted birthday/
phone columns are excluded. Writes use literal string cells, except the AS date
which uses a numeric date serial and yyyy-mm-dd formatting. Existing formulas in
target roster cells block a write. Reads scan at most 20,000 rows per sheet,
names-only pages of 1,000 rows, at most three reads concurrently. Matching
rows are reread for name/address/phone (and AS type) in batches of 20. Failed
parallel reads cancel and drain siblings before client shutdown. AS batches cap at 100
matching rows. Missing/full guardian slots block rather than creating columns.

`POST /api/ax768/workflow/information-runs` is admin/CSRF protected, checks
`information_version: "2"` on the private graph before dispatch, and validates
receipt ordering, row counts and verification before returning a minimal result.
It strips private state/context. Server/browser timeouts are 540/555 seconds;
node budgets are 95/240/70/120 seconds. Disconnect continues already-authorized
work; stateless execution deletes the run on completion. No automatic resubmission.

The frontend has a separate typed client and three stage result sections.
Region is returned from the matched roster, and is null when no identity was resolved. Existing image popup, OCR indicators,
editing lock, filename removal and removed copy remain. Extraction never writes.

## Validation

- Live read-only column guards passed for all three rosters and the AS sheet.
- Synthetic local-model checks cover birthday leading zeros, new subscriber
  phone vs identity, guardian add, non-actionable text and multiple subscribers.
  All 5 saved cases passed under `tests/evals/test_ax768_information_update_intent.py`.
- 104 focused agent tests passed. They cover full staged flow, duplicate AS matching, AS absence,
  identity/header drift, formula preservation, guardian slot selection,
  uncertain-write stopping, member ambiguity, append/dedup and exact cell masks.
- 27 information/extraction API tests and 53 existing device API tests passed. They validate admin/CSRF, strict input, fixed graph/version gating,
  minimal output and impossible receipt rejection. 73 frontend tests passed and validate
  receipts and retain extraction/device behavior.
- Chromium smoke uses synthetic OCR/API responses: execution without region input,
  separate information execution and stage results, extraction states, switching,
  empty results, failures and narrow layout. No real business records were edited.
- Frontend production build passed (existing bundle-size warning).
- Tauri passed with `CARGO_TARGET_DIR=/tmp/ax768-information-cargo cargo check
  --manifest-path src-tauri/Cargo.toml --offline`. Default target cache references
  a missing old checkout; isolated cache avoids that unrelated failure.
- Dependency audit still reports 8 pre-existing findings (4 low, 2 moderate,
  2 high); dependency manifests/lockfiles were not changed.

## Activation and recovery

From the `agents/` folder:

```bash
sudo docker compose -f ../compose.yaml up -d --build --no-deps agent-server
```

Activation was attempted but remains blocked by host `sudo` interactive
authentication. The graph is **not claimed active** in the running container.
The backend/frontend source mounts reload the product changes; graph registration
requires the Agent Server image rebuild. Until then Run returns the stale-server
message before dispatch. No new credentials, mounts or services are required.

Run focused checks:

```bash
uv run pytest tests/unit/test_ax768_information_update.py
AX768_LIVE_INFORMATION_EVAL=1 uv run --env-file .env pytest tests/evals/test_ax768_information_update_intent.py
```

Writes across Sheets and the member service are not a transaction. Rechecks
reduce stale-row risk but cannot provide atomic compare-and-swap or cross-tab
locking. Do not replay unknown writes automatically; inspect the reported
roster/AS rows and member notes first. A subscriber-phone change intentionally
leaves AS identity columns unchanged; a later manual replay can require resolving
old/new phone evidence rather than silently associating cases by the new number.
Partial successes are visible; there is no automatic rollback or resume API.
Member notes beyond 2,000 characters block to preserve existing history.


## Startup import fix (2026-11-12)

After the container startup failure was reported, file-based loading reproduced
`ImportError: attempted relative import with no known parent package` in the new
information-update entrypoint. Agent Server loads file graph registrations with
a synthetic module name rather than a Python package context. The earlier
package-import tests did not cover this boundary. The entrypoint now uses
absolute `workflows.ax768.*` imports, matching the existing graph entrypoints.

`tests/unit/test_ax768_graph_registration.py` loads both information graphs from
their actual `langgraph.json` paths using the server's synthetic-name convention
and verifies input/output schemas. These and the information workflow tests
passed (20 tests). A temporary local Agent Server loaded every configured graph;
`GET /ok` and both information assistant schema endpoints returned successfully.
The check executed no graph and was shut down afterward. This verifies local
startup, not the Docker container: Docker socket access and noninteractive sudo
remain unavailable. Rebuild the Agent Server with the activation command above.


## Automatic three-roster lookup (2026-11-12)

The user replaced mandatory room-region selection with ordered lookup. Version 2
accepts only message/version as graph input, and the API no longer accepts a
caller-selected region. Roster lookup is sequential in the existing USER_SHEETS
order (울진 → 광명 → 영덕). Each roster is header-checked before searching.
No matching name/address/current phone moves to the next roster. At the first
candidate set, AS evidence can resolve same-name ambiguity; unresolved ambiguity
or a read failure blocks instead of skipping to a potentially different person.
The resolved region is used for AS-stage roster rechecks and survives partial or
unknown write results. Multiple matching AS rows still use the pre-edit phone.

Validation: 27 agent/registration tests, 13 information API tests and 5 focused
frontend tests passed. Cases cover matches in each position, early stopping, all
three misses, read failures and ambiguity. Chromium verified no region selector,
region-free request dispatch and resolved-region results. Production build and
isolated Tauri check passed; npm audit retains the same 8 existing findings.
Local Agent Server startup/schema checks passed for extraction v1 and update v2.
No customer records were changed. Docker activation was attempted again but host
sudo authentication remains required; run the documented rebuild command above.


## Structured birthday correction (2026-11-13)

The reported `이수교 · 생년월일: 38. 02. 15` failed because the intent prompt
required an explicit 수정 verb and the plan date validator rejected dots/spaces.
The reviewed, subject-qualified birthday field is now an update request. An
exact, complete single-field request is parsed deterministically without a model
call; extra lines, additional edits, multiple subjects or instructions cannot be
silently discarded by that path. Richer requests retain model analysis, with
explicit guidance for subject-qualified fields and literal dotted dates.

Birthday validation accepts compact dates, existing YYYY-MM-DD dates and dotted
YY/MM/DD or YYYY/MM/DD components (dots, optional horizontal spacing and an
optional final dot). It validates the calendar date and preserves the supplied
year width; `38. 02. 15` becomes `380215`, not an inferred four-digit year.
Model/deterministic outputs retain the literal birthday until source grounding
passes. Only then are dotted dates converted to compact strings for roster cells
and notes. Other field grounding, sequential lookup, ambiguity stops and write
gates are unchanged. Input/output graph version remains 2.

Validation: the exact reported request parses to name 이수교 and birthday 380215
without calling a model or business tools. Fifty-two focused birthday, workflow
and file-registration tests passed, covering leading zeros, invalid dates,
source mismatch, extra fields/people, normalized cell values and notes. The
six-case local-model suite passed, including a multi-line qualified birthday/address draft.
No live customer records were changed. Agent Server image rebuild is required
for the policy/prompt changes, using the activation command above.


## Oversized roster-read correction (2026-11-13)

Read-only reproduction of the supplied birthday request found that the first
울진 roster scan exceeded the shared Google Sheets adapter's 128,000-byte
response limit. The scan fetched name, address and phone for 1,000 unrelated
rows at once. The broad roster exception handler replaced this technical cause
with a misleading address/phone/guardian instruction.

Lookup now reads only the name column in bounded pages, then reads details for
exact-name matches in batches of at most 20 rows. Names are reread with details;
identity drift raises an error rather than becoming absence. AS issue filtering
still happens before resolution. Results retain sheet order, all duplicate
matches and the original three-sheet traversal. The shared response-size limit
was not raised. Sibling read tasks are cancelled and drained on any failure or
cancellation so they cannot outlive their HTTP client.

Roster failures now show the failing phase and a safe adapter/policy reason,
including which roster or AS read failed. Validation/shape failures exclude raw
input and record contents. Uncertain dispatched writes retain their warning and
stop downstream stages; the version-2 public receipt contract is unchanged.

Validation: 58 focused read/workflow/birthday/registration tests passed. A fixture
with long Korean addresses exceeds the real adapter limit under the old broad
read and succeeds through names-only scanning. Additional cases cover no-match
without detail reads, duplicate matches, identity drift, sibling cancellation,
AS filtering and safe error reporting. A read-only live replay then traversed
울진 and 광명, found one matching 영덕 row, confirmed no matching information AS,
and passed the birthday update preflight. A mutation guard stopped the operation
before writing: no roster, AS or master-page records were modified.

Agent Server rebuild remains required; host sudo authentication is still needed
for Docker activation. Use the command in Activation and recovery.


## Master-page administrative-prefix matching (2026-11-13)

Read-only investigation reproduced the next failure: login succeeded and member
search returned one exact-name subscriber, but the master address included
`영덕군` while the roster began with the same 읍/면 and road address. The strict
whole-address comparison rejected the record before any note write.

The information workflow now strips only known leading province/municipality
labels for its already-resolved roster region (경북/경상북도 plus 울진군 or
영덕군; 경기/경기도 plus 광명시). Prefixes must be separated by whitespace.
It still requires one exact-name candidate and equal remaining address text;
different regions, building numbers, unit details and multiple equivalent
candidates block. It does not perform arbitrary suffix/substring matching.
The original full master identity is preserved and reread before/after saving.
The standalone/device note policies and shared member adapter are unchanged.

Member-stage receipts now distinguish login, matching, identity refresh, existing
notes, pre-save check, write and readback failures. Locally defined safe adapter/
policy messages are retained; raw validation data is excluded. Dispatched but
unverified writes remain unknown, and earlier Sheets receipts remain visible.

Validation: 99 information, member-note, device-member and registration tests
passed, including administrative-prefix equivalence, wrong-region/building/unit
rejection, duplicate blocking, identity drift and failed-login reporting. A live
read-only replay confirmed one match and passed all checks up to the note PUT;
a mutation guard prevented that PUT. No roster, AS or master-page writes were
performed during diagnosis. Existing notes were read for append validation and
not printed. Rebuild Agent Server to activate the fix; Docker requires host sudo
authentication in this environment.


## Conflicting master address after phone update (2026-11-13)

A subsequent read-only investigation found a true data conflict, not a prefix
variant: the selected Yeongdeok roster address and the exact-name master
candidate's Seoul address differed. The requested new phone was already present
in both records. No valid roster IMEI or attached master device was available
to verify the link. No customer data was changed during diagnosis, and no
previous Sheets step was replayed. Identity clarification is pending; a matching
new phone is not silently promoted to evidence overriding conflicting addresses.

Member resolution now distinguishes no exact-name candidate, multiple matching
candidates, and address conflicts. For one same-name candidate, the bounded
admin-facing error includes its ID and both addresses (at most 140 characters
each) so the operator can resolve the actual discrepancy. This is an error
reporting improvement, not a relaxation of write eligibility. Existing receipts
are preserved. Graph/API version 2 is unchanged.

Forty-eight focused information/registration tests passed, including matching
phones with conflicting addresses, no note write, preserved sheet receipts,
missing candidates and ambiguous identities. Clearer messages need the usual
Agent Server rebuild; rebuilding alone does not resolve conflicting source data.
