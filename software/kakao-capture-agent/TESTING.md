# Validation and Windows acceptance

## Windows release validation

[Release v0.1.0-rc.13](https://github.com/prof-lijar/ax-project/releases/tag/kakao-capture-agent-v0.1.0-rc.13) was built and published on 2026-11-17 by [Windows Actions run 44033354154](https://github.com/prof-lijar/ax-project/actions/runs/44033354154).

- Windows Server 2022 x64, Python 3.12.10: **141 tests passed in 11.93 seconds**, including the mocked capture/vision/summary/send cycle, LLM cancellation and failure handling, workflow GUI controls, native long/multiline Korean and emoji replacement, rejection without sending old drafts, parent change notifications, intercepted Enter input encoding, capture/upload regressions, and the native directory ACL regression test.
- Both the source application and the standalone executable passed their synthetic startup checks; the executable exited with code 0.
- Startup checks covered native imports, private-directory ACL setup, configuration, SQLite, synthetic PNG creation, retention, and Qt window/preview initialization. They captured no screen content and sent no input.
- Published executable: `KakaoCaptureAgent-v0.1.0-rc.13-windows-x64.exe`, 109,000,515 bytes.
- SHA-256 reported by GitHub for the uploaded executable: `a412302e953f4230ae540b991bc72c32f039d61ca6a1ecc4f4d29c25aeb26eaf`.

Actual KakaoTalk capture/scrolling and test-reply delivery, a clean Windows 10/11 PC, sign-in startup, mixed-DPI selection, and the soak gate below still require manual validation. The release is therefore marked as a prerelease.

## Automated validation

### Settings credential save — 2026-11-17

The credential writer now supplies a Python string to pywin32 `CredWrite`; the reader still decodes the returned UTF-16 bytes. The pywin32 implementation converts `CredentialBlob` with `PyWinObject_AsWCHAR`, so pre-encoding it was incorrect ([source](https://github.com/mhammond/pywin32/blob/main/win32/src/win32credmodule.cpp)). Portable tests cover both credential destinations, config persistence, no sign-in registry call when startup remains disabled, and failures at each save stage with secret redaction. A native Windows test creates a UUID-named synthetic credential, reads it back, replaces it, reads it again, and deletes only that test credential in cleanup. No real API keys are used in these tests.

### One-cycle LLM workflow — 2026-11-17

The workflow integration test uses a synthetic screenshot and two HTTPX mock responses to verify that the exact saved PNG reaches the vision request, extracted Korean text reaches the summary request, and exactly one multiline `[test]` reply reaches the guarded composer. It checks that the PNG remains unassigned to the upload API and monitoring stays stopped. Regressions cover cancellation during an active asynchronous request, target changes, unavailable targets, storage failure, authentication/rate-limit/server errors, redirects, timeouts, invalid/oversized/truncated/empty responses, environment settings, local HTTP opt-in, and GUI duplicate/stale timer handling. No test sends a real chat message.

A live model check on 2026-11-17 called the existing `nexgent/agents` server at `http://192.168.0.17:8000/v1` using model `gemma-4-31b` and its locally stored credential. The input was a generated white image with two English requests about preparing a meeting agenda, project status, and next steps. Both image extraction and text summarization succeeded and produced the intended `[test]` reply format. No actual chat image was transmitted, no KakaoTalk input was sent, and no credential was printed or committed. This verifies model image support from the development host, not connectivity from the user's Windows PC or Korean OCR accuracy.

The user reported the rc.11 fixed-message send working in KakaoTalk. The new full capture/LLM/multiline-send cycle still requires the manual check below.

The first workflow build, rc.12 ([run 44033009821](https://github.com/prof-lijar/ax-project/actions/runs/44033009821)), stopped before packaging: 133 tests passed and four long-text native cases failed because the synthetic Edit control lacked `ES_AUTOVSCROLL`. [Windows documents that such controls reject text exceeding the visible lines](https://learn.microsoft.com/en-us/windows/win32/controls/about-edit-controls). The fixture now enables vertical scrolling for long-text acceptance and retains separate non-scrolling refusal cases verifying that the sender never presses Enter on an unchanged old draft. The application does not modify KakaoTalk control styles.

After the fixture correction, the focused Linux reply/workflow/GUI suite passed **60 tests, with 16 native cases skipped in 0.55 seconds**. The complete corrected Windows suite passed all 141 tests as recorded above.

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
