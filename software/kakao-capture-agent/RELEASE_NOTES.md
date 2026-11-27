Download `VoyagerI-v<VERSION>-windows-x64.exe` from Assets and double-click it on Windows 10/11 (64-bit). Python, uv, and a separate installation step are not required. First launch may take a moment while bundled libraries unpack.

## v0.1.0-rc.55 — 2026-11-27

Vision requests now enlarge the complete screenshot to twice its width and height before sending it to the configured model. This applies to startup snapshots, before/after comparisons, saved-image analysis and Test Workflow. Original captures and previews remain unchanged; no message cropping is applied.

The supplied screenshot was checked through the actual application code with `gemma-4-31b`: the 748×1268 image returned the correct `영덕대게로` spelling. This is one successful sample, not a guarantee of OCR accuracy.

The current unified API responses passed desktop compatibility checks for all supported workflows, including blocked collection and skipped loss AS steps. API text is preserved, and SMS decisions continue to follow the existing contract. Response parsing loads image-processing libraries only when vision preprocessing is used.

## v0.1.0-rc.54 — 2026-11-26

Device slash commands now use the web workbench's request directly: `workflow_id`, original `message`, and `confirmed_name: null`. Run Agent and device mode skip a second LLM parse of these commands. For a device response with `ok: true`, the exact `response` text is sent; the desktop no longer independently checks completion receipts or requires a duplicate `kakao-reply` field. Reply text limits and one-attempt delivery tracking remain in place.

Continuous watching now captures changed frames while keyword screening is busy. Frames are screened in order from a bounded temporary memory buffer; only incoming action-keyword matches are saved and queued as workflows. Ordinary messages do not create workflow tasks. Slow API calls and a failed API attempt do not prevent later matched requests from being processed in order.

Temporary focus loss before typing keeps the prepared reply for recovery without repeating the API operation. In multi-chat mode, other selected chats keep running while the affected chat retries focus.

Restarting Run Agent archives old review captures as history and clears pending work for the selected chat before checking its latest visible message. Archived captures retain their evidence and are never replayed. Their counts no longer appear in the new run.

Failed screenshot analysis keeps the last successfully screened message baseline for the next display change. Activity now reports when screening starts and when no incoming action keyword is found. The status shows screening time while analysis is running.

An **API Responses** tab next to Activity displays the last 50 AX768 response bodies as formatted JSON, with chat, timestamp and HTTP status, plus copy and clear controls. It includes invalid response contracts and HTTP error bodies; authentication responses and headers are excluded. Live chats, device mode and saved-image tests share this view.

## v0.1.0-rc.53 — 2026-11-26

AX768 replies now follow the unified response contract. The client requires an execution ID, consistent `status`/`ok`/`verified`, matching nonempty `response` and `kakao-reply` strings, and structured issues for unsuccessful outcomes. Business failures are sent unchanged, including partial completion and unknown-write wording. A legitimately skipped AS row does not turn a completed workflow into a failure.

Each operation records its job ID, original request, API execution ID, full response, exact outgoing text, and observed chat submission outcome. Resumed API attempts never replay saved messages; new identical incoming messages execute independently. Device mode uses the unified endpoint and sends no greeting.

Installation and guardian addition append only the authorized SMS outcome observed by the client: provider acceptance, test-number routing, sandbox acceptance, or uncertainty. Provider acceptance is described as request acceptance, not confirmed phone delivery. The complete reply including its SMS notice must fit 2,000 characters; longer replies are retained for review without being sent.

**Backend compatibility:** the unified API must provide the fields above. Installation `kakao-reply` must be a complete string; stage lists belong in receipts. Missing or inconsistent envelopes stay in the activity log and produce no chat reply.

## v0.1.0-rc.52 — 2026-11-26

Each click on **Run Agent (auto)** or **Restart Agent (auto)** clears unfinished tasks in each selected chat and reads its current screenshot. If the latest visible message is an incoming action request, VoyagerI starts its workflow even if a previous run attempted the same message. A previously submitted API call or message may still complete.

