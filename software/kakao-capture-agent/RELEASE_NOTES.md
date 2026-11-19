Download `KakaoCaptureAgent-v<VERSION>-windows-x64.exe` from Assets and double-click it on Windows 10/11 (64-bit). Python, uv, and a separate installation step are not required. First launch may take a moment while bundled libraries unpack.

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
