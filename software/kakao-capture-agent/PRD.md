# Product Requirements Document (PRD)

# KakaoTalk Screen Capture Agent

**Version:** 1.0  
**Status:** Ready for implementation  
**Platform:** Windows 10/11  
**Application Type:** Lightweight desktop automation agent  
**Primary Language:** Python 3.11+  
**Target Environment:** Dedicated, always-on Windows PC

---

## 1. Product Overview

### 1.1 Purpose

Develop a lightweight Windows desktop application that automatically monitors a user-selected region of a KakaoTalk PC group chat, captures screenshots, scrolls through conversation history, detects visual changes, and uploads captured images to a configurable backend REST API.

The application runs on a dedicated Windows PC where KakaoTalk remains open.

The capture agent acts as a data collection component. The backend is responsible for interpreting screenshots, extracting chat information, processing messages, and integrating with other AI services.

### 1.2 Primary Goal

Enable automated collection of visible KakaoTalk group chat content without requiring manual screenshot capture, scrolling, or uploading.

### 1.3 Core Capabilities

1. Select a screen region using mouse drag.
2. Persist the selected region between application restarts.
3. Automatically capture screenshots at configurable intervals.
4. Detect visual changes to reduce unnecessary uploads.
5. Automatically scroll the KakaoTalk conversation.
6. Capture overlapping screenshots while scrolling.
7. Upload captured screenshots to a REST API.
8. Handle network failures and retry uploads.
9. Provide a desktop GUI for configuration and monitoring.
10. Support unattended operation on a dedicated Windows PC.

### 1.4 Non-Goals for MVP

- Direct integration with private or undocumented KakaoTalk APIs.
- Automatic KakaoTalk message sending.
- OCR or AI vision processing inside the Windows application.
- Automatic download of original-resolution KakaoTalk attachments.
- Monitoring multiple chat rooms simultaneously.
- Capturing conversations not displayed in the KakaoTalk desktop interface.
- Bypassing KakaoTalk authentication or Windows security restrictions.

---

## 2. Target Environment

### 2.1 Operating Conditions

- Windows 10 or 11.
- KakaoTalk PC installed and authenticated.
- The dedicated PC stays powered on.
- An interactive Windows desktop session remains active and unlocked during capture.
- The selected KakaoTalk conversation window remains open.
- Internet connectivity to the backend API is normally available.

The application must handle temporary internet failures and application interruptions gracefully.

A Windows lock screen, sleep state, minimized window, or disconnected graphical session may prevent reliable capture. These states must be detected where possible, not silently treated as successful capture.

### 2.2 Application Constraints

The application must not depend on KakaoTalk internal APIs or reverse-engineered protocols for the MVP.

Screen automation must use operating-system-level APIs or standard desktop automation libraries.

Because KakaoTalk's exact scrolling, resizing, and chat-navigation behavior may vary by version, the implementation must validate those behaviors against the installed client.

---

## 3. Technology Stack

| Component | Preferred Technology |
|---|---|
| Programming language | Python 3.11+ |
| Desktop GUI | PySide6 |
| Screenshot capture | mss |
| Mouse automation | pyautogui |
| Window identification | pywin32 |
| Image processing | OpenCV + NumPy |
| HTTP client | httpx |
| Local database | SQLite |
| Configuration | JSON + environment variables |
| Logging | Python logging |
| Application packaging | PyInstaller |
| Automated testing | pytest |

The coding agent may replace a library if necessary, provided the replacement satisfies the requirements.

---

## 4. System Architecture

```text
Dedicated Windows PC
│
├── KakaoTalk PC
│   └── Selected Group Chat
│
└── Kakao Capture Agent
    │
    ├── Desktop GUI
    │   ├── Region Selection
    │   ├── Monitoring Controls
    │   ├── API Settings
    │   └── Status Display
    │
    ├── Window Manager
    │   ├── Detect KakaoTalk Window
    │   ├── Track Window Position
    │   └── Validate Window State
    │
    ├── Capture Engine
    │   ├── Screenshot Capture
    │   ├── Region Tracking
    │   └── Change Detection
    │
    ├── Scroll Controller
    │   ├── Scroll Up
    │   ├── Scroll Down
    │   └── History Capture
    │
    ├── Upload Manager
    │   ├── HTTP Client
    │   ├── Retry Queue
    │   └── Upload Status
    │
    └── SQLite
        ├── Capture Metadata
        ├── Pending Uploads
        └── Processing History
              │
              ▼
       HTTPS REST API
              │
              ▼
        AI Backend
        ├── OCR / Vision
        ├── Message Extraction
        ├── Deduplication
        └── Downstream Processing
```

