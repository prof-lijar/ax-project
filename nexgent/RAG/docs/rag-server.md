# RAG Server

This document is the canonical reference for the RAG API, ingestion boundary,
database schema, and host-service operation. See
[Vector search](rag-vector-search.md) for embedding and ranking details,
[UI integration](rag-ui-integration.md) for browser behavior, and
[retrieval evaluation](rag-retrieval-evaluation.md) for benchmark evidence.

## Current architecture

```text
Browser /rag
  -> http://192.168.0.18:8765/rag/v1/*
  -> FastAPI (rag_server.py)
  -> extraction -> shared SourceDocument ingestion
  -> tokenizer chunking -> Qwen document embeddings
  -> PostgreSQL rag.documents + rag.embeddings

Chat page (RAG Agent)
  -> backend POST /api/rag/chat/stream
  -> Agent Server rag_chat graph
  -> http://host.docker.internal:8765/rag/v1/search
  -> existing OpenAI-compatible chat adapter
```

The browser calls the RAG API directly. The earlier `/rag-server` Vite proxy is
not part of the current design. Server-side RAG Chat retrieval reaches the same
host API through `host.docker.internal:8765`.

The repository defines the system-level `nexgent-rag.service` unit in
`RAG/deploy/systemd/nexgent-rag.service`. The recorded 2026-08-25 transition
installed it, passed `systemd-analyze verify`, enabled it for
`multi-user.target`, and validated readiness. It binds `0.0.0.0:8765`, uses the
repository `.venv`, loads the embedding tokenizer/model once during FastAPI
startup, and writes stdout/stderr to journald. PostgreSQL remains a separate
Docker Compose dependency. Runtime status should always be checked with
`systemctl` rather than inferred from the repository.

## Configuration

`embedd.py` and `search.py` load `RAG/.env` with `override=False`. The systemd
unit deliberately has no `EnvironmentFile=` directive. It supplies only
non-secret process settings and lets the application use the established
configuration path.

| Name | Purpose | Default |
| --- | --- | --- |
| `RAG_POSTGRES_PASSWORD` | Required database password | none |
| `RAG_POSTGRES_HOST` | PostgreSQL host | `127.0.0.1` |
| `RAG_POSTGRES_PORT` | PostgreSQL port | `5433` |
| `RAG_POSTGRES_DB` | Database name | `nextgent` |
| `RAG_POSTGRES_USER` | Database role | `rag` |
| `HF_HOME` | Hugging Face cache | `RAG/.cache/huggingface` when unset |

Do not put credentials in the unit file, commands, logs, or documentation.

## API contracts

All routes use the `/rag/v1` prefix. The configured browser CORS origin is
`http://192.168.0.18:5173`.

| Method and route | Purpose |
| --- | --- |
| `POST /rag/v1/embed` | Upload and ingest one supported file |
| `POST /rag/v1/embed/text` | Ingest directly entered text |
| `GET /rag/v1/search` | Exact cosine retrieval |
| `GET /rag/v1/data/stats` | Lightweight RAG row counts |
| `DELETE /rag/v1/data` | Delete all RAG documents and chunks after exact confirmation |

### File ingestion

`POST /rag/v1/embed` accepts `multipart/form-data`:

| Field | Type | Rules |
| --- | --- | --- |
| `file` | file | Required; `.txt`, `.md`, `.docx`, or `.pdf` |
| `max_chunk_tokens` | integer | Optional; default 500, range 100–1000 |

The uploaded filename is reduced to a safe basename and persisted as
`source_name`; a client path is never stored. Unsupported extensions return
HTTP 415. Extraction errors return sanitized client errors. DOCX processing
limits return HTTP 413. OCR runtime, timeout, and recognition/render failures
map to sanitized 503, 504, and 422 responses respectively.

### Direct-text ingestion

`POST /rag/v1/embed/text` accepts JSON:

```json
{
  "text": "required non-whitespace text",
  "title": "optional display title",
  "max_chunk_tokens": 500
}
```

Blank text is rejected before model or database work. A blank or omitted title
uses a short display-name fallback derived from the first meaningful source
line. Direct text has `source_type="text"` and no filename.

### Ingestion response

Both ingestion routes return the same structure and preserve `"ok": true`:

| Object | Fields |
| --- | --- |
| `source` | `document_id`, `source_type`, `source_name`, nullable `filename`, `size_bytes`, `character_count`, `token_count` |
| `chunking` | applied maximum, chunk count, full token-count list, truncation flag, first ten chunk previews |
| preview item | one-based index, token/character counts, source character span, overlap with previous chunk, context |
| `timing_ms` | chunking, embedding, and total server processing time |

