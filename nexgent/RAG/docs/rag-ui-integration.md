# RAG UI Integration

This document is the canonical reference for the Nexgent browser UI that uses
RAG. Server/API contracts belong in [RAG Server](rag-server.md), retrieval
quality in [Retrieval Evaluation](rag-retrieval-evaluation.md), and Chat
orchestration in [RAG Chat Agent](../../agents/docs/rag-chat-agent.md).

## Current browser topology

The RAG workspace is available at:

```text
http://192.168.0.18:5173/rag
```

Its API client reads `VITE_RAG_SERVER_BASE_URL` and calls the host RAG API
directly:

```text
Browser /rag
  -> http://192.168.0.18:8765/rag/v1/*
```

There is no current `/rag-server` Vite proxy. The historical proxy design was
replaced by direct browser-to-RAG routing and explicit FastAPI CORS for the
frontend origin.

RAG Chat uses a different, server-side path:

```text
Browser Chat (RAG Agent)
  -> POST /api/rag/chat/stream
  -> backend SSE relay
  -> Agent Server rag_chat
  -> host RAG API
  -> existing chat model adapter
```

## Frontend ownership

| File | Responsibility |
| --- | --- |
| `frontend/src/features/rag/RagPage.tsx` | File/Direct Text ingestion, search, previews, statistics, and guarded deletion UI |
| `frontend/src/features/rag/RagPage.module.css` | RAG page layout, responsive behavior, previews, and dialog styling |
| `frontend/src/shared/api/ragClient.ts` | Typed direct RAG API client and validation |
| `frontend/src/features/chat/ChatPage.tsx` | RAG Agent selection, text-only composer policy, and streamed answer rendering |
| `frontend/src/shared/api/agentServerClient.ts` | Dedicated RAG Chat streaming request |
| `frontend/src/shared/api/agentCatalogClient.ts` | RAG Agent catalog metadata |

The sidebar and route table expose `/rag`; the Chat page exposes `RAG Agent` in
the existing agent selector.

## RAG page behavior

### Ingestion modes

The Embedding panel has two explicit modes:

- **File Upload** accepts case-insensitive `.txt`, `.md`, `.docx`, and `.pdf`.
  Double extensions such as `.docx.exe` and legacy `.doc` are rejected.
- **Direct Text** provides a multiline textarea and optional title. Blank or
  whitespace-only text is rejected before the request.

Both modes share the **Maximum tokens per chunk** control. It defaults to 500,
accepts whole integers from 100 through 1000, and explains that natural
boundaries can make chunks shorter.

The support message distinguishes TXT, Markdown, DOCX, PDF, and automatic
scanned-PDF OCR. It does not imply that images embedded in DOCX are OCRed.

After success, the page shows source name/type, file size, source token count,
chunk count, configured maximum, and chunking/embedding/total server timing.
The **Chunk preview** renders at most the first ten chunks with preserved line
breaks, token and character counts, source spans, overlap, and context. A clear
message indicates when the preview is truncated.

### Search

The Search panel sends a non-empty query and `top_k` (default 5, range 1–20) to
`GET /rag/v1/search`. It preserves server order and derives the displayed rank
from array position. Each result shows:

- Rank and **Cosine similarity**;
- source name, File/Direct text type, and chunk number when provenance exists;
- `Source unavailable — legacy row` for null provenance; and
- retrieved context with line breaks preserved.

Server processing time is shown as Query embedding, DB search, and Total. The
UI does not reinterpret similarity as confidence or reorder results.

## RAG data administration

The lower RAG-data panel fetches document, total embedding, legacy, and
provenance-bearing counts from `GET /rag/v1/data/stats`.

**Empty database** is deliberately secondary and cannot delete data with one
click. It opens a confirmation dialog that:

1. explains that all indexed documents and chunks are permanently removed
   while schema remains;
2. shows current counts;
3. requires the exact text `DELETE`; and
4. enables **Delete all data** only after that exact confirmation.

The backend independently enforces the same confirmation. Cancel makes no
request. On confirmed success, the dialog resets, counts are refreshed, and a
success message reports the cleared state. The application is not reloaded.
Errors never render a success state.

The live validation removed 109 embeddings and 7 documents, including both 71
legacy and 38 provenance-bearing embeddings. Independent database counts and
the UI counters reached zero, and a search returned the normal
`No matching context found.` state. This was a dated destructive validation;
it is not a statement about current row counts. Backup restoration remains
unvalidated.

## RAG Agent on Chat

`RAG Agent` is a real execution path, not a preview agent. When selected, the
Chat page sends the question as JSON to `POST /api/rag/chat/stream` and reuses
the existing streamed assistant-message and Markdown renderer. Normal Chat,
preview agents, and Weekly Reporter retain their existing routes.

Phase 1 is text-only. Selecting RAG Agent clears any pending attachment and
disables attachment controls; the API also rejects attachment-like extra
fields. The UI transcript can show earlier messages, but only the current
question is sent for each one-turn RAG request.

For populated retrieval, the streamed answer ends with a deterministic
Markdown Sources section supplied by code. For zero retrieval results, the
fixed insufficient-context answer has no Sources section and the model is not
called. See [RAG Chat Agent](../../agents/docs/rag-chat-agent.md) for the prompt,
SSE contract, and source rules.

## Validation summary

Recorded deterministic frontend tests cover:

- file type acceptance/rejection and multipart upload;
- Direct Text validation and JSON request shape;
- chunk controls, observability, previews, and search timing/order;
- provenance and legacy-row rendering;
- exact-confirmation deletion and count refresh;
- RAG Agent selection, dedicated routing, attachment blocking, streaming, and
  regressions for normal Chat/other agents.

Recorded live browser validation covers:

- TXT, Markdown, native PDF, scanned PDF OCR, DOCX, and Direct Text ingestion;
- ingestion metrics and chunk previews;
- exact vector results with source/type/chunk provenance;
- guarded Empty Database and normal empty-corpus search;
- RAG Agent zero-result handling, grounded populated-corpus generation,
  deterministic sources, unsupported-fact behavior, and streaming; and
- the same RAG flows after transition to the systemd-managed host service.

The RAG Chat populated-path check used a synthetic source named
`RAG Chat Live Validation Document`; it is validation data, not business data.
The last recorded readiness check showed one document and one embedding, but
the actual live counts must be read from the stats endpoint rather than assumed
from this document.

## Current limitations

- Browser RAG API access has no application authentication, authorization, or
  TLS layer. Network exposure is controlled operationally.
- Duplicate ingestion and re-ingestion/version replacement are unresolved; the
  UI warns but does not prevent duplicate uploads.
- `source_name` is display-only provenance. There are no Nextcloud file IDs,
  paths, or clickable source links.
- Standalone image uploads and OCR for images embedded in DOCX are unsupported.
- DOCX complex visual layout and advanced structures are flattened or omitted.
- OCR can make Korean/English-boundary errors.
- RAG Chat is one-turn and text-only; it has no attachment ingestion or
  conversation memory.
- Production retrieval remains vector-only. Hybrid/RRF is experimental and is
  not exposed by the UI.
- Backup restore, post-restore counts, and post-restore retrieval regression
  have not been validated.
