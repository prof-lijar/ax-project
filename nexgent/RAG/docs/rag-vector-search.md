# RAG Vector Search Implementation

Date: 2026-08-19

## Purpose

This is the running implementation record for the PostgreSQL/pgvector RAG
pipeline. It is updated after each meaningful discovery, decision,
implementation step, and validation run.

Secrets must not be recorded here. Commands and examples use redacted values or
environment-variable names where connection details would otherwise appear.

## Status legend

- **Actual host fact**: confirmed by the user in the interactive Linux shell;
  authoritative for host architecture and capability decisions.
- **Codex sandbox observation**: observed only inside the restricted Codex
  execution environment; not evidence that the actual host lacks a capability.
- **Decision**: an implementation choice adopted for this project.
- **Open question / assumption**: not yet verified or agreed.
- **Historical checkpoint**: accurate for a dated point in the running log but
  potentially superseded by a later entry; authoritative current state appears
  above the chronological log.

## Current implementation at a glance

**Overall status: Minimal RAG proof-of-concept complete;
production/source-document integration is not yet complete.**

- **Database:** The implemented proof-of-concept uses an isolated
  PostgreSQL/pgvector instance with database `nextgent`, schema `rag`, and table
  `rag.embeddings(id, context, vector(1024))`. The final PostgreSQL deployment
  topology still requires project-owner confirmation.
- **Embedding:** `Qwen/Qwen3-Embedding-0.6B` runs in BF16 on CUDA and produces
  normalized 1024-dimensional vectors. Documents use no query prompt; queries
  use `prompt_name="query"`.
- **Chunking:** Source documents are split with the Qwen tokenizer using an
  experimental preferred range of 300–500 tokens, a maximum target of 500
  tokens, and 40–80 tokens of exact overlap aimed near 60. Boundaries are
  selected in paragraph → sentence → whitespace → token-level hard-split
  order. These starting parameters still require evaluation with real project
  documents.
- **Ingestion:** `embedd.py` supports a persistent interactive multi-document
  session and UTF-8 file mode (`embedd.py file1.txt file2.txt`); file mode does
  not require `.done`. Qwen loads lazily once and is reused across documents or
  files within that process. Each source document has its own atomic insert
  transaction.
- **Retrieval:** `search.py` is a persistent multi-query session. It lazily
  loads Qwen once per process, performs exact pgvector cosine retrieval, and
  accepts top-k values from 1–20 with a default of 5.
- **Duplicate ingestion:** Duplicate content is currently allowed. Source/chunk
  identity and re-ingestion policy remain unresolved.
- **Indexing:** No HNSW or IVFFlat index exists; exact search is intentional at
  the current scale.
- **Validation:** Korean embedding and exact-search smoke tests, automatic
  chunking checks, persistent model-reuse checks, and nine deterministic
  file-ingestion tests passed.

## Current status

### Actual host facts

- At the initial repository inspection, the workspace was effectively empty:
  only `.git/`, `.agents/`, and `.codex/` metadata directories were present.
- At that same initial inspection, no pre-existing `docs/` hierarchy,
  documentation convention, application source, database schema, or
  project-specific nested `AGENTS.md` was found. This is historical discovery
  context, not a description of the repository after implementation.
- The project instructions require material implementation and infrastructure
  changes to be documented under `docs/` and indexed in `docs/README.md`.
- A PostgreSQL 16 server process was confirmed running from
  `/usr/lib/postgresql/16/bin/postgres`.
- The PostgreSQL process cgroup is
  `/system.slice/docker-<container-id>.scope`, confirming that the existing
  PostgreSQL 16 instance runs in Docker.
- The actual-host Docker inventory later showed exactly two
  PostgreSQL/pgvector-related containers in the inspected Docker environment:
  `nexgent-rag-postgres-1` using
  `pgvector/pgvector:0.8.6-pg16-bookworm`, and the pre-existing
  `nextcloud-aio-database` using
  `ghcr.io/nextcloud-releases/aio-postgresql:latest`. No other stopped or
  running PostgreSQL/pgvector container appeared in that inventory.
- Before `nexgent-rag-postgres-1` was created, the only PostgreSQL Docker
  container identified in that inspected Docker environment was
  `nextcloud-aio-database`. It belongs to Nextcloud, not RAG, and was not
  reused or modified for this exercise.
- This Docker inventory is scoped only to the actual-host Docker environment
  that was inspected. It does not rule out remote PostgreSQL services,
  non-Docker PostgreSQL installations, or other infrastructure that was not
  visible in that inventory.
- `sudo` works in the user's actual interactive shell with interactive password
  authentication. Passwordless or non-interactive sudo is not established.
- `nvidia-smi` succeeds on the actual host. The server has two NVIDIA RTX A6000
  GPUs with approximately 46 GiB VRAM each, reports CUDA 13.2, and both GPUs
  were effectively idle when checked.
- Python 3.14.4 is the actual host default, and Python 3.12 is also installed.
- The approved smoke test used project-local CPython 3.12.3, one visible
  NVIDIA RTX A6000, PyTorch 2.13.0+cu130, and BF16 successfully.
- The user completed live validation of the isolated RAG PostgreSQL service
  from the actual interactive shell: database `nextgent`, pgvector 0.8.6,
  schema `rag`, and table `rag.embeddings` with the approved 1024-dimensional
  vector column are present, with no approximate vector index.
- The isolated PostgreSQL/pgvector deployment is a functioning, validated
  implementation based on the infrastructure visible during this exercise.
  Whether it is the intended final deployment topology still requires
  confirmation from the project owner.

### Codex sandbox observations — not actual-host conclusions

- PostgreSQL commands were not on the sandbox `PATH`; common sockets/listeners
  were not visible; and the sandbox package view did not show an installed
  PostgreSQL server or pgvector package.
- Docker daemon and systemd inspection were blocked or incomplete in the
  sandbox. These results do not contradict the actual Docker-hosted PostgreSQL
  process confirmed by the user.
- Sandbox `sudo` failed because that environment has `no new privileges`. This
  is a sandbox-only limitation. On the actual host, sudo commands work with
  interactive password authentication; passwordless/non-interactive sudo is
  not established.
- Sandbox `nvidia-smi` could not communicate with the driver. This is a
  sandbox-only visibility limitation; the actual host GPUs are usable.
- The sandbox showed Python 3.14.4, Python 3.12.3, `uv` 0.11.26, 96 logical
  x86-64 CPUs, and approximately 750 GiB RAM. Host runtime details relevant to
  implementation must still be confirmed from the interactive shell when
  needed.
- No PostgreSQL-related environment-variable values were printed or recorded.

## Decisions

- `docs/rag-vector-search.md` is the canonical running implementation log for
  this work.
- `docs/README.md` is the document map because no prior documentation hierarchy
  exists to extend.
- Facts, decisions, and unresolved assumptions will be kept distinct throughout
  the work.
- Use a project-local Python 3.12 `.venv`, `uv`, and project-local download
  caches for the Qwen smoke test. The measured dependency versions are recorded
  below.
- `Qwen/Qwen3-Embedding-0.6B` is the selected and validated embedding model for
  the current proof-of-concept.
- Use its validated default 1024-dimensional output. Do not compare MRL
  truncation unless a concrete storage or performance need appears later.
- The isolated PostgreSQL/pgvector database setup is implemented and
  live-validated for the proof-of-concept. This validates the implementation,
  but does not settle the project owner's final deployment-topology choice.
- Initial retrieval is implemented and validated as exact cosine search with no
  HNSW or IVFFlat index.
- The current experimental automatic chunking parameters are a preferred
  300–500-token range, a 500-token maximum, and 40–80-token overlap aimed near
  60, with paragraph, sentence, whitespace, then token-level hard-split
  priority. Qwen's tokenizer is the authoritative counter. These values require
  evaluation against real project documents.
- Duplicate ingestion remains allowed. No `UNIQUE(context)` constraint is added
  because identical text may legitimately belong to different sources; stable
  source/chunk identity must be designed with the real ingestion format.
- Persistent ingestion uses `.done` to finish one document and continue;
  `.exit`, `.quit`, EOF, or Ctrl+C ends the process. Each document retains its
  own atomic chunk-insert transaction.
- One or more positional file paths select file mode. All paths are validated
  and UTF-8-decoded before ingestion begins, each non-empty file is one source
  document, and `.done` has no special meaning in file contents. Invalid input
  fails the whole run before model loading or database insertion; valid empty
  files are reported and skipped.

## Open questions / assumptions

- The source documents and their formats have not yet been identified.
- The automatic Korean-aware chunker is implemented and validated with
  synthetic and controlled proof-of-concept documents. Its current
  300–500-token range and 40–80-token overlap are not claimed to be optimal and
  still require evaluation/refinement against real source formats.
- A duplicate/re-ingestion identity policy remains unresolved. Candidate inputs
  include a source/document identifier, stable chunk identifier or index,
  content hash, replace/upsert rules, and deliberate document versioning.
- The final PostgreSQL deployment topology requires project-owner confirmation:
  either keep the currently implemented isolated RAG PostgreSQL/pgvector
  instance, or create `nextgent` inside another existing PostgreSQL instance
  that has not yet been identified or approved for RAG use.

## Architecture and configuration decisions

- The smoke-test runtime is project-local CPython 3.12 with `uv`, PyTorch's
  official CUDA 13.0 wheel, Sentence Transformers, one GPU, and BF16. This does
  not yet define the final ingestion/search dependency manifest.
- Secrets and credentials will be supplied only at runtime through standard
  PostgreSQL environment variables or an equivalent credential-free local
  socket configuration; they will not be committed or logged.
- The implemented proof-of-concept excludes the Nextcloud PostgreSQL container
  and uses an isolated Compose project, container, network, volume, and
  localhost-only host port. No existing Nextcloud or Nexgent service, database,
  network, or volume is referenced by this implementation.
- This isolated topology is live-validated and remains a valid implementation
  unless the project owner selects a different final PostgreSQL environment.
  It is not yet documented as the owner-confirmed production topology.
- The persistent CLI retains one Qwen model only within one running `search.py`
  process. A future backend/agent integration should own the model at service
  lifetime scope; moving `load_model()` to a shared module cannot share memory
  across separate Python processes.
- The same process-lifetime rule applies to `embedd.py`: one running ingestion
  session reuses one lazily loaded Qwen instance across documents, but separate
  `embedd.py` processes cannot share that in-memory object.

## Database and schema design

### Implemented isolated setup — live-validated

