#!/usr/bin/env python3
"""Persistently chunk, embed, and insert multiline source documents."""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
MODEL_CACHE = BASE_DIR / ".cache" / "huggingface"
DEVICE = "cuda:0"
EMBEDDING_DIMENSION = 1024
NORM_TOLERANCE = 0.01
MIN_CHUNK_TOKENS = 300
MAX_CHUNK_TOKENS = 500
MIN_OVERLAP_TOKENS = 40
TARGET_OVERLAP_TOKENS = 60
MAX_OVERLAP_TOKENS = 80
EXIT_COMMANDS = {".exit", ".quit"}
INSERT_SQL = """
INSERT INTO rag.embeddings (context, vector)
VALUES (%s, %s::vector)
RETURNING id;
"""

PARAGRAPH_BREAK_RE = re.compile(r"\n[ \t]*\n+")
SENTENCE_END_RE = re.compile(
    r"[.!?。！？][\"'”’」』）\]\}】〉》]*(?=\s|$)"
)
WHITESPACE_RE = re.compile(r"\s+")
MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+\S")
BRACKETED_HEADING_PAIRS = (
    ("[", "]"),
    ("【", "】"),
    ("(", ")"),
    ("（", "）"),
    ("〈", "〉"),
    ("《", "》"),
)

load_dotenv(BASE_DIR / ".env", override=False)
os.environ.setdefault("HF_HOME", str(MODEL_CACHE))
# Use standard CUDA operators because the host has no Python development
# headers required by PyTorch 2.13's optional native Triton helper build.
os.environ.setdefault("TORCH_DISABLE_NATIVE_JIT", "1")

import psycopg  # noqa: E402
import torch  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402
from transformers import AutoTokenizer, PreTrainedTokenizerBase  # noqa: E402


@dataclass(frozen=True)
class ChunkingResult:
    """Token measurements and exact source spans for one chunking run."""

    source_text: str
    source_token_count: int
    chunks: list[str]
    chunk_token_counts: list[int]
    chunk_spans: list[tuple[int, int]]
    overlap_token_counts: list[int]


def read_document(input_fn: Callable[[str], str] = input) -> tuple[str, bool]:
    """Return one document and whether the ingestion session should exit."""
    print(
        "Paste one source document. Blank lines are preserved; "
        "use .done to ingest it or .exit/.quit to end the session."
    )
    lines: list[str] = []
    while True:
        try:
            value = input_fn("document> " if not lines else "... ")
        except EOFError:
            return "\n".join(lines).strip(), True
        command = value.strip().lower()
        if command == ".done":
            return "\n".join(lines).strip(), False
        if command in EXIT_COMMANDS:
            if any(line.strip() for line in lines):
                print("Partial document discarded; ingestion session closing.")
            return "", True
        lines.append(value)


