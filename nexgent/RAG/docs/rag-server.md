# RAG Server Implementation

Date: 2026-08-20

## Purpose

This is the running implementation record for exposing the validated RAG
ingestion and exact-search logic through a minimal FastAPI server.

## Current status

The minimal RAG proof-of-concept currently provides:

- `POST /rag/v1/embed`: accepts one UTF-8 `.txt`, UTF-8 `.md`, or text-based
  `.pdf`, extracts text, applies the existing token-based chunker, creates a
  normalized 1024-dimensional Qwen document embedding without a query prompt,
  and inserts the document's chunks atomically into PostgreSQL/pgvector.
- `GET /rag/v1/search`: requires `query`; accepts optional `top_k` with default 5
  and range 1–20; creates a Qwen query embedding and performs exact pgvector
  cosine retrieval. Results contain `id`, `similarity`, and `context`.
- FastAPI lifespan loads the tokenizer and model once per server process. Both
  endpoints reuse those process-local objects; cross-process sharing is not
  claimed.
- Deterministic tests and live end-to-end TXT, Markdown, and text-based PDF
  validations have passed. The manual PDF run inserted one chunk as `id=31` and
  retrieved that content at rank 1.
- A user-performed live real-project baseline evaluated five Markdown and five
  PDF questions: Top-1 was 7/10 (70%), while Top-3 and Top-5 were both 10/10
  (100%). This sample is too small to establish general retrieval accuracy.
- Scanned/image-only PDFs, OCR, DOCX, and the other deferred formats remain
  unsupported.

## Scope

- Keep every change inside `nexgent/RAG/`.
- Add one minimal FastAPI application without premature package abstraction.
- Expose one UTF-8 `.txt`/`.md`/text-based `.pdf` ingestion endpoint and one
  exact cosine-search endpoint.
- Reuse the existing token chunker, document/query embedding functions,
  PostgreSQL insert/search functions, model choice, and vector dimension.
- Do not add OCR, scanned/image-only PDF support, DOCX, approximate indexing,
  authentication, or Nexgent application integration in this phase.

## Architecture

The implemented single-process flow is:

```text
FastAPI lifespan
  ├─ load Qwen tokenizer once
  └─ load Qwen embedding model once
       ├─ POST /rag/v1/embed
       │    .txt/.pdf → text extraction → token chunking
       │              → document embedding → atomic insert
       └─ GET /rag/v1/search
            query → prompted query embedding → exact cosine search → results
```

The implementation uses one `rag_server.py` file and calls existing functions
from `embedd.py` and `search.py` rather than duplicate RAG logic. Server workers
are separate processes, so tokenizer/model reuse applies only within one server
process.

### Execution and concurrency considerations

- The shared Qwen model is reused by embed and search requests within one
  FastAPI server process. Concurrent access to that same model instance has not
  yet been load-tested, so request serialization and the concurrency policy
  remain future integration considerations.
- `POST /rag/v1/embed` reads the uploaded file asynchronously, then performs
  file extraction, token-based chunking, model inference, and PostgreSQL
  insertion synchronously. This is acceptable for the current minimal server.
  Event-loop blocking, inference offloading, and the worker strategy should be
  revisited if concurrent production traffic is introduced.

### Import-time environment behavior

- `rag_server.py` imports `embedd.py` and `search.py` at module import time.
- Both imported modules call `load_dotenv(BASE_DIR / ".env", override=False)`
  during import. Importing `rag_server.py` may therefore load variables from the
  RAG-local `.env` file when it exists; variables already present in the process
  environment are not overwritten because `override=False` is used.
- This behavior was verified from source code only. The `.env` file was not
  inspected or modified during this documentation update.

## API contracts

### `POST /rag/v1/embed`

Request:

- `multipart/form-data` containing one uploaded `.txt`, `.md`, or `.pdf` file.
- TXT and Markdown content must be non-empty valid UTF-8. PDF content must
  contain extractable non-whitespace text.

Processing:

1. Route by the case-insensitive `.txt`, `.md`, or `.pdf` filename extension.
2. Decode TXT/Markdown strictly as UTF-8, or extract PDF text in page order
   with `pypdf` and no OCR.
3. Apply the existing Qwen-tokenizer chunking strategy.
4. Generate normalized 1024-dimensional document embeddings without a query
   prompt.
5. Insert all chunks for that document with the existing atomic PostgreSQL
   insertion function.

Success response:

```json
{"ok": true}
```

Empty/whitespace-only files, unsupported extensions, and invalid TXT/Markdown
UTF-8 return an appropriate HTTP client error without embedding or insertion.
A PDF with no extractable text returns HTTP 400 explaining that
scanned/image-only PDFs are not supported. Unsupported extensions return HTTP
415.

### `GET /rag/v1/search`

