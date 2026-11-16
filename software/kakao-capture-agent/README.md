# KakaoTalk Capture Agent

Windows desktop application for capturing an explicitly selected KakaoTalk conversation region, collecting bounded history, and uploading PNGs through a durable local queue. It implements the four phases in [PRD.md](PRD.md). It does not interpret messages or use private KakaoTalk APIs.

**Validation status:** the release workflow runs automated tests and a synthetic startup check of the packaged executable on Windows. Real KakaoTalk behavior, mixed-DPI selection, sign-in startup, and unattended operation require the manual checks in [TESTING.md](TESTING.md). Releases remain prereleases until those checks are completed.

## Download and run the executable

Open [GitHub Releases](https://github.com/prof-lijar/ax-project/releases) and download the `KakaoCaptureAgent-v<VERSION>-windows-x64.exe` asset from a successful capture-agent release. Double-click the downloaded file on Windows 10/11 (64-bit). Python, uv, and Git are not required on that PC. The repository is private, so sign in with an account that has repository access.

The executable includes its runtime and libraries; the first launch may take a moment while they unpack. It is unsigned, so Windows may show an unrecognized-app prompt. Each release includes a `.sha256` checksum file. Configuration and captures stay in `%LOCALAPPDATA%\KakaoCaptureAgent`, separate from the executable.

Open the intended KakaoTalk conversation, choose **Select Window** and **Select Region**, then enter a chat identifier in **Settings**. Configure the API URL/token if uploads are desired. See the controls below for preview, calibration, and monitoring. Keep the downloaded executable at a stable path if you enable launch at sign-in.

## Run from source on Windows

Use Windows 10/11 with an unlocked interactive desktop and an authenticated KakaoTalk conversation. Start with a conversation authorized for testing. The setup below uses **uv** to install Python 3.12 (the version used for the automated tests), create the project environment, and install dependencies. You do not need to install Python or the `py` launcher separately.

Install uv from Command Prompt or PowerShell:

```powershell
winget install --id=astral-sh.uv -e
```

Close and reopen your terminal, then check `uv --version`. If WinGet is unavailable, use one of the other methods in the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

If you do not already have the repository, install Git and download the `develop` branch:

```powershell
git clone --branch develop https://github.com/prof-lijar/ax-project.git
cd ax-project\software\kakao-capture-agent
```

If you already have a checkout, open a terminal in its `software\kakao-capture-agent` directory instead. Run:

```powershell
uv python install 3.12
uv sync --python 3.12
uv run --python 3.12 python -m app.main
```

`uv sync` reads `pyproject.toml`, creates `.venv`, and resolves dependencies into `uv.lock`. No manual environment activation is needed. For subsequent launches, run the last command from the project directory. See [uv's project guide](https://docs.astral.sh/uv/guides/projects/).

If `python --version` prints only `Python`, or `where python` points only to `Microsoft\WindowsApps\python.exe` while `py` is unavailable, use the uv commands above. They select the uv-managed Python runtime without depending on that Windows shortcut. If `uv` itself is not recognized, reopen the terminal after installation and check `where.exe uv`.

The GUI does not run on Linux. Linux can run the portable tests and mock API. No administrator privileges are required; run the agent and KakaoTalk at the same privilege level.

1. Open the intended KakaoTalk conversation in a separate, visible window.
2. Choose **Select Window**, review the executable and title, and confirm the authorized conversation. All accessible titled windows are listed because the application does not assume a fixed KakaoTalk executable or title format. Likely KakaoTalk executables sort first.
3. Choose **Select Region** and drag over the message area, excluding the message composer, sidebars, and unrelated content. Press Escape to cancel. The selection must be at least 32 × 32 physical pixels and entirely inside the target client area.
4. In **Settings**, enter a chat identifier. Configure the API URL and bearer token if uploads are desired. A blank URL enables local collection; it is not an API connectivity check.
5. Choose **Preview**. The agent minimizes itself and allows three seconds to bring the selected chat to the foreground. Restore the agent to inspect the preview; taking foreground focus pauses active monitoring.
6. Use **Scroll Up** and **Scroll Down** while stopped to establish that wheel events move the selected conversation and preserve overlap. These actions also queue captures as history.
7. Choose **Start / Resume** and bring the chat to the foreground within three seconds. The agent verifies the latest-message position before monitoring.
8. If bottom verification is inconclusive, manually move to the latest messages and use **Confirm Latest Position**. This is explicit operator confirmation, not proof inferred from a stationary image. Confirmation is invalidated after an interruption.

Keep the selected chat in the foreground, unobscured, and the Windows session unlocked. The GUI intentionally minimizes before capture-related actions. The agent does not activate or click windows for you.

## Controls and recovery

| Control | Behavior |
|---|---|
| Start / Resume | Verifies the target and bottom position, then monitors changed content |
| Stop | Cancels pending GUI actions and stops capture/navigation; uploads continue |
| Capture History | Pauses live capture, scans upward within the limit, and restores downward |
| Cancel History | Stops the upward scan and attempts bounded restoration |
| Ctrl+Shift+F12 | Global emergency stop, including while the GUI is minimized |
| Pointer at a primary-screen corner | PyAutoGUI fail-safe checked before wheel input |
| Retry Failed Uploads | Resets failed jobs for the currently configured destination and clears authentication pause |
| Assign Local Captures to API | Explicitly assigns captures created with no URL to the configured endpoint |

History and live scrolling run in the same worker, so they cannot overlap. History defaults to 50 steps, an 800 ms settle delay, and a minimum 30% overlap. The controller starts with one native wheel notch, measures vertical displacement, and adjusts up to the configured maximum of three notches. Poor overlap or uncertain motion stops the operation and records incomplete coverage.

Bottom verification first checks an exposed standard scrollbar. If unavailable, it requires previously observed wheel-induced movement and three settled downward attempts with negligible change. This is an approximate visual boundary, not message-level coverage. An explicitly confirmed latest position also permits stationary recovery checks until interrupted. Inconclusive restoration leaves monitoring paused.

Temporary focus loss, obstruction, or session unavailability pauses collection. Automatic recovery requires the same window identity, valid region, and successful bottom verification. Window closure, title changes, resizing, DPI changes, or ambiguous identity require explicit intervention. Use **Stop** to enable configuration and target selection again. The agent never silently substitutes another conversation.

Closing the application stops navigation and waits for the current upload (bounded by the configured request deadline). Remaining jobs persist. Optional sign-in launch is configured in Settings; automatic monitoring at sign-in is a separate opt-in. A new KakaoTalk process/window after reboot requires reselection.

## Test with the mock API

Start the loopback server in a separate PowerShell window in the project directory. `--with-requirements` supplies the additional development dependencies for the command:

```powershell
$env:KAKAO_MOCK_TOKEN = 'local-test-token'
uv run --python 3.12 --with-requirements requirements-dev.txt python -m mock_api
```

In Command Prompt, set the token with `set KAKAO_MOCK_TOKEN=local-test-token` instead of the PowerShell `$env:` command, then run the same `uv run` command. Keep this terminal open while testing uploads; run the desktop application from another terminal.

In the GUI, set:

- Upload URL: `http://127.0.0.1:8000/api/v1/captures`
- Bearer token: the same local test token
- **Allow loopback HTTP mock API**: enabled
- Chat identifier: a test identifier such as `authorized-test-chat`

The server validates PNG dimensions/content/hash, metadata, authentication, and the idempotency key. It commits image bytes and metadata together in `mock-data/mock.db` before acknowledging. Repeating an identical capture ID is accepted; conflicting metadata receives HTTP 409. It limits images to 20 MiB and 40 million pixels. It is a development server, not a production backend.

To simulate transient failure, stop the server, set these variables, and start it again:

```powershell
$env:KAKAO_MOCK_FAILURES = '2'
$env:KAKAO_MOCK_STATUS = '503'
$env:KAKAO_MOCK_RETRY_AFTER = '1'
uv run --python 3.12 --with-requirements requirements-dev.txt python -m mock_api
```

The first two authenticated requests fail, then requests succeed. Set the failure count back to zero afterward. `KAKAO_MOCK_DATA` can select a different data directory. The default bind is always `127.0.0.1:8000`.

## Production API contract

Configure a reachable HTTPS endpoint and bearer token. Credentials are saved in Windows Credential Manager under a destination-specific name. `KAKAO_CAPTURE_API_TOKEN` overrides the saved token for the current process; do not put tokens in JSON or source control. Clearing the token field leaves the existing credential unchanged; remove it using Windows Credential Manager when needed.

The agent sends `POST multipart/form-data` with `image`, `capture_id`, `device_id`, `chat_id`, `timestamp`, `capture_mode`, `image_hash`, `region`, and `sequence_number`, as specified in the PRD. Timestamps are UTC, `region` is a JSON string of physical desktop coordinates, and the hash is SHA-256 of PNG bytes. Capture IDs are UUIDs; sequence numbers start at one for each agent session. The local audit records the associated session ID.

Headers include `Authorization: Bearer ...` and `Idempotency-Key: <capture_id>`. A successful response must be HTTP 2xx with:

```json
{"status": "accepted", "capture_id": "the-same-capture-id"}
```

The backend must authenticate the sender, validate payloads, persist before acknowledgement, and deduplicate by capture ID. The client verifies TLS, does not follow redirects, and disables implicit environment proxy configuration. HTTP is accepted only for an explicitly enabled literal loopback address. OCR and message-level deduplication belong to the backend.

Connection/time-out failures, 429, 5xx, and invalid acknowledgements retry with exponential backoff and jitter. Both seconds and HTTP-date forms of `Retry-After` are honored. Five retries are allowed by default in addition to the initial attempt. Authentication errors pause dispatch; other permanent errors and exhausted retries remain available for operator review. Correct settings and select **Retry Failed Uploads** to retry them.

Each job keeps the URL and chat identifier it had when captured. Changing the API URL does not redirect existing jobs. Jobs for another destination remain pending until that URL is selected again. Captures created without a URL require **Assign Local Captures to API** before upload.

## Configuration and local data

The application automatically creates `%LOCALAPPDATA%\KakaoCaptureAgent\config.json`. The file in `config/config.example.json` is a reference, not a second active configuration. Edit advanced settings only while the application is closed. Unknown schema versions and invalid values stop startup rather than resetting data.

| Setting | Default |
|---|---|
| Capture interval | 2 seconds, allowed range 1–60 |
| Meaningful difference | 1% of blurred grayscale pixels differing by more than 20 intensity units |
| Debounce / maximum debounce | 0.5 / 2 seconds, evaluated at capture ticks |
| Bottom recovery interval | 30 seconds |
| Request deadline | 15 seconds |
| Local storage budget | 5 GiB; warning at 80% |
| Uploaded image retention | 0 hours; removed on maintenance after acknowledgement |
| Metadata/audit retention | 30 days |
| Startup / automatic monitoring | Both disabled |

Data layout:

```text
%LOCALAPPDATA%\KakaoCaptureAgent\
  config.json          Non-secret configuration and window-relative selection
  queue.db             SQLite queue, metadata, and audit events
  captures\            Pending/retained PNGs
  logs\agent.log       Rotating diagnostic logs
```

The directory ACL grants the current user and SYSTEM access. PNG files are not encrypted; use Windows disk encryption if required by your environment. Logs exclude tokens, response bodies, and chat message contents. Window titles are part of the saved target identity and should be treated as private configuration.

PNG writes use a flushed temporary file and atomic rename before the queue transaction commits. SQLite uses WAL and FULL synchronous mode. Interrupted uploads return to pending on restart. Orphan PNGs are retained for investigation; missing queued images become failed jobs. A crash before the queue transaction commits can leave an orphan without upload metadata, so it is never reported as a completed capture.

Capacity checks include local files and a disk-space reserve. Captures pause when capacity is exhausted; unsent and failed screenshots are never automatically deleted. Uploaded images and old diagnostic metadata are cleaned periodically. Back up the data directory with the application closed, preserving the database and image directory together.

## Development and build

Run these commands from the project directory. Portable tests on Linux, with uv installed:

```bash
uv python install 3.12
uv sync --python 3.12
uv run --python 3.12 --with-requirements requirements-dev.txt python -m pytest -q
uv run --python 3.12 --with-requirements requirements-dev.txt ruff check app mock_api tests
```

Windows tests and single-file packaging:

```powershell
.\build.ps1
```

`build.ps1` uses uv to create a Python 3.12 environment when needed, install development dependencies, run the tests, build the executable, and run its synthetic `--self-test` startup check. It stops on failure. No separate `py` launcher or pip installation is required. Development dependencies remain in `requirements-dev.txt`; the project does not currently define a uv development dependency group.

The output is **`dist\KakaoCaptureAgent.exe`**, a single executable that can be copied to a Windows PC without Python installed. The build includes a per-monitor DPI manifest and SQLite schema. Build on Windows; [PyInstaller is not a cross-compiler](https://pyinstaller.org/en/stable/). Do not copy a Linux virtual environment to Windows; create a new environment there.

## Publishing a GitHub Release

The repository workflow `.github/workflows/kakao-capture-release.yml` runs on GitHub's Windows runner when a tag matching `kakao-capture-agent-v*` is pushed. It tests the code, builds the single executable, checks packaged startup using synthetic data, calculates SHA-256, and publishes the executable/checksum as a GitHub prerelease. It never captures a conversation or sends mouse input during the startup check.

After committing the intended source revision, create a new, unused release tag, for example:

```powershell
git tag kakao-capture-agent-v0.1.0-rc.1
git push origin kakao-capture-agent-v0.1.0-rc.1
```

Use a new tag for each build; do not move published release tags. Review the Actions run and its `self-test.json` artifact before distributing the build. Update `RELEASE_NOTES.md` for subsequent releases. The workflow uses GitHub's repository-scoped token with release permission; no personal access token needs to be stored as a workflow secret. Manual workflow dispatch builds an artifact without publishing when run from a branch; its availability in the Actions UI depends on the workflow being present on the repository's default branch.

Implementation modules follow the PRD: GUI on the Qt thread; capture and scrolling on one automation thread; asynchronous HTTP in an independent worker; SQLite operations under a shared lock with separate connections. Business logic can be tested with injected desktop/capture/HTTP adapters.

## Known limits and implementation decisions

- Screen pixels cannot establish message identities or exhaustive history. Fast arrivals, dynamic loading, animations, blank regions, and interruptions can leave gaps. Audit events and history outcomes record uncertainty.
- Visibility and input checks are conservative and happen before and after actions. Windows does not make these checks atomic with desktop capture/input; extremely brief overlays or focus changes can race them. In-window custom content cannot be classified without message/UI interpretation. Use the dedicated PC and an explicitly selected message area.
- Window titles are matched exactly to avoid switching chats. If KakaoTalk changes the title for unread counts or other reasons, reselect the window. Cross-process/window recreation is never automatically rebound.
- Settings and target changes require Stop. Normal GUI interaction takes focus away from KakaoTalk and pauses capture. There is no tray interface in this release.
- Only standard scrollbar position is read; custom KakaoTalk controls use the measured visual fallback. Bottom position and overlap must be calibrated against the installed client. Uncertain checks remain paused.
- Native Win32 `SendInput` emits one 120-unit wheel notch and verifies success. PyAutoGUI supplies the mouse fail-safe. This deliberately replaces its wheel helper because [the Windows implementation passes raw wheel data and suppresses some OS input errors](https://github.com/asweigart/pyautogui/blob/master/pyautogui/_pyautogui_win.py).
- The selection uses native cursor coordinates rather than multiplying Qt global positions, because [Qt logical screen geometry differs from physical geometry on mixed-DPI Windows displays](https://doc.qt.io/qtforpython-6/overviews/qtdoc-highdpi.html). Real mixed-DPI behavior remains a manual acceptance check.
- Dependency versions have bounded ranges; the tested versions are recorded in `TESTING.md`. Packaging and runtime compatibility must be confirmed on the target Python/Windows combination before unattended use.