`total` includes extraction/OCR, chunking, embedding, validation, and database
insertion. OCR does not have a separate public timing field.

### Search

`GET /rag/v1/search` accepts:

| Query parameter | Rules |
| --- | --- |
| `query` | Required non-whitespace string |
| `top_k` | Default 5, range 1–20 |

The response contains an ordered `results` array and `timing_ms` for query
embedding, database search, and total server work. Each result contains:

- `id`, `similarity`, and `context`;
- nullable `document_id`, `source_type`, `source_name`, and `chunk_index`;
- nullable `source_start_character`, `source_end_character`, and `token_count`.

Legacy rows remain searchable through a `LEFT JOIN` and return null provenance.
The server does not add a rank field; consumers use result-array order.

### RAG data statistics and deletion

`GET /rag/v1/data/stats` returns document, total embedding, legacy embedding,
and provenance-bearing embedding counts.

`DELETE /rag/v1/data` requires the exact JSON body:

```json
{"confirmation":"DELETE"}
```

The operation deletes every row from `rag.embeddings` first and then every row
from `rag.documents` in one transaction. A failure rolls back both deletes.
It does not drop schema objects, use cascade deletion, truncate tables, or
reset identity sequences. This includes legacy embeddings with null
`document_id`.

## Extraction behavior

| Format | Current behavior |
| --- | --- |
| UTF-8 TXT | Strict UTF-8 decode; empty text rejected |
| UTF-8 Markdown | Same text behavior as TXT; markup is retained as text |
| PDF | Native `pypdf` text per page; OCR only when that page has no non-whitespace native text |
| DOCX | Top-level paragraphs/headings and tables extracted with `python-docx` |

PDF page order is preserved. Native and OCR text are never combined for the
same page. OCR rasterizes one fallback page at a time with Tesseract at 300 DPI,
`kor+eng`, `--psm 6`, a 30-second per-page timeout, and at most 50 OCR pages per
document. Standalone image upload is not supported.

DOCX paragraphs and headings become plain text blocks. Top-level table cells
are joined with tabs, rows with newlines, and document blocks with blank lines.
Embedded images are ignored; image-only DOCX is rejected because DOCX image OCR
is not implemented. DOCX preflight limits are 25 MiB compressed upload,
100 MiB declared uncompressed content, 2,000 archive members, and 50 MiB for one
member. Legacy `.doc`, complex visual-layout reconstruction, and advanced
nested-table fidelity are unsupported.

Extracted or OCR-derived text enters the same downstream `SourceDocument`
pipeline. Character spans are zero-based and end-exclusive offsets into that
final flattened source text. They are not PDF byte/page coordinates, OCR boxes,
DOCX XML offsets, Word page positions, or table coordinates.

## Chunking and embedding summary

- Model/tokenizer: `Qwen/Qwen3-Embedding-0.6B`.
- Device/runtime: `cuda:0`, BF16, normalized 1024-dimensional vectors.
- Document embeddings use no query prompt; query embeddings use
  `prompt_name="query"`.
- `max_chunk_tokens` defaults to 500 and accepts 100–1000 per request.
- The preferred minimum is 300 when the requested maximum is at least 300 and
  contracts safely below that maximum for smaller experiments.
- Natural boundaries are preferred in this order: paragraph, sentence
  punctuation, whitespace, then hard token split.
- Overlap normally remains between 40 and 80 tokens with a target near 60; the
  effective overlap contracts when required by small chunk maxima.

Per-request values are passed as function arguments; shared module state is not
mutated. See [Vector search](rag-vector-search.md) for algorithm and retrieval
details.

## Data model and transaction semantics

`sql/001-init-rag.sql` defines fresh installs; the additive provenance
migration is `sql/002-add-document-provenance.sql`.

### `rag.documents`

| Column | Definition |
| --- | --- |
| `id` | identity bigint primary key |
| `source_type` | required `file` or `text` |
| `source_name` | required display name |

### `rag.embeddings`

| Column | Definition |
| --- | --- |
| `id` | identity bigint primary key |
| `document_id` | nullable foreign key to `rag.documents.id` |
| `chunk_index` | nullable one-based per-document order |
| `source_start_character` / `source_end_character` | nullable source-text span |
| `token_count` | nullable positive count |
| `context` | required chunk text |
| `vector` | required `vector(1024)` |

Constraints require provenance fields to be either all null or all populated.
A partial unique index enforces `(document_id, chunk_index)` for provenance
rows. There is no `UNIQUE(context)`, no cascade delete, and no HNSW/IVFFlat
index.