The agent then watches each selected chat for new action keywords and processes matching messages in arrival order. Messages awaiting delivery review stay in the review list.

## v0.1.0-rc.51 — 2026-11-26

Run Agent checks changed chat frames in memory. It saves a screenshot and queues a workflow only when a newly received participant message contains a supported action keyword. Slash commands accept the action keyword first, in the middle, or last. Keep the other worksheet fields in their expected order.

Each selected chat processes its own requests in arrival order. Separate bubbles with identical commands get separate jobs, including when KakaoTalk hides a repeated sender label. Restarting a multi-window run resumes pending requests for those chats. Messages that scroll out of view between readings can still be missed.

## v0.1.0-rc.50 — 2026-11-25

**Run Agent (auto)** recognizes the Kakao worksheet commands for information updates, guardian additions and corrections, device replacement, collection, loss, installation lookup and fault confirmation. It sends the original message and matching workflow ID to the AX768 unified API. These commands require the matching Nexgent backend and agent-server update.

Verified guardian additions use the configured Bizgo routing. The desktop checks the recipient against the incoming command and records the SMS attempt before sending. **Run Image Test** displays the API result and skips chat and phone delivery.

When a new installation is held for a disconnected device, the reply asks for a power check and lists the held steps. Other incomplete installations show the recorded issue summary.

## v0.1.0-rc.49 — 2026-11-25

Each click on **Run Agent (auto)** starts with a fresh screenshot of each selected chat. The latest visible incoming request is processed first. Pending captures from earlier runs leave the active queue. Existing workflow receipts still prevent a repeated registration or reply on restart.

**Run Image Test** now submits a complete incoming 신규설치 form to AX768 and displays the registration result. The test can update registration records and sends no chat reply or guardian SMS. Reopening an image previously skipped for this issue rechecks the form if no API call was attempted.

## v0.1.0-rc.48 — 2026-11-25

Run Agent (auto) checks extracted incoming messages for device-action keywords. A complete command such as `위치조정/이은경/헌릉로8길58` goes directly to AX768. Ordinary chat is skipped locally. The agent checks intent for free-form messages that mention a supported action.

Malformed or incomplete LLM analysis responses now use the capture queue’s three-attempt limit. After the third failure, the agent retains the capture for review and processes the remaining queue in order.

## v0.1.0-rc.47 — 2026-11-25

When the AX768 API returns structured 신규설치 results, the Kakao reply lists the subscriber roster, device inventory, master-page registration, and guardian SMS status. Item 4 shows `보호자 앱설치문자 발송 : 완료` after Bizgo accepts every part for every production guardian number. Blocked or failed registrations show the individual stage results and the issue summary.

The reply heading reports device signal confirmation when the API supplies that result. Older API responses still use the text reply format.

## v0.1.0-rc.46 — 2026-11-25

VoyagerI opens in Korean by default. To switch to English, open **설정 → 언어**, choose **English**, and click **설정 저장**. The interface updates immediately and remembers the selection.

For 신규설치 registrations, once Bizgo accepts every part of the installation guide for every production guardian number, the Kakao reply says “보호자님께 앱 설치 안내 문자를 성공적으로 발송했습니다.” and lists the last four digits of each guardian number. Sandbox runs, test-number sends, and unconfirmed sends have their own status messages.

## v0.1.0-rc.45 — 2026-11-24

**Run Agent (auto)** recognizes incoming forms headed `신규설치` or `가입자신규설치` and sends the complete form to the updated AX768 unified API. For verified registrations, VoyagerI sends the API’s installation guide through Bizgo and replies in the originating KakaoTalk chat. Blocked registrations use the API’s Kakao reply and skip SMS. Existing 위치조정 and 전원연결 requests continue to use the device workflow.

To redirect installation guides, open **Settings → Bizgo**, enable **Test Bizgo SMS for 신규설치**, and enter comma-separated installation test numbers. For delivery to those phones, clear **Bizgo sandbox**. Registration still runs when testing SMS routing. The chat reply identifies redirected, sandbox, or unconfirmed sends.

## v0.1.0-rc.44 — 2026-11-24

