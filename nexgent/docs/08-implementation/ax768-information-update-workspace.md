# AX768 information update workspace

Date: 2026-11-12

`정보확인&수정` (`information_update`) is selectable in the AX768 Workflow
composer for development. Operators can prepare text and image inputs. The panel
disables Run for this selection until
its execution logic is implemented. Other planned workflows remain disabled.

The existing client and backend execution guards remain in place: selecting this
workspace cannot dispatch the device adjustment/power workflow. No graph,
API, persistence or deployment boundary changes are introduced.

Validation (run from `frontend/`):

- `npm test -- src/features/agents/Ax768WorkflowPanel.test.tsx src/shared/api/ax768WorkflowClient.test.ts`: 39 tests passed, including enabled selector markup and rejection before fetch for unimplemented workflows.
- `npm run build`: passed; existing bundle-size warning remains.
- `npm audit --audit-level=moderate`: reports 8 existing dependency vulnerabilities (4 low, 2 moderate, 2 high); dependencies were not changed in this task.
- `CARGO_TARGET_DIR=/tmp/ax768-information-cargo cargo check --manifest-path src-tauri/Cargo.toml --offline`: passed after allowing Tauri to generate its build assets.
- `git diff --check`: passed.
- The running LAN Vite server serves `information_update` with `available: true`.
- Browser interaction was not exercised; manual check: select `정보확인&수정`, confirm the editable request and disabled Run, then switch to `기기위치조정/전원연결` and confirm Run is available.

The development Vite service mounts frontend source, so this change requires no
Agent Server restart. Refresh `/agents/ax768` and select `정보확인&수정`.

Next: define business-record lookup/update targets and write verification policy before implementing record changes.

Update (2026-11-12): removed both the device-processing guidance and information-update development notice from the composer at the operator’s request. Removed their unused translations and the Run button’s reference to the deleted description. Workflow selection and execution behavior are unchanged.

## Uploaded image overlay (2026-11-12)

Click an uploaded thumbnail in the AX768 Workflow composer to open its image in
a viewport-sized native modal dialog. The filename and X close button remain
visible above the contained image. X or Escape closes the preview; native dialog
behavior contains keyboard focus and restores it to the thumbnail on close.
The preview reuses the existing local object URL, which is revoked when the
attachment is removed. It does not upload the image or dispatch a workflow.
Broken image thumbnails cannot open a preview. The separate thumbnail removal
button keeps its existing behavior.

Validation:

- `npm run build`: passed (existing bundle-size warning).
- Existing panel/client test suites: 39 tests passed.
- `CARGO_TARGET_DIR=/tmp/ax768-information-cargo cargo check --manifest-path src-tauri/Cargo.toml --offline`: passed.
- `node /tmp/ax768-image-overlay-check.cjs`: passed in Chromium at 1280×900 and 390×700, using the actual Vite panel with OCR stubbed and workflow API calls blocked. Verified image loading and viewport bounds, click/Enter opening, X/Escape closing, native modal focus behavior and focus restoration, and attachment removal; no browser errors.
- `git diff --check`: passed. Dependency files are unchanged; the earlier audit findings still apply.

Manual verification: attach an image in `/agents/ax768`, click its thumbnail,
close with X, reopen and close with Escape. The browser smoke check isolates the
composer and does not exercise authentication or OCR.

## Workflow-specific agent extraction (2026-11-12)

Information update now discovers open-ended data fields from typed requests and
locally recognized image text through its own agent graph. Uploaded images are
automatically analysed for the selected workflow; the Analyse & extract button
also handles text-only input. Generated fields are editable, and full raw sources
remain available for checking. Values retain source identity and literal text.

Device adjustment keeps its existing extraction rules. Without a selection,
recognized text remains raw. Changing the workflow cancels the current browser
request and invalidates stale results. The existing image popup is preserved.
Run remains disabled for information update because record changes are not yet
implemented; Analyse & extract is the available operation.

See [extraction architecture, validation and activation](../../agents/docs/ax768-information-extraction.md).
The dev Agent Server must be rebuilt to register the new graph. This session
could not activate it: Docker socket access is denied and sudo requires
interactive authentication. Frontend/backend source changes are mounted live.

## Structuring progress and clean output (2026-11-12)