def read_source_files(path_values: list[str]) -> list[tuple[Path, str]]:
    """Validate and UTF-8-decode every source path before ingestion starts."""
    sources: list[tuple[Path, str]] = []
    for path_value in path_values:
        path = Path(path_value)
        if not path.exists():
            raise ValueError(f"Source file does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"Source path is not a regular file: {path}")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"Source file is not valid UTF-8: {path}") from None
        except OSError:
            raise ValueError(f"Source file could not be read: {path}") from None
        sources.append((path, content))
    return sources


def _is_heading_like(line: str) -> bool:
    """Return whether a standalone line looks like a simple heading."""
    value = line.strip()
    if not value or len(value) > 80:
        return False
    if MARKDOWN_HEADING_RE.match(value):
        return True
    if value.endswith((":", "：")):
        return True
    if any(
        value.startswith(left) and value.endswith(right)
        for left, right in BRACKETED_HEADING_PAIRS
    ):
        return True
    return len(value) <= 40 and not value.endswith((".", "!", "?", "。", "！", "？"))


def _heading_protected_ranges(text: str) -> list[tuple[int, int]]:
    """Return ranges where a split would orphan a heading from following text."""
    lines: list[tuple[int, int, int, str]] = []
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        content = raw_line.rstrip("\r\n")
        visible_end = offset + len(content.rstrip(" \t"))
        raw_end = offset + len(raw_line)
        lines.append((offset, visible_end, raw_end, content))
        offset = raw_end
    if offset < len(text) or not lines:
        content = text[offset:]
        lines.append((offset, len(text), len(text), content))

    protected: list[tuple[int, int]] = []
    for index, (_, visible_end, raw_end, content) in enumerate(lines):
        if not _is_heading_like(content):
            continue
        next_content_start: int | None = None
        for next_start, _, _, next_content in lines[index + 1 :]:
            if next_content.strip():
                next_content_start = next_start
                break
        if next_content_start is not None:
            protected.append((visible_end, max(raw_end, next_content_start)))
    return protected


def _is_protected_boundary(
    position: int, protected_ranges: list[tuple[int, int]]
) -> bool:
    return any(start <= position <= end for start, end in protected_ranges)


def _skip_whitespace(text: str, position: int) -> int:
    while position < len(text) and text[position].isspace():
        position += 1
    return position


def _boundary_positions(text: str) -> tuple[tuple[list[int], ...], tuple[list[int], ...]]:
    """Return prioritized chunk-end and overlap-start boundary positions."""
    paragraph_matches = list(PARAGRAPH_BREAK_RE.finditer(text))
    sentence_matches = list(SENTENCE_END_RE.finditer(text))
    whitespace_matches = list(WHITESPACE_RE.finditer(text))

    end_groups = (
        [match.start() for match in paragraph_matches],
        [match.end() for match in sentence_matches],
        [match.start() for match in whitespace_matches],
    )
    start_groups = (
        [_skip_whitespace(text, match.end()) for match in paragraph_matches],
        [_skip_whitespace(text, match.end()) for match in sentence_matches],
        [_skip_whitespace(text, match.end()) for match in whitespace_matches],
    )
    return end_groups, start_groups


def count_tokens(tokenizer: PreTrainedTokenizerBase, text: str) -> int:
    """Count Qwen tokenizer tokens without adding model special tokens."""
    return len(tokenizer.encode(text, add_special_tokens=False))


def _token_offsets(
    tokenizer: PreTrainedTokenizerBase, text: str
) -> list[tuple[int, int]]:
    """Return fast-tokenizer character offsets for exact source slicing."""
    encoded = tokenizer(
        text,
        add_special_tokens=False,
        return_offsets_mapping=True,
    )
    raw_offsets = encoded.get("offset_mapping")
    if raw_offsets is None:
        raise RuntimeError("The selected Qwen tokenizer does not expose offsets")
    offsets = [
        (int(start), int(end))
        for start, end in raw_offsets
        if int(end) > int(start)
    ]
    if text and not offsets:
        raise RuntimeError("The selected Qwen tokenizer produced no usable offsets")
    return offsets


def _max_end_within_token_limit(
    text: str,
    start: int,
    tokenizer: PreTrainedTokenizerBase,
    span_token_count: Callable[[int, int], int],
) -> int:
    """Find an exact source end whose re-tokenized span fits the maximum."""
    offsets = _token_offsets(tokenizer, text[start:])
    if len(offsets) <= MAX_CHUNK_TOKENS:
        return len(text)

    token_index = min(MAX_CHUNK_TOKENS, len(offsets)) - 1
    while token_index >= 0:
        end = start + offsets[token_index][1]
        if end > start and span_token_count(start, end) <= MAX_CHUNK_TOKENS:
            return end
        token_index -= 1
    raise RuntimeError("Token-level hard split could not make forward progress")


def _choose_chunk_end(
    text: str,
    start: int,
    previous_end: int,
    tokenizer: PreTrainedTokenizerBase,
    span_token_count: Callable[[int, int], int],
    end_groups: tuple[list[int], ...],
    protected_ranges: list[tuple[int, int]],
) -> int:
    """Choose a natural boundary using re-tokenized span sizes."""
    hard_end = _max_end_within_token_limit(
        text, start, tokenizer, span_token_count
    )
    if hard_end <= previous_end:
        raise RuntimeError("Chunking cannot add new source content")

    fallback_minimum = max(MIN_CHUNK_TOKENS // 2, MAX_OVERLAP_TOKENS + 1)
    for minimum_tokens in (MIN_CHUNK_TOKENS, fallback_minimum):
        for positions in end_groups:
            for position in reversed(positions):
                if position <= max(start, previous_end) or position > hard_end:
                    continue
                if _is_protected_boundary(position, protected_ranges):
                    continue
                tokens = span_token_count(start, position)
                if minimum_tokens <= tokens <= MAX_CHUNK_TOKENS:
                    return position

    return hard_end


def _choose_overlap_start(
    text: str,
    start: int,
    end: int,
    tokenizer: PreTrainedTokenizerBase,
    span_token_count: Callable[[int, int], int],
    start_groups: tuple[list[int], ...],
) -> int:
    """Choose an exact 40–80-token suffix, aiming near 60 tokens."""
    chunk_tokens = span_token_count(start, end)

    for positions in start_groups:
        candidates: list[tuple[int, int]] = []
        for position in positions:
            if not start < position < end:
                continue
            overlap_tokens = span_token_count(position, end)
            if (
                MIN_OVERLAP_TOKENS <= overlap_tokens <= MAX_OVERLAP_TOKENS
                and overlap_tokens < chunk_tokens
            ):
                candidates.append((position, overlap_tokens))
        if candidates:
            return min(
                candidates,
                key=lambda item: (
                    abs(item[1] - TARGET_OVERLAP_TOKENS),
                    item[0],
                ),
            )[0]

    offsets = _token_offsets(tokenizer, text[start:end])
    candidates = []
    for local_start, _ in offsets:
        position = start + local_start
        if not start < position < end:
            continue
        overlap_tokens = span_token_count(position, end)
        if (
            MIN_OVERLAP_TOKENS <= overlap_tokens <= MAX_OVERLAP_TOKENS
            and overlap_tokens < chunk_tokens
        ):
            candidates.append((position, overlap_tokens))
    if not candidates:
        raise RuntimeError("Token-level overlap selection could not make progress")
    return min(
        candidates,
        key=lambda item: (abs(item[1] - TARGET_OVERLAP_TOKENS), item[0]),
    )[0]


def chunk_document(
    document: str, tokenizer: PreTrainedTokenizerBase
) -> ChunkingResult:
    """Split a document using Qwen token counts and exact source spans."""
    text = document.strip()
    if not text:
        return ChunkingResult("", 0, [], [], [], [])

    @lru_cache(maxsize=None)
    def span_token_count(start: int, end: int) -> int:
        return count_tokens(tokenizer, text[start:end])

    source_token_count = span_token_count(0, len(text))
    end_groups, start_groups = _boundary_positions(text)
    protected_ranges = _heading_protected_ranges(text)
    chunks: list[str] = []
    chunk_token_counts: list[int] = []
    chunk_spans: list[tuple[int, int]] = []
    overlap_token_counts: list[int] = []
    start = 0

    while start < len(text):
        previous_end = chunk_spans[-1][1] if chunk_spans else 0
        if span_token_count(start, len(text)) <= MAX_CHUNK_TOKENS:
            end = len(text)
        else:
            end = _choose_chunk_end(
                text,
                start,
                previous_end,
                tokenizer,
                span_token_count,
                end_groups,
                protected_ranges,
            )

        if end <= start:
            raise RuntimeError("Chunking failed to make forward progress")
        if chunk_spans and end <= previous_end:
            raise RuntimeError("Chunking failed to add new source content")

        chunk = text[start:end]
        if not chunk.strip():
            raise RuntimeError("Chunking produced an empty chunk")
        chunk_tokens = span_token_count(start, end)
        if chunk_tokens > MAX_CHUNK_TOKENS:
            raise RuntimeError(
                f"Chunk exceeds {MAX_CHUNK_TOKENS} tokens: {chunk_tokens}"
            )

        if chunk_spans:
            previous_start, previous_end = chunk_spans[-1]
            if not previous_start < start < previous_end:
                raise RuntimeError("Adjacent chunks do not contain an overlap")
            overlap_text = text[start:previous_end]
            if not chunks[-1].endswith(overlap_text) or not chunk.startswith(
                overlap_text
            ):
                raise RuntimeError("Adjacent chunks do not preserve exact overlap")
            overlap_tokens = span_token_count(start, previous_end)
            if not MIN_OVERLAP_TOKENS <= overlap_tokens <= MAX_OVERLAP_TOKENS:
                raise RuntimeError(
                    f"Overlap outside token range: {overlap_tokens}"
                )
            if overlap_tokens >= chunk_token_counts[-1]:
                raise RuntimeError("Overlap would repeat the entire previous chunk")
            overlap_token_counts.append(overlap_tokens)

        chunks.append(chunk)
        chunk_token_counts.append(chunk_tokens)
        chunk_spans.append((start, end))

        if end == len(text):
            break

        next_start = _choose_overlap_start(
            text,
            start,
            end,
            tokenizer,
            span_token_count,
            start_groups,
        )
        if not start < next_start < end:
            raise RuntimeError("Overlap selection failed to make forward progress")
        start = next_start

    if chunk_spans[0][0] != 0 or chunk_spans[-1][1] != len(text):
        raise RuntimeError("Chunking did not cover the complete source document")
    for (_, previous_end), (next_start, _) in zip(
        chunk_spans, chunk_spans[1:], strict=False
    ):
        if next_start > previous_end:
            raise RuntimeError("Chunking left a gap in the source document")

    return ChunkingResult(
        source_text=text,
        source_token_count=source_token_count,
        chunks=chunks,
        chunk_token_counts=chunk_token_counts,
        chunk_spans=chunk_spans,
        overlap_token_counts=overlap_token_counts,
    )


def database_config() -> dict[str, str | int]:
    """Build connection parameters without constructing or printing a DSN."""
    password = os.environ.get("RAG_POSTGRES_PASSWORD")
    if not password:
        raise ValueError("RAG_POSTGRES_PASSWORD is required in the environment or .env")

    port_text = os.environ.get("RAG_POSTGRES_PORT", "5433")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError("RAG_POSTGRES_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("RAG_POSTGRES_PORT must be between 1 and 65535")

    return {
        "host": os.environ.get("RAG_POSTGRES_HOST", "127.0.0.1"),
        "port": port,
        "dbname": os.environ.get("RAG_POSTGRES_DB", "nextgent"),
        "user": os.environ.get("RAG_POSTGRES_USER", "rag"),
        "password": password,
        "connect_timeout": 10,
    }


def load_tokenizer() -> PreTrainedTokenizerBase:
    """Load the authoritative Qwen tokenizer used for chunk measurements."""
    print(f"Loading tokenizer for {MODEL_ID}...")
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ID,
        cache_dir=str(MODEL_CACHE),
        use_fast=True,
    )
    if not tokenizer.is_fast:
        raise RuntimeError("Token-based chunking requires a fast Qwen tokenizer")
    return tokenizer


def load_model() -> SentenceTransformer:
    """Load the validated embedding model on one BF16 CUDA device."""
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required but is not available to PyTorch")
    if not torch.cuda.is_bf16_supported():
        raise RuntimeError("The selected CUDA device does not report BF16 support")

    print(f"Loading {MODEL_ID} on {DEVICE} in BF16...")
    return SentenceTransformer(
        MODEL_ID,
        device=DEVICE,
        cache_folder=str(MODEL_CACHE),
        model_kwargs={"torch_dtype": torch.bfloat16},
    )


def embed_documents(
    model: SentenceTransformer, chunks: list[str]
) -> list[list[float]]:
    """Create validated normalized document embeddings without a query prompt."""
    # Documents deliberately receive no query prompt or prompt_name.
    embeddings = model.encode(
        chunks,
        batch_size=len(chunks),
        convert_to_tensor=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).float()

    expected_shape = (len(chunks), EMBEDDING_DIMENSION)
    if tuple(embeddings.shape) != expected_shape:
        raise RuntimeError(
            f"Unexpected embedding shape {tuple(embeddings.shape)}; "
            f"expected {expected_shape}"
        )
    if not bool(torch.isfinite(embeddings).all().item()):
        raise RuntimeError("Embedding output contains a non-finite value")

    norms = torch.linalg.vector_norm(embeddings, dim=1)
    max_norm_error = float(torch.max(torch.abs(norms - 1)).item())
    if max_norm_error > NORM_TOLERANCE:
        raise RuntimeError(
            f"Embedding normalization check failed: max error {max_norm_error:.8f}"
        )

    print(
        f"Embedded {len(chunks)} chunk(s): dimension={embeddings.shape[1]}, "
        f"max_norm_error={max_norm_error:.8f}"
    )
    return embeddings.cpu().tolist()


def insert_chunks(chunks: list[str], vectors: list[list[float]]) -> list[int]:
    """Insert chunks and vectors atomically, returning generated identity IDs."""
    inserted_ids: list[int] = []
    with psycopg.connect(**database_config()) as connection:
        with connection.cursor() as cursor:
            for context, vector in zip(chunks, vectors, strict=True):
                vector_literal = json.dumps(vector, separators=(",", ":"))
                cursor.execute(INSERT_SQL, (context, vector_literal))
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("INSERT ... RETURNING id produced no row")
                inserted_ids.append(int(row[0]))
    return inserted_ids


def ingest_document(
    document: str,
    tokenizer: PreTrainedTokenizerBase | None,
    model: SentenceTransformer | None,
) -> tuple[PreTrainedTokenizerBase, SentenceTransformer, list[int]]:
    """Chunk, embed, and atomically insert one non-empty source document."""
    if tokenizer is None:
        tokenizer = load_tokenizer()
    result = chunk_document(document, tokenizer)
    token_lengths = ", ".join(str(value) for value in result.chunk_token_counts)
    character_lengths = ", ".join(str(len(chunk)) for chunk in result.chunks)
    overlap_lengths = ", ".join(str(value) for value in result.overlap_token_counts)
    print(f"Source characters: {len(result.source_text)}")
    print(f"Source tokens: {result.source_token_count}")
    print(f"Generated chunks: {len(result.chunks)}")
    print(f"Chunk token lengths: [{token_lengths}]")
    print(f"Chunk character lengths: [{character_lengths}]")
    print(f"Overlap token lengths: [{overlap_lengths}]")

    if model is None:
        model = load_model()
    vectors = embed_documents(model, result.chunks)
    inserted_ids = insert_chunks(result.chunks, vectors)
    return tokenizer, model, inserted_ids


def run_interactive_mode() -> int:
    """Ingest multiple interactively entered documents in one process."""
    tokenizer: PreTrainedTokenizerBase | None = None
    model: SentenceTransformer | None = None
    document_number = 0
    print("Persistent ingestion session started.")
    while True:
        document, exit_after_document = read_document()
        if not document:
            if exit_after_document:
                print("Ingestion session closed.")
                return 0
            print("No source document entered; start another or exit.")
            continue

        tokenizer, model, inserted_ids = ingest_document(
            document, tokenizer, model
        )
        document_number += 1
        print(
            f"Inserted document {document_number}: "
            f"{len(inserted_ids)} chunk(s); ids={inserted_ids}"
        )

        if exit_after_document:
            print("End of input; ingestion session closed.")
            return 0


def run_file_mode(path_values: list[str]) -> int:
    """Ingest validated UTF-8 files with one lazily loaded model."""
    sources = read_source_files(path_values)
    tokenizer: PreTrainedTokenizerBase | None = None
    model: SentenceTransformer | None = None
    inserted_documents = 0

    for path, document in sources:
        if not document.strip():
            print(f"Skipping empty source file: {path}")
            continue

        print(f"Source file: {path}")
        tokenizer, model, inserted_ids = ingest_document(
            document, tokenizer, model
        )
        inserted_documents += 1
        print(
            f"Inserted file {path}: "
            f"{len(inserted_ids)} chunk(s); ids={inserted_ids}"
        )

    print(
        f"File ingestion complete: {inserted_documents} non-empty "
        f"document(s) processed."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    try:
        if arguments:
            return run_file_mode(arguments)
        return run_interactive_mode()
    except KeyboardInterrupt:
        print("\nIngestion cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
