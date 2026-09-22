# Chat Math Rendering

Date: 2026-09-22

## Implementation

Chat answers previously displayed LaTeX source such as `$x$`, `$\frac{a}{b}$`,
and `$\rightarrow$` literally because the renderer only handled standard
Markdown and GFM. `ChatMarkdown` now parses `$...$` inline math and `$$` block
math using `remark-math`, then renders it through `rehype-katex`.

KaTeX is configured for native MathML output. This preserves mathematical
structure for browser layout and accessibility without adding remote styles,
fonts, scripts, or CSP exceptions. See the supported output modes in the
[KaTeX options documentation](https://katex.org/docs/options.html).
Model-provided math uses `trust: false`, bounded macro expansion, and bounded
explicit sizes. Raw HTML remains disabled by the existing Markdown pipeline.

Formulas render inside paragraphs, lists, and GFM tables. Display equations get
spacing and a horizontally scrollable wrapper. Inline code and normal fenced
code preserve dollar signs literally. Escaped dollar signs (`\$`) represent
currency; unescaped paired dollars are interpreted as math. Unfinished streamed
expressions and invalid LaTeX fall back to readable source rather than crashing.
Copy-message behavior continues to copy the original Markdown source.

Dependencies and the npm lockfile include `remark-math` and `rehype-katex`.
The prior uncommitted history-race fix is retained independently.

## Validation

Passed from `frontend/`:

```bash
npm run build
npm test
CARGO_TARGET_DIR=/tmp/nexgent-cargo-check cargo check --manifest-path src-tauri/Cargo.toml
npm audit --audit-level=moderate
git diff --check
```

All 287 tests passed and the audit reported zero vulnerabilities. Regression
coverage includes the reported SAT formulas, inline variables, fractions,
powers, text commands, arrows, tables, block equations, code/currency literals,
partial streaming, malformed formulas, and blocked math link/image commands.

All 19 Chromium checks in `scripts/chat-streaming-ui-smoke.mjs` passed, including
native MathML namespace, stacked-fraction geometry, and display equations.
Use a fresh Vite process for the browser fixture:

```bash
npm run dev -- --host 127.0.0.1 --port 5189
CHAT_UI_URL=http://127.0.0.1:5189 PLAYWRIGHT_BROWSERS_PATH=/tmp/nexgent-chat-ui-tools/browsers PLAYWRIGHT_MODULE=/tmp/nexgent-chat-ui-tools/node_modules/playwright/index.mjs node scripts/chat-streaming-ui-smoke.mjs
```

## Limitations and Follow-up

Rendering relies on native MathML and the webview's math fonts. Chromium was
verified; native Tauri visual verification was not performed. Run
`npm run tauri:dev` and open a saved answer containing SAT formulas to verify
the installed WebKit version. No live model request was needed for these checks.
The supported delimiters are dollar delimiters; bare `\(...\)` and `\[...\]`
are not normalized. Formulas can reflow when closing delimiters arrive during
streaming.

The renderer increases the production JavaScript bundle from approximately
545 kB to 820 kB (164 kB to 248 kB gzip). Vite's existing over-500-kB warning
remains. A separate lazy math bundle is a possible future loading optimization.

## Docker Dependency Refresh

Date: 2026-09-22

The Docker development frontend mounts a separate named volume at
`/app/node_modules`. Installing these packages on the host does not update that
volume while its container is running. The lockfile-aware entrypoint synchronizes
dependencies at container startup. A running container can therefore show
`Failed to resolve import "remark-math"` after hot-reloading the changed source.

From `frontend/`, rebuild/recreate only the frontend, then reload the browser:

```bash
sudo docker compose -f ../compose.yaml up --build -d --no-deps frontend
sudo docker compose -f ../compose.yaml exec -T frontend npm ls remark-math rehype-katex
```

Host package resolution was confirmed (`remark-math@6.0.0`,
`rehype-katex@7.0.1`). Container refresh and verification could not be performed:
Docker socket access was denied, including outside the sandbox, and noninteractive
sudo requires authentication. The commands above remain to be run by the host
operator. No dependency volumes need to be deleted.
