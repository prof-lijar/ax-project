#!/usr/bin/env python3
"""Run a persistent interactive exact-cosine pgvector search session."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
MODEL_CACHE = BASE_DIR / ".cache" / "huggingface"
DEVICE = "cuda:0"
EMBEDDING_DIMENSION = 1024
NORM_TOLERANCE = 0.01
DEFAULT_TOP_K = 5
MAX_TOP_K = 20
EXIT_COMMANDS = {".exit", ".quit"}
SEARCH_SQL = """
WITH query_embedding AS (
    SELECT %s::vector AS vector
)
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
"""

load_dotenv(BASE_DIR / ".env", override=False)
os.environ.setdefault("HF_HOME", str(MODEL_CACHE))
# Match the validated Qwen runtime and avoid PyTorch's optional native Triton
# helper build, which requires unavailable Python development headers.
os.environ.setdefault("TORCH_DISABLE_NATIVE_JIT", "1")

import psycopg  # noqa: E402
import torch  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402


def read_query() -> str | None:
    """Read one query, returning None on EOF."""
    try:
        return input("Search query [.exit/.quit]> ").strip()
    except EOFError:
        return None


def read_top_k() -> int:
    """Read and validate the optional top-k value."""
    try:
        value = input(f"Top-k [{DEFAULT_TOP_K}]> ").strip()
    except EOFError:
        value = ""
    if not value:
        return DEFAULT_TOP_K
    try:
        top_k = int(value)
    except ValueError as exc:
        raise ValueError("Top-k must be an integer") from exc
    if not 1 <= top_k <= MAX_TOP_K:
        raise ValueError(f"Top-k must be between 1 and {MAX_TOP_K}")
    return top_k


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


def embed_query(model: SentenceTransformer, query: str) -> list[float]:
    """Create one validated normalized query embedding with Qwen's prompt."""
    embedding = model.encode(
        [query],
        prompt_name="query",
        batch_size=1,
        convert_to_tensor=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).float()

    expected_shape = (1, EMBEDDING_DIMENSION)
    if tuple(embedding.shape) != expected_shape:
        raise RuntimeError(
            f"Unexpected embedding shape {tuple(embedding.shape)}; "
            f"expected {expected_shape}"
        )
    if not bool(torch.isfinite(embedding).all().item()):
        raise RuntimeError("Query embedding contains a non-finite value")

    norm = float(torch.linalg.vector_norm(embedding[0]).item())
    if abs(norm - 1) > NORM_TOLERANCE:
        raise RuntimeError(
            f"Query embedding normalization check failed: norm {norm:.8f}"
        )

    print(
        f"Embedded query: dimension={embedding.shape[1]}, norm={norm:.8f}, "
        'prompt_name="query"'
    )
    return embedding[0].cpu().tolist()


def search_database(vector: list[float], top_k: int) -> list[tuple[Any, ...]]:
    """Return exact cosine-ranked rows without mutating the database."""
    vector_literal = json.dumps(vector, separators=(",", ":"))
    with psycopg.connect(**database_config()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(SEARCH_SQL, (vector_literal, top_k))
            return cursor.fetchall()


def print_results(rows: list[tuple[Any, ...]]) -> None:
    """Print ranked IDs, similarities, and contexts without raw vectors."""
    if not rows:
        print("No matching contexts found.")
        return
    for rank, row in enumerate(rows, start=1):
        (
            row_id,
            context,
            similarity,
            document_id,
            source_type,
            source_name,
            chunk_index,
            _,
            _,
            _,
        ) = row
        provenance = (
            f"source={source_name} type={source_type} "
            f"document_id={document_id} chunk={chunk_index}"
            if document_id is not None
            else "source=unavailable (legacy row)"
        )
        print(
            f"[{rank}] id={row_id} similarity={float(similarity):.6f} "
            f"{provenance}\n"
            f"{context}"
        )


def main() -> int:
    model: SentenceTransformer | None = None
    print("Interactive search session started. Blank queries are ignored.")
    try:
        while True:
            query = read_query()
            if query is None:
                print("End of input; search session closed.")
                return 0
            if not query:
                print("Blank query ignored; enter a query or .exit.")
                continue
            if query.lower() in EXIT_COMMANDS:
                print("Search session closed.")
                return 0

            try:
                top_k = read_top_k()
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                continue

            if model is None:
                model = load_model()
            vector = embed_query(model, query)
            rows = search_database(vector, top_k)
            print_results(rows)
    except KeyboardInterrupt:
        print("\nSearch session cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