### Architectural Requirements

- GUI operations must not block screenshot capture or HTTP uploads.
- Capture, scrolling, and uploading must have separate responsibilities.
- Only one scrolling operation may execute at a time.
- The upload worker must support asynchronous processing.
- Unsuccessful uploads must remain in a persistent local queue.
- An unexpected application crash must not corrupt queued data.

---

## 5. Functional Requirements

## FR-01: Screen Region Selection

**Priority:** P0

### Description

The user must be able to select a rectangular region on the screen with the mouse.

### Functional Behavior

1. The user opens the application.
2. Clicks "Select Region".
3. A transparent, full-screen selection overlay appears.
4. The user clicks and drags to draw a rectangle.
5. The selected rectangle is highlighted.
6. Releasing the mouse confirms the selection.
7. The application saves the selection coordinates.

### Required Data

```json
{
  "left": 300,
  "top": 150,
  "width": 650,
  "height": 800
}
```

### Additional Requirements

- Display a preview of the selected region.
- Allow region reselection.
- Validate minimum dimensions.
- Persist the region across application restarts.
- Support Windows display scaling and multi-monitor coordinates.
- Prefer storing coordinates relative to the KakaoTalk window's client area rather than only absolute desktop coordinates.
- Detect invalid or off-screen regions.

### Acceptance Criteria

- The user can select a region without entering coordinates.
- Only the selected region appears in the captured image.
- The region can be restored after restarting the application.
- Region tracking remains correct after small KakaoTalk window movements when window-relative coordinates are used.

---

## FR-02: KakaoTalk Window Detection

**Priority:** P0

### Description

Identify and monitor the intended KakaoTalk window.

### Functional Behavior

- Detect KakaoTalk PC windows.
- Allow the user to select a target window if multiple candidates exist.
- Save window identification information.
- Detect whether the target window is available and visible.
- Detect substantial window movement or resizing.
- Avoid capture and scrolling when the target window is invalid.

### Recommended Approach

Use Windows window handles and process identification through `pywin32`.

Do not assume a fixed KakaoTalk process name or window-title format without validating it.

### Safety Requirements

- Do not send scrolling or clicking events to an unverified target.
- Pause automation when the target window cannot be identified.
- Do not automatically switch to another conversation window with ambiguous identity.

---

## FR-03: Automatic Screenshot Capture

**Priority:** P0

### Description

Capture the selected region automatically at a configurable interval.

### Default Configuration

```json
{
  "capture_interval_seconds": 2,
  "image_format": "png",
  "capture_mode": "region"
}
```

### Requirements

- Capture the selected region.
- Use PNG format by default.
- Preserve screenshot resolution.
- Attach an accurate timestamp.
- Generate a unique capture identifier.
- Calculate an image hash.
- Support configurable capture intervals from 1 to 60 seconds.
- Avoid storing unnecessary duplicate image files.

### Acceptance Criteria

- Capture can start and stop without restarting the application.
- Captures match the selected region.
- The application runs without freezing its interface.

---

## FR-04: Visual Change Detection

**Priority:** P0

### Description

Detect changes in the selected chat region and upload screenshots only when the visible content changes meaningfully.

### Recommended Algorithm

1. Capture the current region.
2. Compare it with the previous screenshot.
3. Calculate the visual difference.
4. If the difference exceeds a threshold, create an upload job.
5. Otherwise, skip uploading.

### Implementation Options

- Exact image hashing for identical screenshots.
- OpenCV image differences.
- Perceptual hashing for near-duplicate detection.

### Requirements

- Make change-detection sensitivity configurable.
- Ignore negligible visual changes where possible.
- Support a short debounce period.
- Prevent excessive uploads caused by blinking cursors, animated elements, and transient UI changes.
- Maintain separate change-detection state for normal monitoring and history scanning.

### Important

Visual changes do not necessarily represent new messages.

The capture agent must not claim to identify a new message solely because image pixels changed.

Actual message interpretation and message-level deduplication belong to the backend.

---

## FR-05: Automatic Scrolling

**Priority:** P0

### Description

The application must support automated scrolling inside the selected KakaoTalk group chat.

### Required Operations

