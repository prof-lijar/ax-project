Download `KakaoCaptureAgent-v<VERSION>-windows-x64.exe` from Assets and double-click it on Windows 10/11 (64-bit). Python, uv, and a separate installation step are not required. First launch may take a moment while bundled libraries unpack.

**Updated: test-reply activation and composer discovery.** Stop monitoring, check the selected target title, and click **Send Test Reply**. Activation is now requested in the button handler before the agent minimizes, with foreground reverified before input. Composer discovery is independent of the capture rectangle, so a rectangle overlapping the message box no longer excludes it. If detection still fails, **Composer diagnostic** log lines report classes/style flags and rejection reasons without chat/draft text.

The reply remains exactly `[AI가 답장드렸습니다]`. Existing drafts are preserved. Exactly one supported writable multiline Edit/RichEdit control must be inside the selected window; zero or multiple matches stop the operation. KakaoTalk must send on Enter. Windows activation denial, obscured controls, changed targets, and cancellation also stop sending. Verify delivery in KakaoTalk; failed/uncertain sends are never automatically retried. Ctrl+Shift+F12 cancels pending actions; a partial attempt can leave a draft. The button still triggers one fixed-text test, with no AI-generated/background replies. Actual KakaoTalk compatibility requires testing on the target PC.

Manual capture/navigation requests now suspend automatic recovery during their countdown, preventing unexpected bottom-position initialization before the requested action starts. Bottom-position verification and missing-image queue warnings are separate from test replies; monitoring need not be started to send the test.

Open your authorized KakaoTalk conversation, select its window and message region, and enter a chat identifier in Settings (your own label, such as `test-chat`). Keep the chat visible and Windows unlocked. Ctrl+Shift+F12 stops automated capture/navigation.

New local capture controls:

- **Save Capture Locally** saves one full-resolution PNG without scrolling or uploading, even when the image is unchanged. Bring the selected conversation to the foreground during the three-second countdown.
- **Open Captures Folder** opens `%LOCALAPPDATA%\KakaoCaptureAgent\captures` to inspect the images. The activity log shows the saved filename.
- **Local-only mode** in Settings saves monitoring/history captures locally and pauses uploads. An upload already in progress may finish. Turning the mode off does not assign local screenshots to an API; use **Assign Local Captures to API** explicitly if desired.

No API or token is required for local testing. Local files survive restarts and are retained within the configured storage budget; collection pauses when the budget is reached.

Focus recovery now stays paused quietly while the selected conversation is not in the foreground, rather than repeatedly logging INITIALIZING/PAUSED. It revalidates the desktop before restarting capture/navigation and still reports a changed failure reason. Keep the selected KakaoTalk conversation active; opening the agent window takes focus away from it. Use **Stop**, then **Save Capture Locally**, for a single screenshot at the current scroll position.

This is a prerelease. The Windows build runs automated tests and a synthetic packaged-app startup check. Real KakaoTalk capture/scroll calibration, mixed-DPI desktop behavior, and the 24-hour unattended acceptance test still require validation on the target PC. Screenshots do not guarantee complete message coverage.

The executable is unsigned. Windows SmartScreen may show an unrecognized-app prompt, and Windows 11 Smart App Control may block execution without offering a per-app override. This release does not resolve code-signing restrictions. A SHA-256 checksum is included. Downloads from this private repository require repository access. See the README and TESTING.md in the tagged source for setup and validation details.