Structured information now contains only field/value lines, without filename or
input-source headings. Filenames remain in the attachment and original-text
review. A status next to the input shows before structuring, extraction,
structuring in progress, completion/editability or failure. The original text
remains visible while structuring; the textarea stays disabled and busy until
the request finishes. Completion displays the structured text and restores
editing. The original-text expander is labeled as the before-structuring view.

Validation: frontend build, 70 focused tests, desktop cargo check and diff whitespace check passed. The browser smoke test held an extraction response to verify that raw text stays visible, the structuring spinner/status is present and editing is disabled; after completion it verified the success indicator, filename-free output and restored editing. Before-structuring state, original-text review, failure handling and workflow switching also passed. This is a frontend-only update and needs no Agent Server rebuild.

## Information extraction UI cleanup (2026-11-12)

Removed the agent-analysis guidance, Extract again button and original-text
expander from information update at the operator's request. Structuring status,
editing lock and Analyse & extract remain. Original inputs are retained internally
for reanalysis and workflow switching. Other workflows keep their existing OCR
controls. Empty information-extraction panels are no longer rendered.

Validation: frontend build, 11 focused tests, browser workflow/structuring checks and diff whitespace check passed. The browser confirmed all three requested items and the empty panel are absent from information update.

## Chat screenshot data cleanup (2026-11-12)

Information extraction now separates message subjects from sender/reply headers,
keeps fields for different people subject-qualified, and filters OCR/interface
noise and chat-only timestamps. Explicit names and add/change requests remain
case data, as do separate device-status and signal observations. Legitimate
Latin identifiers and business times are not filtered by character set.

Successful empty extraction no longer inserts the raw source into the structured
output. The UI shows `추출할 업무 정보 없음`, retains the source internally for
retry, and keeps clear available. Empty sources in a mixed batch are omitted.
Model/API errors still retain raw input. The model prompt requires an Agent
Server rebuild; the frontend changes reload from the source mount.

Validation and runtime activation are recorded in
[the extraction document](../../agents/docs/ax768-information-extraction.md).


## Information update execution (2026-11-12)

Run is now enabled for `정보확인&수정`. The operator selects the Kakao room's
region, reviews the structured draft, then runs the separate version-1
information workflow. This supersedes the development-only execution guard above.
There is no Kakao API connection; room region is an explicit selector.

Supported edits include birthday, subscriber phone and guardian information.
Old subscriber phone is distinct from new/guardian numbers. Resolve exactly one
regional roster row, optionally using matching information-confirmation AS
evidence; complete every AS row with the same subscriber identity and phone;
then append a dated information-update note while preserving master-page history.
AS absence skips that stage. Ambiguous roster identity, full guardian slots,
changed headers/rows, or unverified writes stop dependent stages. Each stage has
its own verified/blocked/unknown receipt. Multiple subscribers are run separately.

Implementation and fixed column mappings are documented in
[the agent workflow contract](../../agents/docs/ax768-information-update-workflow.md).
The admin/CSRF API is `/api/ax768/workflow/information-runs`; it checks graph
version before dispatch and excludes private snapshots from product output.
Existing device execution, extraction indicators, image popup and removed text
remain as implemented.

Validation: 104 focused agent tests, 27 API/extraction tests, 73 frontend tests,
5 saved live-model intent evaluations, browser smoke, frontend build and isolated
Tauri cargo check passed. Live read-only header guards passed for all three
rosters and AS. Real customer records were not changed during testing. Existing
npm audit reports 8 findings; dependencies were not changed. The default Tauri
cache refers to an old checkout; `/tmp/ax768-information-cargo` passes.

The Agent Server rebuild was attempted but `sudo` requires interactive host
authentication. Runtime activation is still pending. From `agents/` run:

```bash
sudo docker compose -f ../compose.yaml up -d --build --no-deps agent-server
```

Backend/frontend source mounts reload automatically. The new graph is rejected
with a restart message until that image rebuild finishes. No new service or
credential configuration is needed. Do not replay an unknown write without
checking the affected records; cross-service writes are not transactional.


## Agent Server startup correction (2026-11-12)

The new graph entrypoint used relative imports, which fail under Agent Server's
file-based graph loader (`attempted relative import with no known parent
package`). Changed the entrypoint to absolute workflow imports. Added a
registration regression that loads both information graphs using the actual
configured file paths and synthetic module names. Twenty registration/workflow
tests passed. A temporary local Agent Server loaded all configured graphs and
passed `/ok` plus both information assistant schema checks without executing
workflows. Container verification remains pending because Docker requires host
sudo authentication; rerun the documented Agent Server rebuild command.