- Compose project: `nexgent-rag`.
- Service: `postgres`; generated container name `nexgent-rag-postgres-1`.
- Image: `pgvector/pgvector:0.8.6-pg16-bookworm`, a versioned official pgvector
  image containing PostgreSQL 16 and pgvector 0.8.6.
- Port: host `127.0.0.1:5433` to container `5432`; it is not exposed on external
  host interfaces.
- Data volume: Docker named volume `nexgent-rag-postgres-data`, mounted at
  `/var/lib/postgresql/data`.
- Initialization mount: `./sql/001-init-rag.sql` mounted read-only at
  `/docker-entrypoint-initdb.d/001-init-rag.sql`.
- Database: `nextgent`; bootstrap/database role: `rag`; schema: `rag`; table:
  `rag.embeddings`.
- No vector index is created. pgvector therefore uses exact nearest-neighbor
  search by default.

Implemented `compose.yaml`:

```yaml
name: nexgent-rag

services:
  postgres:
    image: pgvector/pgvector:0.8.6-pg16-bookworm
    environment:
      POSTGRES_DB: nextgent
      POSTGRES_USER: rag
      POSTGRES_PASSWORD: ${RAG_POSTGRES_PASSWORD:?RAG_POSTGRES_PASSWORD must be set}
    ports:
      - "127.0.0.1:5433:5432"
    volumes:
      - rag_postgres_data:/var/lib/postgresql/data
      - ./sql/001-init-rag.sql:/docker-entrypoint-initdb.d/001-init-rag.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  rag_postgres_data:
    name: nexgent-rag-postgres-data
```

`RAG_POSTGRES_PASSWORD` must be supplied at execution time and must not be
committed. The official entrypoint variables and SQL initializer only affect an
empty data directory during first initialization.

Implemented `sql/001-init-rag.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS rag;

CREATE TABLE IF NOT EXISTS rag.embeddings (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    context text NOT NULL,
    vector vector(1024) NOT NULL
);
```

The `rag` bootstrap role owns the initialized database objects in this minimal
exercise. A separate least-privilege application role is intentionally deferred
unless the exercise later requires production-style role separation.

## Embedding and chunking design

### Candidate model evaluation

At the historical documentation-only evaluation checkpoint, this comparison
used published primary documentation and no model or dependency had yet been
downloaded. The table retains that comparison and incorporates the later local
Qwen smoke-test measurements. The subsequent dated entries record the model
download, validation, and final proof-of-concept selection.

| Candidate | Published dimensions and context | Korean / multilingual evidence | GPU and expected speed on RTX A6000 | License | Dense-only implementation complexity |
| --- | --- | --- | --- | --- | --- |
| Qwen3-Embedding-0.6B | 0.6B parameters; up to 1024 dimensions with MRL-supported custom dimensions from 32–1024; 32K-token context | Korean is explicitly listed; 100+ languages; the publisher reports MTEB Multilingual mean-task 64.33 and retrieval 64.64 | Measured successfully in BF16 on one RTX A6000: 1,165.01 MiB peak allocated VRAM and 30.73 ms mean single-query latency for the small smoke-test input. These are smoke-test measurements, not throughput benchmarks. | Apache-2.0 | Medium: Sentence Transformers is supported, but queries should use the retrieval prompt while documents should not; requires current Transformers/Sentence Transformers versions. |
| BGE-M3 | 569M parameters; fixed 1024-dimensional dense vector; 8192-token context; published model size 2.27 GB | Trained across 170+ languages with uneven coverage; strong multilingual/MIRACL evidence, but the primary pages reviewed do not isolate Korean results | Similar parameter class to Qwen; FP16 is supported and reduces weight memory. Expected similar or somewhat faster/slower depending on length and library; no comparable A6000 result was published or measured. | MIT | Low for dense-only use: Sentence Transformers is supported, query instructions are not required, and sparse/multi-vector outputs can simply remain unused. |
| EmbeddingGemma-300M | 308M parameters; 768 dimensions, truncatable to 512/256/128 with MRL; 2048-token context | Trained on 100+ spoken languages and reports MTEB Multilingual mean-task 61.15 at 768 dimensions; reviewed primary material does not publish a Korean-only result | Smallest candidate and therefore expected to be fastest and lowest-VRAM for comparable short batches. BF16 parameter storage is approximately 0.62 GB; FP16 activations are unsupported. Google's sub-22-ms result is for EdgeTPU and is not transferable to RTX A6000. Not measured locally. | Gemma terms; Hugging Face weight access requires accepting the usage license; Google states responsible commercial use is allowed | Medium: simple `encode_query`/`encode_document` Sentence Transformers API, but gated model access, Gemma terms, prompt roles, and BF16/FP32 requirements add setup constraints. |

### Historical recommendation and selected result

At the evaluation checkpoint, **Qwen3-Embedding-0.6B** was recommended for the
first manual Korean retrieval validation because:

1. Korean is explicitly included in its publisher-maintained language list.
2. Its reported multilingual retrieval score is stronger than BGE-M3 in the
   Qwen-published comparison, while remaining small enough that either RTX A6000
   has ample memory.
3. Apache-2.0 avoids EmbeddingGemma's gated weight-access and Gemma-terms step.
4. Sentence Transformers handles its last-token pooling and exposes the required
   query prompt, keeping the additional integration logic small.

`Qwen/Qwen3-Embedding-0.6B` was subsequently approved after passing local
validation. Its measured default 1024-dimensional output is selected and used
by the current implementation; no MRL truncation comparison is planned.
BGE-M3 and EmbeddingGemma performance statements remain published-data
estimates because they were not run locally.

### Current automatic document-ingestion design

- In interactive mode, `embedd.py` keeps one process alive for multiple
  multiline source documents.
  `.done` completes the current document and returns to a new-document prompt;
  ordinary blank lines remain paragraph structure.
- `.exit` or `.quit` ends the session and discards any partial document. EOF
  ingests a non-empty partial final document once and then exits; Ctrl+C cancels
  the session cleanly.
- An empty `.done` reprompts before loading the tokenizer or Qwen and does not
  connect to PostgreSQL. Each non-empty document prints source character and
  token counts, generated chunk count, per-chunk token and character lengths,
  and overlap token lengths without printing embeddings.
- If one or more positional paths are supplied, `embedd.py` switches to file
  mode. It reads each file as UTF-8, preserves all internal line breaks, and
  treats each non-empty file as one source document. File mode does not require
  or interpret `.done`.
- File mode is fail-fast: it validates and decodes every supplied path before
  loading Qwen or inserting any document. A missing path, directory, unreadable
  file, or invalid UTF-8 file aborts the entire run; low-level exception details
  are not printed. Empty files are reported and skipped.
- Documents of at most 500 Qwen tokens remain one chunk. Longer documents use
  an experimental preferred 300–500-token range and 40–80 tokens of exact
  adjacent overlap, targeting 60 tokens when a natural boundary permits.
- Chunk ends prefer paragraph boundaries, then sentence endings, then
  whitespace, and finally a token-level hard split based on the fast Qwen
  tokenizer's offset mapping. Recognized sentence endings are `.`, `!`, `?`,
  `。`, `！`, and `？`, including trailing Unicode/ASCII quotation or bracket
  characters.
- A deterministic heading heuristic protects Markdown headings, bracketed
  headings, colon-terminated lines, and short standalone lines from being
  separated from following content when avoidable.
- Overlap starts prefer paragraph, sentence, then whitespace boundaries. The
  selected previous-chunk suffix is the actual next-chunk prefix. Explicit
  guards prevent zero progress and whole-chunk repetition.
- Natural boundaries remain character offsets only to preserve exact source
  slices. Candidate spans, hard splits, and overlaps are accepted according to
  tokenizer counts of the exact substrings with special tokens disabled.
- These token parameters are initial experimental choices, not empirically
  optimal values for all Korean documents; real project documents still need
  evaluation.
- In either mode, lazily load and retain one Qwen tokenizer for chunking and one
  Qwen embedding-model instance for encoding. Reuse both for the rest of the
  process and encode every document's generated chunks with
  `Qwen/Qwen3-Embedding-0.6B`, BF16, `normalize_embeddings=True`, and no query
  prompt or `prompt_name`.
- Require finite output with shape `(chunk_count, 1024)` and unit norms within
  tolerance before connecting to the database.
- Insert each document's chunks in one transaction and rely on the table's
  identity primary key. A later document uses a separate atomic transaction.
  The parameterized SQL is:

```sql
INSERT INTO rag.embeddings (context, vector)
VALUES (%s, %s::vector)
RETURNING id;
```

- PostgreSQL access uses `psycopg[binary]==3.3.4`; ignored `.env` loading uses
  `python-dotenv==1.2.2`. No separate pgvector Python adapter is required
  because the normalized numeric list is bound as text and explicitly cast to
  the database `vector` type.
- Read `RAG_POSTGRES_HOST`, `RAG_POSTGRES_PORT`, `RAG_POSTGRES_DB`, and
  `RAG_POSTGRES_USER`, with defaults matching the isolated local service.
  `RAG_POSTGRES_PASSWORD` is mandatory and has no default. Environment values
  take precedence over the ignored `.env` file.
- Do not print credentials, a credential-bearing DSN, or embedding values.

### Duplicate and re-ingestion behavior

- `rag.embeddings` has no source/chunk uniqueness constraint and `embedd.py`
  executes unconditional parameterized inserts. Re-ingesting the same content
  therefore creates additional rows with identical embeddings.
- Manual testing demonstrated this with IDs `[4, 5, 6]` and duplicate IDs
  `[7, 8, 9]`. Exact cosine search correctly returned both copies with identical
  similarities, including the remote-work contexts at IDs 5 and 8.
- No duplicate row is deleted and no `UNIQUE(context)` constraint is added.
  Identical text can legitimately occur in different source documents.
- Before real ingestion, define identity and re-ingestion semantics using the
  actual source format. Options include source/document IDs, chunk indexes or
  stable chunk IDs, content hashes, replace/upsert behavior, and deliberate
  version coexistence.

Dependency references:

- <https://www.psycopg.org/psycopg3/docs/basic/install.html>
- <https://pypi.org/project/python-dotenv/>

Primary references:

- <https://huggingface.co/Qwen/Qwen3-Embedding-0.6B>
- <https://github.com/QwenLM/Qwen3-Embedding>
- <https://huggingface.co/BAAI/bge-m3>
- <https://github.com/FlagOpen/FlagEmbedding/blob/master/docs/source/bge/bge_m3.rst>
- <https://huggingface.co/google/embeddinggemma-300m>
- <https://ai.google.dev/gemma/docs/embeddinggemma>
- <https://ai.google.dev/gemma/docs/embeddinggemma/model_card>