One ingestion transaction creates one document row and all of its embedding
rows. Chunk indexes are deterministic and one-based; a one-chunk document uses
index 1. Any failure rolls back the document and every chunk together.
Duplicate ingestion is currently allowed.

The provenance migration preserved 71 pre-migration rows with null provenance;
no source identity was invented. Those rows were later removed during the
validated Empty Database operation. If an old backup is restored, null
provenance remains the intended legacy behavior.

## Current validation evidence

Recorded deterministic suites cover extraction, chunking, embedding and search
contracts, provenance transactions, OCR/DOCX fallbacks, data deletion, API
errors, and frontend integration without requiring live model/database work.

Recorded live validation covers:

- TXT, Markdown, native-text PDF, scanned PDF OCR, DOCX, and Direct Text
  ingestion paths; mixed native/OCR page selection is covered deterministically;
- source/document/chunk provenance and legacy null-provenance rendering;
- exact vector retrieval, timing, chunk previews, and empty-corpus search;
- guarded deletion of 109 embeddings and 7 documents, including legacy rows;
- OCR-derived searchability with English technical terms retained sufficiently
  for retrieval;
- the systemd-managed host server, Agent Server connectivity, and browser RAG
  Chat streaming.

The pre-empty custom and SQL backups were structurally inspected but have not
been restored. Restore fidelity, post-restore counts, and post-restore retrieval
remain unvalidated.

The last recorded post-empty live check contained one synthetic RAG Chat
validation document and one embedding. That is a dated observation, not a
guarantee of the database's state at documentation-read time; use
`GET /rag/v1/data/stats` for the actual current counts.

Retrieval-quality evidence is maintained only in
[retrieval evaluation](rag-retrieval-evaluation.md). Production retrieval is
still vector-only.

## Operations

Run commands from the repository root unless noted otherwise.

```bash
# Service state and logs
sudo systemctl status nexgent-rag.service --no-pager
sudo journalctl -u nexgent-rag.service -n 200 --no-pager
sudo journalctl -u nexgent-rag.service -f

# Host readiness (loads no new data)
curl --fail http://127.0.0.1:8765/rag/v1/data/stats
```

To install or update the repository-owned unit:

```bash
sudo install -m 0644 RAG/deploy/systemd/nexgent-rag.service \
  /etc/systemd/system/nexgent-rag.service
sudo systemd-analyze verify /etc/systemd/system/nexgent-rag.service
sudo systemctl daemon-reload
sudo systemctl enable nexgent-rag.service
sudo systemctl start nexgent-rag.service
```

Before the first systemd start, gracefully stop any manually launched Uvicorn
process and confirm port 8765 is free; two processes cannot bind the same port.
After any start or restart, check both `systemctl status` and the HTTP readiness
endpoint. Keep the narrowly scoped host firewall/network policy that permits
the Agent Server runtime to reach TCP 8765.

The service uses `Restart=on-failure`, a 15-second restart delay, bounded start
attempts, SIGTERM, and a 90-second stop timeout. It does not start or supervise
the PostgreSQL container. GPU/CUDA, model cache, Tesseract, PostgreSQL, and the
application `.env` must be available before the API can become ready.

Rollback is operationally separate from data restore:

```bash
sudo systemctl disable --now nexgent-rag.service
```

After disabling the unit, a manual Uvicorn process may be started only after
port 8765 is confirmed free. Removing the unit does not change RAG data.

## Known limitations and next work

- No authentication, authorization, TLS termination, or production ingress is
  implemented by the RAG API. Binding `0.0.0.0` relies on the existing narrow
  network policy.
- PostgreSQL container automatic startup/recovery is outside the systemd unit.
- Duplicate upload, source replacement, re-ingestion, versioning, and stable
  external source identity are unresolved.
- `source_name` is display metadata, not a Nextcloud file ID, path, or link.
- Production retrieval is vector-only. The lexical/RRF experiment is promising
  but remains offline and unindexed.
- Standalone images, legacy `.doc`, DOCX embedded-image OCR, and complex DOCX
  layout reconstruction are unsupported.
- OCR can misrecognize Korean/English boundaries; automatic per-page language
  selection and broader representative evaluation remain deferred.
- Backup restoration and a post-restore fixed retrieval regression remain
  unvalidated.
- Upload-size limits exist for DOCX only; broader upload policy, concurrency
  limits, structured logging/error policy, and duplicate controls need a
  production review.

RAG Chat-specific limitations—one-turn operation, no attachments, and no
conversation memory—are documented in
[RAG Chat Agent](../../agents/docs/rag-chat-agent.md).
