Download `KakaoCaptureAgent-v<VERSION>-windows-x64.exe` from Assets and double-click it on Windows 10/11 (64-bit). Python, uv, and a separate installation step are not required. First launch may take a moment while bundled libraries unpack.

**Fixed: saving API keys in Settings.** The credential writer now passes the Unicode string expected by pywin32 instead of pre-encoded bytes. Upload and LLM keys remain in Windows Credential Manager. Settings saves no longer access the sign-in registry when startup was and remains disabled. Any remaining save error identifies the failed step and numeric OS error without logging the key. A Windows regression test saves, reads, replaces, and deletes a uniquely named synthetic credential.

**New: Test Workflow.** Click once to capture the selected region at its current position, save the PNG locally, send it to your configured vision LLM for text extraction, generate a simulated completion summary, and automatically send one `[test]` message containing the summary and extracted text. Capture remains stopped afterward; the workflow does not execute the tasks described in the chat.

Configure **LLM base URL**, **Vision LLM model**, **LLM API key**, and the vision checkbox in Settings. For the existing local server, use `http://192.168.0.17:8000/v1`, `gemma-4-31b`, your existing API key, and enable trusted LAN HTTP. The server successfully processed a generated English test image through both LLM stages. Keys are stored in Windows Credential Manager, never in the executable or configuration JSON. See the README for environment-variable support and limits.

The workflow makes two bounded model requests, keeps the interface responsive, supports Stop / Ctrl+Shift+F12 during inference, and stops without sending on invalid output or changed targets. Local-only mode still allows this explicitly requested LLM workflow; its saved PNG remains separate from ordinary uploads. Logs show progress and the local capture path without including extracted chat text. There are no automatic model/reply retries. Multiline Korean reply verification now supports longer generated messages.

**Send Test Reply** remains available for the fixed message `[AI가 답장드렸습니다]`. Both buttons stop capture/navigation, activate the selected chat, focus its message box, replace its contents through an edit operation that notifies the client, verify the exact text, and inject a native Enter down/up pair. No manual clearing, focusing, or Stop step is required. Existing drafts, whitespace, and leftover test text are replaced.

The agent observes the box after Enter for up to two seconds. It reports whether the box cleared, text remains (**send NOT confirmed**), or the outcome is uncertain. It does not infer server delivery from a cleared box or retry uncertain sends. Leave the mouse and keyboard alone during the operation; cancellation, target focus, and modifiers are checked immediately before the native keypress.

Exactly one supported writable multiline Edit/RichEdit control must be inside the selected window; zero or multiple matches stop the operation and log control diagnostics without chat/draft contents. KakaoTalk must send on Enter. Windows activation denial, obscured controls, changed targets, and cancellation also stop sending. Verify delivery in KakaoTalk; failed/uncertain sends are never automatically retried. Ctrl+Shift+F12 cancels pending actions; a partial attempt can leave the reply text in the message box. There are no background replies triggered by incoming messages. Actual KakaoTalk workflow compatibility requires testing on the target PC.

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
