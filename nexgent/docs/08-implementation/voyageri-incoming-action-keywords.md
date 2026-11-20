# VoyagerI incoming action keyword filter

Date: 2026-11-20 (Asia/Seoul)

## Behavior

VoyagerI Run Agent (auto) acts only on newly received messages containing the
literal substring `위치조정` or `전원연결`, including their `기기` prefixes.
Outgoing messages and incoming messages without either keyword are ignored without
invoking the workflow API or sending a chat reply. Startup remains silent, and
the UI shows the enabled keywords. Screenshot classification still distinguishes
new incoming messages from outgoing bubbles and screen changes; keywords never
establish direction. Ambiguous direction retains the existing retry/review behavior.

The keyword gate runs before request splitting and again for each complete source
message in mixed batches. A single message containing both actions is ignored
rather than guessing. Saved plans pass the same gate on restart. Combined replies
are rebuilt from per-message receipts so old unrelated replies cannot be replayed;
existing operation claims prevent repeating external actions. Whole messages retain
negations and qualifications for server validation. A keyword authorizes routing,
not a claim of successful completion.

## Unified API

The client uses `POST /api/ax768/runs`, with an explicit workflow and action:

```json
{"workflow_id":"device_adjustment_power","action":"기기위치조정","message":"위치조정/이영희/광명시 OO동 OO로 56","confirmed_name":null}
```

```json
{"workflow_id":"device_adjustment_power","action":"전원연결","message":"전원연결/박철수/울진군 OO면 OO길 78 ","confirmed_name":null}
```

Both actions select the existing 기기위치조정/전원연결 device handler. The backend
canonicalizes slash-separated fields for explicit workflow selection, using the
same grounded parser as auto dispatch. All six action/name/address orders work.
The optional `action` argument preserves compatibility with existing callers.
When supplied, it must match the source's single action and the device workflow;
it cannot override a different action or invent one missing from the message.
Unsupported, ambiguous, cancelled or mismatched slash requests return
needs_confirmation without calling the workflow. Successful receipts must prove
the requested action before a success template is emitted. Existing non-slash
web requests retain their existing validation and workflow handling.

The existing graph receives canonical message text containing the specific action,
for example `울진군 OO면 OO길 78 박철수님 전원연결 신호확인요.`. Its existing
signal, AS, and member-note stages support both actions; no graph changes are needed.

## Server-owned chat replies

On verified power-connection success:

```text
[자동 확인]
박철수님 기기 전원연결 후 기기신호 확인 완료입니다.
내용 기재해두었습니다.
감사합니다. :)
```

When the device signal is not confirmed:

```text
[자동 확인]
박철수님 신규설치 기기신호가 아직 확인되지 않습니다.
기기 전원 및 설치 위치 확인 부탁드립니다.
```

Names come from the verified workflow result. The existing disconnected template
retains its trailing space for compatibility. The desktop sends the returned
`response` unchanged. Location success retains its `기기 위치변경 후` wording.

## No Bizgo SMS for either device action

Both 위치조정 and 전원연결 return their result to KakaoTalk without SMS. The unified
client, API dispatcher and device graph already have no Bizgo send step. The older
separate 기기위치조정/전원연결 desktop button's Bizgo step has now also been removed,
along with its client creation and credential validation. Neither entry point
requires a phone sender, recipient or Bizgo key, even when the generic Test
Workflow's optional SMS setting is enabled.

Old SMS journal receipts remain untouched and are never replayed. The older device
queue retains its legacy identity fields so pending captures remain accessible;
those fields no longer configure an SMS operation. The independent Send Bizgo
Sample and generic Test Workflow SMS tools retain their explicit test behavior.
No additional server change or rebuild is needed specifically for SMS removal.

SMS-removal validation: 123 focused device, unified-workflow, GUI and Bizgo tests
passed. Both business-workflow suites fail if any Bizgo client is created or sends
a message; GUI checks cover enabled SMS settings with missing phone credentials.
Legacy uncertain SMS receipts remain unchanged. Lint and whitespace checks passed.
No live SMS or chat was sent during these tests.

## Rollout

VoyagerI v0.1.0-rc.36 packages these changes. The user authorized the Windows
build and release on 2026-11-20. The release workflow runs native Windows tests
and packaged startup checks before publishing the EXE and SHA-256 manifest.
Update the backend before running the updated client. The existing unified API
graph from rc.34 must already be deployed; this change needs no additional
agent-server graph build.

For the development stack (source mounted and hot-reloaded), from nexgent:

```sh
sudo docker compose restart backend
```

For the production stack, rebuild only the backend using its normal environment:

```sh
sudo docker compose -f compose.prod.yaml up -d --build --no-deps backend
```

## Validation

- Final desktop suite: 460 passed, 24 platform-specific skips on Linux. Tests cover
  both action payloads, outgoing suppression, mixed keyword/chatter batches,
  ambiguous actions, saved-plan filtering, and exact API reply forwarding.
- Backend dispatcher/device suites: 114 passed. They cover six field orders for each action,
  both power-signal outcomes and exact templates, action/source mismatch,
  mismatched completion receipts, cancellation and existing API behavior.
- Lint and whitespace checks passed.
- Upstreams and desktop input are mocked. No live chat, roster, sheet or device
  operations were performed. Screenshot direction still depends on the configured
  vision model; these checks do not prove real-world OCR accuracy.

Reproduce from software/kakao-capture-agent:

```sh
QT_QPA_PLATFORM=offscreen uv run python -m pytest -q
```

Reproduce from nexgent/backend:

```sh
uv run python -m pytest tests/test_ax768_dispatch.py tests/test_ax768_workflow.py -q
```

After deployment, verify in a controlled chat: ordinary incoming text and outgoing
keyword messages must not invoke workflows or reply; an incoming keyword request
for a test record must return the server's signal-result template. No live chat
acceptance check has been performed in this session.
