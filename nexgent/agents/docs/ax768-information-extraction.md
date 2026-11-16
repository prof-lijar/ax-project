# AX768 workflow-specific information extraction

Date: 2026-11-12

## Scope and acceptance

The information-update composer uses an agent to discover fields from supplied
text and locally recognized image text. Field names are open-ended: identity,
contact details, relationships, addresses, device IDs, dates, requests, old/new
values and miscellaneous details are examples, not an allowlist. Different
people, sources and conflicting values must remain distinguishable. Extracted
values must be literal source substrings and remain editable. Recognized text remains visible during structuring and retained internally
for reanalysis; uploaded images remain available for visual checking.

The device-adjustment workflow retains its existing deterministic name/address/
action extraction. No workflow selection means no workflow-specific template.
Changing selection invalidates stale extraction and rebuilds from original input.
Information extraction never calls the device workflow or modifies records.

## Implementation

`workflows/ax768/information_extraction.py` defines the version-1
`ax768_information_extraction` graph with one extraction node and no tools. Its
workflow-owned prompt instructs the existing configured local model to discover
all meaningful case fields, preserve relationships and old/new values, mark ambiguity,
and treat source instructions as untrusted data. No model selection, credentials,
external service or dependency changes were made.

The strict input contains `workflow_id: information_update`, extraction version 1
and up to six sources of 1–8,000 characters each. Each output field has a label,
literal value, source index and uncertainty flag. Values must occur verbatim in
the specified source. Output is limited to 200 fields and 56,000 label/value
characters. Duplicate label/value pairs from overlapping chunks are combined only
within the same source; uncertainty is preserved.

The configured model has an 8,192-token context. Extraction uses source chunks of
at most 1,000 characters, prefers line boundaries and overlaps 100 characters
when splitting a long line. At most two model requests run concurrently, with
3,500 output tokens each, no transport retries and a 100-second aggregate
deadline. A sender-assignment violation permits one semantic correction attempt
for that chunk within the same deadline. A
truncated, invalid, ungrounded or failed chunk rejects the whole result. Large or
unusual inputs can still exceed the model/deadline bounds; no partial extraction
is presented as successful.

The product boundary is `POST /api/ax768/workflow/extract` in
`backend/app/ax768_extraction.py`. It requires the existing admin permission and
CSRF protection, validates the fixed workflow and sources, checks the private
assistant's version before dispatch, and revalidates all returned values against
sources. It strips raw graph state from the response. Agent runs are stateless
and deleted on completion; API and browser budgets are 110s and 120s. Browser
abort invalidates results immediately; runtime cancellation after an HTTP
disconnect is best-effort and is bounded by the agent deadline.

The frontend's `ax768WorkflowExtraction.ts` routes by workflow ID. The information
workflow analyses images automatically after local OCR and offers an Analyse &
extract button for text-only requests. Drafts contain field/value lines without filename headings, preserving literal
values and uncertain markers. The input shows before/during/after structuring
status and remains disabled until structuring finishes; raw text remains visible while structuring. Successful empty sources are omitted from the structured draft; original
sources are retained internally. A wholly empty result shows no-case-information
status, with retry and clear still available. The original-text
expander, extra guidance and Extract again button are hidden for information
update at the operator’s request. Analysis errors retain the original/OCR text.
The editable draft allows 64,000 characters to accommodate generated output;
an individual source submitted for analysis is limited to 8,000 characters.

Selecting another workflow cancels the browser request and ignores late results;
recognition already completed can be reused with the newly selected policy.
Removing attachments recomputes using remaining inputs. Image popup behavior is
preserved. Run remains disabled for information update: this change implements
extraction, while lookup/update destinations and write policy await development.

## Validation

- Agent extraction tests: 21 passed; cover schemas, exact grounding, source IDs,
  arbitrary fields, invalid inputs, truncated output, no retry, failure cleanup,
  complete chunk coverage and bounded concurrency.
- Backend extraction and existing workflow API tests: 68 passed; cover
  authentication, CSRF, admin permission, fixed dispatch, version checks,
  limits, literal values and stripping raw state.
- Frontend extraction, image input, panel and workflow client tests: 70 passed.
- Frontend build and desktop cargo check passed. The existing bundle-size warning
  remains. Dependencies are unchanged; previously recorded audit findings remain.
- Browser smoke check (preserved in `frontend/tests/ax768-extraction.browser.cjs`) passed using the
  real composer with synthetic OCR/API fixtures: workflow-specific automatic
  extraction, raw source review, unchanged device template, late-response
  rejection, error preservation, text-only extraction and narrow layout.
- Actual configured-model smoke check (`PYTHONPATH=. .venv/bin/python
  /tmp/ax768-live-extraction.py`) passed with synthetic data: all 11 expected
  facts, including full address, relationship, old/new phone numbers, S/N with
  leading zeros, IMEI, visit date, request and note were retained.
- A second configured-model smoke check (`/tmp/ax768-extraction-chunks.py`)
  preserved all 27 expected synthetic values across chunks and sources, including
  an arbitrary field outside the prompt examples.