- Scroll upward.
- Scroll downward.
- Perform configurable incremental scrolling.
- Wait for the interface to settle after each scroll.
- Capture screenshots between scroll actions.
- Stop scrolling on user request.
- Stop when the target window or scroll region becomes invalid.

### Default Settings

```json
{
  "scroll_step": 3,
  "scroll_delay_ms": 800,
  "max_scroll_steps": 50,
  "overlap_target_percent": 30
}
```

### Scrolling Rules

- Mouse wheel events must be directed to the correct conversation area.
- The configured scroll amount must be calibrated against actual KakaoTalk behavior.
- Capture screenshots with visual overlap to reduce gaps between consecutive images.
- Do not assume a fixed number of wheel events equals a fixed number of pixels.
- Stop when repeated scroll attempts produce no meaningful movement.
- Provide an emergency stop control.

### Acceptance Criteria

- The application can scroll through a visible conversation.
- It captures images after scrolling.
- It does not scroll unrelated windows.
- It stops safely if the KakaoTalk window disappears.

---

## FR-06: Live Monitoring Mode

**Priority:** P0

### Description

Continuously monitor the most recent messages in the selected group chat.

### Behavior

1. Validate that the target KakaoTalk window is open.
2. Position the chat near the latest messages.
3. Capture the selected region.
4. Compare the screenshot against the previous capture.
5. Queue changed screenshots for upload.
6. Repeat at the configured interval.

### Requirements

- Remain near the bottom of the conversation.
- Avoid unnecessary scrolling when no new content appears.
- Support a configurable recovery check to confirm that the chat remains at the latest messages.
- Revalidate the target after interruptions.

### Limitations

The application cannot guarantee that every message will be captured if many messages arrive between screenshots, if the window loses visibility, or if the desktop session becomes unavailable.

The application must record interruptions so missing history can be investigated or backfilled.

---

## FR-07: History Collection Mode

**Priority:** P1

### Description

Allow the application to scroll upward through older conversation content and capture screenshots.

### Trigger

A user clicks "Capture History" in the desktop GUI.

### Workflow

1. Pause normal live monitoring.
2. Record the current capture state.
3. Scroll upward incrementally.
4. Capture each newly revealed region.
5. Preserve overlapping content across screenshots.
6. Queue screenshots for upload.
7. Continue until the configured step limit, a detected boundary, or a stop request.
8. Navigate toward the latest messages.
9. Verify that the chat is back near the bottom.
10. Resume normal monitoring.

### Requirements

- History collection must not run simultaneously with live scrolling.
- Support cancellation.
- Display collection progress.
- Avoid endlessly scrolling through unchanged content.
- Record coverage boundaries and uncertainty.
- Do not silently resume live monitoring if the return-to-bottom verification fails.

### Important Limitation

History collection cannot guarantee exhaustive coverage because messages may arrive during scanning, KakaoTalk may load history dynamically, and screenshots can overlap or skip content.

If history scanning fails, explicitly report incomplete coverage.

---

## FR-08: REST API Integration

**Priority:** P0

### Description

Upload captured screenshots and metadata to a configurable backend HTTP endpoint.

### API Configuration

```json
{
  "api_url": "https://example.com/api/v1/captures",
  "request_timeout_seconds": 15,
  "max_retries": 5
}
```

### Request

**Method:** `POST`

**Content-Type:** `multipart/form-data`

**Authentication:** Bearer token over HTTPS

### Request Fields

| Field | Type | Description |
|---|---|---|
| image | File | Screenshot in PNG format |
| capture_id | String | Unique capture identifier |
| device_id | String | Stable device identifier |
| chat_id | String | User-assigned monitored chat identifier |
| timestamp | String | UTC ISO 8601 timestamp |
| capture_mode | String | live or history |
| image_hash | String | SHA-256 hash of the image |
| region | JSON string | Captured region coordinates |
| sequence_number | Integer | Capture sequence within a session |

### Example Metadata

```json
{
  "capture_id": "c8f1a2e9-120d-4d18-9d45-e2a6f8333400",
  "device_id": "kakao-pc-01",
  "chat_id": "group-001",
  "timestamp": "2026-11-16T05:00:00Z",
  "capture_mode": "live",
  "image_hash": "SHA256_HEX_VALUE",
  "region": {
    "left": 300,
    "top": 150,
    "width": 650,
    "height": 800
  },
  "sequence_number": 123
}
```

### Expected Success Response

```json
{
  "status": "accepted",
  "capture_id": "c8f1a2e9-120d-4d18-9d45-e2a6f8333400"
}
```

