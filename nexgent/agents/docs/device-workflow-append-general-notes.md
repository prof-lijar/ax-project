# Device workflow: append general notes using name and address

Date: 2026-11-19

The 기기위치조정/전원연결 workflow now requires the resolved roster name and address for the final member lookup and appends `YYYY-MM-DD [현지관리자 방문] 기기위치조정` or `전원연결` to the last line of 일반 사항. Existing text, whitespace, and line endings are preserved; a separator is added only when needed. The matching policy retains exact-name preference and existing unique partial-name support, always constrained by normalized address equality. Ambiguity or mismatch does not write.

`member_note_node` calls the existing verified writer with an internal `append=True` flag. It cannot be selected by message text. The standalone member-note Test case retains its existing replacement behavior. Append requires an explicit address, skips an identical standalone line anywhere in history, and stops before writing if the full result would exceed 2,000 characters. It rechecks identity and the whole old field before writing, then verifies the whole combined field afterward. No automatic write retries are introduced. The upstream still has no conditional-write/ETag contract, so an external edit racing the final read and write remains possible.

The graph retains workflow version 5 and adds `member_note_mode: Literal["append"]` to its input schema as a capability marker. The rc.31 desktop checks this through the authenticated same-origin schema proxy before posting any workflow request; older replacing runtimes are refused. The desktop requires target name, address and one action in each request and uses a new policy-specific queue key so earlier queued plans cannot bypass the new requirements. The returned member receipt still carries only the new entry, not private historical text. The existing backend/browser result validators remain compatible.

## Validation

Focused agent suite: **189 passed**. Desktop suite: **403 passed, 24 Windows-only tests skipped**. Ruff and diff checks passed.

Focused synthetic agent tests cover history preservation, duplicate entries, empty/multiline/CRLF fields, overflow, pre-write conflicts, whole-field readback, both name/address matching, signal/AS gates, and the supplied Korean end-to-end cases. The desktop tests cover missing address and refusal of absent/replacing capabilities without a workflow POST. No live business record was changed.

Run from `nexgent/agents`:

```bash
.venv/bin/python -m pytest -o addopts='' -q tests/unit/test_ax768_member_note.py tests/unit/test_ax768_workflow_member_note.py tests/unit/test_ax768_unified.py tests/unit/test_ax768_supplied_inputs.py --disable-warnings
```

## Activation

Activation is pending: Docker access is denied for the current account and `sudo -n` requires interactive authentication. Run the following on the Nexgent host after installing the committed rc.31 source. It builds from the tagged agent source to exclude unrelated local edits, then recreates only the development Agent Server used by port 5173. It does not execute a business workflow.

```bash
cd /home/nextor-ai-02/nextor_ai/ax-project
append_build_dir=$(mktemp -d /tmp/nexgent-append-build.XXXXXX)
git archive kakao-capture-agent-v0.1.0-rc.31:nexgent/agents | tar -x -C "$append_build_dir"
sudo docker build -f "$append_build_dir/apps/agent_server/Dockerfile.dev" -t ax-agent-server-dev:local "$append_build_dir"
cd nexgent
sudo docker compose -f compose.yaml up -d --no-deps --no-build agent-server
sudo docker compose -f compose.yaml exec -T agent-server .venv/bin/python -c 'from workflows.ax768.unified_graph import graph; print(graph.get_input_jsonschema()["properties"]["member_note_mode"])'
```

Expected capability: `const: append`. Stop if the image build fails; do not recreate from an old image. For production port 5174, use image `ax-agent-server-prod:local` and `compose.prod.yaml` instead. Keep the stopped/restarted service's active jobs in mind when scheduling activation. After activation, use a designated test person with a known existing note; verify matching name and address, retained old text, one new last line, and one success notification. An identical repeat must not append a second copy.