The original one-non-empty-line-per-chunk flow was successfully used for the
first Korean smoke test and remains preserved in the chronological log. It was
later superseded by the automatic document chunker described above.

## Retrieval design

- Initial retrieval is an exact scan ordered by pgvector cosine distance
  (`vector <=> query_vector`) with a top-k `LIMIT`.
- Cosine similarity, when returned, is calculated as
  `1 - (vector <=> query_vector)`.
- No HNSW or IVFFlat index exists. An approximate index remains optional future
  work only if measured data-size or latency needs justify it.
- `search.py` is a persistent interactive, read-only CLI session. Blank queries
  reprompt; `.exit`, `.quit`, EOF, or Ctrl+C ends the session. Every valid query
  accepts an independent top-k value from 1 through 20, defaulting to 5.
- Qwen is loaded lazily for the first valid query and retained for all later
  queries in that running process. A later query or top-k change does not reload
  the model. Starting a separate Python process still creates a separate model
  instance.
- Query embeddings use the validated Qwen BF16 runtime with
  `prompt_name="query"`, `normalize_embeddings=True`, and required finite
  shape `(1, 1024)` with norm tolerance 0.01.
- The exact parameterized retrieval SQL binds the query vector once:

```sql
WITH query_embedding AS (
    SELECT %s::vector AS vector
)
SELECT
    embeddings.id,
    embeddings.context,
    1 - (embeddings.vector <=> query_embedding.vector) AS similarity
FROM rag.embeddings AS embeddings
CROSS JOIN query_embedding
ORDER BY embeddings.vector <=> query_embedding.vector
LIMIT %s;
```

- Output includes rank, generated row ID, cosine similarity, and context. It
  does not print raw vectors, credentials, or a credential-bearing DSN.
- If this code later moves into a persistent backend or agent service, that
  service should initialize and retain the model for its own lifetime. A shared
  Python module alone cannot provide cross-process in-memory reuse.

## Operational commands

Current ingestion CLI:

```bash
# Persistent interactive mode; .done completes one document.
.venv/bin/python embedd.py

# File mode; each UTF-8 path is one document and .done is not required.
.venv/bin/python embedd.py file1.txt file2.txt
```

File mode validates and decodes the complete path list before any model or
database work. An invalid path aborts the whole run; empty files are skipped.

Initial repository inspection:

```bash
pwd
rg --files -g 'AGENTS.md' -g 'docs/**'
find . -maxdepth 4 -type f -o -type d
```

Historical Codex sandbox PostgreSQL diagnostics (not representative of the
actual host; connection-variable values were excluded):

```bash
command -v psql
psql --version
command -v postgres
postgres --version
command -v pg_config
pg_config --version
pg_isready
systemctl is-active postgresql
systemctl list-units --type=service --all 'postgresql*' --no-pager
find /var/run/postgresql /run/postgresql -maxdepth 2 -type s -name '.s.PGSQL.*' -print
ss -ltn | rg ':(5432|5433|5434)\b'
env | cut -d= -f1 | rg '^(PG|POSTGRES|DATABASE_)' | sort
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}'
podman ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}'
dpkg-query -W -f='${binary:Package}\t${Version}\n' 'postgresql*' 'pgvector*'
find /usr/share/postgresql -maxdepth 4 -type f \
  \( -name 'vector.control' -o -name 'vector--*.sql' \) -print
dpkg-query -W -f='${db:Status-Abbrev}\t${binary:Package}\t${Version}\n' |
  rg '^(ii|hi)\s+.*(postgresql|pgvector|libpq)'
find /usr/lib/postgresql /usr/share/postgresql /etc/postgresql -maxdepth 3 \
  -type f \( -name psql -o -name postgres -o -name pg_config \
  -o -name vector.control -o -name postgresql.conf -o -name pg_hba.conf \) -print
```

Historical Codex sandbox runtime and hardware diagnostics:

```bash
python3 --version
python3 -m pip --version
uv --version
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
lscpu | rg '^(Architecture|CPU\(s\)|Model name|Thread|Core|Socket)'
free -h
python3 - <<'PY'
from importlib.util import find_spec
for name in ('torch', 'sentence_transformers', 'transformers', 'psycopg', 'pgvector'):
    print(f"{name}: {'available' if find_spec(name) else 'not installed'}")
PY
```

Qwen smoke-test environment, installation, CUDA check, and execution:

```bash
export UV_CACHE_DIR="$PWD/.cache/uv"
export HF_HOME="$PWD/.cache/huggingface"
uv venv --python /usr/bin/python3.12 .venv
uv pip install --python .venv/bin/python \
  --index-url https://download.pytorch.org/whl/cu130 \
  "torch==2.13.0"
uv pip install --python .venv/bin/python \
  --index-url https://pypi.org/simple \
  "sentence-transformers==5.6.1" \
  "transformers==5.14.1"
CUDA_VISIBLE_DEVICES=0 HF_HOME="$PWD/.cache/huggingface" \
  .venv/bin/python -c 'import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0), torch.cuda.is_bf16_supported())'
CUDA_VISIBLE_DEVICES=0 HF_HOME="$PWD/.cache/huggingface" \
  TOKENIZERS_PARALLELISM=false .venv/bin/python evaluate_models.py
```

The following historical inspection commands are superseded and must not be run
for this exercise because the discovered PostgreSQL container belongs to
Nextcloud and is outside scope. They are retained only as a record of the
earlier proposed validation.

```bash
PG_PID="$(pgrep -o -f '^/usr/lib/postgresql/16/bin/postgres([[:space:]]|$)')"
cat "/proc/${PG_PID}/cgroup"

PG_CONTAINER_ID="$(sed -n 's#.*docker-\([0-9a-f]\{64\}\)\.scope.*#\1#p' "/proc/${PG_PID}/cgroup" | head -n1)"
sudo docker ps --no-trunc --filter "id=${PG_CONTAINER_ID}" \
  --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'

PG_CONTAINER="$(sudo docker ps --no-trunc --filter "id=${PG_CONTAINER_ID}" --format '{{.Names}}')"
sudo docker inspect "${PG_CONTAINER}" \
  --format 'Name={{.Name}} Image={{.Config.Image}} ImageID={{.Image}} Ports={{json .NetworkSettings.Ports}}'
sudo docker top "${PG_CONTAINER}" -eo user,pid,ppid,args

sudo docker exec -u postgres "${PG_CONTAINER}" \
  psql -X -d postgres -c 'SHOW server_version;'
sudo docker exec -u postgres "${PG_CONTAINER}" \
  psql -X -d postgres -c '\l+'
sudo docker exec -u postgres "${PG_CONTAINER}" \
  psql -X -d postgres -c \
  "SELECT name, default_version, installed_version FROM pg_available_extensions WHERE name = 'vector';"

sudo docker exec -u postgres "${PG_CONTAINER}" \
  psql -X -d postgres -Atc \
  "SELECT datname FROM pg_database WHERE datallowconn AND NOT datistemplate ORDER BY datname" |
while IFS= read -r database_name; do
  printf '\nDatabase: %s\n' "${database_name}"
  sudo docker exec -u postgres "${PG_CONTAINER}" \
    psql -X -d "${database_name}" -c \
    "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
done
```

## Validation and test results

- Documentation discovery completed: no existing documentation files or
  conventions were available to preserve or extend.
- Documentation consistency validation passed: required sections and the
  document-map link are present, and a targeted credential-pattern scan found
  no secrets.
- The standalone Korean embedding/retrieval smoke test passed. Live ingestion
  inserted three Korean rows into `rag.embeddings`, and subsequent read-only
  exact cosine searches returned the expected top-1 context for all three
  Korean queries, as recorded in the dated validation entries below.
- The earlier character-based deterministic chunking checks passed and remain
  historical evidence. The superseding token-based suite uses the cached Qwen
  tokenizer and validates short/long Korean documents, paragraph and sentence
  boundaries, token-level hard splits, exact overlap, the 500-token maximum,
  empty input, forward progress, and lossless source coverage.
- Controlled automatic ingestion inserted new urban-ecology chunks as IDs 10
  and 11. Both stored vectors are normalized and 1024-dimensional; subsequent
  paraphrased queries ranked the appropriate new chunk first.
- Deterministic persistent-ingestion checks processed two non-empty documents
  in one session with exactly one `load_model()` call, the same model object for
  both embedding calls, and one insert call per document. Empty-document,
  `.done`, `.exit`, `.quit`, partial EOF, and partial-discard behavior passed
  without model or database access.
- Nine deterministic file-mode tests passed without loading Qwen or accessing
  PostgreSQL. They cover one Korean UTF-8 multiline file, ordered multiple-file
  reading, empty-file skipping, missing-path fail-fast behavior, directory and
  invalid-UTF-8 rejection, sanitized unreadable-file errors, use of the existing
  document pipeline for one file, and reuse of one mocked model across two
  files.
- The complete offline ingestion suite passed 17 tests in 2.671 seconds: the
  nine file-mode tests plus seven token-chunking cases and one interactive
  tokenizer/model-reuse regression case. It loaded tokenizer files from the
  local cache but did not load model weights or access PostgreSQL.
- Model-free comparison of `manual_long_test.txt` changed the 1,388-character
  source from four historical character-based chunks of
  `[421, 499, 321, 374]` characters to two token-based chunks. The source has
  792 Qwen tokens; chunk token lengths are `[478, 362]`, character lengths are
  `[835, 641]`, and the exact overlap is 48 tokens.
- A persistent two-query search session loaded Qwen exactly once, respected
  top-k 2 and top-k 1, and left the 9-row pre-ingestion database fingerprint
  unchanged. A later two-query retrieval check for IDs 10 and 11 also loaded
  Qwen once and remained read-only.

## Issues encountered

- At initial inspection, the `rg --files` search produced no project files
  because the workspace then contained only metadata directories. A bounded
  `find` confirmed that initial repository state.
- The Codex sandbox did not represent the actual interactive host accurately
  for Docker, PostgreSQL, sudo, or GPU discovery. This caused incorrect initial
  conclusions, which were retracted and corrected on 2026-08-19.
- The first Qwen forward pass failed because PyTorch 2.13's optional native
  Triton operator tried to compile a helper and `/usr/include/python3.12/Python.h`
  was absent. No system package was installed. Setting PyTorch's supported
  `TORCH_DISABLE_NATIVE_JIT=1` opt-out before importing `torch` selected the
  standard CUDA operator path, after which the smoke test passed.