Query parameters:

- `query`: required non-empty string; surrounding whitespace is removed.
- `top_k`: optional integer; defaults to 5 and must be between 1 and 20.
- No JSON request body is used.

Example:

```bash
curl -sG http://127.0.0.1:8765/rag/v1/search \
  --data-urlencode "query=대한민국의 수도는 어디인가요?" \
  --data-urlencode "top_k=1"
```

Processing uses `prompt_name="query"`, normalized 1024-dimensional query
embeddings, and the existing read-only exact pgvector cosine search.

Success response:

```json
{
  "results": [
    {
      "id": 1,
      "similarity": 0.75,
      "context": "matched source text"
    }
  ]
}
```

Each ranked result contains `id`, `similarity`, and `context`. Similarity is the
cosine similarity returned by the validated pgvector search and is not accuracy,
probability, or confidence.

## Model/tokenizer lifecycle

- FastAPI lifespan loads the tokenizer for
  `Qwen/Qwen3-Embedding-0.6B` once per server process.
- The same lifespan loads the BF16 CUDA embedding model once per server
  process.
- Both endpoint handlers retrieve and reuse those exact process-local
  objects.
- This design does not provide or claim cross-process model sharing.

## Current file support

- One uploaded UTF-8 `.txt`, UTF-8 `.md`, or text-based `.pdf` file per embed
  request.
- TXT decoding preserves its internal line breaks and paragraph structure.
- Markdown reuses the same strict UTF-8 text path and preserves headings, lists,
  syntax, line breaks, and paragraph structure without parsing or stripping.
- PDF extraction uses `pypdf==6.16.1`, visits pages in order, preserves the
  extractor's internal line structure, and separates non-empty pages with a
  blank line before token chunking.
- Reject empty/whitespace-only input, unsupported extensions, invalid TXT
  UTF-8, unreadable PDFs, and PDFs with no extractable text.
- Duplicate ingestion remains allowed under the existing proof-of-concept
  policy.

## Deferred file extraction/OCR

Markdown-aware structural chunking, scanned/image-only PDF OCR, general image
OCR, DOCX, HWP, PPTX, XLSX, multi-file requests, archive handling, broad
MIME/signature detection, and production document extraction are outside the
current scope. Markdown currently uses the same general token chunker as plain
text. PDF text extraction depends on how each PDF encodes and orders its text;
support for text-based PDF does not mean that every PDF layout or encoding is
supported faithfully.

## Validation

Validation evidence is intentionally separated by execution context:

1. **Offline deterministic/mock validation:** The latest full RAG-local suite
   passed all 33 tests in 2.481 seconds: nine CLI file-ingestion tests, eight
   token-chunking/lifecycle tests, eleven file-extraction tests, and five server
   endpoint tests. Coverage includes GET query validation, response formatting,
   model/tokenizer reuse, prompt behavior, normalized 1024-dimensional
   embeddings, and mocked insert/search boundaries. Server endpoint tests use
   `httpx.ASGITransport` without a live server or database.
2. **Codex-executed bounded live validation:** The loopback server loaded Qwen
   once, retrieved existing Korean rows, inserted one TXT chunk as `id=29`, and
   retrieved it at rank 1 with an exact-keyword query. This run used the former
   POST search interface and remains historical evidence only.
3. **User-performed manual TXT validation:** A one-time TXT upload was stored as
   `id=30`; exact-keyword and semantic searches ranked it first, and same-process
   tokenizer/model reuse was observed.
4. **User-performed manual PDF validation:** A one-time text-based PDF upload
   passed through `pypdf`, token chunking, Qwen embedding, PostgreSQL insertion,
   and pgvector retrieval. It produced exactly one row/chunk as `id=31`, which
   semantic search ranked first. Scanned/image-only PDFs were not validated and
   remain unsupported.
5. **User-performed corrected GET validation:** Two GET searches returned the
   expected Seoul and Hallasan rows, process-local model reuse was observed, and
   the superseded POST method returned HTTP 405 with `Allow: GET`.
6. **User-performed live real-project retrieval evaluation:** One real Markdown
   document (21 chunks) and one real text-based PDF (6 chunks) were evaluated
   with five questions each. The first sufficient-evidence chunk ranked Top-1
   for 7/10 questions and within Top-3 for all 10. This is a small baseline, not
   a general accuracy claim.

The detailed IDs, similarities, chunk counts, and observations remain in the
chronological log below. At the initial PDF implementation checkpoint, PDF
validation was deliberately offline and write-free; the later user-performed
manual PDF validation subsequently exercised the live API/database path.

Validation command:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 PYTHONPATH="$PWD" \
  .venv/bin/python -m unittest discover -s tests -v