### Error Handling

- Retry temporary connection failures.
- Retry HTTP 429 and 5xx responses with exponential backoff.
- Respect `Retry-After` where supplied.
- Do not automatically retry permanent authentication or validation failures indefinitely.
- Retain failed uploads locally.
- Mark permanently failed jobs for operator review.
- Use `capture_id` as an idempotency key so backend retries do not create duplicate records.

### Backend Responsibility

The backend must validate the authenticated sender, image size, payload fields and capture identifier.

It should support idempotent uploads and acknowledge successfully persisted captures.

---

## FR-09: Local Upload Queue

**Priority:** P0

### Description

Maintain a persistent queue so temporary API failures do not result in lost captures.

### Storage

SQLite for metadata, with screenshot files stored in a managed local directory.

### Suggested Table

```sql
CREATE TABLE capture_queue (
    capture_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    image_path TEXT NOT NULL,
    image_hash TEXT NOT NULL,
    capture_mode TEXT NOT NULL,
    upload_status TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    uploaded_at TEXT
);
```

### Requirements

- Persist queued uploads before considering a capture complete.
- Resume pending uploads after restarting the agent.
- Delete successfully uploaded screenshot files according to a configurable retention policy.
- Retain metadata for diagnostics.
- Set a maximum local storage limit.
- Warn before storage reaches capacity.
- Do not silently discard unsent captures when the storage limit is exceeded.

---

## FR-10: Desktop GUI

**Priority:** P0

### Description

Provide a simple user interface for managing capture automation.

### Main Window

```text
┌──────────────────────────────────────┐
│ KakaoTalk Capture Agent              │
├──────────────────────────────────────┤
│                                      │
│ Status: ● Monitoring                 │
│ Target: KakaoTalk Group Chat         │
│                                      │
│ [ Select Window ]                    │
│ [ Select Region ]                    │
│                                      │
│ ┌──────────────────────────────────┐ │
│ │                                  │ │
│ │      Selected Region Preview     │ │
│ │                                  │ │
│ └──────────────────────────────────┘ │
│                                      │
│ Capture Interval: 2 seconds          │
│ Change Detection: Enabled            │
│                                      │
│ [ Start Monitoring ]                 │
│ [ Stop Monitoring ]                  │
│ [ Capture History ]                  │
│                                      │
│ API Status: Connected                │
│ Pending Uploads: 0                   │
│ Last Upload: 14:32:10                │
│                                      │
│ [ Settings ] [ Logs ]                │
└──────────────────────────────────────┘
```

### Requirements

- Window selection.
- Region selection.
- Screenshot preview.
- Start and stop controls.
- Capture interval configuration.
- Visual-change detection toggle.
- History collection controls.
- API configuration.
- Queue status display.
- Error indicators.
- Recent activity log.

### User Experience

The application must remain responsive while performing captures, scrolling and uploads.

A system tray option is desirable but not mandatory for the first release.

---

## FR-11: Logging and Diagnostics

**Priority:** P1

### Requirements

Record events including:

- Application startup and shutdown.
- Target window identification.
- Region changes.
- Capture attempts.
- Change detection results.
- Scrolling operations.
- Upload attempts and responses.
- Retry events.
- Lost target-window events.
- History scanning completion or failure.

Logs should not include API credentials or unnecessary chat contents.

### Example

```text
[14:30:00] Agent started
[14:30:01] Target window detected
[14:30:02] Live monitoring started
[14:30:04] Visual change detected
[14:30:04] Capture queued
[14:30:05] Upload successful
[14:31:00] History scan requested
[14:31:01] Live monitoring paused
[14:31:02] Scrolling upward
[14:31:03] History capture queued
```

---

## FR-12: Application Lifecycle

**Priority:** P1

### Requirements

- Save configuration automatically.
- Recover pending uploads after a restart.
- Optionally launch when the Windows user signs in.
- Allow safe start and stop.
- Close gracefully.
- Recover from transient network interruptions.
- Stop automated input when the target window is unavailable.
- Detect and display degraded monitoring states.

The app should not claim successful monitoring when the desktop is locked or capture is unavailable.

---

## 6. Application State Machine

The application should implement explicit operational states.

