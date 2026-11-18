# Validation and Windows acceptance

## Windows release validation

[Release v0.1.0-rc.23](https://github.com/prof-lijar/ax-project/releases/tag/kakao-capture-agent-v0.1.0-rc.23) was built and published on 2026-11-18 by [Windows Actions run 44274607262](https://github.com/prof-lijar/ax-project/actions/runs/44274607262).

- Windows Server 2022 x64, Python 3.12: **341 tests passed in 69.42 seconds**, including continued replies after accepted Enter with unconfirmed observation, empty-composer checks, observation-only retries, continuous screenshot collection during slow inference, FIFO replies, repeated replies, image persistence/integrity/retention, Stop/restart and uncertain-send review, post-send observation without composer focus, and existing GUI/capture/reply/Bizgo regressions.
- Both source and standalone executable passed their synthetic startup checks; the executable exited with code 0.
- Startup checks covered native imports, private-directory ACL setup, configuration, SQLite, synthetic PNG creation, retention, and Qt window/preview initialization. They captured no screen content and sent no input.
- Published executable: `KakaoCaptureAgent-v0.1.0-rc.23-windows-x64.exe`, 109,062,755 bytes.
- SHA-256 reported by GitHub for the uploaded executable: `4402babbfcf66154d88ff076158e860acf9de38dc0cd19303f4caf2f73bb4bb9`.

Actual KakaoTalk capture/scrolling and test-reply delivery, a clean Windows 10/11 PC, sign-in startup, mixed-DPI selection, and the soak gate below still require manual validation. The release is therefore marked as a prerelease.

## Automated validation

### Continue after accepted Enter with unconfirmed observation — 2026-11-18

Portable validation: **321 passed, 20 native Windows cases skipped in 8.68 seconds**. Ruff lint/format and diff checks passed.

Regression tests reproduce the reported sequence using the real reply sender: Windows accepts Enter, the synthetic composer clears but observation is unavailable, a second incoming capture arrives, and a second reply is sent without rearming. The persisted `submitted` jobs never replay after restart. A companion case leaves the first reply in the composer and verifies the next send neither overwrites it nor presses Enter. Additional checks cover existing drafts, transient read failures, content-free diagnostics, and partial-input quarantine.

Windows/KakaoTalk acceptance: after resolving any existing rc.22 review job, start Auto Catch and send two separate questions from another participant. Verify both replies and continued watching, including when `composer clearing unconfirmed` is logged. Send more questions during inference and check FIFO processing. Leave text in the composer and verify no automated overwrite. Actual client delivery and observation failure reasons remain subject to this manual check.

### Queued screenshot Auto Catch — 2026-11-18

Portable validation: **315 passed, 20 native Windows cases skipped in 9.14 seconds**. Ruff lint/format and diff checks passed.

Auto Catch now captures changed before/after image pairs continuously while one background vision/answer job runs. Automated coverage includes two consecutive replies without rearming, typing and outgoing-AI suppression, three captures queued during blocked inference then answered in FIFO order, adjacent-frame sharing, Stop and explicit restart, malformed-analysis backoff while later frames queue, prepared-answer preservation across focus recovery, and uncertain-send quarantine. Missing/modified images and invalid paths require review before calling the LLM. Storage failure leaves the previous baseline unchanged. Native-text jobs remain isolated.

Manual acceptance on the user's Windows/KakaoTalk client remains required:

1. Select the open group, configure a vision model, and click Auto Catch. Verify the screenshot preview and local path under `captures\auto_catch`.
2. Send a question from another participant. Verify one `[AI] ... (자동 응답)` reply, then send another without restarting and verify a second reply.
3. Send two more questions while the first LLM request is processing. Confirm capture paths and queue counts appear before the first reply completes, then verify replies follow in order. Messages visible in one changed frame may be batched.
4. Verify typing indicators and the agent's own reply cause no answer. Move focus within KakaoTalk after Enter and confirm watching continues when the original composer clears.
5. Stop during inference, restart Auto Catch, and verify queued work resumes. Restart the application and verify it waits for explicit rearming. Another selected chat must not receive the old chat's replies.
6. Test an uncertain send: inspect the chat, then Stop → Review Replies → Auto Catch. The uncertain attempt must never be resent automatically. Test storage capacity and unavailable targets; already queued captures must survive.

Tests use synthetic images/mocked inference and send no real messages. Actual client geometry, Korean OCR/classification, sending behavior, and complete message coverage are not established by these tests. The post-send observation fix remains covered by Windows composer tests.

### Historical rc.21: direct-text Auto Catch and queued replies — 2026-11-18

This describes the previous release; the current Auto Catch uses the queued screenshot workflow above.

Release rc.20 was not published: [Windows run 44262942622](https://github.com/prof-lijar/ax-project/actions/runs/44262942622) passed 319 cases but failed the native transcript test because the managed UIA provider exposed the editor as a generic pane. Diagnostic runs confirmed that explicitly registering managed providers did not resolve it. The reader now supports standard read-only Win32 text controls directly and retains UIA for other accessible transcript providers. No screenshots or clipboard fallbacks were added.

Portable validation: **300 passed, 20 native Windows cases skipped in 8.46 seconds** in the final portable suite. Ruff checks pass. New tests prohibit screenshot calls in Auto Catch, exercise two consecutive text replies, and hold the first LLM request open while second and third arrivals are durably queued and later answered in FIFO order. They cover Stop during inference, retained jobs, invalid-analysis backoff, restart recovery, uncertain-send quarantine/review, prepared-answer preservation across focus recovery, own-reply suppression, changed/unavailable controls, text-only HTTP requests, and cancellation of the Windows helper. Post-send observation tests allow changed keyboard focus while still checking the original composer's owner and validity.

The configured local LLM passed synthetic Korean text-only checks: `테스터: 2 더하기 2는?` was classified incoming, generated `[AI] 4입니다. (자동 응답)`, and the agent's own reply was ignored. A mixed batch containing an earlier `[AI] 4입니다.` reply and the participant question `3 더하기 3은?` extracted only the new question and answered `[AI] 6입니다.`. No images, real conversation contents, or real chat input were used.

A Windows-only integration test opens a synthetic native read-only transcript and a separate writable composer. The real Win32 reader must read Korean transcript text and exclude the private synthetic draft. The UI Automation helper must either expose the same safe text or explicitly report unsupported controls. The Windows runner exposed its native editor only as a generic UIA pane, which prompted the supported read-only Win32 control path rather than assuming every native editor implements UIA text patterns. The rc.21 packaged startup check passed and verified that the helper resource is included. These checks validate Windows APIs and packaging; it does **not** establish whether the installed KakaoTalk client exposes equivalent accessibility data. If it does not, Auto Catch explicitly reports unsupported direct text and never switches to screenshots.

Manual acceptance on the user's PC:

1. Select the open group and click Auto Catch. Confirm `Text source ready` and readable conversation text in the new text preview; no PNG should be created by Auto Catch. If the selected region excludes part of the transcript pane, reselect its full message area.
2. Send a Korean question from another participant, verify a reply, then send another question without restarting.
3. While the first LLM request is processing, send two more questions. Confirm queue counts increase and replies follow in order. Multiple messages observed in one read may be batched.
4. Stop during processing, restart Auto Catch, and verify pending text resumes. Restart the application during inference and verify explicit rearming is required. Change to another chat and verify pending work is not sent there.
5. Test focus movement after Enter: a cleared original composer should permit continued watching. Remaining text, target loss, and unverified sends must stop. Inspect chat, click Stop → Review Text Replies → Auto Catch, and confirm only later queued batches proceed without resending the uncertain attempt.

Text collection is polling of accessible transcript content, not a server-side incoming-message API. Read latency, accessibility support, visible/accessible coverage, sender labels, transcript trimming and interpretation remain client-dependent. Pending text is stored privately in `queue.db`; sent/ignored payloads are cleared. No phone/Bizgo or screenshot-upload calls occur in Auto Catch.

### Incoming-message analysis recovery and plain-text replies — 2026-11-18

Portable suite: **276 passed, 19 native Windows cases skipped in 8.20 seconds**; Ruff lint/format and diff checks passed. Focused Auto Catch/incoming/workflow coverage passed **127 tests in 2.04 seconds**. A mocked HTTP workflow follows typing indicator → malformed analysis on the incoming frame → automatic recheck against the retained baseline → plain Korean reply → outgoing reply ignored. It verifies exactly one local capture and one submission, with no manual restart. Other cases cover bounded retry frequency, persistent uncertainty, Stop/target loss during failed analysis, plain-text answers, invalid/duplicate JSON fields, fence variations, and cancellation/no extra request on API errors.

The configured local `gemma-4-31b` server also passed a live synthetic paired-image test: typing activity was classified `none`, the subsequent question was `incoming`, and the plain-text answer became `[AI] 2 plus 2 is 4. (자동 응답)`. Its structured JSON mode was accepted without fallback. No real chat contents or desktop input were used. Actual Korean KakaoTalk message detection and automatic reply delivery still require the user's Windows test.

Analysis uses the OpenAI-compatible `response_format: {"type":"json_object"}` option, documented by [vLLM](https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/). Servers explicitly rejecting that parameter with HTTP 400/422 receive one cancellable fallback without it; subsequent analysis calls on that workflow instance omit it. Other HTTP errors are not retried. Model analysis still undergoes field/type/length checks. Unreadable analysis leaves the previous baseline untouched and backs off up to 30 seconds while Auto Catch remains armed; this does not retry reply generation or chat submission. Test Workflow 2 remains one-shot and still stops on invalid analysis.

Client acceptance: start Auto Catch before another participant types. Typing dots should cause no reply. Submit a short question such as `2 더하기 2는?`; verify one `[AI] 4입니다. (자동 응답)` answer (wording can vary), then ask a different question without restarting. Confirm the agent ignores its own answer. If analysis needs another check, the log must show a delay while remaining AUTO_CATCHING, and Stop/hotkey must still end the workflow. All image-based coverage remains approximate.

### Auto Catch foreground recovery — 2026-11-18

Portable validation: **253 tests passed, 19 native Windows cases skipped in 7.80 seconds**; Ruff lint/format checks passed. New cases exercise focus loss after startup and during classification, temporary activation denial, quiet periodic retries, preserved baseline/reply count/duplicate cache, Stop/new-action/shutdown cancellation, and refusal to recover after lock/minimization/obstruction/retargeting or a send attempt. A real MonitoringService thread with fake desktop/model/composer adapters starts watching, loses focus, reacquires it, processes incoming text, and stops. Native adapter tests distinguish foreground-only failures from other target failures; no real desktop input or messages are sent by these tests.

Client acceptance: start Auto Catch, temporarily put the agent or an ordinary application in front, then send a new text from another participant. Verify automatic activation of the same selected chat and one reply without clicking Auto Catch again. If activation is denied, the status should report automatic waiting; after recovery it must retain the previous capture and avoid replying to previously handled text. Test Stop/hotkey while waiting. Lock, minimized/closed/changed windows, persistent covering dialogs, and uncertain sends must remain paused without automatic resend. The actual KakaoTalk client focus behavior remains unverified on the Linux development host.

### Auto Catch — 2026-11-18

Portable suite: **241 tests passed, 19 native Windows cases skipped in 7.07 seconds** in the full portable suite. The final focused Auto Catch/LLM/GUI/Windows-adapter suite passed **89 tests with 2 native cases skipped in 2.43 seconds**. New coverage includes continuous replies beyond the one-shot timeout, window-only setup, respecting manual regions, local capture retention, cooldown and 60-second duplicate suppression, a 256-entry cache bound, messages arriving during inference, generated/outgoing message rejection, cancellation, target loss/change, storage/model failures, uncertain submission, explicit rearming, suffix settings/migration, and GUI serialization. Physical-coordinate region tests cover negative monitor origins, DPI, search/history controls, missing/ambiguous/password/disabled/custom composers, off-screen geometry, locks, and movement during detection. Existing one-shot/Bizgo/capture regressions pass. Automated tests send no real chat or phone messages.

The existing local `gemma-4-31b` server passed synthetic paired-image checks for new incoming text, outgoing AI text, and unchanged content. A two-message frame produced both extracted questions and `[AI] 2 plus 2 is 4, and 3 plus 3 is 6. (자동 응답)`. No actual chat screenshots or messages were used. This establishes model support for the batch prompt on the development host, not actual Korean-chat OCR accuracy or Windows UI behavior.

Manual acceptance on Windows with the installed KakaoTalk client:

1. With only a chat window selected and no region/chat identifier configured, start Auto Catch. Verify the detected preview excludes the composer and follows small window movements. Stop/restart and verify configuration persistence.
2. Have another participant send text. Verify one local PNG, one `[AI] ... (자동 응답)` answer, and automatic return to AUTO_CATCHING. Send another different message without clicking Auto Catch again and verify another answer.
3. Send text while the first answer is being generated. Verify it remains eligible on the next comparison. Test several incoming bubbles in one frame, Korean text, photos, rapid traffic, animations, and cropped bubbles; coverage is approximate, not guaranteed.
4. Verify existing baseline text, outgoing replies, and unchanged frames cause no answers. Test that identical sender/text within 60 seconds is suppressed and that the guard expires. Check no Bizgo request occurs even when Workflow 1's Bizgo option is enabled.
5. Stop/hotkey during waiting and model inference; minimize/close/resize the chat, lock the session, or force model/storage errors. Verify no automatic restart or uncertain-send retry. Ordinary foreground loss now follows the dedicated recovery checks above. Leave the chat visible for an extended run and measure target-PC CPU/memory/latency before unattended use.

Auto region detection relies on the native composer classes already supported by the reply sender, with explicit ambiguity/geometry checks. It has not yet been validated against the user's actual Windows/KakaoTalk layout. Model OCR/direction inference, foreground transitions, and continuous message delivery also remain client acceptance checks.

### Incoming-message workflow and focus recovery — 2026-11-17

Portable validation: **201 tests passed, 19 native Windows cases skipped in 6.58 seconds**. Tests cover paired-image HTTP payloads, Korean reply formatting, malformed classifications, generated-message suppression, baseline/debounce behavior, one-shot sending, ignored changes, timeout at each stage, cancellation during active inference, lost/changed targets, storage/send failures, rearming, GUI command serialization, and temporary Windows input-queue cleanup. Existing workflow and Bizgo regressions still pass. Mocked focus tests cover delayed activation, cancellation, attachment failure, activation errors, modifier guards, and detachment. A native Windows case checks required APIs without activating another window.

A live synthetic check used the existing local `gemma-4-31b` server with two generated chat-like images per classification. It identified a newly appended incoming question and generated `[AI] 2 plus 2 is 4.`. It classified both an outgoing `[AI]` bubble and identical frames as `none`, correctly producing no reply for those cases. No real chat screenshots, phone messages, or KakaoTalk input were used. This validates two-image support on that server, not Korean OCR or actual KakaoTalk bubble classification.

Manual acceptance on the user's Windows/KakaoTalk installation remains required:

1. Run **Test Workflow**, allow inference to finish, and verify automatic focus recovery plus exactly one submitted summary. Repeat after another ordinary window takes foreground during inference. A locked session, changed target, or covering dialog must still stop sending.
2. Open the latest chat messages and arm **Test Workflow 2: Reply to Next Message**. Verify existing visible text causes no reply. Send one new text from another participant and verify one local PNG, one `[AI]` answer, and a stopped watcher.
3. Rearm and test an outgoing message, a previous `[AI]` reply, unchanged content, and cosmetic changes. None should receive an answer. Test Korean text and full bubble alignment on the installed client.
4. Test Stop/hotkey during waiting and inference, session lock, overlap, window closure/resizing, API timeout, and the configured waiting deadline. No automatic rearm or repeated submission should occur.
5. Verify Workflow 2 never calls Bizgo, including when Workflow 1's Bizgo option is enabled. Check that pressing the button again takes a new baseline and does not answer old messages.

Foreground recovery uses a short wait plus one temporary `AttachThreadInput` attempt with guaranteed detach attempts in `finally`; all typing still requires the exact verified foreground/composer. It is not proof that Windows will grant focus in every installation. Actual recovery from the user's reported post-inference denial is pending their client test.

### Bizgo final workflow step — 2026-11-17

Contract tests follow the official [v2 SMS/LMS reference](https://developers.bizgo.io/en/api-sdk/api-reference/comm/mt) and [common authentication/environment reference](https://developers.bizgo.io/api-sdk/api-reference). They verify production/sandbox URLs, raw API-key authentication, one configured recipient, the SMS/LMS byte boundary, LMS formatting, explicit shortening/encoding changes, reference/idempotency fields, response-code/recipient/reference validation, and retention of acceptance identifiers without message/credential/phone logging. They also cover authentication failure, rate limiting, server errors, redirect refusal, malformed/oversized replies, timeout, cancellation before/during submission, and storage audit failure. All HTTP requests use an in-memory mock transport and synthetic phone numbers; no actual Bizgo messages were sent.

Workflow tests verify that Bizgo runs only after one KakaoTalk send and observed composer clearing, skips after uncertainty/cancellation, and does not repeat the chat send after a Bizgo failure. The standalone sample test requires no chat selection, capture, or LLM. GUI tests verify editable number persistence, sandbox/production settings, and duplicate/cancelled sample timers. A typed composer observation supplies the next-stage gate; the application does not infer success by searching log strings.

Real Bizgo sandbox acceptance, production acceptance, registered sender validation, IP allowlisting, and final handset delivery remain unverified without the user's account configuration. The user chose to enter numbers in Settings; no real phone numbers or API keys are bundled in the application or committed as defaults.

Portable validation on 2026-11-17: **163 tests passed, 18 native Windows cases skipped in 5.60 seconds**. Ruff lint and formatting passed.

Windows validation: **181 tests passed in 15.89 seconds**, followed by successful source and frozen startup checks in [rc.15 run 44045139976](https://github.com/prof-lijar/ax-project/actions/runs/44045139976). Production/Sandbox Bizgo account testing remains pending; no real messages were sent during development or CI.

### Settings credential save — 2026-11-17

The credential writer now supplies a Python string to pywin32 `CredWrite`; the reader still decodes the returned UTF-16 bytes. The pywin32 implementation converts `CredentialBlob` with `PyWinObject_AsWCHAR`, so pre-encoding it was incorrect ([source](https://github.com/mhammond/pywin32/blob/main/win32/src/win32credmodule.cpp)). Portable tests cover both credential destinations, config persistence, no sign-in registry call when startup remains disabled, and failures at each save stage with secret redaction. A native Windows test creates a UUID-named synthetic credential, reads it back, replaces it, reads it again, and deletes only that test credential in cleanup. No real API keys are used in these tests.

Validation: **130 tests passed, 18 Windows-only cases skipped in 4.63 seconds** on Linux; lint and formatting passed. All **148 tests passed on Windows**, including the native credential test, and both source/frozen startup checks passed. Saving the user's actual key on their Windows PC remains the acceptance check.

### One-cycle LLM workflow — 2026-11-17

The workflow integration test uses a synthetic screenshot and two HTTPX mock responses to verify that the exact saved PNG reaches the vision request, extracted Korean text reaches the summary request, and exactly one multiline `[test]` reply reaches the guarded composer. It checks that the PNG remains unassigned to the upload API and monitoring stays stopped. Regressions cover cancellation during an active asynchronous request, target changes, unavailable targets, storage failure, authentication/rate-limit/server errors, redirects, timeouts, invalid/oversized/truncated/empty responses, environment settings, local HTTP opt-in, and GUI duplicate/stale timer handling. No test sends a real chat message.

A live model check on 2026-11-17 called the existing `nexgent/agents` server at `http://192.168.0.17:8000/v1` using model `gemma-4-31b` and its locally stored credential. The input was a generated white image with two English requests about preparing a meeting agenda, project status, and next steps. Both image extraction and text summarization succeeded and produced the intended `[test]` reply format. No actual chat image was transmitted, no KakaoTalk input was sent, and no credential was printed or committed. This verifies model image support from the development host, not connectivity from the user's Windows PC or Korean OCR accuracy.

The user reported the rc.11 fixed-message send working in KakaoTalk. The new full capture/LLM/multiline-send cycle still requires the manual check below.

The first workflow build, rc.12 ([run 44033009821](https://github.com/prof-lijar/ax-project/actions/runs/44033009821)), stopped before packaging: 133 tests passed and four long-text native cases failed because the synthetic Edit control lacked `ES_AUTOVSCROLL`. [Windows documents that such controls reject text exceeding the visible lines](https://learn.microsoft.com/en-us/windows/win32/controls/about-edit-controls). The fixture now enables vertical scrolling for long-text acceptance and retains separate non-scrolling refusal cases verifying that the sender never presses Enter on an unchanged old draft. The application does not modify KakaoTalk control styles.

After the fixture correction, the focused Linux reply/workflow/GUI suite passed **60 tests, with 16 native cases skipped in 0.55 seconds**. The rc.13 Windows suite passed all 141 tests in [run 44033354154](https://github.com/prof-lijar/ax-project/actions/runs/44033354154), before the credential-save tests were added.

The test-reply suite covers exact Korean text, automatic replacement of existing text/whitespace/leftover test drafts, cancellation, changed focus/control, text mismatch, audit failure, uncertain sends without retries, dispatch serialized after Stop, control validation, and duplicate/cancelled GUI timers. Windows-only cases target a synthetic hidden native Edit control to replace each kind of draft and verify both the Unicode result and the parent's `EN_CHANGE` notification. `SendInput` is intercepted in these tests to verify Enter down/up scan-code encoding and native structure size without injecting keys. Portable tests additionally cover rejected/partial input with key-up cleanup, last-moment cancellation/focus guards, and cleared/remaining/uncertain composer observations. Real KakaoTalk sending remains a manual acceptance check.

Development environment: Linux, CPython 3.12.3. Run `python -m pytest -q` from the project directory. The suite uses temporary directories, synthetic images, fake desktop adapters, and HTTPX mock/ASGI transports; it does not collect real conversations.

Verified on 2026-11-17 after the one-cycle workflow changes: **124 tests passed, 13 Windows-only cases skipped in 5.36 seconds**, with process exit code 0. Ruff lint and formatting checks passed. Coverage also includes capture-independent composer discovery, bounded control diagnostics, activation before GUI minimization, stopping auto-recovery during manual countdowns, exact-target activation, refusal after handle reuse or activation denial, obstruction/cancellation before clicking, and cleanup after a partially injected mouse press. The offscreen GUI fixture explicitly cleans up widgets and native event filters before QApplication teardown.

Local-save regression tests verify full-resolution PNG bytes, repeated manual saves without scrolling or live-baseline changes, invalid-target rejection, persistence across restart/maintenance, explicit API assignment, pausing/resuming pre-existing uploads, the folder-opening action, and persistence of the local-only setting.

Tests cover region geometry and display gaps, window-relative movement, DPI/resize invalidation, configuration persistence, change detection/debounce, measured overlap, state transitions, cancellation, foreground/lock/obstruction guards, handle reuse, queue recovery, storage limits, file/transaction failures, upload acknowledgements, authentication, retries, idempotency, and the offscreen Qt interface.

The suite also runs a real loopback HTTP integration test: a synthetic live capture receives HTTP 503, monitoring pauses when the fake desktop becomes unavailable, the independent upload worker retries successfully with the same capture ID, retention removes the acknowledged PNG, and both workers shut down cleanly.

The development sandbox reported stream-file-descriptor errors and stalled `asyncio.to_thread` completion. The suite was therefore run outside that sandbox with local temporary data, mock transports, and a loopback-only server. This is an environment limitation, not a passing Windows integration test.

| Component | Tested version |
|---|---|
| Python | 3.12.3 |
| pytest | 9.2.0 |
| PySide6 | 6.12.0 |
| NumPy | 2.5.5 |
| OpenCV headless | 4.14.0.94 |
| HTTPX | 0.28.1 |
| FastAPI | 0.163.1 |
| Uvicorn | 0.54.0 |
| MSS | 10.2.0 (installed; native capture not exercised on Linux) |
| Ruff | 0.17.5 |

PyWin32, PyAutoGUI, Win32 input/capture, Credential Manager, ACLs, sign-in registry entries, and PyInstaller packaging have not been executed in this Linux environment. The Windows release workflow runs the same automated suite and a packaged startup check covering native imports, data-directory ACL setup, configuration, SQLite, synthetic PNG/retention, and the Qt window/preview. It records the result in `dist/self-test.json`. Consult the specific release's Actions run for its actual Windows build result; real capture/input and the manual acceptance checks remain pending.

## Manual Windows checklist

Record Windows build, Python version, KakaoTalk version, monitor arrangement/scales, wheel settings, hardware, test API URL, and application commit before testing. Use an authorized test conversation. All items below are **pending** until run on a real Windows PC.

| Scenario | Expected result |
|---|---|
| Edit Bizgo sender/recipient, save, restart | Both numbers persist and the configured recipient is used; main-window label masks it |
| Send Bizgo Sample with no chat/LLM configuration | One fixed sample goes to the configured environment/recipient; no capture or desktop input occurs |
| Bizgo sandbox | Test request can be accepted but no real phone delivery is claimed |
| Bizgo production with registered sender and allowlisted IP | One accepted message reference/key is recorded; handset delivery checked separately |
| Full workflow with Bizgo enabled | Capture → LLM → KakaoTalk reply → composer clearing → one Bizgo request |
| KakaoTalk uncertain / Stop before Bizgo | Phone send is skipped; no automatic replay |
| Stop or connection loss during Bizgo request | Uncertain result is explicit; no resend or false delivery claim |
| Test Workflow with configured local vision LLM | One current-position capture is saved, two model calls complete, and one `[test]` simulation summary plus extracted text appears in the selected conversation |
| Stop while LLM is processing | Pending HTTP work cancels; no later reply or monitoring restart occurs |
| LLM error / unreadable image / changed chat | Visible failure; local capture retained if saved; no send or automatic retry |
| Test Workflow in local-only mode | Explicit LLM call still runs; saved PNG remains unassigned to ordinary uploads |
| Long Korean multiline workflow reply | Native readback matches the complete message; one Enter submits it as one message |
| Fresh install and launch | GUI opens, data directory and schema initialize, capture starts stopped |
| Send Test Reply while monitoring or paused | Click once; capture/navigation stops, chat and composer focus automatically, existing draft is replaced, and exactly `[AI가 답장드렸습니다]` appears once |
| Activation denied / zero or multiple composers | Send stops without typing; no fallback to another window or guessed click position |
| Capture rectangle includes message composer | A unique valid composer is still detected; capture coordinates do not filter it out |
| Unsupported composer | Bounded diagnostic lines show class/style and rejection reason, without message or draft contents |
| Manual action while temporarily paused | Automatic bottom-position recovery does not run during the manual countdown |
| Existing text / whitespace / leftover test reply | Draft is replaced by the exact fixed reply and Enter requested once; no manual clearing required |
| Native Enter submission | Client handles the native keypress and sends the message; status reports box clearing, while actual delivery is checked in the conversation |
| Text remains / focus changes after Enter | Status says send not confirmed or delivery uncertain; no automatic second Enter or resend |
| Wrong focus / unsupported control | No input is sent to an unverified control; no automatic retry occurs |
| Stop during send countdown / focus change after text insertion | Pending send cancels or pauses; inspect any remaining draft; no automatic resend |
| Small display | All controls, including Send Test Reply, are reachable by scrolling the agent window |
| Window selection | Intended chat can be selected among multiple candidates; executable/title shown |
| Region drag/reselection | Preview contains only the selected message area; small/outside regions rejected |
| Save Capture Locally | After the countdown, one full-resolution PNG appears in the captures folder without scrolling or uploading, including repeated identical frames |
| Open Captures Folder | File Explorer opens the displayed directory; newest PNG matches the selected region |
| Local-only monitoring/history | New captures remain local and existing uploads pause; a request already in progress may finish |
| Disable local-only and restart | Local PNGs remain unassigned until explicitly assigned; existing assigned jobs can resume |
| Scaling at 100%, 125%, 150%, 200% | Preview dimensions and coordinates match physical selected pixels |
| Secondary monitor to left/above primary | Negative coordinates capture correctly; monitor gaps rejected |
| Region spanning two monitors | Native selection is accurate or visibly rejected; no unrelated pixels captured |
| Small window movement | Relative region follows the selected client area |
| Resize or DPI change | Capture pauses and requires reselection |
| Text, rapid messages, and photos | Meaningful visual changes queue PNGs; identical frames do not |
| Animation/blinking cursor | Sensitivity/debounce reduce uploads; maximum debounce prevents indefinite suppression |
| Other app overlap, popup, or tooltip | Collection pauses; invalid captures are discarded |
| Target closed/recreated or title changed | No input goes to a replacement; operator reselects |
| Lock/unlock or graphical session disconnect | Pause is visible/logged; only verified recovery resumes |
| Up/Down calibration | Conversation moves in correct direction; overlap measured, no clicks/message input |
| History scan limit and boundary | Ordered overlapping captures; bounded outcome recorded |
| Cancel History | Upward scan ends, restoration attempted, incomplete coverage recorded |
| Stop / Ctrl+Shift+F12 / pointer corner | Further automated wheel events cease; uploads remain independent |
| Failed bottom verification | Agent stays paused with a meaningful status |
| Manual latest-position confirmation | Operator can start a stationary/short chat; interruption invalidates confirmation |
| API 429 and 503 | Retries honor Retry-After and preserve capture ID |
| API authentication/validation error | Failure is retained and visible; no infinite permanent-error loop |
| Network loss and recovery | Queue persists; pending jobs upload or become reviewable after retry exhaustion |
| Crash/restart during pending upload | Pending/in-flight jobs recover without duplicate backend records |
| API URL changed with pending captures | Existing jobs keep their destination; unassigned captures require explicit assignment |
| Storage near/full limit | Warning then capture pause; unsent data preserved; uploads continue |
| Credentials and ACL | Token absent from config/logs; local data limited to configured user/SYSTEM |
| Application close while uploading | UI remains responsive while request finishes or times out; restart recovers work |
| Sign-in startup | Optional startup works; capture auto-start is separate; stale targets require reselection |
| Packaged EXE on a clean PC | Launches without Python installed; Qt, OpenCV, schema, and Win32 adapters load |

## End-to-end run

1. Start the mock server and agent using the README commands.
2. Select and preview the authorized chat region, configure chat ID and API token, and calibrate scrolling.
3. Start monitoring, send several test messages/photos using KakaoTalk manually, and verify accepted capture records in the mock SQLite database.
4. Start a short history scan. Review image overlap and ordering, boundary/outcome audit events, and successful return to live monitoring.
5. Stop the mock server, generate captures, restart the agent, and verify pending jobs survive.
6. Restart the mock server. Pending jobs should complete; use Retry Failed Uploads if the bounded retry budget was exhausted.
7. Move, obscure, minimize, and close the chat; lock/unlock Windows; verify pauses and safe recovery/reselection.
8. Exercise all emergency stops during scanning. Verify no navigation occurs after stop and that uploads can continue.
9. Build with `build.ps1`, copy `dist\KakaoCaptureAgent.exe` to a clean Windows PC without Python installed, and repeat the basic capture/upload scenario. The single executable should run without additional files from the build directory.

## 24-hour soak gate

Keep the PC unlocked and target visible. Record CPU, resident memory, queue depth, local storage, and upload latency hourly. Include network interruption, lock/unlock, and history scanning. Pass only if the UI stays responsive, memory/storage remain bounded, every durably queued capture is either acknowledged or visibly retained, and no known target-invalid state is reported as monitoring. Retain logs and record any incomplete history intervals. Message-level completeness is not an acceptance claim.

Do not mark this gate or the Windows packaging checks passed based solely on Linux unit tests.
