from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch


os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import httpx  # noqa: E402

import rag_data  # noqa: E402
import rag_server  # noqa: E402


class FakeCursor:
    def __init__(
        self,
        *,
        stats_row: tuple[int, int, int, int] = (72, 2, 71, 1),
        deleted_embedding_rows: int = 72,
        deleted_document_rows: int = 2,
        fail_document_delete: bool = False,
    ) -> None:
        self.stats_row = stats_row
        self.deleted_embedding_rows = deleted_embedding_rows
        self.deleted_document_rows = deleted_document_rows
        self.fail_document_delete = fail_document_delete
        self.operations: list[str] = []
        self.rowcount = -1

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, statement: str) -> None:
        normalized = " ".join(statement.split())
        self.operations.append(normalized)
        if normalized == rag_data.DELETE_EMBEDDINGS_SQL:
            self.rowcount = self.deleted_embedding_rows
        elif normalized == rag_data.DELETE_DOCUMENTS_SQL:
            if self.fail_document_delete:
                raise RuntimeError("simulated document deletion failure")
            self.rowcount = self.deleted_document_rows

    def fetchone(self) -> tuple[int, int, int, int]:
        return self.stats_row


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.test_cursor = cursor
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: object,
    ) -> None:
        self.committed = exc_type is None
        self.rolled_back = exc_type is not None
        return None

    def cursor(self) -> FakeCursor:
        return self.test_cursor


class RagDataDatabaseTests(unittest.TestCase):
    def test_stats_distinguish_legacy_and_provenance_rows(self) -> None:
        cursor = FakeCursor(stats_row=(80, 2, 71, 9))
        connection = FakeConnection(cursor)
        with (
            patch.object(rag_data, "database_config", return_value={"dbname": "test"}),
            patch.object(rag_data.psycopg, "connect", return_value=connection),
        ):
            result = rag_data.get_data_stats()

        self.assertEqual(
            result,
            rag_data.RagDataStats(
                embedding_rows=80,
                document_rows=2,
                legacy_embedding_rows=71,
                provenance_embedding_rows=9,
            ),
        )
        self.assertIn("FROM rag.embeddings", cursor.operations[0])
        self.assertIn("FROM rag.documents", cursor.operations[0])

    def test_delete_uses_one_transaction_and_dependency_order(self) -> None:
        cursor = FakeCursor(deleted_embedding_rows=80, deleted_document_rows=2)
        connection = FakeConnection(cursor)
        connect = Mock(return_value=connection)
        with (
            patch.object(rag_data, "database_config", return_value={"dbname": "test"}),
            patch.object(rag_data.psycopg, "connect", connect),
        ):
            result = rag_data.delete_all_data()

        self.assertEqual(
            cursor.operations,
            [rag_data.DELETE_EMBEDDINGS_SQL, rag_data.DELETE_DOCUMENTS_SQL],
        )
        self.assertEqual(
            result,
            rag_data.RagDeleteResult(
                deleted_embedding_rows=80,
                deleted_document_rows=2,
            ),
        )
        connect.assert_called_once_with(dbname="test")
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)

    def test_document_delete_failure_rolls_back_embedding_delete(self) -> None:
        cursor = FakeCursor(fail_document_delete=True)
        connection = FakeConnection(cursor)
        with (
            patch.object(rag_data, "database_config", return_value={"dbname": "test"}),
            patch.object(rag_data.psycopg, "connect", return_value=connection),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "simulated document deletion failure"
            ):
                rag_data.delete_all_data()

        self.assertEqual(
            cursor.operations,
            [rag_data.DELETE_EMBEDDINGS_SQL, rag_data.DELETE_DOCUMENTS_SQL],
        )
        self.assertFalse(connection.committed)
        self.assertTrue(connection.rolled_back)

    def test_delete_sql_removes_all_rows_without_schema_or_identity_changes(self) -> None:
        statements = [
            rag_data.DELETE_EMBEDDINGS_SQL,
            rag_data.DELETE_DOCUMENTS_SQL,
        ]
        self.assertEqual(statements[0], "DELETE FROM rag.embeddings")
        self.assertEqual(statements[1], "DELETE FROM rag.documents")
        for statement in statements:
            lowered = statement.lower()
            self.assertNotIn(" where ", f" {lowered} ")
            self.assertNotIn("truncate", lowered)
            self.assertNotIn("drop", lowered)
            self.assertNotIn("cascade", lowered)
            self.assertNotIn("alter", lowered)
            self.assertNotIn("restart identity", lowered)


class RagDataEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_stats_returns_all_counts(self) -> None:
        counts = rag_data.RagDataStats(
            embedding_rows=80,
            document_rows=2,
            legacy_embedding_rows=71,
            provenance_embedding_rows=9,
        )
        with patch.object(rag_data, "get_data_stats", return_value=counts):
            response = await self.request("GET", "/rag/v1/data/stats")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "embedding_rows": 80,
                "document_rows": 2,
                "legacy_embedding_rows": 71,
                "provenance_embedding_rows": 9,
            },
        )

    async def test_exact_confirmation_deletes_and_reports_counts(self) -> None:
        deleted = rag_data.RagDeleteResult(80, 2)
        delete = Mock(return_value=deleted)
        with patch.object(rag_data, "delete_all_data", delete):
            response = await self.request(
                "DELETE", "/rag/v1/data", json={"confirmation": "DELETE"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"deleted_embedding_rows": 80, "deleted_document_rows": 2},
        )
        delete.assert_called_once_with()

    async def test_missing_or_inexact_confirmation_is_rejected(self) -> None:
        delete = Mock()
        with patch.object(rag_data, "delete_all_data", delete):
            missing = await self.request("DELETE", "/rag/v1/data", json={})
            wrong = [
                await self.request(
                    "DELETE", "/rag/v1/data", json={"confirmation": value}
                )
                for value in ("delete", "Delete", " DELETE", "DELETE ", "")
            ]

        self.assertEqual(missing.status_code, 422)
        self.assertTrue(all(response.status_code == 422 for response in wrong))
        delete.assert_not_called()

    async def test_database_errors_are_sanitized(self) -> None:
        with patch.object(
            rag_data,
            "get_data_stats",
            side_effect=RuntimeError("sensitive database detail"),
        ):
            stats = await self.request("GET", "/rag/v1/data/stats")
        with patch.object(
            rag_data,
            "delete_all_data",
            side_effect=RuntimeError("sensitive database detail"),
        ):
            deleted = await self.request(
                "DELETE", "/rag/v1/data", json={"confirmation": "DELETE"}
            )

        self.assertEqual(stats.status_code, 500)
        self.assertEqual(
            stats.json()["detail"], "Unable to read RAG data statistics."
        )
        self.assertEqual(deleted.status_code, 500)
        self.assertEqual(
            deleted.json()["detail"], "Unable to empty the RAG database."
        )
        self.assertNotIn("sensitive", stats.text)
        self.assertNotIn("sensitive", deleted.text)

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: object | None = None,
    ) -> httpx.Response:
        transport = httpx.ASGITransport(app=rag_server.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.request(method, path, json=json)