```text
STOPPED
   │
   ▼
INITIALIZING
   │
   ▼
LIVE_MONITORING
   │
   ├── History Requested
   │          │
   │          ▼
   │    HISTORY_SCANNING
   │          │
   │          ▼
   │    RESTORING_POSITION
   │          │
   │          ▼
   │    LIVE_MONITORING
   │
   ├── Target Unavailable
   │          │
   │          ▼
   │        PAUSED
   │
   └── Stop Requested
              │
              ▼
           STOPPED
```

An independent upload worker must be allowed to continue processing its queue while capture or scrolling is paused.

---

## 7. Project Structure

Use the following suggested structure:

```text
kakao-capture-agent/
│
├── app/
│   ├── main.py
│   ├── config.py
│   │
│   ├── gui/
│   │   ├── main_window.py
│   │   ├── region_selector.py
│   │   └── settings_dialog.py
│   │
│   ├── capture/
│   │   ├── screen_capture.py
│   │   ├── region_manager.py
│   │   └── change_detector.py
│   │
│   ├── automation/
│   │   ├── window_manager.py
│   │   ├── scroll_controller.py
│   │   └── monitoring_service.py
│   │
│   ├── api/
│   │   ├── client.py
│   │   └── upload_worker.py
│   │
│   ├── storage/
│   │   ├── database.py
│   │   └── capture_queue.py
│   │
│   └── utils/
│       └── logger.py
│
├── tests/
├── config/
│   └── config.example.json
│
├── requirements.txt
├── README.md
└── build.ps1
```

The coding agent may adjust the structure for maintainability.

---

## 8. Security and Privacy Requirements

The application processes private group-chat content, which may contain personal information.

### Requirements

- Obtain appropriate participant notice and authorization before collecting group conversations.
- Only capture explicitly configured chat regions.
- Do not collect screenshots from unrelated applications.
- Use HTTPS for external uploads.
- Store API credentials securely, preferably using Windows Credential Manager or DPAPI.
- Avoid embedding credentials in application binaries or ordinary configuration files.
- Restrict access to local screenshot storage.
- Configure retention and deletion policies.
- Provide a clear pause/stop mechanism.
- Avoid uploading screenshots of unexpected dialogs, unrelated windows, or credentials.
- Maintain an operational audit log.

The MVP should have no automatic message-sending or chat-interaction functionality beyond capture-related navigation and scrolling.

---

## 9. Performance and Reliability Requirements

| Metric | Target |
|---|---|
| Default capture interval | 2 seconds |
| Screenshot format | PNG |
| UI responsiveness | No visible blocking during routine capture |
| Change detection | Completed within capture interval under normal conditions |
| Failed uploads | Persistent queue + retry |
| Network interruption | Recover without losing successfully queued captures |
| Restart recovery | Reload configuration and pending uploads |
| Duplicate uploads | Idempotency by capture ID |
| History scanning | Bounded and cancellable |
| CPU utilization | Minimize idle usage; benchmark on target PC |
| Memory consumption | Measure and prevent unbounded growth |

Avoid claiming guaranteed message coverage or zero missed messages from screenshots alone.

---

## 10. Error Handling

The application must explicitly handle:

1. KakaoTalk not running.
2. Target chat window closed.
3. Target window minimized or obscured.
4. Windows desktop locked.
5. Selected region outside the screen.
6. Screen resolution or DPI scaling changes.
7. Internet connection failure.
8. API authentication failure.
9. HTTP request timeout.
10. Local disk space exhausted.
11. SQLite errors.
12. Unexpected screenshot capture failure.
13. History scroll position not restored.
14. Application restart during pending uploads.
15. Multiple KakaoTalk windows causing target ambiguity.

Every failure must produce a meaningful log entry and visible operational status.

---

## 11. Implementation Phases

### Phase 1 — Core Capture MVP

**Priority:** Highest

Deliver:

- PySide6 desktop interface.
- KakaoTalk window selection.
- Mouse-based screen region selection.
- Persisted configuration.
- Screenshot preview.
- Start/stop monitoring.
- Configurable screenshot interval.
- Basic visual change detection.

**Definition of Done:** The application can monitor a selected KakaoTalk chat region and capture screenshots automatically.

### Phase 2 — Backend Integration

Deliver:

- REST API integration.
- Authenticated screenshot uploads.
- Capture metadata.
- Persistent SQLite queue.
- Retry and backoff.
- Upload status display.

**Definition of Done:** Changed screenshots reach the configured backend API reliably, including after temporary network interruptions.

### Phase 3 — Scroll Automation

Deliver:

- Manual scroll-up and scroll-down controls.
- Incremental scrolling.
- Overlapping screenshot collection.
- History collection mode.
- Scroll limits and cancellation.
- Return-to-latest-message recovery.
- Live monitoring pause/resume logic.

**Definition of Done:** The application can perform a bounded history scan, upload captured screenshots, and return to live monitoring after verifying the target chat position.

### Phase 4 — Unattended Reliability

Deliver:

- Optional automatic startup on user sign-in.
- Target-window recovery.
- Diagnostic logs.
- Queue maintenance.
- Disk-capacity monitoring.
- Graceful interruption handling.
- Packaging as a Windows executable.

**Definition of Done:** The application can operate on a dedicated, unlocked Windows PC for an extended test period with controlled recovery from expected failures.

---

## 12. Testing Requirements

### Unit Tests

- Screenshot region validation.
- Image hashing and change detection.
- Configuration load/save.
- Upload queue persistence.
- Retry/backoff logic.
- Application state transitions.

### Integration Tests

- Mock HTTP API receives screenshot uploads.
- API failure and recovery.
- Application restart with pending uploads.
- Invalid target window handling.
- Scrolling-controller cancellation.

### Manual Windows Tests

Use a real KakaoTalk PC instance and authorized test conversation.

Test:

- A new text message arriving.
- Several messages arriving rapidly.
- A photo appearing in the conversation.
- The window moving to another position.
- The window being resized.
- The window becoming obscured.
- History scrolling.
- Returning to the latest message.
- Network disconnection.
- Application restart.
- Windows session lock and unlock.

### End-to-End Acceptance Scenario

1. Start KakaoTalk and open the authorized test group.
2. Launch the capture agent.
3. Select the KakaoTalk window.
4. Select the message region.
5. Configure an API endpoint.
6. Start monitoring.
7. Send test messages to the group.
8. Verify that changed screenshots are uploaded.
9. Trigger a bounded history scan.
10. Verify overlapping history captures.
11. Verify that the agent returns to normal monitoring.
12. Disconnect the network.
13. Generate another capture.
14. Restore connectivity.
15. Verify that pending uploads complete.
16. Restart the application and verify configuration persistence.

---

## 13. Future Enhancements

The following features are outside the MVP and should not delay initial implementation.

### 13.1 AI-Based Message Extraction

Use backend vision models or OCR to identify:

- Message content.
- Sender names.
- Visible timestamps.
- Images and attachments.
- Message order.

Deduplicate overlapping screenshots at the message level.

### 13.2 Original Image Collection

Implement a separate, authorized KakaoTalk UI workflow for downloading original attachment files where supported.

Screen capture alone is not sufficient for original-resolution images.

### 13.3 Multiple Chat Monitoring

Support monitoring several selected group chats by explicitly switching between verified windows or using separate controlled sessions.

### 13.4 Adaptive Capture

Automatically adjust capture frequency based on observed activity.

### 13.5 Advanced Capture

Evaluate Windows Graphics Capture or other platform capture mechanisms if basic screen-region capture proves unreliable.

---

## 14. Instructions for the Coding Agent

Implement this project incrementally.

### Development Rules

1. Use Python 3.11+ and the preferred technology stack unless a documented technical limitation requires a change.
2. Begin with Phase 1, then implement Phases 2–4 in order.
3. Keep GUI, automation, capture, and networking modules separate.
4. Write unit tests for non-GUI business logic.
5. Provide a mock API server for testing uploads.
6. Avoid hardcoding screen coordinates, URLs, or API credentials.
7. Use explicit state management for capture and scrolling.
8. Do not introduce undocumented KakaoTalk API integrations.
9. Implement safe stopping and recovery for automated mouse actions.
10. Document any feature that cannot be validated without a real Windows/KakaoTalk environment.
11. Provide a clear README with installation, configuration, testing and packaging instructions.
12. Ensure that the application can be packaged into a Windows `.exe`.

### Required Deliverables

- Complete Python source code.
- `requirements.txt`.
- Configuration example.
- SQLite schema and initialization.
- Unit and integration tests.
- Mock upload API.
- `README.md`.
- Windows build script.
- Packaged `.exe` instructions.
- Known limitations and test results.

### Completion Criteria

The project is complete when a user can launch the Windows application, select a KakaoTalk conversation region, start automated monitoring, upload changed screenshots to an API, perform bounded history scrolling, and recover safely from temporary failures without manually taking screenshots.

**End of PRD — Version 1.0**
