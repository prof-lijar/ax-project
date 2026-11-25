# VoyagerI

VoyagerI (formerly KakaoTalk Capture Agent) is a Windows desktop application for capturing automatically detected KakaoTalk message areas, running the same continuous workflow in up to three selected conversations, collecting bounded history, and uploading PNGs through a durable local queue. It implements the four phases in [PRD.md](PRD.md), with operator-triggered reply tests added afterward. It uses no private KakaoTalk APIs.

**Send Test Reply** sends the editable **Test reply message**, initially `[AI가 답장드렸습니다]`. **Test Workflow** performs one capture → LLM text extraction → simulated completion summary → KakaoTalk reply → optional Bizgo SMS/LMS cycle. **Send Bizgo Sample** tests only the configured phone-message connection. **Test Workflow 2: Reply to Next Message** explicitly arms a one-shot watcher: a newly observed incoming message triggers one `[AI]` reply, then it stops. **Run Agent (auto)** continuously watches and replies until stopped. Incoming messages trigger replies only while one of these modes is explicitly armed.

**Run Image Test**, under **Test tools**, accepts a saved capture, runs the existing unified API workflow, and shows its response in **Output** without sending a KakaoTalk reply. It requires no selected chat window.

**Validation status:** the release workflow runs automated tests and a synthetic startup check of the packaged executable on Windows. Real KakaoTalk behavior, mixed-DPI window detection, sign-in startup, and unattended operation require the manual checks in [TESTING.md](TESTING.md). Releases remain prereleases until those checks are completed.

The app uses the VoyagerI logo in its header, window, Windows taskbar and executable. See [branding and Windows icon setup](docs/voyageri-branding.md). New Windows release assets use the VoyagerI name; older release assets retain their original names.

## Download and run the executable