**KakaoTalkUI conversation windows.** Select Window and Select Agent Chats now include Pick chat. Click the intended conversation and review its title, program name and window handle before confirming. For KakaoTalkUI.exe, VoyagerI uses Windows accessibility to locate the Qt message box, derive the conversation area for capture and monitoring, and verify drafts before sending replies. This applies to every selected conversation, including each window in a multi-chat run.

## v0.1.0-rc.42 — 2026-11-24

**Send Test Reply** now finds the selected chat’s message box directly. Previously it could focus the chat and pause with “Cannot identify one message box below the conversation” before typing. The test now works with an expanded composer above the midpoint and recognizes KakaoTalk’s native RichEdit reply field when another editor is present. Activity lists control details if the editor cannot be identified. The sender verifies focus and the exact draft before pressing Enter once.

## v0.1.0-rc.41 — 2026-11-23

**Live logs for each chat.** Activity now has a named tab for each selected KakaoTalk chat, plus All activity for the combined stream. Hidden tabs continue updating. Capture, processing and reply events follow each chat's stable identity, even when titles are identical. Stop/Pause appears in every affected chat's log. Each view keeps the latest 300 lines and preserves your position when reading earlier events.

**Drag-and-drop image tests.** Drop one PNG, JPEG or BMP onto the Test tools preview, or use Choose Capture Image. Both methods use the same validation and unified API workflow. Dropping selects and previews the image; click Run Image Test to process it. Invalid files preserve the previous selection, and replacement is disabled during an active run. Test output stays in the app; no KakaoTalk reply or SMS is sent.

The full Linux suite passed 573 tests, with 24 Windows-only checks skipped. Windows tests and source/packaged startup checks must pass before publication. Real KakaoTalk operation and native Explorer dragging still require an on-device check. No additional backend change is needed for these UI features; the rc.39 server update remains necessary for the revised missing-roster response.

## v0.1.0-rc.40 — 2026-11-23

Includes the rc.39 application changes below. Tag builds now publish the EXE, SHA-256 checksum and `self-test.json` directly as GitHub release assets, without a duplicate Actions artifact upload. This avoids the Actions artifact-storage quota that blocked rc.39 publication after all 587 Windows tests, EXE packaging and startup checks had passed. Manual branch builds continue to produce Actions artifacts.

## v0.1.0-rc.39 — 2026-11-23 (build passed; publication blocked)

**Monitor up to three chats.** Select one to three KakaoTalk windows and run the same device workflow for each. Each chat has its own queue and inference worker; desktop capture and reply input rotate through verified windows. Activity entries identify the chat, and replies return to their originating conversation. Stop cancels all chats; a window failure pauses the group. Activity remains one shared log with chat labels.

**Capture folders by chat name.** Automatic and manual captures now use separate folders named after the conversation, with a short stable ID to distinguish duplicate names. Korean names are preserved. Existing flat-folder captures and retained queues remain readable after upgrading.

**Test a saved image.** In Test tools, choose a PNG, JPEG or BMP and click Run Image Test. VoyagerI runs the same extraction, structured action analysis and unified API workflow, then displays the exact response in Output without sending a KakaoTalk reply or SMS. The API can still update operational records. Repeating the same image reuses its saved result to avoid repeating actions.

**Missing-roster reply.** The accompanying backend change returns the named signal-unconfirmed message when no roster row matches, while preserving the internal not_found status and skipped-write receipts. Both automatic replies and image tests use the server response unchanged. Update/restart the Nexgent backend from this revision to enable this wording; the EXE alone cannot change server responses. Previously cached test outputs retain their original text; use a new capture to verify the updated backend.

The supported business actions remain 기기위치조정 and 전원연결. This prerelease uses automated tests and synthetic Windows startup checks; real three-window KakaoTalk operation still needs validation on the target PC.

## v0.1.0-rc.38 — 2026-11-20

**Process the latest message immediately on Run Agent.** Startup now saves one snapshot and checks only the latest visible message. An incoming action request already on screen, such as `위치조정/이은경/헌릉로8길58`, can run through structured analysis → unified API → exact API reply without waiting for a screen change. An outgoing/automated latest message, unrelated text, or unclear direction does not trigger an older request. Startup still sends no introduction; the UI reports its progress. Continuous before/after watching continues while startup analysis runs.

