# AX768 unified KakaoTalk workflow API

Date: 2026-11-20 (Asia/Seoul)

## Implemented contract

`/agents/ax768` remains the workbench page. Both workflow panels and the capture
agent's **Run Agent (auto)** use `POST /api/ax768/runs` on the same origin:
`http://192.168.0.18:5173` for this installation.

```json
{"workflow_id":"auto","message":"위치조정/이영희/광명시 OO동 OO로 56","confirmed_name":null}
```

Only `message` is required; `workflow_id` defaults to `auto`. Administrator login,
session cookies, Origin and X-CSRF-Token remain required. The desktop uses
`POST /auth/login`, then `GET /api/me`, then the unified POST, without retrying
an execution attempt. Credentials never enter the workflow or model prompt.

Explicit `device_adjustment_power` and `information_update` selections are also
accepted for the web panels. Existing `{case_id,message}` requests use the same
route and retain their original response contract. The old workflow-specific
endpoints remain compatible. There is exactly one registered unified POST route.

`backend/app/ax768_dispatch.py` owns action aliases and the handler registry.
Automatic location/power requests must have exactly three slash-separated fields:
one explicit action, one Korean target name, and one road-number address, in any
order. Whitespace in an action is normalized. Location aliases include 위치조정,
기기위치조정, 위치변경, 위치점검 and 기기이동. Power aliases include 전원연결,
기기전원연결 and 전원접속. Unknown, missing or multiple actions return
`needs_confirmation` with `workflow_id: null` and perform no upstream work.
Unstructured prose, questions and ambiguous address fields need clarification.
Information updates use an explicit 정보수정/정보변경/정보확인&수정 field and the
existing source-grounded information planner for identity and proposed changes.

Future workflows require a registered handler, aliases, validated receipts and
reply policy on the server. The desktop sends the source text, never chooses a
graph or invents a workflow ID. The common response envelope uses `api_version: "1"`, a workflow ID, status,
`verified` (true only for validated completion), and `response`. Future handlers
using this envelope need no new desktop endpoint or workflow selection logic.
The desktop additionally checks the current device/information receipt shapes.

## Replies and verification

The dispatcher reuses the existing runtime capability/version gates and receipt
validators. Device success requires a fresh connected signal, verified AS handling
(or an allowed no-match skip), and verified member-note storage. Only then does
the API's `response` contain:

```text
[자동 확인]
이영희님 기기 위치변경 후 기기신호 확인 완료입니다.
내용 기재해두었습니다.
감사합니다. :)
```

A verified disconnected signal returns the requested template (including its
신규설치 wording):

```text
[자동 확인]
이영희님 신규설치 기기신호가 아직 확인되지 않습니다.
기기 전원 및 설치 위치 확인 부탁드립니다.
```

Lookup failures, unknown writes and confirmation requests retain their truthful
workflow responses; they are not treated as disconnected or successful. Power
completion uses 전원연결 in the success sentence. All existing structured receipts
remain available to the workbench and desktop validator.

## Capture agent and recovery

`UnifiedWorkflow` is the default worker for **Run Agent (auto)**. It reuses the
screenshot FIFO and source extraction, splits complete incoming messages without
changing their contents, and journals each plan/API attempt/reply before delivery.
It sends server text unchanged, without a generic suffix or local success template.
Multiple responses are joined with blank lines; oversize combined replies are set
aside instead of silently truncating. No Bizgo configuration is required for this
mode. The separate legacy device/Bizgo button remains available.

Queues are scoped to the unified protocol, chat, API destination and account, so
old general-answer captures cannot execute business workflows after an upgrade.
An uncertain/cancelled POST is never retried automatically; a server write can
continue after local Stop, so inspect receipts before manually resubmitting.
No new database, service, model or dependency is introduced.

Settings accept the origin, `/agents/ax768`, or `/api/ax768/runs` URL; authentication
and saved credentials resolve to the origin. Set the administrator username and
password, enable trusted LAN HTTP for the provided origin, and configure the
existing vision LLM. New configs default to 555 seconds for operations; existing
435-second saved configs should be increased to 555 for information updates.
Vite proxy timeout is now 570 seconds, above the longest 540-second server workflow.

## Validation and activation

Verified with mocked external workflow services: 120 backend unified/case/device/info
contract tests, 78 Agent Server device workflow tests, 422 capture-agent tests
(24 skipped, including Windows-only tests), and 45 frontend AX768 client tests.
The capture suite includes screenshot → source extraction → API → exact reply
and continued watching. Capture Python lint and `npm run build` pass. No live Google Sheets,
member-page writes, SMS or KakaoTalk messages were submitted by these checks.
The LAN page returns 200 and an unauthenticated API request returns 401; this does
not prove authenticated runtime deployment or business completion.

Required frontend checks also found unrelated existing issues: `cargo check`
references missing permissions in an old workflow-helper build directory, and
`npm audit --audit-level=moderate` reports 8 vulnerabilities (4 low, 2 moderate,
2 high). Dependencies and unrelated Rust build state were not changed.

From `nexgent/`, activate the packaged Agent Server parser change when Docker
access is available:

```bash
sudo docker compose up -d --build --no-deps agent-server
```

The development backend/frontend bind mounts normally reload source automatically;
if necessary restart just those services with
`sudo docker compose restart backend frontend`. This session could not access the
Docker socket and `sudo -n` required interactive authentication; no container was
rebuilt. The Windows executable also needs a normal Windows build (`.\build.ps1`)
or launch the updated source using `uv run python -m app.main`.

Reproduction commands:

```bash
cd backend
uv run python -m pytest tests/test_ax768_dispatch.py tests/test_ax768.py tests/test_ax768_workflow.py tests/test_ax768_information.py -q
cd ../agents
uv run python -m pytest tests/unit/test_ax768_unified.py -q
cd ../frontend
npm run test -- src/shared/api/ax768WorkflowClient.test.ts src/shared/api/ax768InformationClient.test.ts
npm run build
cd ../../software/kakao-capture-agent
uv run python -m pytest -q
```

Remaining Windows acceptance: configure the server/LLM credentials, select the
intended chat, click **Run Agent (auto)**, and send an authorized real member's
`위치조정/이름/주소` request. Confirm the signal and saved note, the exact server
reply, continued watching, disconnected reply, and no duplicate work after Stop.
The OO address is a format example, not a real member lookup fixture.