Open [GitHub Releases](https://github.com/prof-lijar/ax-project/releases) and download the `VoyagerI-v<VERSION>-windows-x64.exe` asset from a successful capture-agent release. Double-click the downloaded file on Windows 10/11 (64-bit). Python, uv, and Git are not required on that PC. The repository is private, so sign in with an account that has repository access.

The executable includes its runtime and libraries; the first launch may take a moment while they unpack. It is unsigned, so Windows may show an unrecognized-app prompt. Windows 11 Smart App Control may block it without offering a per-app override; this requires a trusted signed distribution to resolve reliably, and the current release remains unsigned. See [Microsoft's Smart App Control FAQ](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions). Each release includes a `.sha256` checksum file. Configuration and captures stay in `%LOCALAPPDATA%\KakaoCaptureAgent`, separate from the executable.

Open the intended KakaoTalk conversation, choose **Select Window**. All chat features detect the message area automatically; a blank chat identifier is generated automatically. Configure the API URL/token if uploads are desired. See the controls below for preview, calibration, and monitoring. Keep the downloaded executable at a stable path if you enable launch at sign-in.


## Watch up to three chats

1. Open up to three KakaoTalk conversations in separate windows, with the latest messages visible in each.
2. Click **Select Agent Chats (1–3)**, check the intended windows, and choose **Use selected chats**.
3. Click **Run Agent (auto)** (or **기기위치조정/전원연결**). The same chosen workflow runs independently for each chat, using the shared LLM and operations settings.

VoyagerI rotates foreground focus through the selected windows. Each chat has its own screenshot baseline, persistent queue, startup check, and reply cooldown. Model/API processing can run concurrently for different chats; capture and keyboard input run in sequence on one desktop worker. A reply always goes back to its originating chat. FIFO ordering is maintained within each chat; completion order across chats can differ.

Captured images are separated by group name. Continuous-workflow images are saved in `%LOCALAPPDATA%\KakaoCaptureAgent\captures\auto_catch\<group name>--<chat ID>\`. The short ID distinguishes different chats with identical or similar names; Korean names are preserved and characters Windows cannot use in a folder name are replaced. Identical screenshots from different groups still have separate files. Each queued job keeps its original chat key and image path across Stop/restart. Replies are submitted only through that chat's verified window; the folder name is a label, not a routing rule. Older flat-folder captures remain readable, and upgrading does not duplicate their queued startup jobs.

This is repeated monitoring of all selected chats, not simultaneous screen capture. A full rotation includes activation, capture, and any ready replies, then waits for the configured polling interval. Keep all selected windows open, unminimized, and at their latest messages, with the desktop unlocked. Do not type or move focus while it is running. Messages that scroll out of view between visits can still be missed.

**Stop / Ctrl+Shift+F12 stops all chats.** If any selected window becomes unavailable, changes identity/layout, or cannot be activated, the group pauses with pending work retained. Correct the problem and explicitly restart; reselect windows if they were closed/reopened. Existing receipts and uncertain-send review rules apply separately to each chat. Startup greetings, where part of the chosen workflow, are sent once per selected chat on each explicit start; ordinary Run Agent stays silent at startup.

The conversation list, screenshot label, extracted-text label, and activity log identify the chats. Inside **Activity**, select one of the three chat-name tabs to follow that chat's live capture, processing and reply events; every tab keeps updating even while hidden. **All activity** keeps the combined view and general application/upload events. Stop/pause status appears in every affected chat's log. Each view retains the latest 300 lines, and reading older lines does not force-scroll to the bottom. Tabs follow the selected chat identities, including chats with duplicate names; histories for retained selections survive reordering during this app session. **Review Replies** applies to all currently selected agent chats. Preview, history, local capture, and one-shot test tools use the first listed chat only. **Select Window** returns to single-chat selection. Saved selections do not automatically start replying after an app restart. This feature requires a build containing these changes; an already downloaded executable does not update itself.

## 기기위치조정/전원연결

The **기기위치조정/전원연결** button starts a continuous business workflow in the selected chat. It sends a short invitation, watches changed screenshots, extracts new participant requests, and queues later captures while the previous request runs. Send, for example, `이은경 / 헌릉로8길58 / 위치변경` or `김순옥 / 울진북로164 / 전원연결`.

In **Settings**, enter the **운영시트에이젠트 Nexgent URL** (the origin you open in your browser, without an API path), administrator username, and password. Enable Nexgent trusted LAN HTTP only for an HTTP LAN installation. The password is saved in Windows Credential Manager, scoped to the URL and username; `OPERATIONS_PASSWORD` can supply it instead. Keep the existing vision LLM settings. No Bizgo sender, recipient, or API key is required. Both device actions reply only in KakaoTalk and never send SMS, even if the separate Test Workflow's Bizgo option is enabled.

The LLM extracts a target name, address, and one action. Missing names/addresses/actions, ambiguous choices, and unrelated text get a Korean request to resend the name/address/action together; fields are not carried across participants. Both target name and address are required. The member update matches both and places the new dated entry before existing 일반 사항 text, preserving history and skipping an identical existing line. Several requests in one visible batch are handled in order, with one numbered KakaoTalk reply; screenshot extraction is limited to 1,200 characters and at most ten requests per batch.

The app authenticates through Nexgent `/auth/login`, reads `/api/me` for the administrator and CSRF checks, and posts `workflow_id: device_adjustment_power` to `/api/ax768/workflow/runs`. Before execution it checks that the deployed graph advertises prepend mode; an older replacing server is refused. It sends the parser-compatible form `주소 이름님 작업 신호확인요.` and leaves `confirmed_name` unset. This invokes the existing **real** signal/sheet/member-note workflow. The default operations timeout is 555 seconds. Needs-confirmation, disconnected, not-found, and failed results are returned to KakaoTalk. A verified completed result sends the completion template below in KakaoTalk. There is no Bizgo notification step for either action.

Verified completion replies use the target name in place of `OOO`. Power-connection requests use `전원연결` in place of `기기 위치변경`. Incomplete or uncertain operations keep their explanatory result instead of this success text.

```text
[자동 확인]
OOO님 기기 위치변경 후 기기신호 확인 완료입니다.
내용 기재해두었습니다.
감사합니다. :)
```

This mode has a separate queue identity from general Run Agent (auto), scoped to the note-placement policy and operations URL/account. Legacy Bizgo fields remain in its queue key solely to preserve access to existing pending captures. Durable plans and receipts prevent automatic repetition of API attempts after Stop/restart or uncertain outcomes. Existing SMS receipts are retained without retrying or sending any SMS. An interrupted API request may still finish on the server: check the operations sheet/member notes before manually resubmitting. Stop / Ctrl+Shift+F12 cancels further local actions; already submitted external actions cannot be recalled. The ordinary upload API is unrelated to this workflow.

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
2. In **Select Window** or **Select Agent Chats**, use **Pick chat** to select the foreground conversation by clicking its typing area during the countdown. KakaoTalkUI.exe windows use their Qt accessibility editor for capture geometry and replies across all workflows. Alternatively, choose a window from the list. Review the executable and title, and confirm the authorized conversation. All accessible titled windows are listed because the application does not assume a fixed KakaoTalk executable or title format. Likely KakaoTalk executables sort first.
3. No region selection is needed. Capture actions detect the area above the message box. **Send Test Reply** locates the message box directly. Old saved manual rectangles are replaced automatically. The message box must be visible and unambiguous; close search panels if detection reports an unsupported layout.
4. In **Settings**, optionally customize the automatically generated chat identifier. Configure the API URL and bearer token if uploads are desired. A blank URL enables local collection; it is not an API connectivity check.
5. Choose **Preview**. The agent minimizes itself and allows three seconds to bring the selected chat to the foreground. Restore the agent to inspect the preview; taking foreground focus pauses active monitoring.
6. Use **Scroll Up** and **Scroll Down** while stopped to establish that wheel events move the selected conversation and preserve overlap. These actions also queue captures as history.
7. Choose **Start / Resume** and bring the chat to the foreground within three seconds. The agent verifies the latest-message position before monitoring.
8. If bottom verification is inconclusive, manually move to the latest messages and use **Confirm Latest Position**. This is explicit operator confirmation, not proof inferred from a stationary image. Confirmation is invalidated after an interruption.

Keep the selected chat in the foreground, unobscured, and the Windows session unlocked. The GUI intentionally minimizes before capture-related actions. Capture/navigation does not activate or click windows. An explicit **Send Test Reply** request activates only the verified selected chat and focuses its verified message box automatically.

## Controls and recovery

The desktop workspace groups controls into five tabs. **Overview** contains the screenshot/incoming-text preview, **Run Agent (auto)**, and device operations; **Review Replies** is under **Incoming text**. **Capture** contains live capture, history, navigation, and local PNG controls. **Test tools** contains the reply, workflow, and Bizgo tests. **Storage / uploads** shows queue usage and upload recovery actions. **Activity** contains the event log. The selected conversation, current status, **Settings**, and **Stop** remain above the tabs.

The interface opens in Korean by default. To switch to English, open **설정 → 언어**, choose **English**, and select **설정 저장**. The change takes effect immediately and is saved for future launches.

Settings are grouped into **Capture**, **AI replies**, **Nexgent**, **Bizgo**, **Uploads**, and **Startup**. Scroll within a category to reach all its options; **Save settings** and **Cancel** remain visible. The screenshot preview keeps its aspect ratio when the window is resized.

### Check capture by saving a local PNG

1. Select the KakaoTalk window. A **Chat identifier** is generated if blank; optionally customize it in **Settings**, for example `test-chat`. This is your own label attached to screenshot metadata, not a KakaoTalk login or internal chat ID.
2. While stopped, click **Save Capture Locally** and bring the selected conversation to the foreground within three seconds. This takes one screenshot without scrolling, even if the image is unchanged.
3. Restore the agent and click **Open Captures Folder**. Open the newest PNG (sort by Date modified) to inspect it at full resolution. The activity log shows its exact filename.

Manual, test, live-capture, and history images are saved in `%LOCALAPPDATA%\KakaoCaptureAgent\captures\<group name>--<chat ID>\`. No API or token is required. **Save Capture Locally** always leaves its image unassigned to an API, even if an upload URL is configured. Existing images saved directly in `captures` remain available.

For continuous local collection, enable **Local-only mode: save PNGs and pause uploads** in Settings, then use **Start / Resume** or **Confirm Latest Position** as described above. Changed frames are saved at the configured interval; turn off **Detect visual changes** while stopped to save every interval. History captures also remain local. Existing uploads pause, although a request already in progress may finish.

Turning local-only mode off resumes previously assigned upload jobs; it does not automatically upload images saved locally. **Assign Local Captures to API** explicitly assigns all unassigned images, including manual test screenshots, for uploading. Local images are retained across restarts and are not automatically deleted by uploaded-image retention. They count toward the storage budget; capture pauses at capacity rather than discarding them.

| Control | Behavior |
|---|---|
| Start / Resume | Verifies the target and bottom position, then monitors changed content |
| Stop | Cancels pending GUI actions and stops capture/navigation; uploads continue |
| Save Capture Locally | Saves one PNG without scrolling or assigning it to an API; available while stopped or paused |
| Open Captures Folder | Opens the local PNG folder in File Explorer |
| Send Test Reply | Stops capture/navigation, activates the selected chat, replaces its message-box contents with your entered test message, and requests Enter once |
| Test Workflow | Saves the automatically detected conversation area, extracts text with the configured vision LLM, generates a simulated summary, and sends one `[test]` reply |
| Send Bizgo Sample | Sends one fixed sample using the Bizgo sender, recipient, key, and environment saved in Settings; no KakaoTalk/LLM setup required |
| Capture History | Pauses live capture, scans upward within the limit, and restores downward |
| Cancel History | Stops the upward scan and attempts bounded restoration |
| Ctrl+Shift+F12 | Global emergency stop, including while the GUI is minimized |
| Pointer at a primary-screen corner | PyAutoGUI fail-safe checked before wheel input and test replies |
| Retry Failed Uploads | Resets failed jobs for the currently configured destination and clears authentication pause |
| Assign Local Captures to API | Explicitly assigns all local/unassigned captures to the configured endpoint |

History and live scrolling run in the same worker, so they cannot overlap. History defaults to 50 steps, an 800 ms settle delay, and a minimum 30% overlap. The controller starts with one native wheel notch, measures vertical displacement, and adjusts up to the configured maximum of three notches. Poor overlap or uncertain motion stops the operation and records incomplete coverage.

Bottom verification first checks an exposed standard scrollbar. If unavailable, it requires previously observed wheel-induced movement and three settled downward attempts with negligible change. This is an approximate visual boundary, not message-level coverage. An explicitly confirmed latest position also permits stationary recovery checks until interrupted. Inconclusive restoration leaves monitoring paused.

Temporary focus loss, obstruction, or session unavailability pauses collection. Automatic recovery requires the same window identity, valid region, and successful bottom verification. Window closure, title changes, resizing, DPI changes, or ambiguous identity require explicit intervention. Use **Stop** to enable configuration and target selection again. The agent never silently substitutes another conversation.

If the status says **Bring the selected conversation to the foreground**, click the exact chat window chosen in Select Window and keep it active. Merely leaving it visible beside the agent is insufficient; inspecting the agent takes focus away from the chat. Recovery checks wait quietly while the same condition persists. For a one-shot test, click **Stop**, then **Save Capture Locally** (below the Preview/Scroll controls), and bring the chat forward during the three-second delay. If this still fails, reselect the conversation window rather than KakaoTalk's main contacts/chat-list window.

Closing the application stops navigation and waits for the current upload (bounded by the configured request deadline). Remaining jobs persist. Optional sign-in launch is configured in Settings; automatic monitoring at sign-in is a separate opt-in. A new KakaoTalk process/window after reboot requires reselection.

## Run Agent (auto): continuous screenshots and queued replies

Previously named **Auto Catch**, this button runs a repeating pipeline: **watch display changes → capture → extract requests → AX768 unified API → reply**. It runs until Stop, with no limit on the total number of messages or replies in a session. New captures join a persistent queue while earlier captures are being extracted or answered; queued jobs finish in capture order. The screenshot preview shows the latest captured change, the text preview shows the latest extracted incoming text, and the log reports each processing stage.

1. Open the intended KakaoTalk group at its latest messages.
2. Configure the LLM URL/model/key in **Settings** and enable vision support. The model must accept two images in one request. Under **Nexgent**, set the AX768 URL to `http://192.168.0.18:5173/agents/ax768`, administrator username/password, and enable trusted LAN HTTP. The origin or `/api/ax768/runs` URL also works. Neither 위치조정 nor 전원연결 sends Bizgo SMS or requires Bizgo credentials.
3. Click **Select Window**, select that conversation with the latest messages visible, then click **Run Agent (auto)**. The agent immediately captures and analyzes the single latest visible message while starting the watcher. An incoming request such as `위치조정/이은경/헌릉로8길58` already on screen can trigger its workflow. If the latest message is outgoing/automated, it does not search backwards for an older incoming request. Startup sends no introductory message and does not change the draft; the UI shows progress. A valid workflow result is replied to normally.
4. The agent captures the detected conversation area, saves meaningful changes, and queues before/after image pairs. The vision LLM extracts newly visible incoming text. For a message whose first line is **신규설치** or **가입자신규설치**, VoyagerI sends the complete form to the installation workflow described below. The agent checks each extracted participant message for device-position or power-connection keywords. A complete slash-separated command such as `위치조정/이은경/헌릉로8길58` goes directly to AX768. The keyword, name and road address can appear in any order. Ordinary chat is skipped locally. For free-form messages with relevant wording, such as “기기를 다른 곳으로 옮겼습니다”, the model checks intent and extracts the request fields. Outgoing, unrelated, cancelled, informational, incomplete or ambiguous requests are ignored without a workflow call or chat reply. Requests retain the full registered name (including prefixes such as `넥스터_이은경`), address, and exact action wording. The client checks source grounding and sends structured `action`, `name`, `address`, `action_text` and original `message` to `POST /api/ax768/runs` with `workflow_id: "device_adjustment_power"`. The server validates fields and completion receipts, and returns the exact KakaoTalk `response`, which the app sends unchanged. Model decisions and API receipts are saved separately to prevent duplicate execution on restart. Update both the backend and agent-server for rc.37; earlier server builds reject registered names containing underscores.
5. **Capture continues while the previous LLM request processes and during the reply cooldown.** Jobs process one at a time in capture order. Several messages appearing between captures can form one batch. Queue counts and submitted-reply counts appear in the status/log.
6. After a reply, Run Agent (auto) keeps watching automatically. **Stop** or **Ctrl+Shift+F12** cancels processing and retains unsent queued captures. Click Run Agent (auto) again to start each selected chat with one fresh screenshot. Earlier pending captures for that chat and API destination are retired when the new screenshot is saved. Application restart never starts sending automatically.

### Worksheet commands

Run Agent (auto) also routes the following incoming worksheet commands through
`POST /api/ax768/runs`. Keep each request in a single message bubble.

| Command | Fields after the command |
| --- | --- |
| 정보수정 | 이름/주소/새 연락처, or 항목/이름/주소/새 값 for 연락처, 생년월일, 이름 or 성별. Use 주소/이름/새 주소 for an address change. |
| 보호자 추가, 보호자 수정 | 가입자 주소/가입자 이름/보호자 이름/보호자 연락처/관계 |
| 기기교체 | 이름/주소/새 S/N |
| 기기회수, 기기분실, 설치확인 | 이름/주소 |
| 고장확인 | S/N |

Replacement, collection and fault reports use the visible sender of that bubble
as the manager. Live loss and fault reports use the capture date in Korea.
At startup and in a saved image, the date must be visible. The server returns
a clarification when required context is missing. Installation confirmation
reads the regional roster. Fault confirmation can take at least three minutes
when the device stays disconnected.

In a live chat, a verified guardian addition can return an app guide for the
new guardian. VoyagerI checks the phone number against the submitted command
and applies the same Bizgo routing and replay protection as new installation.
Run Image Test displays the API result and skips phone and Kakao delivery.

### 가입자신규설치 and Bizgo

An incoming bubble headed `신규설치` or `가입자신규설치` triggers the unified API with `workflow_id` set to `new_installation`. Keep the complete form visible in one message. VoyagerI passes its line breaks, manager, serial number (including leading zeros), subscriber details and guardian details through to the API.

### 신규설치 Kakao reply

VoyagerI formats the three ordered registration items from the unified API and
adds the guardian SMS result as item 4. The signal-confirmed heading requires
a fresh response from the registered device. A disconnected device or an
unverified signal gets its own heading. Only acceptance of all SMS parts for
all production recipients marks item 4 완료. Test numbers, sandbox sends and
uncertain sends have separate wording. Failed or blocked registrations show
the individual stage results and the agent's issue summary.

Under **Settings → Bizgo**, enter the registered sender number and API key. For verified registrations, VoyagerI sends the API’s full `sms.text` and `sms.title` to each guardian in `sms.recipients`, then posts the Kakao reply to the originating chat. Once Bizgo accepts every part for every production guardian number, item 4 reads `보호자 앱설치문자 발송 : 완료`. A blocked registration shows the API’s failure summary and item 4 reads `미발송`.

To test recipient routing, enter one or more comma-separated numbers in **Installation test numbers** and enable **Send installation and guardian-addition guides to test numbers only**. The guide goes only to those numbers. A test number matching a guardian stops the send for review. **Bizgo sandbox** is enabled by default. Clear it for delivery to real phones, including test phones. These settings affect phone delivery; the installation API still performs registration. The chat reply reports test routing, sandbox acceptance or an unconfirmed SMS outcome as applicable. An interrupted or uncertain send is retained for review to prevent duplicate messages.

Each explicit start checks the latest visible message before collecting further changes. Temporary focus recovery continues the current run.

Polling defaults to 0.5 seconds with a short debounce. Only the latest visible message is checked at startup; older history remains the baseline. Captures from this run are processed in order. Startup requests matching a retained API attempt in the same chat/destination are skipped, including uncertain attempts. This protection lasts for the metadata retention period; a new incoming message during monitoring can intentionally repeat the same text. Typing indicators, cosmetic changes, and the agent's own `[AI]` messages are classified and ignored. Configure polling and reply timing in Settings. The legacy response-suffix setting does not alter API replies. The agent does not scroll in this mode: keep the latest messages visible. Each generated workflow reply replaces the selected message box's contents; starting the watcher itself leaves the draft untouched. Existing drafts, leftover text, and the placeholder do not pause the queue. Each replacement is verified against the exact intended message before Enter is pressed.

Run Agent (auto) uses screenshots again; Windows accessibility and notification access are not required. The exact selected target is checked before capture and input. If it loses foreground focus, the agent attempts to reactivate that same chat. A locked desktop, invalid target, unavailable capture, or failed/partial input stops collection. An accepted Enter with unconfirmed composer clearing does not stop watching. Capture and inference can miss or misclassify messages; this is not a guaranteed incoming-message event feed. Brief sending operations also occupy the desktop worker.

Screenshots are saved under `%LOCALAPPDATA%\KakaoCaptureAgent\captures\auto_catch\<group name>--<chat ID>`. Their full paths appear in the activity log; **Open Captures Folder** opens the parent `captures` directory. Adjacent pairs in the same group share identical image files; different groups have separate copies. The persistent FIFO is the `image_reply_queue` table in `queue.db`, partitioned by chat and workflow destination. These images do not enter the ordinary upload queue or Bizgo workflow, but clicking Run Agent (auto) authorizes their transmission to the configured LLM even in local-only mode. Old native-text and generic-answer jobs remain separate and are not replayed as business requests. Unified jobs are scoped to the operations URL and account.

Pending and review jobs retain their images. Review items are set aside: they are never automatically resent and do not block later pending captures. The log reports their count separately from the active queue. A pending capture whose saved image is missing, changed, or invalid is moved to review, and watching and other jobs continue. Completed image jobs and unreferenced PNGs are cleaned at startup according to the metadata retention period (default 30 days). Storage capacity and a 1,000 active-capture limit stop collection visibly instead of discarding queued work. Review items do not use that active-job limit, but retained images still use disk space. Messages arriving after collection stops are not guaranteed to be captured.

Malformed or unclear vision analysis gets **at most three attempts per saved capture**, with 2- and 4-second delays before the retries. If the third attempt fails, that capture is retained for review and later queued captures proceed. This prevents a single unclear screenshot from blocking every subsequent message. Retry counts persist for the capture. A fresh run starts a new analysis budget. Logs distinguish ambiguous incoming/outgoing text, invalid analysis output, and captures classified as outgoing/AI or UI/no new incoming text. Network/authentication or reply-generation errors pause processing with pending work retained. Restart during inference returns unfinished work to pending; restart during a send marks it for review, preventing automatic resubmission.

After Windows accepts the Enter keypress, the sender observes the original verified composer for up to two seconds. Empty/whitespace readback and the exact `메시지 입력` placeholder count as an empty message box. Transient read failures retry observation only and appear as `Post-send observation` diagnostics. If clearing remains unconfirmed, Run Agent (auto) records the job as `submitted`, logs the observation, and keeps watching. That job is never replayed, including after restart; a later queued reply replaces any remaining composer contents with its own newly generated text. `submitted` means Enter was accepted, not that KakaoTalk delivery was independently confirmed.

Failed/partial input and interruption after writing starts still pause the current run and retain that attempt for review. On the next explicit start, that review item stays available while the fresh capture is processed. A crash during sending follows the same recovery rule. **Review Replies**, available while stopped or paused without automatic recovery, optionally marks set-aside items handled without resending them. Older releases that paused immediately with **A previous reply has uncertain delivery** can be upgraded without deleting `queue.db` or manually clearing those review items. On restart the agent checks the latest visible message.

Startup warnings about missing **upload queue** images refer to the separate capture/upload queue and do not block agent replies.

A focus or preparation check that fails before any draft write keeps the untouched job pending. Restore the chat, then explicitly restart Run Agent (auto) to process that job; no reply review is needed for that attempt. Partial draft writes still require review.

Worksheet commands carry the workflow ID, original message and `source: "kakao"`.
The server checks the requested workflow against the message, verifies the
agent-server capability and validates operation receipts before composing the reply.

API attempts and results are journaled separately from reply delivery. A timeout or Stop never triggers an automatic repeat of a potentially completed write. Inspect the operations sheet and member notes before manually submitting the same request again. Signal failure is not fabricated from an API error.

See the [server contract, exact reply templates and activation steps](../../nexgent/agents/docs/ax768-unified-kakaotalk-api.md).

**Test Workflow** and **Test Workflow 2** remain separate one-cycle tests.

## Test the unified workflow with a saved image

1. Stop any active monitoring and open **Test tools → Test unified workflow with an image**.
2. Drag one PNG, JPEG or BMP file onto the image preview, or click **Choose Capture Image**, and review the preview. Images must be at least 32 × 32 pixels, at most 16 megapixels, and at most 20 MiB before and after PNG conversion. The original file is not modified. Dropping only selects the image; click **Run Image Test** to start processing. Image selection is disabled while a test or monitoring is running.
3. Click **Run Image Test**. The same vision classifier used by Run Agent's startup reads **only the latest visible message**. Its extracted text appears beside the preview.
4. A supported incoming request goes through the same grounded action analysis and `POST /api/ax768/runs` workflow. For a single incoming form headed 신규설치 or 가입자신규설치, the test submits the full form to AX768 for registration. The API response appears unchanged in the read-only **Output** field, where it can be selected and copied. Outgoing, automated or unsupported messages show a no-action result; ambiguous images and failures show an explanation.

Choosing an image only previews it locally. Running the test sends it to the configured vision model and invokes the real unified API, which can update operational records. This is not the older simulated Test Workflow. It never activates KakaoTalk, captures the desktop, types into a composer, sends a chat reply, or sends SMS. The app stays visible while processing; no chat selection is required.

Repeated tests of the same image and operations URL/account reuse retained results and API receipts, including after restart. An interrupted API attempt is not automatically repeated. Choosing a different image processes that image rather than earlier pending test files. Saved-image jobs are separate from live-chat queues and can never be picked up for automatic chat replies. Imported PNG copies are stored in `captures/auto_catch/Image tests--<ID>`; completed results follow the existing metadata retention period (default 30 days).

**Stop / Ctrl+Shift+F12** cancels further processing. An API operation already submitted may still finish on the server; cancellation cannot undo its record updates. The result or cancellation message stays in **Output**.

## Test one capture → LLM → reply workflow

In **Settings**, configure the separate LLM connection using the same OpenAI-compatible API as `nexgent/agents`:

| Setting | Local server used for the synthetic image test |
|---|---|
| LLM base URL | `http://192.168.0.17:8000/v1` |
| Vision LLM model | `gemma-4-31b` |
| LLM API key | Your existing `OPENAI_API_KEY`; stored in Windows Credential Manager |
| Enable image input for this vision-capable LLM | Checked |
| Allow unencrypted LLM HTTP on trusted LAN/localhost | Checked for this HTTP address |
| Whole LLM workflow timeout | 120 seconds by default, configurable to 300 |

These are examples, not embedded server settings. The Windows PC must be able to reach the model server. The configured server passed a generated English image extraction/summary test on 2026-11-17; real Korean chat extraction still needs testing. Use HTTPS for non-local endpoints. HTTP requires the explicit LAN option and a private IP or localhost; it carries the image and key without encryption.

Save Settings, select the chat window, then click **Test Workflow** once. The agent stops monitoring, activates that same conversation, captures the region at its current scroll position, and saves its PNG in `%LOCALAPPDATA%\KakaoCaptureAgent\captures`. The activity log shows the exact file path. It makes two non-streaming `/v1/chat/completions` calls: an image-input request extracting visible message text, followed by a text request generating a simulated completion summary. It then focuses the verified composer, replaces its contents, and sends one message:

```text
[test]
-- What is done (simulation): A meeting agenda was prepared including project status and next steps.
-- User request (extracted text): Please prepare a meeting agenda.
```

The generated summary uses the source language where possible. The task described in the chat is **not actually performed**; this is only a test simulation. OCR is limited to the most recent complete messages fitting 1,200 characters, with a summary of at most 400 characters. Earlier `[test]` replies are excluded by the extraction prompt; this is model behavior, not guaranteed message-level filtering. Screenshot text is supplied as untrusted data and no model tools are available.

**Stop** / **Ctrl+Shift+F12** cancels a pending model request or send. The GUI remains responsive during inference. Errors, empty/unreadable text, malformed/truncated model responses, cancellation, or a changed target stop the cycle. There are no automatic model retries or reply retries. After one cycle, capture remains stopped. The final status reports whether the composer cleared; check the conversation for actual delivery. Local-only mode pauses the normal screenshot-upload queue; explicitly clicking **Test Workflow** still sends its screenshot to the configured LLM. Its saved PNG remains unassigned to the normal upload API.

Environment variables follow the agents adapter: `OPENAI_BASE_URL` takes precedence over `URL`, `OPENAI_MODEL` over `MODEL`, and these override saved LLM fields. `OPENAI_SUPPORTS_VISION` overrides the saved vision checkbox. `OPENAI_API_KEY` overrides the separately stored LLM credential. URL may be a server root, `/v1` base, or complete `/chat/completions` endpoint. The executable does not load another project's `.env` automatically and never bundles credentials. Set the key in Settings for double-click launches. The capture-upload token is not reused as the LLM key.

If an older release displays **Unable to save settings, credentials, or sign-in entry**, update to rc.14 or later and save the key again. The credential writer was passing bytes where pywin32 expects Unicode. Updated versions identify the exact failed save step (upload key, LLM key, sign-in entry, or configuration file) and include a numeric OS error where available; they never log the submitted key. Saving ordinary settings does not access the sign-in registry when startup remains disabled. If a later step fails, previously saved credentials may already have changed, while the new configuration is not applied.

## Add Bizgo SMS/LMS as the final workflow step

Open **Settings** and fill in:

- **Bizgo registered sender number**: a sender registered with your Bizgo account.
- **Sample / Test Workflow recipient**: the number to receive the test; editable and persisted across restarts. Neither number is hardcoded.
- **Bizgo API key**: the v2 integrated API key, saved separately in Windows Credential Manager. `BIZGO_API_KEY` can supply it instead.
- **Send Bizgo SMS/LMS after Test Workflow**: enables the last step of **Test Workflow**.
- **Bizgo sandbox: test requests only, no real phone delivery**: checked by default. Clear it to send actual SMS/LMS through production. The main window shows the environment and only the recipient's last four digits.

The Windows PC's public outbound IP must be allowlisted for the key in Bizgo. Sandbox uses the same key but does not deliver messages. These requirements and the two service hosts are documented in the [Bizgo API overview](https://developers.bizgo.io/api-sdk/api-reference).

To test the phone connection first, save Settings and click **Send Bizgo Sample**. This sends the fixed text `[test] Kakao Capture Agent Bizgo SMS test.` to the configured recipient, using the selected sandbox/production environment. It works even when the final workflow checkbox is off. It stops capture/navigation and stays stopped; no chat window, region, or LLM is needed for this sample.

For the full cycle, enable the final step and click **Test Workflow**. The agent saves the capture, extracts/summarizes with the LLM, submits the KakaoTalk reply, and waits for its composer to clear before requesting the phone-message copy. If the composer stays filled, focus changes, or Stop is requested, Bizgo is skipped. Composer clearing is an observation, not independent KakaoTalk delivery confirmation. Missing Bizgo settings/key stop the workflow before capture or chat input.

The adapter follows the [v2 SMS/LMS contract](https://developers.bizgo.io/en/api-sdk/api-reference/comm/mt): `POST /api/comm/v1/send/omni`, raw API key in `Authorization` (no `Bearer` prefix), one recipient and one message flow. It selects SMS up to 90 EUC-KR bytes and LMS beyond that. The phone copy replaces unsupported characters such as emoji with `?`; over 2,000 bytes is shortened with a visible suffix. These changes are announced in the activity log, and the full KakaoTalk reply stays intact. The LMS title is `[test] Workflow summary`; there are no image attachments or fallback channels.

Each request uses its capture/sample UUID as both `ref` and `idempotencyKey`, with `idempotencyTtl=86400`, following [Bizgo's idempotency guidance](https://developers.bizgo.io/en/api-sdk/sdk/send). It checks gateway, service, and recipient acceptance codes, matching recipient/reference, and message key. An accepted API request is **not final delivery**; check the Bizgo console/reports. The app does not poll or acknowledge delivery reports. Audit events retain the reference, environment, channel, and accepted message key without phone numbers, message text, or credentials.

There is one attempt and no automatic resend, fallback, or restart replay. Stop during an HTTP request cannot recall a message already accepted by Bizgo; a lost response is reported as uncertain. If Bizgo fails after the KakaoTalk reply, the error states that the chat reply was already requested. Inspect the previous result before clicking again: a new click is a new cycle and can send another message. Local-only capture mode does not disable these explicitly requested LLM/Bizgo actions.

## Test Workflow 2: reply to the next incoming message

1. Configure the same vision LLM URL, model, and key used by **Test Workflow**. The model must accept two images in one request.
2. Open the selected conversation at its **latest messages**. The area above the message box is detected automatically, including the visible message bubbles.
3. Click **Test Workflow 2: Reply to Next Message**. The app stops ordinary monitoring, activates that conversation, records a baseline in memory, and shows **WAITING_FOR_MESSAGE**.
4. Have another participant send a new text message. Keep the selected chat visible. The agent compares changed frames with the baseline, asks the vision model to identify new incoming text, generates a direct response in the message's language, and automatically sends **`[AI] ...response`** to that same chat.
5. The workflow stops after one reply. Click the button again for another test. **Stop** or **Ctrl+Shift+F12** cancels it.

This is visual detection, not a KakaoTalk incoming-message event API. Existing text is part of the baseline; outgoing replies, `[AI]` / `[test]` messages, and cosmetic changes are ignored. Uncertain classification pauses without sending. It can miss or misclassify messages, particularly during scrolling, animations, rapid arrivals, cropped bubbles, or ambiguous layouts. Do not scroll during this test. When several new messages appear together, it answers only the latest complete readable one. It does not promise exhaustive coverage.

The positive incoming screenshot is saved in `%LOCALAPPDATA%\KakaoCaptureAgent\captures`; its exact path appears in the log and **Open Captures Folder** opens the directory. Baseline and ignored frames stay in memory. Clicking this button authorizes sending before/after screenshots to the configured LLM even in local-only mode. Saved screenshots remain unassigned to the ordinary upload API. Workflow 2 has **no Bizgo step** and its response is conversational, not a simulated task-completion report. It cannot perform external tasks.

Settings include **Workflow 2 waiting limit** (default 300 seconds) and **Workflow 2 changed pixel fraction** (default 0.001). Polling uses the capture interval, with a short debounce independent of the normal change-detection toggle. Timeout is checked on polling and after model calls; an in-flight request remains cancellable and has the configured LLM timeout. No reply starts after the waiting deadline. Lost visibility, session lock, target changes, API failures, or failed sending stop this test without automatic recovery/retry. Restarting the app does not rearm it. Sending uses the existing verified composer and replaces its current contents, just like the other reply tests.

## Send an editable test reply

1. Select the intended KakaoTalk group window and check its title in the agent. No manual region or chat identifier is required.
2. Edit **Test reply message** in the main window, then click **Send Test Reply**. The default is `[AI가 답장드렸습니다]`; Korean text, emoji and multiple lines are supported, up to 2,000 characters. Empty messages and unsupported control characters are rejected. KakaoTalk must send on Enter.
3. The agent stops capture/navigation, requests activation of the verified chat before minimizing, then automatically locates and focuses its message box. No manual Stop, clearing, or chat/message-box click is needed; leave the mouse and keyboard alone during the operation.
4. The agent recognizes KakaoTalk’s native reply field or a unique writable multiline Edit/RichEdit control inside the selected window. The reply field can start above the midpoint when expanded. It checks the target, visibility, and focus, replaces the entire draft through an edit operation that notifies the client of the change, verifies the exact test text, and sends one native Enter keypress. It then observes the message box for up to two seconds and reports **message box cleared**, **text remains / send NOT confirmed**, or **delivery uncertain**. A cleared box is not independent proof of server delivery. Capture remains stopped afterward.

The last submitted test text is saved in local configuration and restored at launch. It does not change the generated responses used by Run Agent (auto) or the LLM workflows.

The button click authorizes replacement of existing message-box contents with your entered text; no additional confirmation dialog is shown. Existing text, whitespace, and leftover test drafts are replaced automatically. Ctrl+Shift+F12 or Stop cancels a pending action. Unsupported controls, changed focus, locked sessions, and mismatched targets stop the operation. A partial attempt may leave the test text as a draft. The agent never retries a send automatically or claims backend delivery based on an Enter request. Local-only mode governs screenshot uploads and does not disable an explicitly clicked test reply.

Text replacement uses targeted `EM_SETSEL` and `EM_REPLACESEL` operations so the client receives edit-change notifications; [Microsoft documents that `WM_SETTEXT` omits `EN_CHANGE` for multiline controls](https://learn.microsoft.com/en-us/windows/win32/controls/en-change). Enter uses a checked [Win32 `SendInput`](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput) scan-code down/up pair after revalidating cancellation, foreground, composer focus, and keyboard modifiers. The clipboard is not used. Native keyboard input goes to the foreground window, so leave the mouse and keyboard alone during sending; Windows does not make focus checks and input atomic. Failed/partial input is reported and never automatically retried.

After model inference, the worker allows up to one second for foreground activation and makes one temporary input-queue attachment attempt if the initial request fails. It detaches before typing, rechecks the exact selected window, and stops if Windows still denies focus. This uses the documented [AttachThreadInput API](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-attachthreadinput), without changing system foreground settings or injecting an Alt key. A locked desktop, changed target, or overlapping dialog still blocks capture/input. Zero or multiple eligible controls also stop sending. In that case, the activity log includes bounded **Composer diagnostic** lines with control classes, style flags, and rejection reasons, never message/draft contents. Share those lines to diagnose an unsupported client control. KakaoTalk client versions with different/custom controls or Enter behavior need manual validation; the agent fails closed instead of guessing coordinates. The window can scroll vertically on smaller displays to keep the controls accessible.

Sending a test reply does not require starting monitoring or proving the bottom position. Click **Send Test Reply** once; any capture/navigation is stopped automatically. For capture-only monitoring at the latest messages, position the chat there manually and use **Confirm Latest Position** if automatic bottom verification is inconclusive. Missing queued-image warnings concern older local PNGs that are absent from disk; they do not block replies. Restore the original files to their recorded paths if those captures must still be uploaded; the agent cannot recreate missing screenshots.

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

The backend must authenticate the sender, validate payloads, persist before acknowledgement, and deduplicate by capture ID. The upload client verifies TLS, does not follow redirects, and disables implicit environment proxy configuration. Upload HTTP is accepted only for an explicitly enabled literal loopback address. Normal capture interpretation and message-level deduplication belong to the backend. The separate Test Workflow LLM connection follows the settings above.

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
| Local-only mode | Disabled; a blank API URL also leaves new captures local |

Data layout:

```text
%LOCALAPPDATA%\KakaoCaptureAgent\
  config.json          Configuration, last test message, and detected window-relative geometry
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

The output is **`dist\VoyagerI.exe`**, a single executable that can be copied to a Windows PC without Python installed. The build includes a per-monitor DPI manifest and SQLite schema. Build on Windows; [PyInstaller is not a cross-compiler](https://pyinstaller.org/en/stable/). Do not copy a Linux virtual environment to Windows; create a new environment there.

## Publishing a GitHub Release

The repository workflow `.github/workflows/kakao-capture-release.yml` runs on GitHub's Windows runner when a tag matching `kakao-capture-agent-v*` is pushed. It tests the code, builds the single executable, checks packaged startup using synthetic data, calculates SHA-256, and publishes the executable/checksum as a GitHub prerelease. It never captures a conversation or sends mouse input during the startup check.

After committing the intended source revision, create a new, unused release tag, for example:

```powershell
git tag kakao-capture-agent-v0.1.0-rc.1
git push origin kakao-capture-agent-v0.1.0-rc.1
```

Use a new tag for each build; do not move published release tags. Review the Actions run and the release's `self-test.json` asset before distributing the build. Tag builds publish the EXE, checksum and startup report directly as release assets without a duplicate Actions artifact upload, so Actions artifact-storage quotas do not block publication. Update `RELEASE_NOTES.md` for subsequent releases. The workflow uses GitHub's repository-scoped token with release permission; no personal access token needs to be stored as a workflow secret. Manual workflow dispatch builds an Actions artifact without publishing when run from a branch; its availability in the Actions UI depends on the workflow being present on the repository's default branch.

Implementation modules follow the PRD: GUI on the Qt thread; capture and scrolling on one automation thread; asynchronous HTTP in an independent worker; SQLite operations under a shared lock with separate connections. Business logic can be tested with injected desktop/capture/HTTP adapters.

## Known limits and implementation decisions

- Screen pixels cannot establish message identities or exhaustive history. Fast arrivals, dynamic loading, animations, blank regions, and interruptions can leave gaps. Audit events and history outcomes record uncertainty.
- Visibility and input checks are conservative and happen before and after actions. Windows does not make these checks atomic with desktop capture/input; extremely brief overlays or focus changes can race them. In-window custom content cannot be classified without message/UI interpretation. Use the dedicated PC and an explicitly selected message area.
- Window titles are matched exactly to avoid switching chats. If KakaoTalk changes the title for unread counts or other reasons, reselect the window. Cross-process/window recreation is never automatically rebound.
- Settings and target changes require Stop. GUI interaction takes focus away from KakaoTalk: ordinary capture pauses, while continuous workflows attempt to reactivate their selected chats. There is no tray interface in this release.
- Only standard scrollbar position is read; custom KakaoTalk controls use the measured visual fallback. Bottom position and overlap must be calibrated against the installed client. Uncertain checks remain paused.
- Native Win32 `SendInput` emits one 120-unit wheel notch and verifies success. PyAutoGUI supplies the mouse fail-safe. This deliberately replaces its wheel helper because [the Windows implementation passes raw wheel data and suppresses some OS input errors](https://github.com/asweigart/pyautogui/blob/master/pyautogui/_pyautogui_win.py).
- Automatic geometry uses native physical client/control coordinates and Windows DPI. Resizing or a DPI change during an active workflow pauses it; Stop and restart the action to detect the new area. Real mixed-DPI behavior remains a manual acceptance check.
- Dependency versions have bounded ranges; the tested versions are recorded in `TESTING.md`. Packaging and runtime compatibility must be confirmed on the target Python/Windows combination before unattended use.