**Restart protection.** Startup snapshots retain their analysis mode across Stop/restart and are not enqueued twice for an identical screen. A startup request with a retained API attempt in the same chat/destination is skipped even if cosmetic screen changes produce another image. A genuinely new incoming message during monitoring can repeat the same request. This startup protection lasts for the configured capture-metadata retention period.

**Shorthand requests and diagnostics.** The semantic action prompt explicitly accepts bare action/name/address requests, leading whitespace and compact road addresses without requiring a verb or province/city. An ignored action decision now logs the extraction length and points to the extracted-text panel. This client update needs no additional server change beyond the rc.37 server updates. No Bizgo SMS is sent for these workflows.

Validation uses synthetic captures and mocked model/API responses; classification on the user's configured vision model and actual KakaoTalk layout still needs an on-device check.

## v0.1.0-rc.37 — 2026-11-20

**Agent-interpreted structured requests.** Run Agent uses the model to decide whether received text requests device repositioning or power connection, including equivalent wording without exact keywords/slash format. It extracts and sends `action`, full `name`, `address`, `action_text` evidence and original `message` to the unified API. Unrelated, cancelled, incomplete and ambiguous model decisions do not call the workflow. Outgoing messages remain ignored; startup is silent and neither device action sends SMS.

**Full registered-name fix.** Both server parsers now preserve names such as `넥스터_이은경` instead of rejecting the underscore or stripping the prefix. Rebuild **agent-server** and update/restart **backend** before using this version. Model extraction is validated against the source text; successful replies still require verified workflow receipts.

## v0.1.0-rc.36 — 2026-11-20

**No device-workflow SMS.** 위치조정 and 전원연결 reply only in KakaoTalk. Removed the older device button's Bizgo notification step and credential requirement as well. Existing SMS receipts are not replayed. The separate Bizgo sample and optional generic Test Workflow SMS tools keep their own behavior.

**Incoming action keywords only.** Run Agent acts only on received messages containing `위치조정` or `전원연결`, including their `기기` prefixes. Outgoing messages, ordinary conversation, and other actions are ignored without an API call or reply. Mixed batches and resumed saved plans use the same filter; saved per-request receipts prevent repeating actions. A single message containing both actions is ignored rather than guessing. Startup remains silent and the UI explains the active keywords.

The unified API payload explicitly selects `device_adjustment_power` (기기위치조정/전원연결) and an `action` of `기기위치조정` or `전원연결`. The backend normalizes slash-separated name/address/action fields in any order and refuses mismatched actions. Power success now uses the exact `OOO님 기기 전원연결 후 기기신호 확인 완료입니다.` server template. Update/restart the backend before using the updated client; no new agent-server graph build is required beyond the previous unified API setup.

## v0.1.0-rc.35 — 2026-11-20

**Silent Run Agent startup.** Clicking Run Agent (auto), including after Stop, begins watching without sending an introductory chat message or clearing the draft. The app shows Watching and Watching for new messages. Normal workflow replies continue after processing incoming requests.

**New VoyagerI logo.** An ivory spacecraft/V and mint navigation star on midnight navy replace the previous yellow logo in the app, taskbar and executable. This is a desktop-only update; no additional Agent Server change is required beyond rc.34 setup.

## v0.1.0-rc.34 — 2026-11-20

**New name: VoyagerI.** A custom chat/relay/checkmark logo replaces the letter badge and default window/taskbar icon. Windows builds produce `VoyagerI.exe` with embedded multi-resolution icons and product metadata. Existing settings, captures and credentials remain available. Restart with the updated build; old pinned shortcuts may need to be replaced.

