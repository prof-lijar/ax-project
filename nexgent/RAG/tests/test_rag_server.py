from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch


os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import httpx  # noqa: E402

import embedd  # noqa: E402
import file_extraction  # noqa: E402
import rag_server  # noqa: E402
import search  # noqa: E402
from tests.test_file_extraction import build_text_pdf  # noqa: E402


class FakeTokenizer:
    is_fast = True

    def __init__(self) -> None:
        self.encoded_texts: list[str] = []

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        if add_special_tokens:
            raise AssertionError("Chunk token counts must not add special tokens")
        self.encoded_texts.append(text)
        return list(range(len(text)))

    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool = False,
        return_offsets_mapping: bool = False,
    ) -> dict[str, list[tuple[int, int]]]:
        if add_special_tokens or not return_offsets_mapping:
            raise AssertionError("Unexpected tokenizer options")
        return {"offset_mapping": [(index, index + 1) for index in range(len(text))]}


class FakeModel:
    def __init__(self) -> None:
        self.encode_calls: list[tuple[list[str], dict[str, object]]] = []

    def encode(self, texts: list[str], **kwargs: object):
        self.encode_calls.append((list(texts), dict(kwargs)))
        vectors = embedd.torch.zeros((len(texts), embedd.EMBEDDING_DIMENSION))
        vectors[:, 0] = 1.0
        return vectors


class RagServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_requests_reuse_lifespan_objects_and_preserve_prompts(
        self,
    ) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()
        load_tokenizer = Mock(return_value=tokenizer)
        load_model = Mock(return_value=model)
        insert = Mock(side_effect=[[30], [31]])
        search_database = Mock(
            side_effect=[
                [(1, "서울 관련 문맥", 0.75)],
                [(2, "한라산 관련 문맥", 0.625), (3, "다른 문맥", 0.5)],
            ]
        )

        with (
            patch.object(embedd, "load_tokenizer", load_tokenizer),
            patch.object(embedd, "load_model", load_model),
            patch.object(embedd, "insert_chunks", insert),
            patch.object(search, "search_database", search_database),
        ):
            async with rag_server.lifespan(rag_server.app):
                transport = httpx.ASGITransport(app=rag_server.app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    first_embed = await client.post(
                        "/rag/v1/embed",
                        files={
                            "file": (
                                "first.txt",
                                "첫 번째 문서".encode(),
                                "text/plain",
                            )
                        },
                    )
                    second_embed = await client.post(
                        "/rag/v1/embed",
                        files={
                            "file": (
                                "second.TXT",
                                "두 번째 문서".encode(),
                                "text/plain",
                            )
                        },
                    )
                    default_search = await client.get(
                        "/rag/v1/search",
                        params={"query": "  서울 질문  "},
                    )
                    override_search = await client.get(
                        "/rag/v1/search",
                        params={"query": "한라산 질문", "top_k": 2},
                    )

        self.assertEqual(first_embed.status_code, 200)
        self.assertEqual(first_embed.json(), {"ok": True})
        self.assertEqual(second_embed.status_code, 200)
        self.assertEqual(second_embed.json(), {"ok": True})
        for response in (
            first_embed,
            second_embed,
            default_search,
            override_search,
        ):
            self.assertTrue(response.content.endswith(b"\n"))
            self.assertFalse(response.content.endswith(b"\n\n"))
        self.assertEqual(
            default_search.json(),
            {
                "results": [
                    {"id": 1, "similarity": 0.75, "context": "서울 관련 문맥"}
                ]
            },
        )
        self.assertEqual(
            override_search.json(),
            {
                "results": [
                    {"id": 2, "similarity": 0.625, "context": "한라산 관련 문맥"},
                    {"id": 3, "similarity": 0.5, "context": "다른 문맥"},
                ]
            },
        )
        load_tokenizer.assert_called_once_with()
        load_model.assert_called_once_with()
        self.assertEqual(insert.call_count, 2)
        self.assertEqual(search_database.call_count, 2)
        self.assertEqual(search_database.call_args_list[0].args[1], 5)
        self.assertEqual(search_database.call_args_list[1].args[1], 2)

        document_calls = model.encode_calls[:2]
        query_calls = model.encode_calls[2:]
        self.assertEqual(len(document_calls), 2)
        self.assertTrue(
            all("prompt_name" not in kwargs for _, kwargs in document_calls)
        )
        self.assertEqual(len(query_calls), 2)
        self.assertTrue(
            all(kwargs.get("prompt_name") == "query" for _, kwargs in query_calls)
        )
        self.assertTrue(
            all(kwargs.get("normalize_embeddings") is True for _, kwargs in model.encode_calls)
        )
        self.assertIn("첫 번째 문서", tokenizer.encoded_texts)
        self.assertIn("두 번째 문서", tokenizer.encoded_texts)

    async def test_search_validation_rejects_blank_and_out_of_range_values(
        self,
    ) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()
        search_database = Mock()

        with (
            patch.object(embedd, "load_tokenizer", return_value=tokenizer),
            patch.object(embedd, "load_model", return_value=model),
            patch.object(search, "search_database", search_database),
        ):
            async with rag_server.lifespan(rag_server.app):
                transport = httpx.ASGITransport(app=rag_server.app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    responses = [
                        await client.get("/rag/v1/search"),
                        await client.get(
                            "/rag/v1/search", params={"query": ""}
                        ),
                        await client.get(
                            "/rag/v1/search", params={"query": "  \n"}
                        ),
                        await client.get(
                            "/rag/v1/search",
                            params={"query": "질문", "top_k": 0},
                        ),
                        await client.get(
                            "/rag/v1/search",
                            params={"query": "질문", "top_k": 21},
                        ),
                    ]
                    old_post = await client.post(
                        "/rag/v1/search",
                        json={"query": "질문", "top_k": 1},
                    )

        self.assertTrue(all(response.status_code == 422 for response in responses))
        self.assertEqual(old_post.status_code, 405)
        search_database.assert_not_called()
        self.assertEqual(model.encode_calls, [])

    async def test_pdf_extraction_enters_existing_ingestion_pipeline(self) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()
        extracted_document = "First page text\n\nSecond page text"
        pdf_content = build_text_pdf([["First page text"], ["Second page text"]])
        insert = Mock(return_value=[32])

        with (
            patch.object(embedd, "load_tokenizer", return_value=tokenizer),
            patch.object(embedd, "load_model", return_value=model),
            patch.object(embedd, "insert_chunks", insert),
        ):
            async with rag_server.lifespan(rag_server.app):
                transport = httpx.ASGITransport(app=rag_server.app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/rag/v1/embed",
                        files={
                            "file": (
                                "document.pdf",
                                pdf_content,
                                "application/pdf",
                            )
                        },
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertTrue(response.content.endswith(b"\n"))
        self.assertFalse(response.content.endswith(b"\n\n"))
        self.assertIn(extracted_document, tokenizer.encoded_texts)
        insert.assert_called_once()
        inserted_chunks, inserted_vectors = insert.call_args.args
        self.assertEqual(inserted_chunks, [extracted_document])
        self.assertEqual(len(inserted_vectors), 1)
        self.assertEqual(len(inserted_vectors[0]), embedd.EMBEDDING_DIMENSION)
        document_call = model.encode_calls[0]
        self.assertNotIn("prompt_name", document_call[1])
        self.assertIs(document_call[1]["normalize_embeddings"], True)

    async def test_markdown_enters_existing_ingestion_pipeline_unchanged(self) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()
        markdown = (
            "# 한국어 제목\n\n"
            "첫 번째 문단입니다.\n\n"
            "- 목록 하나\n"
            "- 목록 둘"
        )
        insert = Mock(return_value=[33])

        with (
            patch.object(embedd, "load_tokenizer", return_value=tokenizer),
            patch.object(embedd, "load_model", return_value=model),
            patch.object(embedd, "insert_chunks", insert),
        ):
            async with rag_server.lifespan(rag_server.app):
                transport = httpx.ASGITransport(app=rag_server.app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/rag/v1/embed",
                        files={
                            "file": (
                                "document.md",
                                markdown.encode("utf-8"),
                                "text/markdown",
                            )
                        },
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertTrue(response.content.endswith(b"\n"))
        self.assertFalse(response.content.endswith(b"\n\n"))
        self.assertIn(markdown, tokenizer.encoded_texts)
        insert.assert_called_once()
        inserted_chunks, inserted_vectors = insert.call_args.args
        self.assertEqual(inserted_chunks, [markdown])
        self.assertEqual(len(inserted_vectors), 1)
        self.assertEqual(len(inserted_vectors[0]), embedd.EMBEDDING_DIMENSION)
        document_call = model.encode_calls[0]
        self.assertNotIn("prompt_name", document_call[1])
        self.assertIs(document_call[1]["normalize_embeddings"], True)

    async def test_embed_rejects_invalid_files_without_insertion(self) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()
        insert = Mock()

        with (
            patch.object(embedd, "load_tokenizer", return_value=tokenizer),
            patch.object(embedd, "load_model", return_value=model),
            patch.object(embedd, "insert_chunks", insert),
        ):
            async with rag_server.lifespan(rag_server.app):
                transport = httpx.ASGITransport(app=rag_server.app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    empty = await client.post(
                        "/rag/v1/embed",
                        files={"file": ("empty.txt", b"", "text/plain")},
                    )
                    whitespace = await client.post(
                        "/rag/v1/embed",
                        files={"file": ("blank.txt", b" \n\t", "text/plain")},
                    )
                    unsupported = await client.post(
                        "/rag/v1/embed",
                        files={
                            "file": (
                                "document.docx",
                                b"text",
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            )
                        },
                    )
                    invalid_utf8 = await client.post(
                        "/rag/v1/embed",
                        files={"file": ("invalid.txt", b"\xff\xfe", "text/plain")},
                    )
                    with patch.object(
                        file_extraction,
                        "extract_pdf_text",
                        side_effect=file_extraction.EmptyDocumentError(
                            "Uploaded PDF contains no extractable text; "
                            "scanned/image-only PDFs are not supported"
                        ),
                    ):
                        no_text_pdf = await client.post(
                            "/rag/v1/embed",
                            files={
                                "file": (
                                    "scan.pdf",
                                    b"non-empty PDF bytes",
                                    "application/pdf",
                                )
                            },
                        )

        self.assertEqual(empty.status_code, 400)
        self.assertEqual(whitespace.status_code, 400)
        self.assertEqual(unsupported.status_code, 415)
        self.assertEqual(invalid_utf8.status_code, 400)
        self.assertEqual(no_text_pdf.status_code, 400)
        self.assertIn("scanned/image-only", no_text_pdf.json()["detail"])
        insert.assert_not_called()
        self.assertEqual(model.encode_calls, [])


if __name__ == "__main__":
    unittest.main()
