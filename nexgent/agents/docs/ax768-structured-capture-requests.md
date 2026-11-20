# AX768 agent-interpreted structured capture requests

Date: 2026-11-20 (Asia/Seoul)

## Cause and registered-name fix

`위치조정/넥스터_이은경/헌릉로8길58` reached the unified API but returned its generic
clarification. The dispatcher accepted only Hangul-only name fields; the underscore
meant it found no valid name. The downstream graph parser had the same restriction.
The user confirmed `넥스터_이은경` is the full registered name to look up.

Both parsers now accept one underscore separating bounded Korean name segments,
preserving the whole name through lookup. No prefix stripping or fallback to
`이은경` is introduced. Exact name/address matching, ambiguity handling, signal
verification and completion-receipt validation remain authoritative. Existing
road whitespace normalization is retained.

## Model decision and structured contract

The user requested agent interpretation instead of exact word matching. After the
vision model separates new incoming from outgoing activity, complete source messages
are split in order. Each incoming source is analyzed by the configured model, which
may choose only `기기위치조정` or `전원연결`. Equivalent wording and natural language
are accepted; no literal keyword or exact slash format is required for this stage.

The analysis prompt asks the model to ignore unrelated conversation, generic signal
checks without an action, questions about actions, examples, cancellations, unclear
identity, incomplete targets and ambiguous/multiple actions. Ignored decisions have
all-null fields and cause no workflow API call or chat reply. Outgoing/automated
messages never enter action analysis. These are instructions to the model, not a
claim that model intent classification is infallible.

An accepted decision includes full name/address and a verbatim action-evidence quote:

```json
{
  "workflow_id": "device_adjustment_power",
  "action": "기기위치조정",
  "name": "넥스터_이은경",
  "address": "헌릉로8길58",
  "action_text": "기기를 다른 곳으로 옮겼습니다",
  "message": "헌릉로8길58 넥스터_이은경님 기기를 다른 곳으로 옮겼습니다",
  "confirmed_name": null
}
```

The client validates the allowed action enum, required field types/lengths and
source grounding. It rejects invented evidence, changed addresses and prefix/suffix
fragments of the registered name. Invalid model output uses the existing bounded
analysis retry/review path before any external action is claimed. Model decisions
(including ignored ones) are journaled per source, separately from API receipts.
Existing API claims prevent repeat execution when old captures resume.

The backend accepts optional structured fields for older-client compatibility.
When supplied, name/address/action must be complete and action_text must occur in
the original message. Identity fields must be grounded there; exact action words
and original slash layout are not required. Known contradictory action evidence
and explicit cancellation markers are rejected. The server builds the graph request
from the validated supplied fields and checks the completed note matches the action.
Older raw-text clients continue using the original grounded dispatcher parser.

The existing graph still receives canonical text such as:

```text
헌릉로8길58 넥스터_이은경님 기기위치조정 신호확인요.
```

No SMS is added. Replies use the server-owned template and verified result name.
Graph version/receipt schemas are unchanged; accepted name syntax and the optional
unified request schema are extended.

## Activation

Install VoyagerI rc.37 for model-interpreted structured requests. Update both backend
and agent-server before using it. From the updated development nexgent checkout:

```sh
sudo docker compose up -d --build --no-deps agent-server
sudo docker compose restart backend
```

For production use the corresponding `-f compose.prod.yaml` environment and rebuild
backend as well, since it does not mount source. Existing rc.36 can use the corrected
server name parser but retains its old literal-keyword behavior. No customer request
was replayed or live sheet/member/SMS operation performed for these checks.

## Validation

- Validation: 179 backend API tests and 128 downstream graph/parser tests passed.
  The desktop full suite passed 464 tests with 24 platform skips before the final
  two regression tests; the final focused unified suite passed 57 tests. Lint and
  whitespace checks passed.
- The original API regression reproduced needs_confirmation before the fix.
- Dispatcher/device API tests cover full names, both actions and all six legacy field
  orders, structured natural-language evidence, identity substitution, cancellations,
  malformed/partial fields and verified receipts.
- Real graph tests use synthetic HTTP services for connected/disconnected outcomes,
  asserting the full name reaches lookup/member stages and disconnected cases do not
  write. These tests do not prove a live roster match or physical signal.
- Desktop tests use mocked model decisions to verify semantic decisions without literal
  keywords reach the API, ignored decisions never call it, malformed decisions cannot
  claim an API attempt, and saved work never duplicates operations. They test wiring
  and validation; live configured-model classification quality has not been measured.
- Native Windows test/startup results and checksum are recorded in the rc.37 release.

Commands: run `uv run python -m pytest tests/test_ax768_dispatch.py tests/test_ax768_workflow.py -q`
in nexgent/backend; `uv run python -m pytest tests/unit/test_ax768_unified.py tests/unit/test_ax768_supplied_inputs.py`
in nexgent/agents; and `uv run python -m pytest tests/test_unified_workflow.py -q`
in software/kakao-capture-agent.