- Manual re-ingestion inserted identical contexts twice: IDs `[4, 5, 6]` on the
  first insertion and `[7, 8, 9]` on the second. Exact search then returned the
  duplicate rows with identical similarities, including IDs 5 and 8 for the
  same remote-work context. This is expected behavior, not a retrieval-model
  failure: the current schema has no source/chunk identity constraint and the
  ingestion SQL performs unconditional inserts. No existing row was changed or
  removed during that implementation step.

## Remaining work

The minimal proof-of-concept described in the at-a-glance section is complete.
The following work remains before real source-document integration:

- Confirm the final PostgreSQL deployment topology with the project owner:
  retain the validated isolated RAG instance, or use a different existing
  PostgreSQL instance if one is identified and explicitly approved for RAG.
- Identify the actual source-document types and formats.
- Evaluate and refine the implemented 300–500-token, 40–80-token overlap
  chunker against those real formats before production ingestion. The current
  parameters are experimental starting values, not proven optima.
- Define source/chunk identity and duplicate/re-ingestion semantics before real
  ingestion. Do not default to `UNIQUE(context)` without source requirements.
- Determine the backend/agent integration requirements, including lifecycle,
  configuration ownership, and how real documents enter the ingestion flow.

## Future improvements

The absence of these improvements does not invalidate the completed
proof-of-concept.

- If the CLIs become a backend/agent service, initialize and retain Qwen at
  service lifetime scope. Separate Python invocations cannot share an in-memory
  model merely through shared-module extraction.
- If PostgreSQL/pgvector integration expands, consider the official pgvector
  Python/Psycopg adapter. The current `%s::vector` implementation is already
  live-validated and does not need to change for this proof-of-concept.
- If additional RAG components introduce meaningful duplication, consider
  extracting database/model configuration into shared configuration. Do not
  add a shared module solely for the current two-script proof-of-concept.
- Consider HNSW or IVFFlat only if measured dataset scale and retrieval latency
  justify approximate indexing. Exact cosine search remains the validated
  current implementation.

## Chronological implementation log

Every entry below is a dated historical checkpoint. Present-tense wording
inside an entry describes that point in the implementation unless the entry
explicitly says the statement remains current. The authoritative present state
is summarized in "Current implementation at a glance" above.

### 2026-08-19 — Documentation initialization

**Checked**

- Inspected the workspace for existing documentation and nested instruction
  files.
- Confirmed that no existing `docs/` structure or conventions were present.

**Decided**

- Created a minimal document map and this topic-specific running log at the
  root of `docs/`.
- Deferred all database, model, schema, and retrieval choices until discovery
  provides evidence.

**Changed**

- Added `docs/README.md`.
- Added `docs/rag-vector-search.md`.

**Validated**

- Confirmed both documentation files exist, the document-map link targets the
  implementation log, the required date and status sections are present, and
  `git diff --check` reports no whitespace errors.
- `git status --short` showed unrelated pre-existing changes elsewhere in the
  parent repository; they were not modified as part of this RAG work.

Validation command:

```bash
git status --short
git diff --check
test -f docs/README.md
test -f docs/rag-vector-search.md
rg -n '^Date: 2026-08-19$|^### Confirmed facts$|^### Decisions$|^### Open questions / assumptions$|rag-vector-search\.md' docs
```

### 2026-08-19 — Codex sandbox PostgreSQL diagnostics, pass 1

**Checked**

- Client/server commands and versions: `psql`, `postgres`, `pg_config`, and
  `pg_isready`.
- Common local sockets and TCP ports 5432–5434.
- PostgreSQL-related environment-variable names without printing their values.
- systemd services, Docker/Podman containers, Debian package names, and
  pgvector extension files.

**Sandbox observations (not actual-host facts)**

- PostgreSQL tooling was not available on the sandbox `PATH`.
- No local socket or common-port listener was visible inside the sandbox.
- Docker is installed, but its daemon socket is inaccessible from the sandbox;
  Podman is unavailable.

**Issues / open questions**

- systemd access failed with `Operation not permitted`.
- Docker daemon access failed with a socket permission error.
- Package glob output did not include versions and is therefore inconclusive.

Follow-up sandbox package-state inspection resolved only what was visible in the
sandbox; it did not establish actual-host package or service state.

**Changed**

- No infrastructure or application state was changed; this was a read-only
  discovery pass.

**Next validation**

- Inspect the actual host from the user's interactive shell before drawing any
  infrastructure conclusion.

### 2026-08-19 — Codex sandbox PostgreSQL package-state verification

**Checked**

- Queried installed-package status abbreviations and versions rather than
  relying on package-name glob matches.
- Searched standard PostgreSQL installation/configuration locations for server,
  client, configuration, and pgvector extension files.

**Sandbox observations (not actual-host facts)**

- `libpq5` was visible, but PostgreSQL client/server executables and pgvector
  extension files were not present in sandbox-visible standard locations.
- The earlier unversioned package-name matches were not installed packages and
  are no longer an open question.

**Changed**

- No infrastructure state was changed.

**Validated**

```bash
dpkg-query -W -f='${db:Status-Abbrev}\t${binary:Package}\t${Version}\n' |
  rg '^(ii|hi)\s+.*(postgresql|pgvector|libpq)'
find /usr/lib/postgresql /usr/share/postgresql /etc/postgresql -maxdepth 3 \
  -type f \( -name psql -o -name postgres -o -name pg_config \
  -o -name vector.control -o -name postgresql.conf -o -name pg_hba.conf \) -print
```

### 2026-08-19 — Codex sandbox service and Docker verification

**Checked**

- Re-ran PostgreSQL systemd service inspection and Docker container listing with
  elevated tool permissions. This still executed in a context that did not
  represent the user's actual interactive host.

**Sandbox observations (not actual-host facts)**

- `systemctl is-active postgresql` returned `inactive`.
- No PostgreSQL service units were listed.
- Docker container inspection still failed with permission denied on the Docker
  API socket; container state cannot be asserted.

**Interpretation limit**

- These results cannot determine actual-host PostgreSQL or Docker availability.
  The earlier conclusion that no usable PostgreSQL instance existed is
  retracted.

**Changed**

- No service, container, or database state was changed.

**Validated**

```bash
systemctl is-active postgresql
systemctl list-units --type=service --all 'postgresql*' --no-pager
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}'
```

### 2026-08-19 — Codex sandbox Python runtime and hardware inventory

**Checked**

- Python and `uv` versions, CPU architecture/count, memory, GPU-driver access,
  and presence of anticipated Python packages.

**Sandbox observations (not actual-host facts)**

- At this checkpoint, the machine appeared suitable for CPU-based model
  evaluation and ingestion, with 96 logical CPUs and roughly 726 GiB available
  RAM.
- GPU driver access was not exposed to the sandbox.
- The system Python is 3.14.4 and does not contain the anticipated RAG
  libraries.

**Interpretation limit**

- The GPU failure cannot be used for model-selection decisions. Actual-host
  checks confirmed two usable RTX A6000 GPUs.

**Changed**

- No packages or runtime state were changed.

**Validated**

The historical sandbox commands completed. Their GPU driver error is a
sandbox-visibility result only.

### 2026-08-19 — Preliminary model documentation review (superseded scope)

**Checked**

- Reviewed the primary Hugging Face model cards for multilingual E5-base and
  BGE-M3 before the required candidate set was clarified.
- Reviewed the primary pgvector documentation for vector dimension limits,
  cosine distance, exact search, and HNSW cosine indexing.

**Confirmed**

- Multilingual E5-base produces 768-dimensional embeddings and requires
  retrieval prefixes for queries and passages.
- BGE-M3 produces 1024-dimensional embeddings and offers an 8192-token context
  plus dense, sparse, and multi-vector modes.
- Both candidate dimensions fit pgvector's HNSW-indexable `vector` type limit of
  2,000 dimensions.
- pgvector's `<=>` operator returns cosine distance; cosine similarity is
  `1 - distance`. Index-compatible queries must order directly by the distance
  operator in ascending order and include a limit.

**Correction**

- The provisional multilingual E5-base/768-dimension direction is retracted.
- The required candidates are Qwen3-Embedding-0.6B, BGE-M3, and
  EmbeddingGemma-300M. E5 is, at most, an optional extra baseline.
- No embedding model or vector dimension is selected.

**Changed**

- No model was downloaded and no schema was changed in this step.

**Validation remaining**

- Evaluate all three required candidates using the criteria in "Embedding and
  chunking design" before any implementation choice.

### 2026-08-19 — Codex sandbox runtime and provisioning observations

**Checked**

- Enumerated installed Python versions and queried Ubuntu package candidates for
  PostgreSQL and pgvector.
- Inspected Docker socket ownership, current user/group identity, and whether
  non-interactive privilege escalation is possible.

**Sandbox observations (not actual-host facts)**

- Python 3.12.3 is available alongside Python 3.14.4.
- Repository candidates are PostgreSQL 18.4 and pgvector 0.8.1.
- `sudo` and Docker access were blocked in the sandbox. Actual-host checks later
  confirmed that sudo works with interactive password authentication and that
  a Docker-hosted PostgreSQL server exists. Passwordless/non-interactive sudo
  was not established.
- `uv python list` could not use its default cache because the user cache path is
  read-only; this does not prevent use of `uv` with a writable project or `/tmp`
  cache.

**Decision at this historical checkpoint**

- Prefer a project-local Python 3.12 environment. `uv` is not yet finalized.

**Correction**

- The user-space PostgreSQL build proposal was withdrawn. A later host finding
  established that the discovered PostgreSQL container belonged to Nextcloud,
  so even read-only inspection was cancelled for this RAG exercise at that
  checkpoint.

**Changed**

- No packages, services, or containers were changed.

**Validated**

```bash
python3.12 --version
uv python list --only-installed
apt-cache policy postgresql postgresql-18 postgresql-18-pgvector postgresql-client
apt-cache search '^postgresql-[0-9]+-pgvector$'
stat -c '%A %U:%G %n' /var/run/docker.sock
id
sudo -n true
```

### 2026-08-19 — Running-log consistency validation

**Checked**

- Confirmed the implementation log and document map exist.
- Confirmed all required status, design, operational, validation, issue, work,
  and chronology sections remain present after incremental updates.
- Scanned the documentation for common credential-bearing URL, password, API
  key, and token assignment patterns.

**Confirmed**

- The document-map link points to this implementation log.
- No credential pattern was detected.
- The documentation is untracked new work under `docs/`; unrelated parent
  repository changes remain untouched.

