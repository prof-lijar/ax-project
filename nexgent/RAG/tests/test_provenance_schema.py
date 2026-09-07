from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRESH_SCHEMA = ROOT / "sql" / "001-init-rag.sql"
MIGRATION = ROOT / "sql" / "002-add-document-provenance.sql"


class ProvenanceSchemaTests(unittest.TestCase):
    def test_fresh_schema_contains_documents_and_chunk_provenance(self) -> None:
        sql = FRESH_SCHEMA.read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS rag.documents", sql)
        self.assertIn("source_type text NOT NULL", sql)
        self.assertIn("source_name text NOT NULL", sql)
        self.assertIn("source_type IN ('file', 'text')", sql)
        for column in (
            "document_id bigint",
            "chunk_index integer",
            "source_start_character integer",
            "source_end_character integer",
            "token_count integer",
        ):
            self.assertIn(column, sql)
        self.assertIn("REFERENCES rag.documents(id)", sql)
        self.assertIn("rag_embeddings_document_chunk_unique", sql)
        self.assertIn("WHERE document_id IS NOT NULL", sql)
        self.assertNotIn("UNIQUE (CONTEXT)", sql.upper())
        self.assertNotIn("ON DELETE CASCADE", sql.upper())

    def test_additive_migration_is_nullable_and_non_destructive(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        normalized = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE).upper()

        self.assertIn("CREATE TABLE IF NOT EXISTS RAG.DOCUMENTS", normalized)
        self.assertIn("ADD COLUMN IF NOT EXISTS DOCUMENT_ID BIGINT", normalized)
        self.assertIn("WHERE DOCUMENT_ID IS NOT NULL", normalized)
        self.assertNotRegex(normalized, r"\bUPDATE\b")
        self.assertNotRegex(normalized, r"\bDELETE\b")
        self.assertNotRegex(normalized, r"\bTRUNCATE\b")
        self.assertNotRegex(normalized, r"\bDROP\b")
        altered_columns = normalized.split("ALTER TABLE RAG.EMBEDDINGS", 1)[1].split(
            "DO $MIGRATION$",
            1,
        )[0]
        self.assertNotIn("NOT NULL", altered_columns)
        self.assertNotIn("UNIQUE (CONTEXT)", normalized)
        self.assertNotIn("ON DELETE CASCADE", normalized)


if __name__ == "__main__":
    unittest.main()
