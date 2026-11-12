# Device adjustment and power connection: three-stage workflow

Date: 2026-11-11

## Scope and acceptance criteria

Refactor the existing AX768 `기기위치조정/전원연결` workflow into input
preparation, three processing stages, and a result. Preserve existing local
changes, the version-5 product contract, sheet columns, credentials, and
verified-write policy.

| Step | Required behavior |
| --- | --- |
| Input | Text or local Korean/English OCR supplies a name and optional address. Name-only input resolves the bottom-most exact-name AS row's address before signal processing. |
| 1. 신호확인 | Search 울진 → 광명 → 영덕 rosters sequentially, stopping at the matching person. Recheck identity and read IMEI from AA/W/Z respectively; check the existing dev-check admin signal API. |
| 2. AS 시트 반영 | Only after a fresh connected signal, update the matching AS row and verify readback. A confirmed missing row skips this write and continues to stage 3. |
| 3. 마스터페이지 일반사항 | Replace the matching member's general notes using the existing visit-note format and verify readback. Return the cause of missing/ambiguous members or failed/uncertain writes, preserving earlier results. |
| Result | Every branch reaches a final result step; unexecuted dependent stages have an explanation. No overall completion is emitted between stages 2 and 3. |

Missing roster/device, disconnected device, stale signal, or signal error stops
both writers. AS authorization/transport errors and uncertain writes still
stop the member step. They are distinct from a confirmed absent AS row.
Name-only requests with no AS row cannot resolve a device safely and ask for
an address before stopping.

## Implementation and decisions

- `unified_graph.py` uses named signal/AS routing functions and a final `result`
  node. Both routing and writer entry gates use verified stage receipts.
  `workflow_member_note.py` owns the shared signal predicate and the AS-to-member
  gate. A verified AS update remains `running` until member completion.
- Finalization preserves all receipts, fills skipped signal/AS reasons, and
  adds a notice explaining dependent work skipped. Member outcomes identify
  `마스터페이지 일반 사항` before the existing cause text.
- The frontend now groups roster details and signal evidence into stage 1,
  AS lookup and write verification into stage 2, and member notes into stage 3.
  Existing expandable receipts, source links, and responsive styles are reused.
- Image preprocessing preserves a recognized `기기위치조정` or `전원연결`
  action in the editable request and canonical text payload. Previously the
  generated draft displayed both actions and serialization discarded them.
  Conflicting actions require correction; an absent action is not invented.
  Standalone action lines are excluded from person-name candidates.
- General notes remain `YYYY-MM-DD [현지관리자 방문] <action>`. An explicit
  request action takes precedence; otherwise verified AS Y supplies the action.
  Without either, the member step reports the missing action. AS S/X/Y write
  rules and full-field general-note replacement remain unchanged.
- No schema field, process, dependency, automatic retry, or deployment change.
  Workflow version remains 5 because existing requests and receipts stay valid.

## Validation

- 223 focused agent tests passed, covering parsing, ordered searches,
  bottom-most AS address selection, IMEI/signal validation, AS write/readback,
  and member replacement. Five added synthetic HTTP cases exercise missing AS
  with/without a missing member and a device-not-found response. They assert
  actual call order and absence of disallowed writes.
- 92 backend contract tests and 74 frontend tests passed. Six new frontend
  cases exercise action preservation, typed-text/image combination, conflicting
  actions, and name-only image input.
- TypeScript/Vite production build and offline Cargo check passed. Vite still
  reports its existing large-bundle warning.
- Required `npm audit --audit-level=moderate` reports 8 findings (4 low,
  2 moderate, 2 high) in existing dependencies. No lockfile or dependency changed.
- Chromium smoke passed against the temporary preview: exactly three stages,
  adjustment completion, structured power-connection input with no AS row,
  uncertain member writes, disconnected/skipped member work, and 390px layout.
  Screenshots: `/tmp/ax768-refactor-browser/` (desktop and mobile inspected).
- Actual Korean OCR passed using a synthetic image containing name, address,
  and `전원연결`. The submitted canonical request preserved all three; image
  removal cancelled stale extraction. Product APIs were mocked and there were
  zero external image uploads. Artifacts: `/tmp/ax768-refactor-ocr/`.
- Ruff and `git diff --check` passed.

Repeat from `agents/` with dependencies installed:

```bash
uv run pytest tests/unit/test_ax768_unified.py tests/unit/test_ax768_supplied_inputs.py tests/unit/test_ax768_workflow_member_note.py tests/unit/test_ax768_member_note.py tests/unit/test_ax768_as_update.py tests/unit/test_ax768_imei.py -q
uv run ruff check workflows/ax768/unified_graph.py workflows/ax768/workflow_member_note.py tests/unit/test_ax768_supplied_inputs.py
```

From `backend/`:

```bash
.venv/bin/python -m pytest tests/test_ax768_workflow.py tests/test_ax768_member_note.py tests/test_ax768.py -q
```

From `frontend/`:

```bash
npm test -- src/features/agents/ax768ImageInput.test.ts src/features/agents/Ax768WorkflowPanel.test.tsx src/shared/api/ax768WorkflowClient.test.ts src/shared/i18n/i18n.test.tsx
npm run build
cargo check --offline --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
AX768_TEST_URL=http://127.0.0.1:5173 node scripts/ax768-workflow-member-note-smoke.mjs
AX768_OCR_URL=http://127.0.0.1:5173 node scripts/ax768-ocr-smoke.mjs
```

This worktree had no installed environments. Python checks used the existing
primary-checkout interpreters with workspace package paths explicitly set.
Frontend checks used a source/dependency copy at `/tmp/ax768-refactor-frontend`;
the preview used port 5183. Async tests and Chromium required sandbox escalation
for local sockets/processes. Initial sandboxed async tests were interrupted and
rerun successfully outside the sandbox.

The browser scripts used the available Playwright installation and Chromium:

```bash
export PLAYWRIGHT_MODULE=/tmp/ax768-browser/node_modules/playwright/index.mjs
export PLAYWRIGHT_CHROMIUM_EXECUTABLE=/home/nextor-ai-02/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome
AX768_TEST_URL=http://127.0.0.1:5183 AX768_TEST_ARTIFACTS=/tmp/ax768-refactor-browser node scripts/ax768-workflow-member-note-smoke.mjs
AX768_OCR_URL=http://127.0.0.1:5183 AX768_OCR_ARTIFACTS=/tmp/ax768-refactor-ocr node scripts/ax768-ocr-smoke.mjs
```

## Activation and limits

Initially implemented and validated in the Codex worktree. On 2026-11-11, at
the operator's request, the scoped refactor was applied to the primary checkout
at `/home/nextor-ai-02/nextor_ai/ax-project` on `master`, preserving existing
commit `5e75e2e` and its UI changes. Changes remain uncommitted for review.
Agent Server still requires the rebuild below. No real subscriber, AS, or member
record was changed during validation.

Rebuild Agent Server from the primary checkout's `nexgent/` directory; the
development frontend uses source reload:

```bash
sudo docker compose -f compose.yaml up -d --build --no-deps agent-server
sudo docker compose -f compose.yaml logs --tail=80 agent-server
```

Remaining live verification requires an operator-selected real service request
because it writes AS and general notes. With approved test data and configured
credentials, run from `agents/` (replace the illustrative name/address):

```bash
uv run python -m apps.ax768.run --workflow "왕피길83-15,정영자,기기위치조정 수신확인요"
```

AS and member updates remain separate operations without rollback. Inspect both
records before rerunning an uncertain result. OCR remains editable and local;
it cannot establish correctness of arbitrary photographs or disambiguate two
people automatically. The flow still accepts one person per run.

## Primary checkout integration verification (2026-11-11)

Applied only this refactor's 13 files to the operator's primary `master`
checkout, preserving commit `5e75e2e` and unrelated UI changes. No commit, push,
branch switch, or Docker rebuild was performed. `git status --short` reports
12 modified files and this new document.

Revalidated directly in that checkout: 223 agent tests, 74 frontend tests,
Ruff, the TypeScript/Vite build, and `git diff --check` passed. Chromium smoke
passed against `http://192.168.0.18:5173/agents/ax768` with mocked APIs for all
product operations, confirming that the serving frontend now displays the
three-stage UI. Screenshots are in `/tmp/ax768-master-browser/`. Agent Server
still needs rebuilding before the changed graph runs in Docker.

The default Cargo target cache referenced a removed `workflow-helper` directory.
The check passed with an isolated cache, without changing Rust source:

```bash
CARGO_TARGET_DIR=/tmp/ax768-ui-refactor/cargo-target cargo check --offline --manifest-path src-tauri/Cargo.toml
```

The dependency audit still reports the same 8 existing findings; no dependency
or lockfile was changed.