**Validated**

```bash
git status --short -- docs
git diff --check -- docs
test -f docs/rag-vector-search.md
test -f docs/README.md
rg -n '^## (Current status|Architecture and configuration decisions|Database and schema design|Embedding and chunking design|Retrieval design|Operational commands|Validation and test results|Issues encountered|Remaining work|Chronological implementation log)$' docs/rag-vector-search.md
rg -n 'rag-vector-search\.md' docs/README.md
```

### 2026-08-19 — Actual-host corrections and decision reset

**Actual host facts supplied and confirmed by the user**

- PostgreSQL 16 is running from `/usr/lib/postgresql/16/bin/postgres` inside a
  Docker cgroup.
- Historical statement later corrected: sudo was initially recorded here as
  passwordless. The post-implementation clarification establishes only that
  sudo works in the actual interactive shell with password authentication;
  passwordless/non-interactive sudo is not established.
- Two approximately 46 GiB NVIDIA RTX A6000 GPUs are usable, CUDA 13.2 is
  reported, and both GPUs were effectively idle when checked.
- Python 3.14.4 and Python 3.12 are installed.

**Corrected**

- Separated actual-host facts from Codex sandbox observations throughout this
  document.
- Retracted the claims that no PostgreSQL instance exists, actual-host sudo is
  unavailable, no usable GPU is available, and a user-space PostgreSQL build is
  needed.
- Retracted multilingual E5-base as a provisional choice and removed 768 as a
  provisional vector dimension.
- At this historical checkpoint, reset the required model evaluation to
  Qwen3-Embedding-0.6B, BGE-M3, and EmbeddingGemma-300M, with no selected model
  or dimension. Later entries record the Qwen/1024 selection.

**Decided**

- Stop infrastructure, database, and model decisions until further discovery.
- Do not inspect the discovered PostgreSQL container further; it belongs to
  Nextcloud and is outside the RAG scope.
- Do not install packages or create/modify databases in this step.

**Changed**

- Documentation only. No infrastructure, database, package, or model state was
  changed.

**Validation status update**

- The previously proposed actual-host PostgreSQL inspection is cancelled. The
  existing container belongs to Nextcloud and must not be touched.

**Documentation validation performed**

- `git diff --check -- docs` passed.
- Confirmed the current-status section separately labels actual-host facts and
  Codex sandbox observations.
- Confirmed that, at this historical checkpoint, all three required model
  candidates were listed as unevaluated and no selected model or vector
  dimension was recorded. Later entries supersede this state.
- A targeted credential-pattern scan found no credential-bearing URL, password,
  API-key, or token assignment.

### 2026-08-19 — Repository audit stopped and RAG scope restored

**Confirmed**

- A broader Nexgent repository configuration audit was started and then
  intentionally stopped at the user's direction because unrelated Nexgent,
  Agents, Nextcloud, backend, and deployment infrastructure is outside the scope
  of this RAG exercise.

**Decision**

- All further work is confined to `RAG/` and its minimal isolated
  PostgreSQL/pgvector implementation.
- The target database is `nextgent`; the schema remains `rag` or `public` until
  approved; and the storage table will contain an auto-incrementing ID,
  `context`, and a model-sized vector column.
- Qwen3-Embedding-0.6B, BGE-M3, and EmbeddingGemma-300M must be evaluated before
  selecting the embedding model or vector dimension.
- No database, container, package, configuration, or model changes will be made
  until the user approves the minimal RAG implementation plan.

**Changed**

- Documentation only. No infrastructure or application state was changed.

### 2026-08-19 — Required embedding-model evaluation, documentation pass

**Scope confirmed**

- Keep the exercise minimal: `evaluate_models.py`, `embedd.py`, `search.py`,
  `compose.yaml`, `pyproject.toml`, SQL initialization, and this documentation.
- Do not add `rag_common.py` unless implementation duplication proves it useful.
- Defer automated tests/fixtures; first validate the full flow manually with
  Korean examples.
- Start with exact pgvector cosine-distance search and no HNSW index.
- This step performs model research only; installation and inference are
  explicitly deferred.

**Published facts checked**

- Reviewed publisher model cards, official repositories, usage examples,
  multilingual benchmark summaries, licenses, dimensions, parameter counts,
  context limits, prompt requirements, and supported precision notes for all
  three required candidates.
- Qwen3-Embedding-0.6B explicitly lists Korean, supports 100+ languages and MRL
  dimensions up to 1024, and uses Apache-2.0.
- BGE-M3 is a 569M-parameter, 1024-dimensional MIT-licensed model trained across
  170+ languages; dense-only use does not require a query instruction.
- EmbeddingGemma is a 308M-parameter model trained on 100+ spoken languages. It
  produces 768 dimensions with smaller MRL options, uses Gemma terms, requires
  Hugging Face license acceptance, and does not support FP16 activations.

**Inference status at this historical evaluation checkpoint**

- All three should fit comfortably on one approximately 46 GiB RTX A6000 for
  short RAG chunks, but actual peak VRAM, latency, and throughput depend on
  precision, token length, batch size, and library implementation.
- EmbeddingGemma is expected to be fastest due to its smaller parameter count;
  no comparable RTX A6000 measurement was found in the reviewed primary sources.
- Published multilingual scores do not replace a project-specific Korean
  retrieval check.

**Recommendation, not final selection**

- Evaluate Qwen3-Embedding-0.6B first locally because Korean support is explicit,
  published multilingual retrieval is strong, licensing is permissive, and the
  prompt-aware Sentence Transformers path is still small enough for this
  exercise.
- Do not fix the vector dimension yet. If the recommendation is approved, first
  validate Korean retrieval and then decide whether to use the full 1024 output
  or an MRL-truncated dimension.

**Changed and validated**

- Updated documentation only. No package, dependency, model, container,
  database, schema, or application file was created or changed.
- Primary-source links are recorded in "Candidate model evaluation". At this
  historical checkpoint, local speed, VRAM, and Korean retrieval validation
  were still pending by design; the immediately following smoke-test entry
  records their completion.
- `git diff --check -- docs` passed, and a targeted documentation scan found no
  credential-bearing URL or credential assignment.

### 2026-08-19 — Qwen3-Embedding-0.6B local CUDA smoke test

**Changed**

- Created `.venv` with CPython 3.12.3 and local caches at `.cache/uv` and
  `.cache/huggingface`.
- Installed `torch==2.13.0+cu130`, `transformers==5.14.1`, and
  `sentence-transformers==5.6.1` in `.venv`.
- Added `evaluate_models.py`; it uses GPU 0 only, BF16, no document prompt,
  Qwen's `query` prompt for queries, and normalized embeddings.
- Downloaded `Qwen/Qwen3-Embedding-0.6B` to the local Hugging Face cache.

**CUDA sanity check**

- PyTorch CUDA build: 13.0; CUDA available: yes; visible GPU count: 1.
- GPU: NVIDIA RTX A6000; BF16 reported supported; a BF16 CUDA matrix operation
  completed successfully.

**Measured results**

| Measurement | Result |
| --- | --- |
| Model load | Success; 7,635.26 ms from the populated local cache |
| Output dimension | 1024 |
| Normalization | All five document norms and three query norms reported 1.0; all values finite |
| Korean retrieval | 3/3 expected documents ranked top 1 |
| Top-1 cosine similarities | Capital 0.578125; highest mountain 0.621094; data-analysis language 0.667969 |
| Document latency | 53.58 ms for a batch of 5 short documents |
| Query latency | 35.25 ms for a batch of 3 short queries |
| Single-query latency | 30.73 ms mean; 30.71 ms median; 30.36–31.32 ms across 10 warm runs |
| Peak GPU memory | 1,165.01 MiB allocated; 1,180.00 MiB reserved |

These are small, warmed smoke-test measurements rather than throughput or
long-context benchmarks. The default 1024 output is now confirmed, but this
did not yet select the database vector dimension at this historical checkpoint.
The immediately following selection entry records the later approval of 1024
dimensions for the implemented database and scripts.

**Issue and resolution**

- The initial forward pass failed when PyTorch 2.13's optional native Triton
  path attempted to compile against missing `Python.h`.
- No additional package or system header was installed. `evaluate_models.py`
  sets `TORCH_DISABLE_NATIVE_JIT=1` before importing PyTorch, using the standard
  CUDA operator path; the subsequent run passed with exit code 0.

**Scope validation**

- No PostgreSQL container, pgvector extension, database, schema, table,
  `embedd.py`, or `search.py` was created or modified.
- The final syntax parse passed, the installed version listing matched all
  three recorded pins, no trailing-whitespace error was reported, and the
  targeted credential-pattern scan returned no matches.

### 2026-08-19 — Embedding selection and isolated database design

**Confirmed decision**

- Selected Qwen3-Embedding-0.6B with its validated default 1024-dimensional
  output. MRL truncation evaluation is deferred unless a concrete need arises.
- Fixed the initial database shape as `nextgent.rag.embeddings` with identity
  primary key `id`, non-null `context`, and a non-null `vector` column typed as
  `vector(1024)`.
- Initial retrieval will use exact cosine distance with no HNSW index.

**Proposed, not executed**

- Use the pgvector project image `pgvector/pgvector:0.8.6-pg16-bookworm`, one
  Compose service, localhost port 5433, and named volume
  `nexgent-rag-postgres-data`.
- Supply the database password only through the runtime
  `RAG_POSTGRES_PASSWORD` environment variable.
- Create only `compose.yaml` and `sql/001-init-rag.sql` after explicit approval.
  The existing documentation file is the only file changed in this design step.
- Pulling the image, creating the isolated network/volume, starting PostgreSQL,
  and running initialization SQL are all deferred. No existing infrastructure
  was inspected or modified.

**Assumption at this design checkpoint, later resolved**

- Host port 5433 must be confirmed free on the actual host before the first
  `docker compose up`. The following database-setup entry records that
  successful read-only preflight.

Primary references checked:

- <https://github.com/pgvector/pgvector>
- <https://github.com/docker-library/docs/blob/master/postgres/README.md>

### 2026-08-19 — Vector column naming correction

**Confirmed and changed**

- Aligned the proposed table with the requested `id | context | vector`
  structure by naming the 1024-dimensional column `vector`.
- Updated the proposed exact cosine expressions to use
  `vector <=> query_vector`. All other database design choices are unchanged.

**Validated**

- Confirmed the proposed SQL contains `vector vector(1024) NOT NULL` and no
  later cosine example references the former column name.
