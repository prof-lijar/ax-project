# Validation and Windows acceptance

## Automated validation

Development environment: Linux, CPython 3.12.3. Run `python -m pytest -q` from the project directory. The suite uses temporary directories, synthetic images, fake desktop adapters, and HTTPX mock/ASGI transports; it does not collect real conversations.

Verified on 2026-11-16: **42 tests passed in 4.25 seconds**, with process exit code 0. Ruff lint and format checks passed, and Python compilation checks passed. The Linux desktop entry point correctly exits with a Windows-required message. The offscreen GUI fixture explicitly cleans up widgets and native event filters before QApplication teardown.

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

PyWin32, PyAutoGUI, Win32 input/capture, Credential Manager, ACLs, sign-in registry entries, and PyInstaller packaging have not been executed in this Linux environment. Their Windows acceptance checks remain pending.

## Manual Windows checklist

Record Windows build, Python version, KakaoTalk version, monitor arrangement/scales, wheel settings, hardware, test API URL, and application commit before testing. Use an authorized test conversation. All items below are **pending** until run on a real Windows PC.

| Scenario | Expected result |
|---|---|
| Fresh install and launch | GUI opens, data directory and schema initialize, capture starts stopped |
| Window selection | Intended chat can be selected among multiple candidates; executable/title shown |
| Region drag/reselection | Preview contains only the selected message area; small/outside regions rejected |
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
9. Build with `build.ps1`, copy the entire output folder to a clean Windows PC, and repeat the basic capture/upload scenario.

## 24-hour soak gate

Keep the PC unlocked and target visible. Record CPU, resident memory, queue depth, local storage, and upload latency hourly. Include network interruption, lock/unlock, and history scanning. Pass only if the UI stays responsive, memory/storage remain bounded, every durably queued capture is either acknowledged or visibly retained, and no known target-invalid state is reported as monitoring. Retain logs and record any incomplete history intervals. Message-level completeness is not an acceptance claim.

Do not mark this gate or the Windows packaging checks passed based solely on Linux unit tests.