## Automatic region lookup supersedes region selection (2026-11-12)

Removed the Kakao-room region selector and required-region error. Information
workflow v2 searches 울진 → 광명 → 영덕 sequentially and stops at the first
uniquely resolved roster. No-match advances; unresolved ambiguity/read failures
block. AS fallback and pre-edit phone matching remain. The API accepts no region
and returns the resolved region (nullable before identification). The API gates
v2 to prevent dispatch to the previous region-required runtime.

Validation: 27 agent/registration, 13 information API and 5 focused frontend tests
passed. Browser smoke verified execution without region input. Production build,
isolated Tauri check and local server/schema checks passed; the dependency audit
retains 8 existing findings. No live customer writes were made. A Docker rebuild
is required; the attempted rebuild is blocked by interactive sudo authentication.
Use the Agent Server rebuild command recorded above from the agents folder.


## Structured dotted birthday input (2026-11-13)

Fixed the reported `이수교 · 생년월일: 38. 02. 15` rejection. The reviewed
subject-qualified birthday field now expresses update intent without a separate
수정 verb. A complete single-field request parses directly; richer drafts keep
model analysis. Literal source grounding precedes calendar-checked normalization
to `380215`, preserving leading zeros and the original year width. Both roster
updates and master notes use the normalized birthday. The original request now
passes without requiring an address or phone at the parsing step; sequential
identity lookup and ambiguity guards still apply before writes.

Fifty-two focused parser, workflow and registration tests passed. Validation
uses mocked business tools; no subscriber records were modified. Policy/prompt
changes require the Agent Server rebuild command already documented above.


## Roster response-size failure (2026-11-13)

A read-only replay found the reported roster-stage failure was the Sheets
128,000-byte response limit: reading 1,000 names, addresses and phones at once
failed on the first roster. The generic error wrongly suggested missing input.
Changed lookup to scan names only, then fetch exact-match details in batches of
20. Identity is reread, duplicates and ordering are preserved, and failed reads
cancel/drain concurrent siblings. The shared transport size limit is unchanged.
Roster errors now retain the failing phase and safe reason, without raw records
or validation input. No frontend/API contract changes are needed.

Fifty-eight focused tests passed, including a long-address response-limit
regression through the real adapter, cancellation cleanup and error reporting.
Live read-only preflight found the supplied subscriber uniquely in 영덕, found
no matching information AS, and reached the birthday write boundary; an explicit
mutation guard stopped before saving. No customer record was changed. Rebuild
Agent Server with the documented command; Docker activation needs host sudo
authentication in this environment.


## Master-page address prefix mismatch (2026-11-13)

Login and subscriber search succeeded, but the master address included 영덕군
and the roster address did not. The previous exact-address check blocked before
saving general notes. Information-update matching now ignores only known
leading province/municipality labels for the resolved roster region. Remaining
road/building/unit text and name must match, with exactly one eligible member.
Original full member identity is still checked before/after writes.

Member errors now show the specific phase/cause; verified Sheets receipts remain
visible and uncertain writes are not retried. No product API schema or other
workflow policy changed. Ninety-nine focused information/member/registration
tests passed. A live read-only check passed all member-note preflight checks and
was explicitly stopped before PUT; no customer record was changed or earlier
Sheets stage repeated. Agent Server rebuild is required, with host sudo access.


## Conflicting address after subscriber phone update (2026-11-13)

The next reported case has genuinely different roster/master addresses rather
than an administrative-prefix difference. Read-only checks confirmed the
requested phone is already present in both records, but no usable IMEI/device
link exists to resolve the conflict. No customer data or earlier workflow stage
was changed during diagnosis. Identity clarification remains pending.

Improved member errors to distinguish missing/ambiguous candidates and expose
bounded ID/address evidence for a single same-name address conflict. The new
phone does not bypass identity checks. Forty-eight focused workflow/registration
tests passed; note writes remain blocked for the conflicting fixture and earlier
Sheet receipts remain visible. Activating this message change needs the usual
Agent Server rebuild; rebuilding is not a fix for the conflicting record data.
