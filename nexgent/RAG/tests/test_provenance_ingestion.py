from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import embedd
import search


class ProvenanceIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = embedd.SourceDocument(
            source_type="file",
            source_name="project.md",
            text="첫 청크와 겹침\n둘째 청크",
        )
        self.chunking = embedd.ChunkingResult(
            source_text=self.source.text,
            source_token_count=12,
            chunks=["첫 청크와 겹침", "겹침\n둘째 청크"],
            chunk_token_counts=[7, 8],
            chunk_spans=[(0, 8), (5, 14)],
            overlap_token_counts=[3],
        )
        self.vectors = [[0.1] * 1024, [0.2] * 1024]

    def test_document_and_chunks_use_one_transaction_with_ordered_metadata(
        self,
    ) -> None:
        connection_context, connection, cursor = self.database_mocks()
        cursor.fetchone.side_effect = [(40,), (101,), (102,)]

        with (
            patch.object(embedd.psycopg, "connect", return_value=connection_context),
            patch.object(embedd, "database_config", return_value={}),
        ):
            result = embedd.insert_chunks(
                self.source,
                self.chunking,
                self.vectors,
            )

        self.assertEqual(result, embedd.PersistedDocument(40, [101, 102]))
        self.assertEqual(cursor.execute.call_count, 3)
        self.assertEqual(
            cursor.execute.call_args_list[0].args,
            (embedd.INSERT_DOCUMENT_SQL, ("file", "project.md")),
        )
        first_chunk_parameters = cursor.execute.call_args_list[1].args[1]
        second_chunk_parameters = cursor.execute.call_args_list[2].args[1]
        self.assertEqual(
            first_chunk_parameters[:6],
            (40, 1, 0, 8, 7, "첫 청크와 겹침"),
        )
        self.assertEqual(
            second_chunk_parameters[:6],
            (40, 2, 5, 14, 8, "겹침\n둘째 청크"),
        )
        self.assertEqual(connection.cursor.call_count, 1)
        connection_context.__exit__.assert_called_once_with(None, None, None)

    def test_chunk_failure_propagates_through_document_transaction(self) -> None:
        connection_context, _, cursor = self.database_mocks()
        failure = RuntimeError("second chunk failed")
        cursor.execute.side_effect = [None, None, failure]
        cursor.fetchone.side_effect = [(41,), (103,)]

        with (
            patch.object(embedd.psycopg, "connect", return_value=connection_context),
            patch.object(embedd, "database_config", return_value={}),
            self.assertRaisesRegex(RuntimeError, "second chunk failed"),
        ):
            embedd.insert_chunks(self.source, self.chunking, self.vectors)

        exit_args = connection_context.__exit__.call_args.args
        self.assertIs(exit_args[0], RuntimeError)
        self.assertIs(exit_args[1], failure)

    def test_same_text_sources_create_separate_document_inserts(self) -> None:
        first_context, _, first_cursor = self.database_mocks()
        second_context, _, second_cursor = self.database_mocks()
        first_cursor.fetchone.side_effect = [(50,), (110,), (111,)]
        second_cursor.fetchone.side_effect = [(51,), (112,), (113,)]
        second_source = embedd.SourceDocument("file", "copy.md", self.source.text)

        with (
            patch.object(
                embedd.psycopg,
                "connect",
                side_effect=[first_context, second_context],
            ),
            patch.object(embedd, "database_config", return_value={}),
        ):
            first = embedd.insert_chunks(self.source, self.chunking, self.vectors)
            second = embedd.insert_chunks(second_source, self.chunking, self.vectors)

        self.assertEqual(first.document_id, 50)
        self.assertEqual(second.document_id, 51)
        self.assertNotEqual(first.document_id, second.document_id)

    def test_search_sql_preserves_exact_cosine_order_and_left_joins_documents(
        self,
    ) -> None:
        self.assertIn("LEFT JOIN rag.documents", search.SEARCH_SQL)
        self.assertIn(
            "1 - (embeddings.vector <=> query_embedding.vector)",
            search.SEARCH_SQL,
        )
        self.assertIn(
            "ORDER BY embeddings.vector <=> query_embedding.vector",
            search.SEARCH_SQL,
        )
        self.assertIn("embeddings.document_id", search.SEARCH_SQL)

    @staticmethod
    def database_mocks() -> tuple[MagicMock, MagicMock, MagicMock]:
        connection_context = MagicMock()
        connection = MagicMock()
        cursor_context = MagicMock()
        cursor = MagicMock()
        connection_context.__enter__.return_value = connection
        connection.cursor.return_value = cursor_context
        cursor_context.__enter__.return_value = cursor
        return connection_context, connection, cursor


if __name__ == "__main__":
    unittest.main()