- Documentation only; no Compose, SQL, container, volume, database, or table
  was created or executed.

### 2026-08-19 — Isolated RAG database setup execution

**Read-only preflight**

- Ran `ss -H -ltn 'sport = :5433'` against the actual host before creating or
  starting the service.
- The command exited with status 0 and no output, confirming no TCP listener
  was bound to host port 5433 at that time.

**Execution state at this historical checkpoint**

- Created `compose.yaml`, `sql/001-init-rag.sql`, `.env.example`, and
  `.gitignore`. The ignore file excludes only the local `.env` credential file.
- `RAG_POSTGRES_PASSWORD=validation-only docker compose config --quiet` passed;
  `validation-only` was a non-secret syntax-check placeholder and was not used
  to start PostgreSQL.
- Confirmed the initializer contains the approved extension, schema, identity
  primary key, text context, and `vector vector(1024)` definitions. The four
  new files passed a trailing-whitespace check.
- The Codex execution context could not start Docker, as recorded below. The
  user subsequently started and validated the isolated service from the actual
  interactive shell.

**Start issue**

- The first sanitized start command was
  `RAG_POSTGRES_PASSWORD='<generated-in-memory>' docker compose up -d --wait postgres`.
  It failed before pulling or creating resources because this execution user
  could not access `/var/run/docker.sock` directly.
- This is a Codex execution-user Docker permission issue, not evidence that
  actual-host Docker or sudo is unavailable. At this point, a retry using
  non-interactive `sudo` with the same project-scoped Compose command was
  proposed; the following result showed that non-interactive sudo was not
  available in the Codex execution context.
- The retry with sanitized command
  `sudo -n env RAG_POSTGRES_PASSWORD='<generated-in-memory>' docker compose up -d --wait postgres`
  also failed before Docker execution with
  `sudo: interactive authentication is required` in the Codex execution
  context. No password was requested or exposed.
- A second `ss -H -ltn 'sport = :5433'` check returned no listener, confirming
  that the service did not start and port 5433 remained free.

**Actual-host live validation supplied by the user**

- Current database: `nextgent`.
- Installed extension: `vector`, version 0.8.6.
- Schema: `rag`.
- Table: `rag.embeddings`.
- Exact observed columns:
  - `id`: `bigint`, `NOT NULL`, identity kind `a` (`GENERATED ALWAYS`).
  - `context`: `text`, `NOT NULL`.
  - `vector`: `vector(1024)`, `NOT NULL`.
- Approximate vector indexes: 0.
- These live results match the approved exact cosine-search design. The
  isolated database setup step is complete; no HNSW or IVFFlat index exists.

### 2026-08-19 — Minimal `embedd.py` design

**Historical status, later superseded**

- This entry records the original line-based smoke-test ingestion behavior.
  Automatic multiline document chunking later superseded only the input and
  chunk-creation path; the validated embedding and atomic insert behavior
  remains in use.

**Decided before implementation**

- Accept at most 10 interactive lines and treat each trimmed, non-empty line as
  one chunk; blank input ends collection early.
- Encode documents as one normalized 1024-dimensional Qwen batch without the
  query prompt, validate the output, then insert every chunk atomically into
  `rag.embeddings(context, vector)`.
- Use parameterized Psycopg SQL with `RETURNING id` and no hardcoded password or
  credential-bearing DSN.
- Pin `psycopg[binary]==3.3.4` for PostgreSQL access and
  `python-dotenv==1.2.2` for the already-ignored local `.env` file.

**Planned file scope**

- Add `embedd.py`; update `.env.example` and this log only.
- Do not change Compose, SQL initialization, database objects,
  `evaluate_models.py`, or create `search.py`.

**Validation status**

- Installed `psycopg==3.3.4`, `psycopg-binary==3.3.4`, and
  `python-dotenv==1.2.2` into the existing project-local Python 3.12 `.venv`
  with:

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv pip install \
  --python .venv/bin/python \
  --index-url https://pypi.org/simple \
  "psycopg[binary]==3.3.4" \
  "python-dotenv==1.2.2"
```

- Historical checkpoint, later superseded: dependency resolution and
  installation had succeeded, while script implementation, CUDA execution,
  and live insertion validation were still pending at that moment. The next
  sections record their subsequent completion.

**Implemented and statically validated**

- Added `embedd.py` and extended `.env.example` with the non-secret host, port,
  database, and user settings. The populated `.env` remains ignored.
- Confirmed the script has valid Python syntax, the exact parameterized insert,
  a 10-line limit, normalized encoding, and no query prompt argument.
- A blank-input CLI run exited with status 0 and reported that nothing was
  inserted; it did not load Qwen or open a database connection.
- Confirmed the installed Psycopg, Psycopg binary, and python-dotenv versions
  match the recorded pins. `embedd.py` and `.env.example` passed the
  trailing-whitespace check.
- Live Korean CUDA embedding and database insertion subsequently passed as
  recorded below.

**Live ingestion command**

```bash
printf '%s\n' \
  '서울은 대한민국의 수도이며 정치와 경제의 중심지입니다.' \
  '제주도 한라산은 대한민국에서 가장 높은 산입니다.' \
  '파이썬은 데이터 분석과 인공지능 개발에 널리 사용되는 프로그래밍 언어입니다.' \
  '' |
CUDA_VISIBLE_DEVICES=0 \
HF_HOME="$PWD/.cache/huggingface" \
TOKENIZERS_PARALLELISM=false \
.venv/bin/python embedd.py
```

**Measured live results**

- Qwen loaded on `cuda:0` in BF16 and embedded three chunks with output
  dimension 1024 and maximum pre-insert norm error 0.00197875.
- The single database transaction succeeded and returned generated IDs
  `[1, 2, 3]`.
- A read-only query using `vector_dims(vector)` and `vector_norm(vector)`
  confirmed the exact three Korean contexts, dimension 1024 for every row, and
  persisted norms 1.001960, 1.001680, and 1.001979 respectively. All remain
  within the 0.01 normalization tolerance.
- Hugging Face emitted an unauthenticated-request rate-limit warning while the
  cached model loaded; no token was supplied or required, and execution
  completed successfully.
- No query prompt was passed for these document embeddings. No `search.py`,
  search query, vector index, schema change, or Compose change was created in
  this step.
- A manual mocked-input check supplied 12 non-empty values to `read_chunks()`;
  it returned exactly 10, from `line-1` through `line-10`, confirming the input
  cap without another model load or database write.
- Final syntax, installed-version, environment-template, scope, and
  trailing-whitespace checks passed. Historical checkpoint, later superseded:
  `search.py` was still absent at the end of the ingestion-only step; its
  subsequent implementation and validation are recorded immediately below.

### 2026-08-19 — Minimal exact-cosine `search.py`

**Historical status, partially superseded**

- The exact cosine SQL and query-embedding behavior remain current. The
  original one-query-per-process CLI lifecycle was later superseded by the
  persistent interactive session recorded below.

**Implemented**

- Added only `search.py`; no dependency, ingestion, Compose, SQL initialization,
  schema, table, data, or index change was made during implementation.
- Added an interactive query and top-k flow, default 5 and allowed range 1–20.
- Reused the validated Qwen model/cache/BF16 configuration, applying
  `prompt_name="query"` only to queries and requiring normalized finite
  1024-dimensional output.
- Added parameterized, read-only exact cosine retrieval with no approximate
  index and output limited to rank, row ID, similarity, and context.

**Static validation**

- Python syntax and trailing-whitespace checks passed.
- A blank-query CLI run exited with status 0 before model or database access.
- Source checks confirmed the query prompt, normalized encoding, exact
  `<=>` ordering, and parameterized `LIMIT`.

**Live validation status**

- The pre-search database snapshot was 3 rows, maximum ID 3, content/vector
  fingerprint `39bf04603fc3fb2a82ca45d3ea1e84e1`, and 0 HNSW/IVFFlat indexes.
- Loaded Qwen once on `cuda:0` in BF16 and ran three read-only Korean searches:

| Query intent | Expected and observed top-1 | Cosine similarity | Full top-3 ID order |
| --- | --- | ---: | --- |
| Seoul / Korean capital | ID 1 — `서울은 대한민국의 수도이며 정치와 경제의 중심지입니다.` | 0.577673 | 1, 2, 3 |
| Hallasan / highest mountain | ID 2 — `제주도 한라산은 대한민국에서 가장 높은 산입니다.` | 0.622703 | 2, 1, 3 |
| Python / data-analysis language | ID 3 — `파이썬은 데이터 분석과 인공지능 개발에 널리 사용되는 프로그래밍 언어입니다.` | 0.722969 | 3, 1, 2 |

- Measured query-vector norms were 1.00058222, 0.99825418, and 1.00214672;
  every output was finite, 1024-dimensional, and within the 0.01 normalization
  tolerance. `prompt_name="query"` was applied to every query.
- A separate top-k 2 request returned exactly two rows, IDs 1 and 2. Input
  checks also confirmed the default 5, accepted bounds 1 and 20, and rejection
  of 0, 21, and non-integer input.
- The post-search snapshot remained 3 rows, maximum ID 3, the identical
  fingerprint `39bf04603fc3fb2a82ca45d3ea1e84e1`, and 0 HNSW/IVFFlat indexes. This
  confirms no row mutation and no approximate vector index creation.
- Hugging Face emitted the same unauthenticated-request rate-limit warning
  during cached model loading; no token was supplied or required, and all
  searches completed successfully.
- `embedd.py`, its chunking behavior, Compose, SQL initialization, database
  schema/table, model configuration, and existing rows were not modified in
  this step.

### 2026-08-19 — Post-implementation documentation clarification

**Actual-host clarification**

- The user supplied the result of this read-only actual-host inventory command:

```bash
sudo docker ps -a --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}' |
  grep -Ei 'postgres|pgvector'
