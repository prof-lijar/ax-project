Download `KakaoCaptureAgent-v<VERSION>-windows-x64.exe` from Assets and double-click it on Windows 10/11 (64-bit). Python, uv, and a separate installation step are not required. First launch may take a moment while bundled libraries unpack.

Open your authorized KakaoTalk conversation, select its window and message region, and enter a chat identifier in Settings (your own label, such as `test-chat`). Keep the chat visible and Windows unlocked. Ctrl+Shift+F12 stops automated capture/navigation.

New local capture controls:

- **Save Capture Locally** saves one full-resolution PNG without scrolling or uploading, even when the image is unchanged. Bring the selected conversation to the foreground during the three-second countdown.
- **Open Captures Folder** opens `%LOCALAPPDATA%\KakaoCaptureAgent\captures` to inspect the images. The activity log shows the saved filename.
- **Local-only mode** in Settings saves monitoring/history captures locally and pauses uploads. An upload already in progress may finish. Turning the mode off does not assign local screenshots to an API; use **Assign Local Captures to API** explicitly if desired.

No API or token is required for local testing. Local files survive restarts and are retained within the configured storage budget; collection pauses when the budget is reached.

This is a prerelease. The Windows build runs automated tests and a synthetic packaged-app startup check. Real KakaoTalk capture/scroll calibration, mixed-DPI desktop behavior, and the 24-hour unattended acceptance test still require validation on the target PC. Screenshots do not guarantee complete message coverage.

The executable is unsigned. Windows SmartScreen may show an unrecognized-app prompt, and Windows 11 Smart App Control may block execution without offering a per-app override. This release does not resolve code-signing restrictions. A SHA-256 checksum is included. Downloads from this private repository require repository access. See the README and TESTING.md in the tagged source for setup and validation details.
