# Device workflow: first-line general notes and equivalent addresses

Date: 2026-11-19

## Final requested behavior

The clarified target is **일반 사항**, not 설치 정보. The workflow prepends the new dated entry on the first line and preserves the entire existing text after a newline. An identical existing standalone line is not duplicated. Empty notes, Unicode text, CRLF, full-field length, pre-write conflicts and full-field readback retain their verification rules. Member writes still require both name and address. The standalone general-note Test case retains its explicit replacement behavior.

## Reported address mismatch

The supplied request `기기위치조정/왕피길83-15,정영자,기기위치조정 수신확인요` resolved the 울진 roster address `금강송면 왕피길 83-15`, whereas the master address included `울진군`. Exact compacted strings rejected this same location. An authorized read-only member lookup found five results named 정영자; the corrected name/address policy matched exactly one member; no live business record was updated.

The device member writer now uses the existing information workflow's region-bound address equivalence, extracted into `member_address.py`. Only the known province and county/city prefixes for the verified roster region may be omitted: 경상북도/경북 + 울진군 or 영덕군; 경기도/경기 + 광명시. Unicode and whitespace are normalized. The remaining 읍/면, road, house number and suffix must match; a different county, town or house is rejected. Name matching and single-candidate selection remain required. No LLM is allowed to choose an approximately matching house. Actual master addresses remain unchanged and appear in receipts.

The backend also requires the prepend capability before executing browser-originated requests, blocking older runtimes with HTTP 409. Backend and browser receipt validators apply the same region-bound rule, so a valid write is not rejected afterward merely because the master receipt contains the extra prefix. The device workflow advertises `member_note_mode: prepend`; rc.32 checks that capability before execution. The pending rc.31 Windows build was cancelled when the user clarified first-line placement. Older queue plans remain isolated by a new policy key. Workflow version 5, credentials, API destinations and other workflows stay compatible.

## Validation

- Agent tests: **243 passed**, including information-workflow regressions, the supplied Korean cases, the reported address, rejected different houses/counties, preserved existing text and duplicate suppression.
- Backend tests: **75 passed**, including matching receipt normalization and rejection of genuinely different addresses.
- Frontend tests: **57 passed**; TypeScript/Vite production build passed (existing bundle-size warning).
- Backend lint has 15 pre-existing E7 style findings (the same in HEAD); E4/E9/F checks and agent/desktop lint passed.
- The required dependency audit reports the existing **8 findings: 4 low, 2 moderate, 2 high**. No dependency changes were made.
- Rust check initially hit stale cached paths from the old checkout; `cargo check --offline --manifest-path src-tauri/Cargo.toml --target-dir /tmp/nexgent-device-notes-cargo -j 2` passed with a fresh temporary build directory.
- Desktop suite: **404 passed, 24 Windows-only tests skipped in 12.74 seconds**. Windows release verification is in the rc.32 release.

## Activation

Agent Server activation is still pending: Docker access is denied to the current account, and `sudo -n` requires interactive authentication. No live AS/member write was made. The new EXE refuses an old runtime rather than invoking its older note-writing behavior.

On the Nexgent Linux host, build from the tagged source to exclude unrelated local edits, then recreate the development Agent Server used by port 5173:

```bash
cd /home/nextor-ai-02/nextor_ai/ax-project
notes_build_dir=$(mktemp -d /tmp/nexgent-first-line-build.XXXXXX)
git archive kakao-capture-agent-v0.1.0-rc.32:nexgent/agents | tar -x -C "$notes_build_dir"
sudo docker build -f "$notes_build_dir/apps/agent_server/Dockerfile.dev" -t ax-agent-server-dev:local "$notes_build_dir" && sudo docker compose -f nexgent/compose.yaml up -d --no-deps --no-build agent-server
sudo docker compose -f nexgent/compose.yaml exec -T agent-server .venv/bin/python -c 'from workflows.ax768.unified_graph import graph; print(graph.get_input_jsonschema()["properties"]["member_note_mode"])'
```

Expected schema: `const: prepend`. Development backend/frontend use the current source mounts and reload; ensure this checkout's backend and frontend changes are installed too. Production port 5174 uses `compose.prod.yaml`, image `ax-agent-server-prod:local`, and also needs its backend/frontend rebuilt from the updated source because their receipt validators changed. Do not restart a service from an old image after a failed build. Schedule the restart when no workflow is running.

After activation, test a designated member with known existing 일반 사항. Verify the correct name/address, the new line first, all old lines below, and no duplicate on a repeat. Disconnected signals or uncertain AS outcomes must still prevent the member write. The upstream has no conditional-update/ETag contract, so edits racing the final pre-write read remain a limitation; inspect the member record after any uncertain result.