```

## Remaining work

1. Load-test concurrent access to the process-local Qwen model and decide the
   request serialization/concurrency policy. Revisit event-loop offloading and
   deployment worker strategy because embed processing after the asynchronous
   file read is synchronous.
2. Expand representative real-project retrieval evaluation beyond the current
   10-question baseline before changing chunking or retrieval design. Investigate
   why broad project chunks sometimes outrank exact rule-bearing or numeric/year
   chunks, while retaining the measured Top-1 70% and Top-3/Top-5 100% baseline
   as sample-specific evidence.
3. Define source/document identity and duplicate/re-ingestion semantics before
   production use. Duplicate ingestion is currently allowed, so uploading the
   same source again can create additional rows; no final deduplication or
   versioning policy has been chosen, and `UNIQUE(context)` is not assumed.
4. Decide other production concerns such as authentication, upload-size limits,
   and error/logging policy before integration with another service.
5. Add scanned/image-only PDF OCR, image OCR, DOCX, other formats, or richer
   metadata only after file-extraction and source-identity requirements are
   defined.

## Chronological implementation log

### 2026-08-20 — Server scope and route discovery

**Checked**

- Reviewed RAG-local documentation and `search.py` for an agreed search HTTP
  route or version.
- Confirmed that `search.py` currently defines a persistent CLI, query
  embedding, exact cosine SQL, and top-k validation, but no HTTP route.
- Confirmed that the documentation contains no agreed search endpoint path.

**Decision / blocker**

- At this historical checkpoint, `POST /rag/v1/embed` was explicit and could be
  implemented after the complete server API contract was known.
- The search method/path/version was still ambiguous at that checkpoint, so
  application implementation stopped before defining a route rather than
  inventing a project contract. The following entry records its resolution.

**Changed**

- Created this RAG-local server implementation log and added it to the RAG
  documentation map.
- No application code or runtime resource was changed.

**Documentation validation**

- Required headings, the documentation-map link, trailing whitespace, and
  credential-pattern checks passed.
- Repository-root `git status --short` showed only
  `nexgent/RAG/docs/README.md` and `nexgent/RAG/docs/rag-server.md` as changes
  from this task. No path outside `nexgent/RAG/` was modified.

### 2026-08-20 — Search route confirmed; implementation resumed

**Historical contract — superseded later on 2026-08-20**

- At this implementation checkpoint, search used `POST /rag/v1/search` with a
  JSON body containing `query` and optional `top_k`. The later API-contract
  correction entry supersedes this interface with GET query parameters.
- `query` must be non-empty. `top_k` defaults to 5 and must be between 1 and 20.
- The response envelope is `results`; each item contains `id`, `similarity`, and
  `context`. Similarity remains the pgvector cosine-similarity value.

**Decision**

- Resume the minimal `rag_server.py` implementation and mocked FastAPI tests.
- Do not perform a live database insertion or change existing RAG runtime,
  schema, index, model, dimension, or chunking configuration.

**Environment discovery and dependency setup**

- The existing RAG-local `.venv` contained `httpx==0.28.1` but did not contain
  FastAPI, Starlette, Uvicorn, Pydantic, or python-multipart.
- The first sandboxed package request failed because DNS was unavailable. The
  approved retry installed server dependencies only into the RAG-local `.venv`.
- Added `requirements-server.txt` with the direct server/test dependencies:
  `fastapi==0.141.1`, `httpx==0.28.1`, `python-multipart==0.0.32`, and
  `uvicorn==0.52.4`.
- The resolver installed FastAPI 0.141.1, Starlette 1.6.0, Pydantic 2.13.4,
  python-multipart 0.0.32, and Uvicorn 0.52.4. Existing model/database package
  choices were not changed.

Command:

```bash
UV_CACHE_DIR="$PWD/.cache/uv" \
  uv pip install --python .venv/bin/python fastapi python-multipart uvicorn
