from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch


os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import embedd  # noqa: E402


class FileIngestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tokenizer = embedd.AutoTokenizer.from_pretrained(
            embedd.MODEL_ID,
            cache_dir=str(embedd.MODEL_CACHE),
            use_fast=True,
            local_files_only=True,
        )

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_text(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_reads_one_utf8_korean_multiline_file_exactly(self) -> None:
        content = "문서 제목\n\n첫 문단입니다.\n둘째 줄입니다.\n"
        path = self.write_text("korean.txt", content)

        sources = embedd.read_source_files([str(path)])

        self.assertEqual(sources, [(path, content)])

    def test_one_file_uses_existing_document_pipeline(self) -> None:
        content = "문서 제목\n\n첫 문단입니다.\n둘째 줄입니다.\n"
        path = self.write_text("one.txt", content)
        fake_model = object()

        with (
            patch.object(
                embedd, "load_tokenizer", return_value=self.tokenizer
            ) as load_tokenizer,
            patch.object(embedd, "load_model", return_value=fake_model) as load,
            patch.object(
                embedd, "embed_documents", return_value=[[0.1] * 1024]
            ) as embed,
            patch.object(
                embedd,
                "insert_chunks",
                return_value=embedd.PersistedDocument(10, [20]),
            ) as insert,
            redirect_stdout(io.StringIO()),
        ):
            result = embedd.main([str(path)])

        self.assertEqual(result, 0)
        load_tokenizer.assert_called_once_with()
        load.assert_called_once_with()
        embed.assert_called_once_with(
            fake_model, ["문서 제목\n\n첫 문단입니다.\n둘째 줄입니다."]
        )
        insert.assert_called_once()
        source, chunking, vectors = insert.call_args.args
        self.assertEqual(source.source_type, "file")
        self.assertEqual(source.source_name, "one.txt")
        self.assertEqual(chunking.chunks, [content.strip()])
        self.assertEqual(len(vectors), 1)

    def test_reads_multiple_files_in_argument_order(self) -> None:
        first = self.write_text("first.txt", "첫 번째 문서")
        second = self.write_text("second.txt", "두 번째 문서")

        sources = embedd.read_source_files([str(first), str(second)])

        self.assertEqual([path for path, _ in sources], [first, second])
        self.assertEqual(
            [content for _, content in sources], ["첫 번째 문서", "두 번째 문서"]
        )

    def test_empty_file_is_skipped_without_model_or_database_work(self) -> None:
        empty = self.write_text("empty.txt", "\n\n")

        with (
            patch.object(
                embedd,
                "load_tokenizer",
                side_effect=AssertionError("tokenizer called"),
            ),
            patch.object(embedd, "load_model", side_effect=AssertionError("model called")),
            patch.object(embedd, "insert_chunks", side_effect=AssertionError("database called")),
            redirect_stdout(io.StringIO()) as output,
        ):
            result = embedd.main([str(empty)])

        self.assertEqual(result, 0)
        self.assertIn("Skipping empty source file", output.getvalue())
        self.assertIn("0 non-empty document(s) processed", output.getvalue())

    def test_nonexistent_file_fails_before_any_ingestion(self) -> None:
        valid = self.write_text("valid.txt", "먼저 처리되면 안 되는 문서")
        missing = self.root / "missing.txt"

        with (
            patch.object(
                embedd,
                "load_tokenizer",
                side_effect=AssertionError("tokenizer called"),
            ),
            patch.object(embedd, "load_model", side_effect=AssertionError("model called")),
            patch.object(embedd, "insert_chunks", side_effect=AssertionError("database called")),
            redirect_stderr(io.StringIO()) as errors,
        ):
            result = embedd.main([str(valid), str(missing)])

        self.assertEqual(result, 1)
        self.assertIn("Source file does not exist", errors.getvalue())

    def test_directory_is_rejected(self) -> None:
        with redirect_stderr(io.StringIO()) as errors:
            result = embedd.main([str(self.root)])

        self.assertEqual(result, 1)
        self.assertIn("Source path is not a regular file", errors.getvalue())

    def test_invalid_utf8_is_rejected(self) -> None:
        path = self.root / "invalid.txt"
        path.write_bytes(b"\xff\xfe\x00")

        with redirect_stderr(io.StringIO()) as errors:
            result = embedd.main([str(path)])

        self.assertEqual(result, 1)
        self.assertIn("Source file is not valid UTF-8", errors.getvalue())

    def test_unreadable_file_reports_sanitized_error(self) -> None:
        path = self.write_text("unreadable.txt", "내용")

        with (
            patch.object(Path, "read_text", side_effect=OSError("private detail")),
            redirect_stderr(io.StringIO()) as errors,
        ):
            result = embedd.main([str(path)])

        self.assertEqual(result, 1)
        self.assertIn("Source file could not be read", errors.getvalue())
        self.assertNotIn("private detail", errors.getvalue())

    def test_multiple_files_reuse_one_mocked_model(self) -> None:
        first = self.write_text("first.txt", "서울의 생태 관찰 문서입니다.")
        second = self.write_text("second.txt", "제주의 생태 관찰 문서입니다.")
        fake_model = object()
        load_tokenizer = Mock(return_value=self.tokenizer)
        load = Mock(return_value=fake_model)
        embed = Mock(side_effect=[[[0.1] * 1024], [[0.2] * 1024]])
        insert = Mock(
            side_effect=[
                embedd.PersistedDocument(10, [20]),
                embedd.PersistedDocument(11, [21]),
            ]
        )

        with (
            patch.object(embedd, "load_tokenizer", load_tokenizer),
            patch.object(embedd, "load_model", load),
            patch.object(embedd, "embed_documents", embed),
            patch.object(embedd, "insert_chunks", insert),
            redirect_stdout(io.StringIO()),
        ):
            result = embedd.main([str(first), str(second)])

        self.assertEqual(result, 0)
        self.assertEqual(load_tokenizer.call_count, 1)
        self.assertEqual(load.call_count, 1)
        self.assertEqual(embed.call_count, 2)
        self.assertTrue(all(call.args[0] is fake_model for call in embed.call_args_list))
        self.assertEqual(insert.call_count, 2)
        self.assertEqual(
            [call.args[0].source_name for call in insert.call_args_list],
            ["first.txt", "second.txt"],
        )


if __name__ == "__main__":
    unittest.main()