**Run Agent (auto) now runs AX768 workflows.** New captured requests go to one authenticated `/api/ax768/runs` endpoint. 위치조정/name/address fields can appear in any slash-separated order. The server owns dispatch, verified success/disconnected templates, and the exact chat response. No Bizgo settings are required for auto mode. Existing case APIs and the separate device/Bizgo button remain supported. Update the Windows app and activate the [server changes](https://github.com/prof-lijar/ax-project/blob/kakao-capture-agent-v0.1.0-rc.34/nexgent/agents/docs/ax768-unified-kakaotalk-api.md) before using auto mode.

## v0.1.0-rc.33

**Cleaner desktop workspace.** A light theme with yellow accents, consistent typography, and grouped cards replaces the long control column. Overview, Capture, Test tools, Storage / uploads, and Activity tabs organize the controls. Conversation selection, status, Settings, and Stop stay visible above the tabs. Screenshot and incoming-text previews share a panel; screenshots retain their aspect ratio when resized. Settings are grouped by service and purpose, with Save and Cancel always visible.

**Updated device completion replies.** Verified location-change completion sends this exact template, with the target person's name replacing `OOO`:

```text
[자동 확인]
OOO님 기기 위치변경 후 기기신호 확인 완료입니다.
내용 기재해두었습니다.
감사합니다. :)
```

Power-connection requests use `전원연결` instead of `기기 위치변경`. The generic auto-reply suffix is not appended to device replies. Incomplete or uncertain operations retain their explanatory result instead of claiming success. Bizgo acceptance and uncertainty remain in the activity log and durable receipts. The new `[자동 확인]` prefix is excluded from incoming-message processing to prevent reply loops. Existing stored replies retain their journaled content on resume.

Capture, workflow execution, queue persistence, credential storage, and Stop behavior remain compatible with existing configuration. The Nexgent `prepend` runtime capability required by rc.32 is still required. This remains a prerelease pending real Windows/KakaoTalk acceptance checks.

## v0.1.0-rc.32

**일반 사항: new entry first, existing text preserved.** The device workflow now matches name and address while accepting the verified region's administrative prefix (for example, `금강송면 왕피길 83-15` and `울진군 금강송면 왕피길 83-15`). Different towns, counties or house numbers remain rejected. The dated entry is inserted on the first line of 일반 사항; identical existing lines are not duplicated. 설치 정보 is not modified.

The desktop requires both name and address and checks the runtime's `prepend` capability before executing the workflow. Update Nexgent Agent Server and the backend/frontend receipt validators using [these activation instructions](https://github.com/prof-lijar/ax-project/blob/kakao-capture-agent-v0.1.0-rc.32/nexgent/agents/docs/device-workflow-first-line-notes-and-address-matching.md). This runtime activation needs administrator access and has not been performed automatically. Older note-writing runtimes are refused.

## v0.1.0-rc.31 (build cancelled; superseded by rc.32)

**Device requests require name and address.** Missing either field, or the requested action, produces a clarification reply without calling the operations API. The updated operations workflow matches both name and address and appends its dated entry to the final line of 일반 사항, preserving history and avoiding duplicate lines.

The desktop verifies the server's append capability before workflow execution and refuses older replacing runtimes. Update/rebuild Nexgent Agent Server before using this mode; see [activation instructions](https://github.com/prof-lijar/ax-project/blob/kakao-capture-agent-v0.1.0-rc.31/nexgent/agents/docs/device-workflow-append-general-notes.md). Existing older business captures are kept separate from requests captured under the new policy. General Run Agent (auto) behavior is unchanged.

## v0.1.0-rc.30

**New: 기기위치조정/전원연결.** A dedicated button continuously watches incoming requests, extracts the target name/address/action, and asks for clarification when needed. Complete requests call 운영시트에이젠트's existing `device_adjustment_power` API. Verified completion sends a fixed success-test notification to the configured Bizgo number, then replies with the returned result in KakaoTalk. Later captures queue while a request is processing.

Configure the Nexgent origin URL, administrator username, and password in Settings, alongside the existing LLM and Bizgo settings. The password is stored in Windows Credential Manager. Sandbox/production follows your existing Bizgo setting; sandbox does not deliver a phone message. This button invokes the real operations workflow and includes Bizgo on success even if the optional Bizgo checkbox for the older Test Workflow is off.

The business queue is separate from general replies and bound to its configured destinations. Persisted action receipts prevent automatically repeating an API or SMS attempt after interruption. Unverified or failed results never produce a success notification. API/Bizgo uncertainty is reported in the KakaoTalk reply, and later requests continue. Clarification replies ask participants to resend their full name/address/action together.

Automated coverage uses mocked services. Live Nexgent access, operations updates, actual screenshot interpretation, and real Bizgo/KakaoTalk delivery still require the configured Windows test.

## v0.1.0-rc.29

**Fixed: one successful reply followed by an endlessly stalled queue.** A capture with ambiguous or malformed text extraction could retry forever at the front of the queue, blocking every later message. Each capture now gets at most three analysis attempts; an unresolved capture is retained for review and later queued captures proceed. Attempts survive restart, and existing entries with three or more failures are set aside immediately after updating, without another model call.

Analysis logs now identify ambiguous message boundaries or invalid-output categories. Ignored captures are labeled separately as outgoing/AI or UI/no new incoming text. Reply content and raw model output are not included in these diagnostics. The change does not retry uncertain sends or discard the unresolved screenshots.

## v0.1.0-rc.28

**Old review items no longer stop Run Agent (auto).** Existing uncertain attempts remain saved for review and are never automatically resent, while pending and new captures continue through extraction, LLM processing, and replies in order. No queue deletion or manual Review Replies step is needed to start watching again after updating.

Missing, changed, or invalid saved screenshots are set aside individually instead of pausing the whole watcher. The log distinguishes active queued captures from items set aside for review. Review items do not consume the 1,000 active-capture limit, although retained images still use storage. A new failed/partial keyboard operation can still pause the current run; its review item will not block later work after an explicit restart.

Missing-image warnings from the separate upload queue now identify that queue explicitly. Messages received while the agent was paused are not recovered unless already captured; send a fresh participant message after restarting.

## v0.1.0-rc.27

**Run Agent (auto) clears existing composer contents and continues.** The startup greeting and each subsequent generated reply replace the selected message box's contents, including the `메시지 입력` placeholder, real drafts, and leftover text. Manual clearing is no longer required. The exact new text is verified before Enter is sent; target, focus, cancellation, and partial-input checks remain in effect.

Post-send observation recognizes the exact Korean input placeholder as an empty composer. An accepted but unconfirmed submission is never replayed; later queued replies replace remaining composer contents with their own generated message. Continuous capture, FIFO processing, the startup greeting, and Stop behavior are unchanged.

## v0.1.0-rc.26

**Run Agent (auto) now initiates the conversation.** Each explicit start sends the exact message `[AI 테스트 보내보시지요!` once, then continuously watches incoming messages and runs capture → extraction → LLM processing → queued replies as before. The startup message has no response suffix, is excluded from incoming-message analysis, and is not repeated by polling or focus recovery. The composer must be empty. Failed/interrupted startup sends are not automatically retried.

The baseline is captured before sending the greeting so a participant response during submission observation is still detected. Pending captures remain queued across Stop/restart; each explicit restart sends a fresh greeting before resuming them.

## v0.1.0-rc.25

- **Run Agent (auto)** continuously watches chat display changes, captures them, extracts incoming text, processes it with the LLM, and replies in capture order until Stop.
- New captures queue while earlier extraction or reply generation is running. There is no session message-count limit; pending work survives Stop and restart.
- The interface shows extracted text and logs extraction, processing, and reply stages.
- **Review Replies** works directly from a paused state without automatic recovery. Attempts refused before typing remain pending; partial or uncertain sends still require review.

Screen polling can combine closely timed messages into one captured batch. UI-only changes and outgoing AI messages are ignored. Existing settings and saved queues remain compatible.

## Changes and earlier release notes

**Auto Catch is now Run Agent (auto).** It watches the selected conversation for display changes and repeats capture → text extraction → LLM processing → reply. New captures are saved and queued even while an earlier extraction or answer is still running. Jobs are processed and replied to in capture order. The interface now shows extracted incoming text and logs extraction, processing, and reply stages. Existing settings, capture files, and pending queues are preserved. UI-only changes and the agent's own outgoing messages remain excluded to prevent reply loops.

**Select Window is now the only chat-area setup.** Select Region and its drag overlay have been removed. Preview, local capture, live monitoring, history/manual scrolling, Send Test Reply, both test workflows, and Auto Catch use the automatically detected area above the selected chat's message box. Each new action replaces any saved manual crop and generates a chat identifier if blank. Unsupported or ambiguous layouts stop with guidance to select the actual chat window and close search panels. Service credentials/settings remain required for features that use them.

**Send Test Reply is editable.** Enter your own Korean, emoji, or multiline message in the main window (up to 2,000 characters), then click Send Test Reply. The default is `[AI가 답장드렸습니다]`. The last submitted text is saved locally; LLM-generated responses are unaffected. Stop still cancels a pending action, and a send is never automatically repeated.

**Fixed: Auto Catch pauses after the first visible reply.** Once Windows accepts Enter, an inconclusive composer-clearing observation no longer stops watching. That job is recorded as submitted and is never resent; later incoming captures continue through the queue. Each new Auto Catch reply requires a freshly verified empty message box, so a leftover reply/draft is not overwritten. Transient post-send read failures retry observation only, with diagnostic reasons in the log. Delivery is still not independently verified.

**Fixed: recovery from an immediate Auto Catch queue pause.** The uncertain-delivery message now names the recovery controls, and **Review Replies** is available directly while safely paused. Inspect the selected chat and draft, click **Review Replies**, confirm marking the old attempts handled without resending, then click **Auto Catch**. Other pending captures remain. On older builds, click **Stop** before Review Replies. Failed/partial keyboard input and crashes during sending still require review.

An empty-composer or focus check that refuses a reply before writing now leaves that job pending instead of incorrectly marking delivery uncertain. Clear the draft or restore the chat and explicitly restart Auto Catch to resume it. Once a draft write begins, failures still require review to avoid replaying partial input.

**Auto Catch returns to screenshots, with continuous collection and a persistent reply queue.** Select the open group and click Auto Catch. Changed frames are saved as before/after pairs while the vision LLM handles earlier work. Replies are submitted sequentially as `[AI] response (자동 응답)`, and watching continues after each reply. Windows accessibility and notification readers are not needed.

**Incoming changes queue while the previous request is processing.** A durable SQLite FIFO and local PNGs retain later captures, including during reply cooldown. Stop/restart preserves unsent work. Typing/UI activity and outgoing AI text are classified and ignored. Several messages seen together can produce one reply; screenshot coverage remains approximate.

**The post-send focus fix is retained.** KakaoTalk moving keyboard focus after Enter no longer prevents observing the original verified composer. Accepted Enter with inconclusive observation follows the continued-watching behavior above; failed/partial input still requires review.

Use a vision-capable model with two-image support. Local PNGs are under `%LOCALAPPDATA%\KakaoCaptureAgent\captures\auto_catch`; exact paths and queue counts appear in the log. They are sent only to the configured LLM, not Bizgo or the normal image-upload endpoint. Old direct-text jobs remain separate. Completed images follow the metadata retention period at startup; pending images are retained and collection pauses at capacity.

The notes below describe earlier releases. The queued screenshot mode above replaces rc.21's direct-text Auto Catch and earlier synchronous visual Auto Catch. The explicit test workflows remain available.

**Fixed: Auto Catch detects typing activity but stops before answering the actual incoming message.** It now requests structured analysis when the LLM supports it, accepts common JSON code fences, and keeps watching through malformed or temporarily unclear analysis. Rechecks retain the last valid capture, with delays from 2 seconds up to 30 seconds, so the pending message remains eligible without clicking Auto Catch again. Typing-only changes are logged and ignored. The answer itself is plain text: `[AI] response (자동 응답)`. Analysis retries never repeat a chat submission.

**Fixed: Auto Catch stops after its initial capture when the chat loses foreground focus.** Auto Catch now reactivates the same verified chat while watching and after classification. If Windows temporarily denies activation, it waits between bounded retries and preserves the previous screenshot, reply count, and duplicate guard. When focus returns, it continues comparing new content instead of silently resetting the baseline. Stop / Ctrl+Shift+F12 cancels recovery.

This mode may bring the selected chat in front of the agent or other applications. Keep that chat open and the Windows session unlocked. Lock, minimization/closure, identity/size changes, persistent obstruction, and uncertain reply submission still require intervention. Focus failure inside a reply attempt never causes an automatic resend.

**New: Auto Catch.** Select the open KakaoTalk group chat and click **Auto Catch**. If needed, the agent detects the capture area above its message box and generates a chat identifier automatically. It watches incoming text, saves local captures, asks your configured LLM for a response, and sends `[AI] ... (자동 응답)`. It keeps watching until Stop / Ctrl+Shift+F12; there is no one-cycle timeout and no Bizgo step.

Default polling is twice per second with a short debounce; LLM inference adds response latency. Several newly visible incoming messages can be combined into one response. Outgoing/AI replies are ignored, and a bounded 60-second duplicate guard plus a three-second pause between replies reduces repeat sends. Messages arriving during inference remain eligible for the next comparison. Change the suffix and timing in Settings. Actual message coverage and classification remain approximate.

Keep the latest chat visible and leave its composer unused; sending replaces its contents. Stop, lost visibility, lock, target changes, uncertain submission, network/authentication or reply-generation errors, or storage failure end automatic replying without retries. Temporarily malformed or unclear classification follows the analysis rechecks described above. Restarting does not rearm Auto Catch. Existing manual regions are respected; unsupported/ambiguous message boxes require manual region selection. The actual installed KakaoTalk layout and continuous delivery still require Windows acceptance testing.

**New: Test Workflow 2: Reply to Next Message.** Open the latest messages and click this button once. It records a baseline, watches for a visual change, asks the configured vision model to identify new incoming text, and sends one direct `[AI] ...` response to the selected chat. Then it stops. Existing messages and outgoing/generated replies are ignored; uncertain analysis stops without sending. This test does not call Bizgo. The incoming capture is saved locally, with its path in the activity log.

Use the same LLM settings as Test Workflow; the model must accept two images. The existing local `gemma-4-31b` server passed a synthetic paired-image check. Keep the chat visible and do not scroll while waiting. The default waiting limit is five minutes, configurable in Settings. Stop / Ctrl+Shift+F12 cancels waiting or inference. This is visual inference, not a KakaoTalk event API, so missed or misclassified messages remain possible. Rearm explicitly for each test.

**Improved: chat activation after LLM inference.** The sender now waits briefly for Windows focus changes and, if needed, makes one temporary input-queue attachment attempt before rechecking the exact target and composer. It detaches before typing, does not change global Windows settings, and never retries message submission. This addresses premature post-inference activation failures; actual KakaoTalk behavior still requires a check on your Windows PC.

**New: Bizgo SMS/LMS as the final Test Workflow step.** Configure the registered sender number, recipient phone number, and Bizgo API key in Settings, then enable the Bizgo workflow checkbox. Both phone numbers are editable. After the KakaoTalk composer clears, the agent submits one phone-message copy via Bizgo v2 Omni. SMS/LMS selection follows the encoded text length; shortened content and unsupported-character replacement are reported in the log.

**Send Bizgo Sample** tests the saved numbers/key with one fixed `[test]` SMS without capturing a chat or calling the LLM. Sandbox is selected by default and does not deliver messages; clear its checkbox for production delivery. The main window labels the environment and masks the recipient. The key is stored in Windows Credential Manager or supplied through `BIZGO_API_KEY`. Bizgo requires the calling PC's public IP to be allowlisted and the sender number registered.

The app records request acceptance separately from delivery, supplies an idempotency key, and makes no automatic retries. Cancellation during a request may occur after Bizgo has already accepted it. The normal workflow skips Bizgo when KakaoTalk submission is uncertain. This release was tested with synthetic recipients and mocked Bizgo responses; real account acceptance and handset delivery require testing from your configured Windows PC.

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