```

**Implemented**

- Added `rag_server.py` with FastAPI lifespan ownership of one tokenizer and one
  embedding model per process.
- Added `POST /rag/v1/embed` for one non-empty valid UTF-8 `.txt` upload. It
  calls `embedd.chunk_document()`, `embedd.embed_documents()`, and
  `embedd.insert_chunks()` and returns only `{"ok": true}`.
- Added the then-current `POST /rag/v1/search` with Pydantic validation for a
  non-empty query and top-k 1–20/default 5. This historical implementation was
  later superseded by GET query parameters. It calls `search.embed_query()` and
  `search.search_database()` and maps the returned cosine similarity without
  transformation.
- Added `tests/test_rag_server.py`. The fake tokenizer/model and mocked database
  boundaries ensure deterministic behavior without model weights, CUDA, or
  PostgreSQL access.

**Deterministic validation result**

- All three server test cases passed in 0.023 seconds.
- Two embed and two search requests in one lifespan caused exactly one
  tokenizer load and one model load. Both endpoints reused the retained model.
- Actual `embedd.embed_documents()` calls omitted a query prompt; actual
  `search.embed_query()` calls supplied `prompt_name="query"`. All calls used
  normalized vectors and the existing 1024-dimensional validation.
- Default/override/invalid top-k, blank-query, empty/blank/unsupported/invalid
  upload, response-shape, and no-database-mutation assertions passed.
- No server process, live model, CUDA operation, PostgreSQL connection, or live
  API insertion was started during validation.
- The subsequent full offline regression passed all 20 RAG-local tests in 2.454
  seconds, including the pre-existing file-ingestion and token-chunking suites.

### 2026-08-20 — Concurrency and import-time environment clarification

**Verified**

- `rag_server.py` imports `embedd.py` and `search.py`; both imported modules
  invoke `load_dotenv(BASE_DIR / ".env", override=False)` at import time.
- Consequently, importing the server may load the RAG-local `.env` when it is
  present, while preserving variables already set in the process environment.
- Verification was limited to source inspection. The `.env` file was not read
  or modified.

**Documented limitations and follow-up**

- The one Qwen instance is reused within a FastAPI server process, but concurrent
  access to that shared instance has not been load-tested. A request
  serialization/concurrency policy remains a future integration decision.
- After its asynchronous upload read, `/rag/v1/embed` performs chunking, model
  inference, and PostgreSQL insertion synchronously. This remains acceptable for
  the minimal proof of concept; event-loop blocking and worker strategy require
  review if concurrent production traffic is introduced.
- No application code or runtime state was changed for this clarification.

### 2026-08-20 — Bounded live API validation

**Server startup and pre-insertion search**

- Started one server process, bound only to `127.0.0.1:8765`, with:

  ```bash
  .venv/bin/uvicorn rag_server:app --host 127.0.0.1 --port 8765
  ```

- Startup completed successfully. The lifespan logged one tokenizer load and
  one `Qwen/Qwen3-Embedding-0.6B` BF16 load on `cuda:0`.
- The first read-only request used `top_k=1`. At the time of this historical
  run, search still used the now-superseded POST interface:

  ```http
  POST /rag/v1/search
  Content-Type: application/json

  {"query":"대한민국의 수도는 어디인가요?","top_k":1}
  ```

  Response:

  ```json
  {"results":[{"id":1,"similarity":0.6524552971238102,"context":"서울은 대한민국의 수도이며 정치와 경제의 중심지입니다."}]}
  ```

- A second `top_k=1` request in the same process queried
  `한라산은 어느 지역에 있나요?`.

  ```json
  {"results":[{"id":2,"similarity":0.608027578080082,"context":"제주도 한라산은 대한민국에서 가장 높은 산입니다."}]}
  ```

- The second request produced no additional tokenizer/model-loading message;
  the lifespan-owned objects were reused.

**Bounded insertion and post-insert retrieval**

- The one-time UTF-8 validation file is
  `server_live_validation_20260820.txt`. Its unique keyword is
  `푸른돌고래서버검증키워드`.
- A read-only pre-insertion check found 28 total rows and no row containing the
  unique keyword.
- After the successful read-only searches, the file was uploaded exactly once:

  ```http
  POST /rag/v1/embed
  Content-Type: multipart/form-data

  file=@server_live_validation_20260820.txt
  ```

  Response:

  ```json
  {"ok":true}
  ```

- The server reported one embedded chunk, dimension 1024, and maximum embedding
  norm error `0.00061893`. No additional tokenizer/model-loading message was
  emitted during ingestion.
- The first post-insert question,
  `푸른돌고래서버검증키워드 문서의 검증 목적은 무엇인가요?`, did not return
  the new row first. It returned the older `보라코끼리청킹테스트` chunk
  (`id=18`, similarity `0.5390020416593345`). This is a retrieval-quality
  observation rather than an HTTP, insertion, or model-lifecycle failure.
- A follow-up exact-keyword request in the same process used the same historical
  POST interface:

  ```http
  POST /rag/v1/search
  Content-Type: application/json

  {"query":"푸른돌고래서버검증키워드","top_k":5}
  ```

  The newly inserted row ranked first as `id=29`, with similarity
  `0.44663360953344344` and the expected uploaded context.
- A final read-only transaction found 29 total rows, exactly one row containing
  the unique keyword, and matching ID `29`. The observed delta was therefore
  exactly one chunk/row. The upload was not repeated, and no existing row was
  modified or deleted.
- Across startup, two pre-insert searches, one embed, and two post-insert
  searches, the server emitted only its initial tokenizer and Qwen load
  messages. Uvicorn then completed a normal application shutdown.

### 2026-08-20 — User-performed manual live API validation

This entry records manual observations supplied by the user. It is distinct
from the preceding automated/mock validation and Codex-executed bounded live
validation. These observations are evidence for this one manual run only; they
are not guarantees about production behavior, concurrency, retrieval accuracy,
or support for other file types.

**Server startup and pre-ingestion searches**

- The existing server was started on loopback with:

  ```bash
  .venv/bin/uvicorn rag_server:app --host 127.0.0.1 --port 8765
  ```

- Two read-only searches were made before ingestion using the then-current
  `POST /rag/v1/search` contract, which was later superseded by GET query
  parameters:
  - Query `대한민국의 수도는 어디인가요?` with `top_k=1` returned `id=1`
    and the expected Seoul context at rank 1.
  - Query `대한민국에서 가장 높은 산은 무엇인가요?` with `top_k=1`
    returned `id=2` and the expected Hallasan context at rank 1.
- The tokenizer and `Qwen/Qwen3-Embedding-0.6B` model loaded during server
  startup only. Subsequent search and embed requests in that same server
  process reused the already-loaded objects. No cross-process reuse was tested
  or claimed.

**Single manual upload**

- The file `manual_server_test_20260820.txt` was created and uploaded exactly
  once. Its content was:

  ```text
  푸른달연구소는 가상의 해양 관측 시스템입니다. 해안에 설치된 센서는 매일 수온과 파도의 변화를 기록하고, 관리자는 저장된 데이터를 통해 시간에 따른 해양 환경의 변화를 확인할 수 있습니다.

  이 문서의 고유 키워드는 청록돌고래API테스트입니다.
  ```

- `POST /rag/v1/embed` returned:

  ```json
  {"ok":true}
  ```

- The server log reported one embedded chunk, dimension 1024, and HTTP 200 for
  the embed request. The inserted document received `id=30`.
- This upload must not be repeated: duplicate-ingestion prevention is not yet
  implemented, so another upload of the same document would create another row.

**Post-ingestion retrieval**

- Exact unique-keyword search used query `청록돌고래API테스트` with `top_k=1`.
  The newly uploaded `푸른달연구소` context (`id=30`) ranked first with cosine
  similarity `0.563908738641001`.
- Semantic search used query
  `해안 센서로 수온과 파도 변화를 기록하는 시스템은 무엇인가요?` with
  `top_k=3`. The same `id=30` context ranked first with cosine similarity
  `0.6792894855052316`; older, less-relevant test chunks ranked below it.
- All observed API requests returned HTTP 200. No model reload was observed
  between requests within the same running server process.

**Scope of this documentation update**

- This entry documents user-reported manual evidence only. No runtime or
  database action was performed while adding it.

### 2026-08-20 — Text-based PDF ingestion implementation

**Checked and decided**

- No PDF text-extraction package was installed in the RAG-local `.venv` before
  this change (`pypdf`, `PyPDF2`, `pdfminer`, and `fitz` were absent).
- Selected the focused pure-Python `pypdf` reader for page-ordered text
  extraction. OCR is deliberately not part of this path.
- Kept file extraction separate from token chunking, Qwen embedding, and
  PostgreSQL insertion so both TXT and PDF feed the same validated downstream
  functions.

**Dependency setup**

- The first sandboxed package request failed because DNS resolution was
  unavailable. The approved network retry installed only `pypdf==6.16.1` in the
  existing RAG-local `.venv`.
- Added the same exact version as a direct dependency in
  `requirements-server.txt`; unrelated dependency versions were unchanged.

**Implementation in progress at this checkpoint**

- Added `file_extraction.py` with extension routing, strict UTF-8 TXT decoding,
  and page-ordered PDF extraction.
- PDF page text is retained in page order, internal extracted line structure is
  preserved, and non-empty pages are separated with a blank line.
- A PDF with no extractable non-whitespace text is rejected explicitly; no OCR
  is attempted, and scanned/image-only PDFs remain unsupported.
- `POST /rag/v1/embed` now delegates extraction and then calls the existing
  `chunk_document()`, `embed_documents()`, and `insert_chunks()` path. Its
  success response remains `{"ok": true}`.
- Deterministic tests and the authoritative current-state sections will be
  updated after validation. No live API upload or database insertion is part of
  this change.

**Validation completed**

- A write-free AST syntax check passed for `file_extraction.py`,
  `rag_server.py`, and the two changed test modules.
- Seven deterministic extraction tests passed, including real two-page PDF
  construction/extraction and a real PDF with no text.
- Four mocked server tests passed. A deterministic real PDF entered the actual
  extraction and chunking code, then the existing document embedding and mocked
  atomic insertion path. The search endpoint tests remained unchanged and
  passed.
- The full RAG-local suite passed all 28 tests in 2.499 seconds.
- At this initial PDF implementation-validation checkpoint, no live FastAPI
  process, Qwen model load, CUDA operation, PostgreSQL connection, API
  ingestion, or database mutation was performed. The later user-performed PDF
  live-validation entry supersedes any inference that PDF remained untested
  against the API/database path.

### 2026-08-20 — User-performed manual PDF live validation

This entry records manual observations supplied by the user after the
deterministic/mock PDF tests. It is separate from those offline tests, the
earlier Codex-executed bounded TXT live validation, and the earlier
user-performed TXT live validation. The observations are evidence for this one
manual PDF run only and are not generalized into production guarantees.

**Server and one-time PDF upload**

- The existing server was started on loopback with:

  ```bash
  .venv/bin/uvicorn rag_server:app --host 127.0.0.1 --port 8765
  ```

- The text-based PDF `manual_pdf_test_20260820.pdf` contained:

  ```text
  푸른등대연구소는 가상의 해양 안전 관측 시스템입니다. 관리자는 해안 센서에서 수집된 파고와 수온 데이터를 확인하여 시간대별 환경 변화를 비교할 수 있습니다. 이 PDF의 고유 키워드는 은빛문어PDF테스트입니다.
  ```

- Exactly one `POST /rag/v1/embed` request was made for this PDF. It returned:

  ```json
  {"ok":true}
  ```

- The server log reported `Embedded 1 chunk(s): dimension=1024` and
  `POST /rag/v1/embed HTTP/1.1 200 OK`.
- The tokenizer and `Qwen/Qwen3-Embedding-0.6B` model loaded during server
  startup only. The PDF embed and subsequent searches reused those objects in
  the same server process; no cross-process reuse was tested or claimed.

**Retrieval and read-only storage confirmation**

- Exact keyword query `은빛문어PDF테스트` with `top_k=1` returned the newly
  inserted PDF content at rank 1.
- Semantic query
  `해안 센서에서 파고와 수온 데이터를 확인하는 시스템은 무엇인가요?` with
  `top_k=3` returned the new content at rank 1 as `id=31`, with cosine
  similarity `0.7424533826742321`.
- A read-only PostgreSQL inspection confirmed exactly one stored row/chunk for
  the uploaded PDF: `id=31`, context beginning
  `푸른등대연구소는 가상의 해양 안전 관측 시스템입니다...` and containing
  the unique keyword `은빛문어PDF테스트`.
- `id=30` was confirmed to be the earlier TXT/API validation document containing
  `청록돌고래API테스트`, not the PDF upload.

**Observed conclusion and scope**

- This manual run exercised the complete text-based PDF path:

  ```text
  PDF upload → pypdf text extraction → token-based chunking
    → Qwen document embedding → PostgreSQL insertion
    → query embedding → pgvector retrieval
  ```

- The PDF produced one chunk, and semantic search retrieved the inserted content
  at rank 1.
- The PDF must not be uploaded again because duplicate-ingestion prevention is
  not implemented.
- This documentation update performed no runtime or database action and did not
  inspect `.env`.

### 2026-08-20 — Successful JSON response newline formatting

**Decision and change**

- Added a small `JSONResponse` subclass as the FastAPI application's default
  response class. It preserves FastAPI's compact JSON serialization and ensures
  that each successful JSON response body ends with exactly one newline byte.
- Applied the formatting consistently to successful `POST /rag/v1/embed` and
  the then-current `POST /rag/v1/search` responses. The later API-contract
  correction changed search to GET without changing this formatting behavior.
  At this checkpoint, endpoint paths, status codes, request and JSON response
  contracts, model behavior, retrieval, chunking, and database logic were not
  changed.

**Validation completed**

- Deterministic endpoint tests now check one trailing newline, reject a doubled
  trailing newline, and continue parsing and comparing the original JSON data.
- A write-free AST syntax check passed for `rag_server.py` and its server test.
- The full RAG-local offline suite passed all 28 tests in 2.522 seconds without
  starting Uvicorn, loading Qwen, connecting to PostgreSQL, or performing an
  ingestion.

### 2026-08-20 — Search HTTP method corrected to the original API design

**Confirmed and changed**

- The original project API design specifies `POST /rag/v1/embed` and
  `GET /rag/v1/search`. The initial server implementation's POST search route
  was therefore superseded.
- Search now uses only `GET /rag/v1/search`. `query` and `top_k` are query
  parameters; no JSON request body is accepted by the public search contract.
- `query` remains required, is stripped of surrounding whitespace, and must not
  be blank. `top_k` remains optional with default 5 and valid range 1–20.
- The old `POST /rag/v1/search` route was not retained as a compatibility alias.
  Requests using that method receive HTTP 405.
- The response envelope and fields remain unchanged, including the single
  trailing newline introduced by the preceding formatting change.

Current request example:

```bash
curl -sG http://127.0.0.1:8765/rag/v1/search \
  --data-urlencode "query=대한민국의 수도는 어디인가요?" \
  --data-urlencode "top_k=1"