```

- The inspected actual-host Docker inventory contained only two
  PostgreSQL/pgvector-related containers:
  `nexgent-rag-postgres-1` using
  `pgvector/pgvector:0.8.6-pg16-bookworm`, and
  `nextcloud-aio-database` using
  `ghcr.io/nextcloud-releases/aio-postgresql:latest`.
- Before the RAG container existed, the only PostgreSQL Docker container
  identified in that inspected Docker environment was the Nextcloud database.
  This evidence does not rule out remote PostgreSQL, non-Docker PostgreSQL, or
  other infrastructure outside the inspected Docker environment.
- Sudo works on the actual host with interactive password authentication.
  Passwordless/non-interactive sudo is not established.

**Current implementation and unresolved scope**

- The isolated RAG PostgreSQL/pgvector setup is implemented and live-validated.
  Final deployment topology still requires project-owner confirmation.
- At this historical documentation-only checkpoint, ingestion still used
  line-based smoke-test chunks: one non-empty input line per chunk, at most 10
  lines, without automatic splitting, paragraph/sentence awareness, or overlap.
  The immediately following entry supersedes that implementation.
- Actual source-document formats remained unresolved. At this checkpoint no
  chunk-size or overlap-size rule was approved; the following implementation
  adopts initial parameters that still require real-document evaluation.
- `embedd.py` and `search.py` remain successfully implemented and validated,
  using the selected Qwen model, normalized 1024-dimensional vectors, and exact
  cosine retrieval without HNSW or IVFFlat.

**Changed**

- Documentation clarification only. No code, environment file, database data
  or object, Docker resource, Compose/SQL configuration, model, dependency,
  package, or runtime state was changed.

### 2026-08-19 — Korean chunking and persistent-search implementation

**Checked**

- Before this implementation, `embedd.py` read at most 10 non-empty lines and
  treated each line as a complete chunk; a blank line ended input.
- Before this implementation, `search.py` handled one query per process and
  loaded Qwen after that query and top-k were entered. A module-level singleton
  would not share the in-memory model between separate Python processes.
- No new environment setting or NLP/chunking dependency is required.

**Decided for implementation**

- Collect one multiline source document until `.done` on its own line or EOF;
  preserve ordinary blank lines as paragraph separators.
- Implement deterministic character-based chunking with a preferred
  300–500-character range, a 500-character maximum target, and 50–100
  characters of overlap aimed near 75 characters.
- Select chunk ends by paragraph, Korean/Unicode sentence, whitespace, then hard
  character fallback priority. Protect simple heading-like lines from being
  orphaned at a chunk end when avoidable.
- Require every split and overlap transition to advance, and never repeat the
  entire previous chunk.
- Change `search.py` to a persistent interactive loop. Load Qwen lazily for the
  first valid query and reuse that instance for later queries in the same
  process; `.exit`, `.quit`, EOF, or Ctrl+C ends the session, while blank input
  reprompts.

**Duplicate-ingestion observation**

- Manual testing inserted the same three contexts as IDs `[4, 5, 6]` and then
  `[7, 8, 9]`. Identical embeddings correctly produced duplicate exact-search
  results with identical cosine similarity, including the matching remote-work
  rows at IDs 5 and 8.
- The current table has no uniqueness constraint for source/chunk identity and
  `embedd.py` performs unconditional inserts. No row deletion, uniqueness
  constraint, or `UNIQUE(context)` change is authorized here. A future real
  ingestion design must choose source IDs, chunk/stable IDs, content hashes,
  replace/upsert behavior, or deliberate document versioning based on actual
  source requirements.

**Validation plan at this checkpoint, completed below**

- Run deterministic chunk/input checks without loading Qwen or connecting to
  PostgreSQL.
- If those pass, run one bounded two-query `search.py` session to verify a
  single model load and read-only retrieval. A controlled new-document insert
  will be considered separately and announced before any database write.

**Implemented; validation pending at this checkpoint**

- Replaced the line-oriented input collector in `embedd.py` with multiline
  document collection terminated by `.done` or EOF. Ordinary blank lines are
  retained.
- Added dependency-free paragraph, sentence, whitespace, and hard-fallback
  chunk boundary selection; heading-protection and overlap selection include
  explicit zero-progress and whole-chunk-overlap guards.
- Added source-character, chunk-count, and per-chunk-length summaries before
  model loading. Empty input returns before model or database work.
- Changed `search.py` to keep a local model reference across a query loop. It
  lazily initializes on the first valid query, reprompts on blank input, accepts
  per-query top-k, and exits on `.exit`, `.quit`, EOF, or Ctrl+C.
- No dependency, environment, model, database SQL, schema, Docker, or index
  change was made in this implementation step.

**Deterministic model-free validation**

- Python syntax validation passed for `embedd.py` and `search.py`; source and
  documentation trailing-whitespace checks passed.
- A 30-character Korean document remained one chunk.
- A representative long Korean document produced five chunks with character
  lengths `[392, 491, 491, 491, 294]`. The first four normal chunks remained in
  the configured 300–500 range; the shorter final chunk contained the remaining
  source content.
- Adjacent overlap was exactly 97 characters for all four transitions, within
  the configured 50–100 range. Each overlap was an exact previous-chunk suffix
  and next-chunk prefix, and none repeated an entire chunk.
- A sentence-only Korean sample produced chunks ending at recognized sentence
  punctuation, including a closing quotation mark after the punctuation.
- A heading case kept `## 원격 근무 지침` with body text rather than producing
  a title-only chunk.
- Unique unbroken Hangul-syllable inputs of 501, 650, 1200, and 2049 characters
  exercised hard-split fallback. Every chunk stayed at or below 500 characters,
  every transition advanced, and every measured overlap was exactly the
  75-character fallback target.
- Multiline input preserved an ordinary blank line, `.done` stopped collection,
  and content after the terminator was ignored.
- An empty-input main-path check returned before the mocked model and database
  functions could be called.
- These checks loaded no embedding model, invoked no CUDA operation, opened no
  database connection, and wrote no database row.
- An initial overlap assertion used one repeated Hangul character, for which a
  longest-common suffix/prefix calculation is inherently ambiguous and can
  exceed the actual indexed overlap. The check was corrected to use distinct
  Hangul syllables; no implementation change was required for this test issue.

**Deterministic search-session validation**

- A mocked single-process session ignored one blank query, executed two valid
  queries with top-k values 1 and 2, and exited on `.quit`.
- `load_model()` was called exactly once; both query embeddings received the
  same retained model object. Both result sets were printed, confirming that
  per-query top-k handling does not recreate the model.
- This check loaded no embedding model, invoked no CUDA operation, and opened no
  database connection.

**Live persistent-search validation**

- One `search.py` process handled two Korean queries and then `.exit`. The
  `Loading Qwen/Qwen3-Embedding-0.6B on cuda:0 in BF16...` message appeared
  exactly once; the second query reused the retained model instance.
- With top-k 2, `대한민국의 수도는 어디인가요?` returned the Seoul context at
  rank 1 (ID 1, similarity 0.652455) and exactly two rows.
- With top-k 1, `제주도에서 가장 높은 산은 무엇인가요?` returned the Hallasan
  context at rank 1 (ID 2, similarity 0.719492) and exactly one row.
- Query embeddings remained finite, normalized, and 1024-dimensional with
  `prompt_name="query"`; measured norms were 1.00009024 and 1.00159717.
- Read-only pre/post snapshots were identical: 9 rows, maximum ID 9, and
  fingerprint `5073e6597d55ada0eafe213663766a4d`. The search session changed no
  row and created no index.

**Controlled ingestion preflight**

- Selected a new benign 893-character Korean document titled
  `도시 생태 관찰 안내`, covering safe observation in urban streams, parks, and
  record-keeping. It does not reuse the earlier HR sample text.
- Model-free chunking predicted exactly two chunks with lengths `[454, 496]`.
  The controlled live step is limited to atomically inserting those two chunks;
  no existing row will be updated or deleted.

**Controlled ingestion and retrieval validation**

- `embedd.py` reproduced the preflight exactly: 893 source characters, two
  chunks with lengths `[454, 496]`, normalized 1024-dimensional document
  embeddings, maximum pre-insert norm error 0.00197041, and atomic insertion as
  IDs `[10, 11]`.
- Read-only storage validation measured ID 10 at 454 characters with norm
  0.99996616 and ID 11 at 496 characters with norm 1.00197041; both vectors have
  dimension 1024. The approximate HNSW/IVFFlat index count remained 0.
- In one subsequent `search.py` process, the paraphrased stream-safety question
  ranked ID 10 first with similarity 0.608718, and the repeated-tree-location
  question ranked ID 11 first with similarity 0.701683. Each top-k 3 request
  returned exactly three rows.
- Qwen loaded exactly once for those two searches; query-vector norms were
  0.99993223 and 1.00174260 with `prompt_name="query"`.
- The live step inserted only the announced new chunks. It did not update or
  delete existing rows, change schema/table definitions, or create an index.

### 2026-08-19 — Persistent multi-document ingestion

**Checked**

- At this historical pre-change checkpoint, automatic chunking and insertion
  operated on one collected document, but `embed_documents()` constructed Qwen
  for each invocation and `main()` exited after that document. The implementation
  recorded below supersedes that lifecycle.
- Chunk creation, normalized document embedding without a query prompt, and the
  per-document atomic insert transaction can remain unchanged in semantics.

**Decided for implementation**

- Keep one `embedd.py` process alive for multiple source documents. `.done`
  finishes the current document; `.exit`, `.quit`, EOF, or Ctrl+C ends the
  session. Blank lines remain document content.
- EOF after partial document input finishes and ingests that document once,
  then closes the session. `.exit` or `.quit` discards any partial document and
  exits without ingesting it.
- Initialize Qwen lazily only after the first non-empty document has been
  chunked. Retain that `SentenceTransformer` instance and pass it into every
  later document-embedding call in the same process.
- Keep each document's generated chunks in its own atomic insert transaction.
  Do not change chunking, SQL, database configuration, model settings, vector
  validation, or duplicate-ingestion behavior.

**Validation planned**

- Use deterministic mocks to confirm empty documents do not load Qwen or touch
  PostgreSQL, two non-empty documents call `load_model()` once, both embedding
  calls receive the same model object, and each document is inserted once.
- Validate `.done`, `.exit`, `.quit`, and EOF collection behavior without model
  loading or database access. No live insertion is planned for this lifecycle
  refactor.

**Implemented; validation pending at this checkpoint**

- `read_document()` now returns the collected document plus an exit-after flag.
  `.done` completes one document and keeps the session open; EOF completes a
  partial final document and requests exit; `.exit` or `.quit` discards partial
  input and requests exit.
- `main()` now loops across documents and holds one initially empty model
  reference. It calls `load_model()` only for the first non-empty document and
  passes that retained object to every `embed_documents()` call.
- Each completed document is chunked independently and its chunks are inserted
  in the existing per-document transaction. An empty `.done` reprompts without
  model or database work.
- No search, chunking, SQL, database configuration, model configuration,
  dependency, environment, schema, Docker, or index change was made.

**Deterministic validation results**

- A two-document mocked session called `load_model()` exactly once. Both
  `embed_documents()` calls received the same retained model object, and each
  document invoked one independent insert call.
