# AX768 local OCR assets

Tesseract.js and Tesseract.js-core 7.0.0; Korean and English data packages 1.0.0.
Used only by the AX768 Workflow image composer. Images stay in the browser.

Sources (pinned npm tarballs):
- https://registry.npmjs.org/tesseract.js/-/tesseract.js-7.0.0.tgz — dist/tesseract.min.js, dist/worker.min.js and accompanying license notices.
- https://registry.npmjs.org/tesseract.js-core/-/tesseract.js-core-7.0.0.tgz — tesseract-core-lstm.wasm.js (portable non-SIMD LSTM core, embedded WASM).
- https://registry.npmjs.org/@tesseract.js-data/kor/-/kor-1.0.0.tgz — 4.0.0_best_int/kor.traineddata.gz.
- https://registry.npmjs.org/@tesseract.js-data/eng/-/eng-1.0.0.tgz — 4.0.0_best_int/eng.traineddata.gz.

Runtime/core are Apache-2.0; accompanying bundled-dependency notices are included.
Data package wrappers declare MIT (LICENSE.tessdata-naptha); underlying Tesseract
trained data is Apache-2.0 (LICENSE.tessdata). Upstream license sources:
https://github.com/naptha/tessdata and https://github.com/tesseract-ocr/tessdata_best.

Keep versions and paths aligned with ax768Ocr.ts. No CDN fallback is configured.
SHA256SUMS verifies the copied runtime, model and license files. Run
`sha256sum -c SHA256SUMS` from this directory after installing/upgrading assets.