```

**Unchanged internals**

- The handler still calls `search.embed_query()` and
  `search.search_database()`. Query prompting, normalized 1024-dimensional
  embeddings, exact pgvector cosine ranking, similarity meaning, and result
  mapping are unchanged.
- Embed routing, extraction, chunking, insertion, model/tokenizer lifespan, and
  database behavior are unchanged.

**Validation completed**

- Deterministic tests were updated to send GET query parameters and to reject
  the superseded POST method with HTTP 405.
- Required and blank `query`, default `top_k=5`, valid `top_k=2`, invalid 0/21,
  unchanged response JSON/newline formatting, prompt behavior, and lifespan
  reuse all passed.
- A write-free AST syntax check passed, and the full RAG-local suite passed all
  28 tests in 2.455 seconds.
- No server process, Qwen model load, PostgreSQL connection, database mutation,
  or live API request was performed.

### 2026-08-20 — User-performed manual validation of GET search

This entry records manual live observations supplied by the user after the
search method was corrected. It is separate from deterministic/mock tests and
the earlier live-validation entries that exercised the now-superseded POST
search interface.

**Server startup and process-local lifecycle**

- The server was started on loopback with:

  ```bash
  .venv/bin/uvicorn rag_server:app --host 127.0.0.1 --port 8765
  ```

- The tokenizer and `Qwen/Qwen3-Embedding-0.6B` model loaded once during server
  startup.

**Corrected GET searches**

- The first request used `GET /rag/v1/search` with query
  `대한민국의 수도는 어디인가요?` and `top_k=1`. It returned HTTP 200 with:
  - `id=1`
  - cosine similarity `0.6524552971238102`
  - context `서울은 대한민국의 수도이며 정치와 경제의 중심지입니다.`
- The second request used the same running server process and
  `GET /rag/v1/search` with query
  `대한민국에서 가장 높은 산은 무엇인가요?` and `top_k=1`. It returned
  HTTP 200 with:
  - `id=2`
  - cosine similarity `0.693271093848147`
  - context `제주도 한라산은 대한민국에서 가장 높은 산입니다.`
- The server logged query embedding for both requests but did not log another
  tokenizer or Qwen load. This manually demonstrates reuse within that one
  server process only; it does not establish cross-process reuse.

**Superseded method rejection and confirmed contract**

- A manual `POST /rag/v1/search` request returned HTTP 405 Method Not Allowed,
  response header `Allow: GET`, and body:

  ```json
  {"detail":"Method Not Allowed"}
  ```

- The observed public endpoint contract is therefore:

  ```text
  POST /rag/v1/embed
  GET  /rag/v1/search
  ```

- No embed or upload request was made, and no database mutation occurred during
  this user-performed validation.
- This documentation update itself performed no server, API, test, database,
  Docker, model, or other runtime action and did not inspect `.env`.

### 2026-08-20 — UTF-8 Markdown ingestion implementation

**Decision and implementation**

- Added `.md` to the existing file-extraction extension router. Markdown uses
  the same strict UTF-8 decoding path as TXT.
- The decoded Markdown source is preserved unchanged, including headings,
  lists, emphasis syntax, line breaks, and paragraph spacing. No Markdown parser
  or new dependency was added.
- Markdown feeds the existing token-based `chunk_document()`, Qwen document
  embedding without a query prompt, and atomic PostgreSQL insertion path.
- Markdown-aware structural chunking is deliberately deferred; the existing
  token limits, overlap, and natural-boundary rules are unchanged.

**Validation completed**

- Deterministic tests cover Korean multiline Markdown preservation, empty and
  whitespace-only rejection, invalid UTF-8 rejection, and the complete mocked
  extraction/chunking/embedding/insertion path.
- A write-free AST syntax check passed for the extraction module and its changed
  tests.
- The full RAG-local suite passed all 33 tests in 2.481 seconds. Existing TXT,
  PDF, corrected GET search, response formatting, and lifespan-reuse tests
  remained passing.
- No Uvicorn server, Qwen/CUDA model, PostgreSQL connection, Docker resource, or
  live ingestion was started or used.

### 2026-08-20 — User-performed manual live Markdown validation

This entry records only the user's observations from one manual Markdown run.
It is separate from the deterministic/mock Markdown tests and does not establish
general production retrieval guarantees.

**Server and one-time Markdown upload**

- The server was already running on loopback with:

  ```bash
  .venv/bin/uvicorn rag_server:app --host 127.0.0.1 --port 8765
  ```

- The file `manual_md_test_20260820.md` was uploaded exactly once with this
  content:

  ```markdown
  # 별무리 관측소

  별무리 관측소는 가상의 야간 기상 관측 시스템입니다.

  ## 관측 항목

  - 기온
  - 습도
  - 풍속

  관리자는 매일 저장된 관측 기록을 비교하여 시간대별 기상 변화를 확인할 수 있습니다.

  이 Markdown 문서의 고유 키워드는 자주고슴도치MD테스트입니다.
  ```

- `POST /rag/v1/embed` returned HTTP 200 and:

  ```json
  {"ok":true}
  ```

- The server reported one embedded 1024-dimensional chunk. The stored context
  preserved the Markdown syntax and line/paragraph structure, and the inserted
  row was `id=32`.

**Observed retrieval results**

- Natural-language query
  `기온과 습도와 풍속을 기록하는 가상의 관측 시스템은 무엇인가요?`
  returned `id=32` at rank 1 with cosine similarity approximately
  `0.7290908234207066`. The returned context was the uploaded Markdown document.
- Arbitrary identifier-only query `자주고슴도치MD테스트` did not return
  `id=32` within the top 10; older validation rows ranked above it. This is a
  retrieval-quality observation, not a Markdown ingestion failure.
- Follow-up query `자주고슴도치MD테스트 별무리 관측소` with `top_k=5`
  returned `id=32` at rank 1 with cosine similarity `0.5859440410321766`.

**Interpretation and limits**

- This manual run exercised UTF-8 Markdown extraction, unchanged token-based
  chunking, Qwen document embedding, PostgreSQL insertion, and GET search
  end-to-end. Semantically meaningful natural-language queries retrieved the
  Markdown row at rank 1 in this run.
- Under the current Qwen embedding plus exact cosine-similarity design, this
  observation does not establish that an arbitrary identifier-only query will
  rank the containing row first. The server does not implement lexical or exact
  string-match search, and no search implementation change was made from this
  evidence.
- Duplicate validation rows already exist and can occupy multiple top-k
  positions, potentially distorting later retrieval-quality evaluation. No row
  was deleted or modified for this documentation entry.
- The Markdown upload must not be repeated because duplicate-ingestion
  prevention is not implemented.
- This documentation update performed no server, API, test, model/CUDA,
  PostgreSQL, Docker, ingestion, search, or `.env` action.

### 2026-08-20 — User-performed real-project retrieval-quality evaluation

This entry records the completed user-performed evaluation of two real project
documents. The results describe this 10-question sample only and are not a
general retrieval-accuracy claim.

**Documents and evaluation method**

- `analysis_wardevaluation_recovery_data_lineage.md` was ingested once and
  produced 21 chunks.
- `광명시 AI.pdf` was ingested once and produced 6 chunks.
- Ten questions were evaluated: five based on the Markdown document and five
  based on the PDF.
- The evaluation rank is the position of the first returned chunk containing
  sufficient evidence to answer the question.

**Observed ranks**

| Question | First sufficient-evidence rank |
| --- | ---: |
| MD-Q1 | 1 |
| MD-Q2 | 3 |
| MD-Q3 | 1 |
| MD-Q4 | 1 |
| MD-Q5 | 1 |
| PDF-Q1 | 1 |
| PDF-Q2 | 1 |
| PDF-Q3 | 2 |
| PDF-Q4 | 1 |
| PDF-Q5 | 3 |

| Baseline metric | Result |
| --- | ---: |
| Top-1 hit rate | 7/10 (70%) |
| Top-3 hit rate | 10/10 (100%) |
| Top-5 hit rate | 10/10 (100%) |

**Observed ranking patterns and interpretation**

- No question missed its sufficient supporting chunk within Top-3.
- Some fine-grained rule questions returned a broadly related chunk before the
  exact rule-bearing chunk.
- Some numeric/year questions returned a semantically broad project chunk ahead
  of the exact-answer chunk. For example, the question about the 2024 participant
  count returned the chunk containing `2024년 920명` at rank 3.
- These are currently treated as retrieval-ranking precision observations, not
  ingestion, extraction, chunking-coverage, embedding, storage, or API failures.
- Ten questions are too few to support a general retrieval-accuracy claim.
  Representative evaluation should be expanded before changing chunking or the
  retrieval design.

**Separate identifier-only observation**

- The earlier arbitrary query `자주고슴도치MD테스트` alone missed its
  containing Markdown chunk within Top-10, while
  `자주고슴도치MD테스트 별무리 관측소` returned it at rank 1.
- That result remains a separate lexical/exact-keyword limitation observation
  under the current embedding plus cosine-retrieval design; it is not part of
  this 10-question real-project baseline, and no lexical search is implemented.

**Documentation-only scope**

- This entry used only the user-provided measurements. Neither real document was
  re-ingested, retrieval was not rerun, and no code, test, API, model, database,
  Docker, chunking, or `.env` action was performed.
