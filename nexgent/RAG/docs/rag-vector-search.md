# RAG Vector Search

This document describes the current chunking, embedding, persistence, and
retrieval design. API and service operation belong in
[RAG Server](rag-server.md); measured retrieval quality belongs in
[Retrieval Evaluation](rag-retrieval-evaluation.md).

## Current pipeline

```text
File upload                         Direct Text
  -> format-specific extraction      |
  -> SourceDocument <----------------+
  -> Qwen-tokenizer chunking
  -> normalized Qwen document embeddings
  -> one rag.documents row + N rag.embeddings rows

Query
  -> normalized Qwen query embedding (prompt_name="query")
  -> exact pgvector cosine ordering
  -> provenance LEFT JOIN
  -> Top-K contexts
```

Production search is vector-only. The experimental lexical scorer and
Reciprocal Rank Fusion are not called by `search.py`, the FastAPI search route,
or RAG Chat.

## Model and vector contract

| Setting | Current value |
| --- | --- |
| Model/tokenizer | `Qwen/Qwen3-Embedding-0.6B` |
| Device | `cuda:0` |
| Precision | BF16 |
| Dimension | 1024 |
| Normalization | enabled; finite and near-unit vectors validated |
| Document prompt | none |
| Query prompt | `prompt_name="query"` |
| Model cache | `RAG/.cache/huggingface` unless `HF_HOME` is set |

The model and tokenizer are loaded once during FastAPI lifespan and reused
within that server process. CLI entry points load their own process-local model
and are not the production service path.

## Chunking

`chunk_document()` receives `max_chunk_tokens` as a call argument; requests do
not mutate module-level configuration.

| Setting | Current behavior |
| --- | --- |
| Configurable maximum | 100–1000 tokens |
| Default maximum | 500 tokens |
| Preferred minimum | 300 when maximum is at least 300; contracts below 300 |
| Overlap | normally 40–80 tokens, target near 60 |
| Boundary order | paragraph → sentence punctuation → whitespace → hard token split |

For small maxima, the effective preferred minimum and overlap contract so they
cannot exceed the requested chunk size. At the normal 500-token default, the
40/60/80 overlap behavior is unchanged. Natural boundaries can produce chunks
shorter than the configured maximum.

The immutable `ChunkingResult` carries:

- final normalized source text and its total token count;
- chunk strings and per-chunk token counts;
- zero-based, end-exclusive source character spans; and
- adjacent overlap token counts.

Public preview indexes and persisted chunk indexes are one-based. Overlap does
not change numbering.

## Extraction boundary

All sources become an immutable `SourceDocument(source_type, source_name,
text)` before chunking. File parsing does not contain embedding or database
logic; Direct Text does not duplicate the downstream pipeline.

- TXT and Markdown use strict UTF-8 decoding.
- PDF uses native `pypdf` text when present and page-level OCR only for pages
  without non-whitespace native text.
- DOCX flattens top-level paragraphs/headings and ordinary tables in document
  order.
- Direct Text preserves submitted text; an optional title or generated display
  name supplies provenance.

For extraction limits and error behavior, see
[RAG Server](rag-server.md#extraction-behavior).

## Persistence and provenance

The schema is intentionally small:

```text
rag.documents
  id, source_type, source_name

rag.embeddings
  id, document_id?, chunk_index?, source_start_character?,
  source_end_character?, token_count?, context, vector(1024)
```

The source type is `file` or `text`. File names are safe basenames; Direct Text
uses a display title, not a fake filename. A single transaction inserts the
document row, obtains its identity, inserts every chunk with provenance, and
commits only after all inserts succeed.

The nullable provenance columns preserve compatibility with pre-migration
rows. Search returns null source fields for such rows. The migration did not
invent provenance; historical legacy rows remained searchable until the later
validated Empty Database operation removed the then-current corpus.

`source_start_character` and `source_end_character` identify offsets in the
exact flattened source string passed to `chunk_document()`. They are useful for
debugging and future source highlighting, but are not file-format coordinates.

The partial unique index on `(document_id, chunk_index)` protects per-document
ordering. Identical context is allowed because the same text can legitimately
occur in multiple documents or chunks.

## Retrieval

`search.py` creates one normalized query vector and executes a read-only exact
cosine query. The essential SQL behavior is:

```sql
SELECT
    embeddings.id,
    embeddings.context,
    1 - (embeddings.vector <=> query_embedding.vector) AS similarity,
    embeddings.document_id,
    documents.source_type,
    documents.source_name,
    embeddings.chunk_index,
    embeddings.source_start_character,
    embeddings.source_end_character,
    embeddings.token_count
FROM rag.embeddings AS embeddings
CROSS JOIN query_embedding
LEFT JOIN rag.documents AS documents
    ON documents.id = embeddings.document_id
ORDER BY embeddings.vector <=> query_embedding.vector
LIMIT %s;
```

The public default is five results and the accepted range is 1–20. There is no
HNSW or IVFFlat index; ordering is an exact pgvector scan over the current
corpus. Cosine similarity is a ranking score, not confidence, probability, or
answer accuracy.

## Retrieval-quality evidence

The fixed benchmark has 20 unchanged questions over one Markdown and one PDF
source. Its two recorded vector runs are:

| Run | Top-1 | Top-3 | Top-5 | MRR |
| --- | ---: | ---: | ---: | ---: |
| 2026-08-20 historical baseline | 12/20 (60%) | 17/20 (85%) | 18/20 (90%) | 0.7183 |
| 2026-08-24 larger-corpus regression | 12/20 (60%) | 16/20 (80%) | 18/20 (90%) | 0.7142 |

The second corpus included later OCR/DOCX/test content. The only sufficient-rank
change was `PDF-Q05` from rank 3 to rank 4; the evidence points to corpus
competition rather than a change in model, chunking, SQL, or API order.

An offline lexical/RRF experiment improved RRF Top-1 to 65%, Top-3 to 85%, and
MRR to 0.7458 while retaining Top-5 at 90%, but two questions worsened and the
lexical prototype scans the corpus in Python. This is evidence for further
research, not approval for production Hybrid retrieval. Exact questions,
per-question ranks, category results, and experiment details are in
[Retrieval Evaluation](rag-retrieval-evaluation.md).

These measurements describe dated pre-deletion corpus states. They are not a
claim about whatever rows happen to be in the live database now.

## Data administration

The RAG API exposes counts and a guarded all-data deletion workflow. Deletion
removes embeddings before documents in one transaction, includes legacy rows,
keeps schema/indexes/constraints, and does not reset identities. See
[RAG Server](rag-server.md#rag-data-statistics-and-deletion) and
[UI Integration](rag-ui-integration.md#rag-data-administration).

Backups created before the live Empty Database validation were structurally
inspected. Restore execution and post-restore retrieval equivalence have not
been validated.

## Known limitations and research priorities

- Duplicate/re-ingestion/version semantics are unresolved; no content-based
  uniqueness or source replacement policy exists.
- Provenance lacks a stable external source identity, version, path, or
  Nextcloud link.
- Exact vector search can favor broad semantic neighbors over numeric, entity,
  and fine-grained rule evidence.
- The fixed benchmark is small and covers only two source documents.
- Hybrid/RRF is experimental; scalable Korean lexical indexing, candidate
  depth, fusion parameters, and known regressions require evaluation.
- There is no approximate vector index. That is acceptable for the current PoC
  scale but must be reconsidered with representative corpus size and latency.
- OCR and DOCX extraction limitations are documented in
  [RAG Server](rag-server.md#known-limitations-and-next-work).
