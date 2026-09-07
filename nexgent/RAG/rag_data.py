"""Read and clear RAG-owned data without altering database structure."""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from embedd import database_config


STATS_SQL = """
SELECT
    count(*)::bigint AS embedding_rows,
    (SELECT count(*)::bigint FROM rag.documents) AS document_rows,
    count(*) FILTER (WHERE document_id IS NULL)::bigint
        AS legacy_embedding_rows,
    count(*) FILTER (WHERE document_id IS NOT NULL)::bigint
        AS provenance_embedding_rows
FROM rag.embeddings
"""

DELETE_EMBEDDINGS_SQL = "DELETE FROM rag.embeddings"
DELETE_DOCUMENTS_SQL = "DELETE FROM rag.documents"


@dataclass(frozen=True)
class RagDataStats:
    embedding_rows: int
    document_rows: int
    legacy_embedding_rows: int
    provenance_embedding_rows: int


@dataclass(frozen=True)
class RagDeleteResult:
    deleted_embedding_rows: int
    deleted_document_rows: int


def get_data_stats() -> RagDataStats:
    """Return lightweight row counts for the two RAG-owned tables."""
    with psycopg.connect(**database_config()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(STATS_SQL)
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("RAG data statistics query returned no row")
    return RagDataStats(*(int(value) for value in row))


def delete_all_data() -> RagDeleteResult:
    """Delete all RAG rows in dependency order in one transaction."""
    with psycopg.connect(**database_config()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(DELETE_EMBEDDINGS_SQL)
            deleted_embedding_rows = int(cursor.rowcount)
            cursor.execute(DELETE_DOCUMENTS_SQL)
            deleted_document_rows = int(cursor.rowcount)
    return RagDeleteResult(
        deleted_embedding_rows=deleted_embedding_rows,
        deleted_document_rows=deleted_document_rows,
    )