- Changed-file Ruff and `git diff --check` passed.
- A broader agent run including the existing unified/device tests stalled after
  48 passing cases and was interrupted. It is not claimed as passing. The new
  extraction suite and targeted frontend/backend regressions completed normally.

To rerun the browser test, make `playwright` available to Node and set
`PLAYWRIGHT_CHROMIUM_PATH` if using a non-default Chromium executable, then run
`node ../frontend/tests/ax768-extraction.browser.cjs` against the dev Vite server.
`AX768_PREVIEW_ORIGIN` defaults to `http://127.0.0.1:5173`.

Browser API fixtures do not prove deployed integration or OCR accuracy. The
agent receives recognized text rather than image pixels; information absent from
OCR cannot be recovered by this step. Grounding verifies literal values, not
semantic label correctness or exhaustive recall. Operators can view the uploaded images and edit the draft. No live customer records were read or written.

## Activation and recovery

Source implementation is complete. Live activation remains blocked in this
session: Docker socket access is denied, including an escalated attempt, and
`sudo -n` reports that interactive authentication is required. This is an OS
permission limitation, not an automatic approval-review rejection.

From the host's `nexgent/` directory, activate the new graph with:

```bash
sudo docker compose -f compose.yaml up -d --build --no-deps agent-server
```

The dev backend/frontend mount their source and reload it. After the Agent Server
is healthy, refresh `/agents/ax768`, select `정보확인&수정` and analyse synthetic
text or an image. Confirm arbitrary fields and structuring status are available, switch
to device adjustment, and confirm its original name/address/action template.
An older Agent Server produces an explicit 409 instead of using another graph.

For recovery, preserve the original text/images, fix the reported runtime/model
issue and use Analyse & extract / Extract again. No business update has occurred
and no mutation replay is involved. Existing execution graphs and their write
policies are unchanged.

## Chat screenshot context correction (2026-11-12)

Issue: the extraction prompt's catch-all rule treated every unclassified OCR
fragment as a field. It also lacked explicit sender/subject and chat timestamp
rules. Acceptance for this correction: omit screenshot artifacts and chat-only
names/times; preserve meaningful body details and literal identifiers; qualify
fields by subject when multiple people appear; retain distinct device/signal
observations and guardian-contact relationships. A successful empty extraction
must not reinsert raw noise into the structured draft.

The prompt now explicitly separates sender/reply metadata from message subjects,
qualifies multi-person labels by subject, emits subject-name and request fields,
and excludes artifacts/chat timestamps. It preserves distinct hardware and signal
observations, guardian relationships, literal phone numbers and meaningful
uncertain language. It does not use an ASCII or keyword blacklist: legitimate
Latin identifiers and business dates/times remain extractable. Explicitly
labeled records retain their full literal values and record identities; similar
wording with different item IDs is not treated as duplicate OCR.

The frontend no longer falls back to raw text when a successful extraction
returns zero fields. Noise-only results show `추출할 업무 정보 없음`; raw input
stays internal for retry, and clear resets it. Mixed data/noise sources display
only their extracted fields. Transport/model failures still preserve raw text.

Reply-header names and explicit body-name lines are supplied as bounded context
hints, not extractable facts. If a returned subject prefix still assigns a known
reply sender without body-name evidence, the workflow requests one correction.
A second invalid assignment rejects the whole extraction. This is separate from
transport retries, which remain disabled. An explicitly named subject can also
be a sender; an explicitly assigned staff role remains valid.

Subject-qualified labels are completed with an explicit name field only when the
same source contains a standalone name-with-honorific line or a labeled name.
Existing name fields are retained, uncertainty is preserved, and source grounding
and output limits are rechecked. Sender headers alone cannot generate a name.

The output contract and grounding validation are unchanged. Semantic cleanup is
model-directed, so OCR context loss and ambiguous role assignments remain limits.
This correction requires rebuilding the Agent Server to load the revised prompt.

Validation for this correction:

- 26 agent unit tests passed, including bounded sender correction, rejection after
  persistent misassignment, direct-evidence name completion, same-person
  sender/subject cases and explicit staff assignments.
- 71 frontend extraction/panel/client tests, production build and desktop cargo
  check passed. Existing bundle-size warning remains.
- Browser regression passed for empty/noise results without raw fallback,
  retry/clear, workflow switching, progress/editing lock and ordinary extraction.
- All four opt-in configured-model evaluations passed: anonymized two-subject
  chat with guardian-add intent, noise-only input, meaningful Latin identifiers
  and business times, and meaningful OCR typos/unusual notes. The initial live
  runs exposed names only in labels and occasional sender-qualified addresses;
  source-backed name completion and the bounded sender guard address those
  observed failures.
- The longer, multi-source configured-model check also passed: all 27 synthetic
  values were retained. Its initial regression exposed over-aggressive duplicate
  collapsing for similar notes with different item IDs; the prompt now explicitly
  preserves full values and identities for labeled records. The same case is
  preserved in the live eval file for future runs.
- Changed-file Ruff and whitespace checks passed. No original customer names or
  phone numbers are stored in the regression fixtures.

Activation was rechecked: `sudo -n docker compose ... ps` still requires
interactive authentication. The revised agent prompt/guard is not activated by
this session; run the host rebuild command above, then reanalyse the image.