- An empty `.done` reprompted before model or database work. `.done` preserved
  multiline content and kept the session open; `.quit` exited empty; `.exit`
  discarded partial input; and EOF returned a partial final document for one
  ingestion before exit.
- Syntax, model/runtime constants, no-query-prompt document encoding,
  normalized batch encoding, vector validation, parameterized SQL, and
  per-document transaction behavior were checked without loading Qwen or
  connecting to PostgreSQL.
- No live insertion was performed for this lifecycle refactor, so no database
  row or runtime infrastructure state changed during its validation.

### 2026-08-19 — UTF-8 source-file ingestion design

**Checked**

- At this historical pre-change checkpoint, `embedd.py` selected persistent
  interactive ingestion unconditionally and had no command-line file path
  handling.
- The existing `chunk_document()`, retained-model embedding path, and
  per-document atomic insertion can be shared by interactive and file modes
  without changing their semantics.
- At that checkpoint, no test module existed in the RAG folder, and the
  required file checks could use Python's standard library without a new
  dependency.

**Decided for implementation**

- One or more positional paths select file mode; no arguments preserve the
  current persistent interactive mode exactly. File mode does not interpret or
  require `.done`.
- Validate and UTF-8-decode every supplied path before model loading or any
  database insertion. A missing path, directory, unreadable file, or invalid
  UTF-8 file aborts the entire run with a sanitized error naming the supplied
  path but omitting low-level exception details.
- Empty files are valid inputs but are reported and skipped. The first non-empty
  file lazily loads Qwen, and every later non-empty file in that process reuses
  the same model instance.
- Treat each non-empty file as one source document, preserve its internal line
  breaks, apply the current Korean-aware chunker, and keep its chunks in one
  independent atomic insert transaction.

**Validation planned**

- Add standard-library deterministic tests for one file, multiple files,
  Korean UTF-8 multiline preservation, empty-file skipping, nonexistent-path
  failure, directory rejection, invalid UTF-8 failure, fail-fast behavior, and
  one mocked model reused across multiple files.
- Do not load Qwen, connect to PostgreSQL, or perform a live insertion for this
  already-live-validated ingestion path.

**Implemented**

- Added positional file-path selection to `embedd.py`. No arguments still enter
  the existing persistent interactive session; one or more arguments select
  file mode, in which `.done` is neither required nor interpreted.
- Added a preflight reader that validates and UTF-8-decodes the complete file
  list before processing its first document. Missing paths, directories,
  unreadable files, and invalid UTF-8 abort the run before Qwen or PostgreSQL is
  used. Valid empty files are reported and skipped.
- Both input modes now share the same per-document chunk, summary, batch
  embedding, vector validation, and atomic insertion path. File mode retains
  one lazily loaded Qwen instance across every non-empty file in that process.
- Added `tests/test_embedd_file_mode.py` using only the Python standard library
  and mocks. No chunking parameter, embedding setting, SQL statement, database
  configuration, schema, model, search behavior, dependency, or environment
  setting changed.

**Deterministic validation results**

- Python compilation passed for `embedd.py` and the new test module.
- All nine tests passed in 0.004 seconds. Coverage includes exact preservation
  of Korean UTF-8 multiline text, one-file use of the existing document
  pipeline, multiple files in argument order, empty-file skipping without
  model/database work, whole-run fail-fast behavior for a later missing path,
  directory rejection, invalid UTF-8 rejection, and sanitized unreadable-file
  errors.
- In the two-file mocked ingestion test, `load_model()` was called exactly once;
  both batch-embedding calls received the same model object, and each file made
  one independent insert call.
- No live model load, PostgreSQL connection, database insertion, Docker command,
  or runtime-resource change was needed or performed for this extension. Real
  production source-file types and formats remain unfinalized and still require
  evaluation with the current chunker.

### 2026-08-19 — Documentation readability and consistency cleanup

**Changed**

- Added the authoritative "Current implementation at a glance" summary.
- Time-scoped the initial repository observations and pre-file-mode ingestion
  state, and clarified how present-tense wording in dated log entries should be
  interpreted.
- Reduced repeated current-state inventories: validation now contains evidence,
  remaining work contains required unresolved work, and future improvements
  contains optional engineering considerations.
- Preserved the chronological implementation/debugging history and all measured
  model, chunking, insertion, retrieval, duplicate-ingestion, model-reuse, and
  file-mode test results.

**Validated**

- Markdown heading and trailing-whitespace scans passed.
- Targeted stale-state and credential-pattern scans found no unqualified stale
  current-state claim or credential value. Historical absence/pending statements
  remain only in dated, explicitly time-scoped checkpoints.
- Only this documentation file was intentionally edited; no application or test
  code, configuration, database, Docker resource, model, package, or runtime
  state was changed.

### 2026-08-19 — Manual live end-to-end validation

**Observed live results — distinct from deterministic/mock validation**

- File-mode ingestion was manually validated with the real Qwen model and
  PostgreSQL. A 364-character Korean file was ingested as one chunk.
- Two files were ingested in one `embedd.py` process. Qwen loaded only once,
  confirming same-process model reuse.
- A 1,388-character Korean document was split automatically into four chunks
  with lengths `[421, 499, 321, 374]` and inserted as IDs 15–18.
- `search.py` retrieved the appropriate long-document chunks for questions
  about the service purpose, extreme-weather/environment information,
  response-history records, and the unique keyword
  `보라코끼리청킹테스트`.
- Interactive ingestion was also independently validated earlier with one
  document inserted as ID 19.
- Interactive multi-document ingestion was manually validated. The first
  document was inserted as ID 20 and the second as ID 21; Qwen loaded for the
  first document only and was reused for the second.
- `.done` completed a document and kept the ingestion session alive. `.exit`
  then closed the session normally.
- A read-only PostgreSQL inspection showed 21 total rows and confirmed that the
  expected test rows and chunks were present.
- Duplicate rows remain present by design, including the previously observed
  duplicate-ingestion behavior.

### 2026-08-19 — Token-based Korean chunking design

**Historical pre-change checkpoint**

- The validated automatic chunker still measured chunk and overlap limits with
  Python character counts. Its earlier 300–500-character chunks and
  50–100-character overlap remain preserved as superseded proof-of-concept
  history.

**Decided for implementation**

- Use the tokenizer for `Qwen/Qwen3-Embedding-0.6B` as the authoritative token
  counter. Natural boundary locations remain character offsets so source text
  can be sliced exactly, but every chunk-size, hard-split, and overlap decision
  must use re-tokenized substring counts.
- Use an experimental preferred range of 300–500 tokens, a maximum target of
  500 tokens, and 40–80 tokens of overlap aimed near 60. These are initial PoC
  values that require evaluation against real project documents; they are not
  final production requirements.
- Retain paragraph, sentence, whitespace, then token-level hard-split boundary
  priority. Preserve exact suffix/prefix overlap and add explicit guards against
  empty chunks, zero progress, lost source content, and repetition of an entire
  preceding chunk.
- Keep interactive and file-mode behavior, per-document atomic insertion,
  same-process tokenizer/model reuse, no-query-prompt document embeddings,
  1024-dimensional vectors, and exact search unchanged.

**Validation required before any live insertion**

- Run deterministic tokenizer-based checks for short and long Korean text,
  paragraph and sentence boundaries, token-level fallback, overlap, empty
  input, forward progress, the 500-token maximum, and lossless source coverage.
- Run a model-free comparison with `manual_long_test.txt`, retaining the prior
  result of 1,388 characters and character-chunk lengths
  `[421, 499, 321, 374]` for comparison.
- Do not perform a live database write until the tokenization results are
  reported and reviewed.

**Implemented; deterministic validation pending at this checkpoint**

- Replaced the character-limit constants with experimental token limits:
  preferred 300–500, maximum 500, and overlap 40–80 aimed near 60.
- Added one lazily loaded Qwen tokenizer per ingestion process. It is reused
  across interactive documents or files independently of the already retained
  embedding-model instance.
- Natural boundaries remain exact source character offsets, but candidate
  chunk and overlap spans are accepted only after re-tokenizing the exact
  substring with `add_special_tokens=False`. Token-level fallback uses the fast
  tokenizer's offset mapping and then revalidates the sliced substring count.
- Added chunk-span metadata and runtime guards for the 500-token maximum, exact
  suffix/prefix overlap, 40–80-token overlap, non-empty output, forward
  progress, new source coverage per chunk, and complete source coverage.
- Updated ingestion summaries to report source characters, source tokens,
  chunk count, per-chunk token and character lengths, and overlap token lengths.
- Preserved file and interactive input behavior, model reuse, document
  prompting, embedding validation, SQL, and per-document atomic transactions.
- Added deterministic token-chunking tests and updated the file-ingestion mocks
  for the new reusable-tokenizer lifecycle. These tests do not load model
  weights or connect to PostgreSQL.

**Deterministic and tokenizer-only validation results**

- All 17 offline tests passed in 2.671 seconds: nine existing file-ingestion
  tests, seven token-chunking tests, and one persistent-interactive lifecycle
  regression test.
- The token suite covered empty and short input, long Korean documents,
  paragraph-first and sentence-first boundaries, token-level hard-split
  fallback, exact overlap, monotonically increasing source coverage, and
  complete lossless coverage. Every generated chunk was non-empty and at most
  500 tokens. Every overlap in documents with sufficient content was 40–80
  tokens, was an exact previous-suffix/next-prefix, and was smaller than the
  previous chunk.
- The lifecycle regression used mocks to process two interactive documents.
  The tokenizer and embedding model each loaded once and were reused; each
  document retained a separate mocked insert call.
- Tests loaded the real Qwen tokenizer from the local Hugging Face cache with
  `local_files_only=True`, `HF_HUB_OFFLINE=1`, and
  `TRANSFORMERS_OFFLINE=1`. They did not load embedding-model weights, invoke
  CUDA, connect to PostgreSQL, or write a database row.

**`manual_long_test.txt` tokenizer-only comparison**

- Historical character-based result: 1,388 source characters produced four
  chunks with character lengths `[421, 499, 321, 374]`.
- Token-based result with the Qwen tokenizer: 1,388 source characters, 792
  source tokens, two chunks, token lengths `[478, 362]`, character lengths
  `[835, 641]`, and an exact 48-token overlap. The exact source spans were
  `(0, 835)` and `(747, 1388)`.
- This comparison only loaded the tokenizer and called the chunker. No live
  embedding or database insertion was performed. Live database writes remain
  deferred pending review of these results.
