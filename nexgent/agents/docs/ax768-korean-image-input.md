# AX768 Korean image extraction into the workflow input

Date: 2026-11-10

## Scope and behavior

This feature applies only to the Workflow tab of 운영시트에이젠트 at
`/agents/ax768`, including the development page
`http://192.168.0.18:5173/agents/ax768`. It does not alter other agents' image
uploads, general chat attachments, the Test tab, or the AS execution graph.

Adding or dropping PNG/JPEG/WebP images starts Korean/English OCR automatically.
The existing limit remains five images / 50 MiB total. Recognized information
fills the same editable input as:

```text
이름: 김순옥
주소: 울진북로 164
요청: 기기위치조정/전원연결 신호확인
```

A typed name can combine with an address-only image. Multiple photos can supply
fields for the same person. Name whitespace is compacted; a unique road-address
candidate is normalized. Conflicting names/addresses stay blank instead of
choosing a person. Missing fields and OCR confidence below 65 produce a review
notice. An unchanged conflicting draft cannot run. Low confidence alone does
not force a character edit when the operator has checked that the text is right.
Original typed input and raw OCR text remain available in collapsed details.

Run remains an explicit action with the existing required workflow dropdown.
The UI converts reviewed structured fields to the already supported canonical
request, e.g. `울진북로 164 김순옥님 신호확인요.`; only that text reaches the
existing API. Blank names, duplicate field labels, unknown fields and multiple
road addresses are rejected locally. A blank address with a valid name retains
the workflow's AS-derived name-only behavior. Raw image text cannot choose a
new workflow operation. The extracted request line is descriptive; the selected
workflow determines the action. No upload triggers signal checking or AS writes.

## Implementation and runtime

All new runtime logic is in `frontend/src/features/agents/`:

- `ax768Ocr.ts`: lazy browser OCR engine, preprocessing, progress, timeout and
  cancellation. Images are EXIF-oriented, white-composited, resized to at most
  2600 pixels on the long edge (upscaled at most 2×), converted to grayscale,
  and enhanced with percentile contrast stretching. Source images over 24 MP
  are rejected after decoding. Each image's recognized text is capped at 8,000
  characters; a batch is bounded to 120 seconds. Images run sequentially.
- `ax768ImageInput.ts`: conservative field extraction and conversion into the
  existing text workflow input. This is composer policy, not a new agent graph.
- `Ax768WorkflowPanel.tsx`: automatic extraction, editable structured input,
  compact progress/retry/raw-text UI, and handling of stale results.

Clear, image removal, replacement batches and unmount invalidate old extraction
generations and abort their result. Existing workers are terminated; a worker
which finishes initializing after cancellation is terminated then. Clear/removal
cannot be overwritten by a late OCR result. Generated text from a removed image
is discarded when still unedited; deliberate user edits are preserved. A failed
batch preserves existing input and blocks Run while unprocessed images remain;
retry or remove the attachments to use the text-only path.

Tesseract.js 7.0.0, its matching portable LSTM core, and Korean/English trained
data 1.0.0 are pinned under `frontend/public/ocr/tesseract-7.0.0/` (about 8.3 MiB).
They load only when the AX768 image composer is used. Explicit same-origin paths
avoid runtime CDN dependencies and images stay in the browser. The directory
includes source URLs, licenses, bundled dependency notices and SHA-256 hashes.
No npm dependency installation, backend configuration, new credential or Agent
Server rebuild is required for this feature.

Automatic Tesseract deskew is deliberately disabled: a real browser experiment
rotated a straight Korean address by 0.3 radians, reducing `영덕군 영덕읍
영덕대게로 699` to Latin noise. With deskew disabled the same fixture read
correctly at confidence 93. EXIF orientation correction remains enabled.

Upstream API/local-asset references:
https://github.com/naptha/tesseract.js/blob/master/docs/api.md and
https://github.com/naptha/tesseract.js/blob/master/docs/local-installation.md.
Package versions, rather than these moving documentation branches, determine
the shipped runtime; relevant behavior was also verified in the package source.

## Validation

- 74 focused frontend tests passed, including structured extraction for the
  supplied names/addresses, spaced names, typed-name/photo-address merging,
  conflicts, low confidence, unknown fields, and ignoring image instructions.
- TypeScript checking and production build passed. The existing bundle-size
  warning remains. Public OCR assets are copied into the production output.
- Real Chromium OCR read a synthetic low-contrast Korean image into
  `김순옥 / 울진북로 164`, merged typed `지영희` with an address-only photo,
  and combined two images containing `김   영호` and `영덕대게로 699`.
- Browser checks covered explicit Run, canonical text-only request payload,
  removal cancellation, corrupt-image failure/clear recovery and a 390px layout.
- The repository smoke script passed on the exact development URL above using
  real OCR and mocked account/product APIs. Zero external image uploads and no
  real workflow executions, device signal requests or AS writes occurred.
- Applied to both the isolated worktree and the primary development frontend.

Repeat from `frontend/`:

```bash
npm test -- src/features/agents/ax768ImageInput.test.ts src/features/agents/Ax768WorkflowPanel.test.tsx src/features/agents/Ax768WorkbenchPage.test.tsx src/shared/api/ax768WorkflowClient.test.ts src/shared/i18n/i18n.test.tsx
npm run build
cd public/ocr/tesseract-7.0.0
sha256sum -c SHA256SUMS
```

Optional browser validation (requires Playwright, Chromium and a Korean font,
e.g. Noto Sans CJK KR). The script mocks product APIs, including workflow Run:

```bash
AX768_OCR_URL=http://192.168.0.18:5173 node scripts/ax768-ocr-smoke.mjs
```

Set `PLAYWRIGHT_MODULE` to an installed Playwright module path and
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` to an installed browser executable when needed.
`AX768_OCR_ARTIFACTS` controls screenshot/fixture output (default
`/tmp/ax768-ocr-artifacts`). Additional local multi-image/corrupt-image validation
was run with `/tmp/ax768-ocr/browser-cases.cjs` against the isolated Vite preview.

## Limits and follow-up

These checks use synthetic printed Korean fixtures, not actual customer photos.
Handwriting, blur, strong perspective, missing orientation metadata, unsupported
address formats or OCR character errors can require manual correction. Only
one subscriber is supported per run; multiple conflicting people need to be
separated or corrected. The operator should review extracted fields before Run.
The existing AS lookup failure reported in the conversation is a separate issue;
this input feature does not diagnose or repair it.
