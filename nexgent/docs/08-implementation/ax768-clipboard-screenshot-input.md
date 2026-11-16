# AX768 clipboard screenshot input

Date: 2026-11-13

The AX768 Workflow composer accepts clipboard image files through the native
paste event. Copy a screenshot, focus the request box and press Ctrl+V (or the
platform paste shortcut). The existing thumbnail, popup preview and local OCR /
workflow extraction path handles it just like a file-picker or dropped image.
The English/Korean placeholder now mentions screenshot paste.

Implementation is scoped to `Ax768WorkflowPanel.tsx`. Image items are read from
`clipboardData.items`, with `clipboardData.files` as fallback, and passed through
the existing `addImages` function. It preserves PNG/JPEG/WebP validation, five
image / 50 MB total limits, duplicate detection, running-state guard and stale
extraction cancellation. Ordinary text-only paste is left to the browser. Image
paste consumes the event so accompanying clipboard HTML/metadata is not inserted.
No background clipboard polling, navigator.clipboard permission request, remote
image URL fetching, Tauri capability, server API or workflow contract is added.
Images must actually be copied to the clipboard; this does not find recent
screenshot files on disk.

Validation:

- Chromium composer smoke passed with synthetic ClipboardEvent/DataTransfer
  image files and stubbed OCR/API responses. Checks include attachment creation,
  OCR routing, popup open/close, text-paste default behavior, duplicate/type/count
  guards, file-picker regression and existing extraction states/workflow results.
- 34 focused panel/image-input/extraction tests passed.
- Production TypeScript/Vite build passed with the existing bundle-size warning.
- `CARGO_TARGET_DIR=/tmp/ax768-information-cargo cargo check --manifest-path
  src-tauri/Cargo.toml --offline` passed.
- `npm audit --audit-level=moderate` still reports the same 8 existing findings;
  dependencies were not changed.
- OS-level screenshot clipboard integration on the user's PC was not automated;
  browser validation exercised the actual React paste handler using clipboard
  events. No customer record writes were performed.

Activation: the mounted frontend development server reloads this source change.
Refresh `/agents/ax768` to use it. No Agent Server rebuild is needed for this
frontend-only feature.
