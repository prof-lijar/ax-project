# Unified response contract and delivery audit

Date: 2026-11-26

Current source exception for device commands: `device_adjustment_power` slash
commands use the web workbench's three-field payload (`workflow_id`, original
`message`, `confirmed_name: null`) without a second LLM parse. For this workflow,
`ok: true` authorizes delivery of the exact `response`; optional receipt metadata
and the duplicate `kakao-reply` field no longer gate successful chat replies.
The full body is still retained for debugging. Other workflow checks and the
delivery audit described below remain applicable. This change is newer than the
release validation recorded here.

## Implementation

The desktop validates the common response envelope before creating any outgoing message. `response` and `kakao-reply` must be equal nonempty strings; status, ok and verified must agree. Execution identity, structured failure issues and SMS instructions are required. Business failures remain valid replies. Existing completion and guardian recipient checks remain in place. No workflow-specific business template is generated in the desktop.

`OperationsResult.api_response` preserves an independent copy of the validated envelope and detailed receipts. Each `operation_journal` API record retains its job ID, original message, structured request, API response ID, outcome, exact outgoing text and send outcome. Delivery metadata links only the API attempts participating in the current send. Audit records are written before desktop input. Refused sends, uncertain input, submitted-but-unconfirmed text and observed composer clearing remain distinguishable; none imply remote Kakao delivery confirmation.

The client appends only the contract's SMS notices for installation or guardian addition. Acceptance means the provider accepted every request, not that a phone received it. SMS state is recorded separately from the server workflow outcome. The combined outgoing message is checked against the 2,000-character limit before submission. Oversized text is retained with a review outcome.

New incoming requests always get fresh API calls. Resuming an existing attempted operation logs a review notice and sends no saved reply. Device mode uses the unified endpoint and no startup greeting. Saved-image testing displays the validated API message without desktop or SMS delivery.

## Validation

The focused Linux suite passed 526 tests with 21 platform skips; changed Python files passed Ruff. Tests exercise simulated HTTP endpoints and desktop input, all unsuccessful statuses across all eight workflows, exact reply preservation, audit linkage, non-replay, SMS outcomes and combined-length boundaries.

Windows CI passed all **874 tests**, built the x64 executable, and passed both source and packaged startup checks. The three uploaded release assets were verified against their local SHA-256 digests. Real KakaoTalk interaction, phone delivery and mixed-DPI desktop behavior still require on-device acceptance testing.

## Compatibility

The backend must provide `id`, `ok`, `verified`, `status`, matching reply strings, `issues`, and `sms`. Missing or inconsistent envelopes are rejected locally. Installation stage arrays must move to receipts; `kakao-reply` must be ready-to-paste Korean text. An optional api_version must equal `1`.

The complete isolated Linux suite passed **847 tests with 27 platform skips** in 19.63 seconds. It ran outside the restricted sandbox to allow the local loopback/threading tests to complete. This validates the release source, not native Windows interaction.

## Published release

- Version: `voyageri-v0.1.0-rc.53` (prerelease).
- Tested source commit: `4402c9839d7e19831466e04075870f7d9a3740b1`.
- [Windows build and validation](https://github.com/prof-lijar/ax-project/actions/runs/45779269069).
- [Release and download](https://github.com/prof-lijar/ax-project/releases/tag/voyageri-v0.1.0-rc.53).
- Executable SHA-256: `362f4c92724ff8d1fd85236bb2bb2099d0e07b4c30c626ee0a69efc496e346d1`.
- Local assets: `dist/rc.53/` (EXE, checksum, packaged startup report).

The release was prepared in an isolated checkout of rc.52 and published from the release branch/tag; unrelated changes in the original repository were left intact.
