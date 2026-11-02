# AX768

AX768 is a local-LLM agent with Google Sheets as its first capability. It reuses
the workspace's `URL`/`MODEL`/`OPENAI_API_KEY` (or `OPENAI_BASE_URL`/
`OPENAI_MODEL`) settings and existing asynchronous model adapter. No cloud LLM
fallback is configured. The model must support JSON-schema structured output.
Google Sheets access still requires internet access to Google.

## Setup and run

1. Run `uv sync` from the workspace root.
2. In Google Cloud project `nexgent-513207`, enable **Google Sheets API**.
3. Configure **Google Auth Platform → Branding / Audience**. For an External
   app in Testing, add the Google account you will sign in with as a test user.
   Under **Data Access**, add `https://www.googleapis.com/auth/spreadsheets`.
4. Under **Clients**, create an OAuth client with application type **Desktop app**
   and download its JSON file. A service-account key is a different credential.
5. Store the downloaded client JSON privately on the Linux server outside the
   repository. In the existing **agents/.env**, set absolute paths:

   ```dotenv
   AX768_GOOGLE_AUTH_MODE=oauth
   AX768_GOOGLE_OAUTH_CLIENT_FILE=/private/ax768/oauth-client.json
   AX768_GOOGLE_OAUTH_TOKEN_FILE=/private/ax768/oauth-token.json
   AX768_SPREADSHEET=https://docs.google.com/spreadsheets/d/YOUR_ID/edit
   ```

   The provided sheet link is already saved in the local .env. The login command
   creates the token file; do not download or invent its contents. Keep the client
   JSON and generated refresh token out of Git and chat. Explicit environment
   variables take precedence over .env.
6. From your **laptop terminal**, establish an SSH tunnel to the agent server:

   ```bash
   ssh -L 8767:127.0.0.1:8767 YOUR_LINUX_USER@YOUR_SERVER
   ```

   In that SSH session, change to the `agents/` workspace and run:

   ```bash
   uv run python -m apps.ax768.oauth_login
   ```

   Open the printed Google authorization URL in your **laptop browser**. Sign in
   with the Google account that has Editor access to the sheet and grant the
   requested access. Keep SSH connected through the callback. The login listener
   binds only to server loopback and waits up to five minutes. The tunnel forwards
   the browser's loopback redirect to it; no public callback or browser on the
   server is needed. If port 8767 is occupied, use a matching tunnel and `--port`.
7. Once the command reports success, run a task:

   ```bash
   uv run python -m apps.ax768.run "Read the headers in 'Sales'!A1:D1"
   ```

OAuth uses the signed-in user's existing spreadsheet permissions. The Sheets
scope can authorize access to all spreadsheets available to that user; AX768's
fixed spreadsheet setting restricts its tools to the selected file. Sheets
scope authorization does not override file sharing or protected ranges.
The runtime refreshes expired access tokens and atomically saves them with mode
0600 under a cross-process file lock. Revoked or expired refresh tokens require
running the login command again. External apps in Testing generally receive
refresh tokens that expire after seven days for this scope; use the appropriate
Google publishing/verification process for longer-term operation.

For containers, mount the token **directory** writable by the agent process so
atomic token replacement and locking work; keep it private. The OAuth client
file is needed only during interactive login, not ordinary graph runs. No browser
login starts inside a graph node. With OAuth, service-account sharing is unused.
The previous service-account path remains available only when explicitly setting
`AX768_GOOGLE_AUTH_MODE=service_account` and `AX768_GOOGLE_CREDENTIALS_FILE`.

The `ax768` graph is also registered for the private Agent Server. Submit input
`{"message":"your task"}` using existing thread/run APIs. Server-backed threads
retain checkpoints; the manual CLI is a single stateless invocation. The product
chat API does not automatically route messages to this new agent.

## Contract and skills

Input: a natural-language `message` of 1–8000 characters. Output: `status`,
`response`, and ordered `observations` with tool arguments and Google receipts.
Status is `completed`, `blocked` (missing sheet/auth configuration), or `failed`.
A completed response can ask for clarification without performing an edit.
Runtime instructions live in [skills/google_sheets.md](skills/google_sheets.md)
and are loaded into the model's system prompt. They are agent capabilities,
not global Codex configuration.

Supported tools read/write cells, append rows, clear values, add/rename/delete
tabs, and delete rows/columns. Ordinary cell writes keep formatting. RAW writes
are the default; formulas require explicit USER_ENTERED actions. There is no
unrestricted API, filesystem, shell, web, Drive-file deletion or sharing tool.
All actions target the single operator-configured spreadsheet; model output
cannot supply another spreadsheet ID. Formatting design, spreadsheet creation,
and additional workflows can be added as separate capabilities when needed.

Limits: ten actions per run, 2000 cells per explicit rectangle/write, 200 rows/
columns per deletion, bounded prompt/tool payloads, 30-second Google HTTP timeout.
Append uses Google's table detection and may write beyond its search rectangle.
There is no automatic tool retry. Metadata identifies sheet IDs and is refreshed
after structural changes. Instructions require reading before edits and checking
results; semantic correctness of the model's selections still needs live evaluation.

## Recovery and verification

Each graph node records its result in Agent Server checkpoints. CLI output shows
partial completion too. Tool errors stop the loop; a timeout can mean Google
committed the mutation without returning its receipt. Inspect actual cells and
recorded observations before issuing a new task. Do not automatically replay
append/delete actions or resume a pending mutation after a crash: a Google write
and a LangGraph checkpoint are not one transaction. Concurrent edits are not
serialized and cross-action rollback/exactly-once execution is not provided.
This initial manual workflow is not an unattended job runner.

Acceptance checks cover fixed target isolation, schema rejection, bounded ranges,
read/update/verify completion, failed mutation without retry, missing configuration,
and correct Sheets request semantics. The configured local model passed a live
structured-action check using synthetic metadata, selecting the requested read
range correctly. End-to-end Google evaluation is pending the OAuth client file and user consent. No real spreadsheet was modified during implementation.

References: [Sheets value operations](https://developers.google.com/workspace/sheets/api/guides/values),
[structural requests](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request),
[service account authentication](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.service_account.html).

OAuth references: [Google Desktop/CLI OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[refresh token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).

Validation on 2026-10-30: 28 OAuth/workflow/dependency-boundary/graph-entry tests passed; scoped Ruff and LangGraph validation passed. OAuth tests cover private token storage, refresh persistence, revoked grants, missing scopes/offline permission and loopback/PKCE configuration. Real Google consent and row 81 writing await the user login.
