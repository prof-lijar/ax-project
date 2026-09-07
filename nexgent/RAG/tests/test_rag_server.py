from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch


os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import httpx  # noqa: E402

import embedd  # noqa: E402
import file_extraction  # noqa: E402
import pdf_ocr  # noqa: E402
import rag_server  # noqa: E402
import search  # noqa: E402
from tests.test_file_extraction import build_docx, build_text_pdf  # noqa: E402


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
    async def test_cors_allows_only_the_nexgent_frontend_origin(self) -> None:
        transport = httpx.ASGITransport(app=rag_server.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            allowed = await client.options(
                "/rag/v1/embed",
                headers={
                    "Origin": rag_server.FRONTEND_ORIGIN,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            denied = await client.options(
                "/rag/v1/search",
                headers={
                    "Origin": "http://untrusted.example",
                    "Access-Control-Request-Method": "GET",
                },
            )
            delete_allowed = await client.options(
                "/rag/v1/data",
                headers={
                    "Origin": rag_server.FRONTEND_ORIGIN,
                    "Access-Control-Request-Method": "DELETE",
                    "Access-Control-Request-Headers": "content-type",
                },
            )

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(
            allowed.headers.get("access-control-allow-origin"),
            rag_server.FRONTEND_ORIGIN,
        )
        self.assertIn("POST", allowed.headers["access-control-allow-methods"])
        self.assertEqual(delete_allowed.status_code, 200)
        self.assertIn(
            "DELETE", delete_allowed.headers["access-control-allow-methods"]
        )
        self.assertNotIn("access-control-allow-origin", denied.headers)

    async def test_valid_requests_reuse_lifespan_objects_and_preserve_prompts(
        self,
    ) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()
        load_tokenizer = Mock(return_value=tokenizer)
        load_model = Mock(return_value=model)
        insert = Mock(
            side_effect=[
                embedd.PersistedDocument(10, [30]),
                embedd.PersistedDocument(11, [31]),
            ]
        )
        search_database = Mock(
            side_effect=[
                [
                    (
                        1,
                        "서울 관련 문맥",
                        0.75,
                        10,
                        "file",
                        "seoul.md",
                        1,
                        0,
                        8,
                        8,
                    )
                ],
                [
                    (2, "한라산 관련 문맥", 0.625, None, None, None, None, None, None, None),
                    (3, "다른 문맥", 0.5, 11, "text", "Direct text: 제주", 2, 40, 50, 10),
                ],
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
        first_embed_payload = first_embed.json()
        self.assertTrue(first_embed_payload["ok"])
        self.assertEqual(first_embed_payload["source"]["document_id"], 10)
        self.assertEqual(first_embed_payload["source"]["source_type"], "file")
        self.assertEqual(first_embed_payload["source"]["source_name"], "first.txt")
        self.assertEqual(first_embed_payload["source"]["filename"], "first.txt")
        self.assertEqual(
            first_embed_payload["source"]["size_bytes"],
            len("첫 번째 문서".encode()),
        )
        self.assertEqual(first_embed_payload["source"]["character_count"], 7)
        self.assertEqual(first_embed_payload["source"]["token_count"], 7)
        self.assertEqual(first_embed_payload["chunking"]["max_chunk_tokens"], 500)
        self.assertEqual(first_embed_payload["chunking"]["chunk_count"], 1)
        self.assertEqual(first_embed_payload["chunking"]["chunk_token_counts"], [7])
        self.assertFalse(first_embed_payload["chunking"]["preview_truncated"])
        self.assertEqual(
            first_embed_payload["chunking"]["chunks"],
            [
                {
                    "index": 1,
                    "token_count": 7,
                    "character_count": 7,
                    "source_start_character": 0,
                    "source_end_character": 7,
                    "overlap_with_previous_tokens": 0,
                    "context": "첫 번째 문서",
                }
            ],
        )
        self.assert_timing_fields(
            first_embed_payload["timing_ms"],
            {"chunking", "embedding", "total"},
        )
        self.assertEqual(second_embed.status_code, 200)
        self.assertTrue(second_embed.json()["ok"])
        for response in (
            first_embed,
            second_embed,
            default_search,
            override_search,
        ):
            self.assertTrue(response.content.endswith(b"\n"))
            self.assertFalse(response.content.endswith(b"\n\n"))
        default_payload = default_search.json()
        self.assertEqual(
            default_payload["results"],
            [
                {
                    "id": 1,
                    "similarity": 0.75,
                    "context": "서울 관련 문맥",
                    "document_id": 10,
                    "source_type": "file",
                    "source_name": "seoul.md",
                    "chunk_index": 1,
                    "source_start_character": 0,
                    "source_end_character": 8,
                    "token_count": 8,
                }
            ],
        )
        self.assert_timing_fields(
            default_payload["timing_ms"],
            {"query_embedding", "database_search", "total"},
        )
        override_payload = override_search.json()
        self.assertEqual(
            override_payload["results"],
            [
                {
                    "id": 2,
                    "similarity": 0.625,
                    "context": "한라산 관련 문맥",
                    "document_id": None,
                    "source_type": None,
                    "source_name": None,
                    "chunk_index": None,
                    "source_start_character": None,
                    "source_end_character": None,
                    "token_count": None,
                },
                {
                    "id": 3,
                    "similarity": 0.5,
                    "context": "다른 문맥",
                    "document_id": 11,
                    "source_type": "text",
                    "source_name": "Direct text: 제주",
                    "chunk_index": 2,
                    "source_start_character": 40,
                    "source_end_character": 50,
                    "token_count": 10,
                },
            ],
        )
        self.assert_timing_fields(
            override_payload["timing_ms"],
            {"query_embedding", "database_search", "total"},
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

    async def test_embed_custom_maximum_is_request_local_and_previews_ten_chunks(
        self,
    ) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()
        insert = Mock(
            side_effect=lambda source, chunking, vectors: embedd.PersistedDocument(
                20,
                list(range(1, len(chunking.chunks) + 1)),
            )
        )
        document = "가" * 3000

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
                    custom = await client.post(
                        "/rag/v1/embed",
                        data={"max_chunk_tokens": "100"},
                        files={
                            "file": (
                                "nested\\long.txt",
                                document.encode("utf-8"),
                                "text/plain",
                            )
                        },
                    )
                    default = await client.post(
                        "/rag/v1/embed",
                        files={"file": ("default.txt", document, "text/plain")},
                    )
                    maximum = await client.post(
                        "/rag/v1/embed",
                        data={"max_chunk_tokens": "1000"},
                        files={"file": ("maximum.txt", document, "text/plain")},
                    )

        self.assertEqual(custom.status_code, 200)
        custom_payload = custom.json()
        self.assertEqual(custom_payload["source"]["filename"], "long.txt")
        self.assertEqual(custom_payload["source"]["size_bytes"], len(document.encode()))
        self.assertEqual(custom_payload["source"]["character_count"], len(document))
        self.assertEqual(custom_payload["source"]["token_count"], len(document))
        self.assertEqual(custom_payload["chunking"]["max_chunk_tokens"], 100)
        self.assertGreater(custom_payload["chunking"]["chunk_count"], 10)
        self.assertTrue(custom_payload["chunking"]["preview_truncated"])
        self.assertEqual(len(custom_payload["chunking"]["chunks"]), 10)
        self.assertTrue(
            all(
                count <= 100
                for count in custom_payload["chunking"]["chunk_token_counts"]
            )
        )
        for offset, chunk in enumerate(custom_payload["chunking"]["chunks"]):
            self.assertEqual(chunk["index"], offset + 1)
            self.assertEqual(
                chunk["character_count"],
                chunk["source_end_character"] - chunk["source_start_character"],
            )
            self.assertEqual(chunk["token_count"], len(chunk["context"]))
            self.assertEqual(
                chunk["overlap_with_previous_tokens"],
                0 if offset == 0 else embedd.TARGET_OVERLAP_TOKENS,
            )

        self.assertEqual(default.status_code, 200)
        self.assertEqual(default.json()["chunking"]["max_chunk_tokens"], 500)
        self.assertEqual(maximum.status_code, 200)
        self.assertEqual(maximum.json()["chunking"]["max_chunk_tokens"], 1000)
        self.assertTrue(
            all(
                count <= 1000
                for count in maximum.json()["chunking"]["chunk_token_counts"]
            )
        )
        self.assertEqual(embedd.MAX_CHUNK_TOKENS, 500)
        self.assertEqual(insert.call_count, 3)
        for call in insert.call_args_list:
            source, chunking, vectors = call.args
            self.assertEqual(source.source_type, "file")
            self.assertEqual(len(chunking.chunks), len(vectors))

    async def test_embed_rejects_invalid_chunk_limits_before_insertion(self) -> None:
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
                    below = await client.post(
                        "/rag/v1/embed",
                        data={"max_chunk_tokens": "99"},
                        files={"file": ("document.txt", "문서", "text/plain")},
                    )
                    above = await client.post(
                        "/rag/v1/embed",
                        data={"max_chunk_tokens": "1001"},
                        files={"file": ("document.txt", "문서", "text/plain")},
                    )

        self.assertEqual(below.status_code, 422)
        self.assertEqual(above.status_code, 422)
        self.assertIn("greater than or equal to 100", below.text)
        self.assertIn("less than or equal to 1000", above.text)
        insert.assert_not_called()
        self.assertEqual(model.encode_calls, [])

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
        insert = Mock(return_value=embedd.PersistedDocument(22, [32]))

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
        self.assertTrue(response.json()["ok"])
        self.assertTrue(response.content.endswith(b"\n"))
        self.assertFalse(response.content.endswith(b"\n\n"))
        self.assertIn(extracted_document, tokenizer.encoded_texts)
        insert.assert_called_once()
        source, chunking, inserted_vectors = insert.call_args.args
        self.assertEqual(source, embedd.SourceDocument("file", "document.pdf", extracted_document))
        self.assertEqual(chunking.chunks, [extracted_document])
        self.assertEqual(len(inserted_vectors), 1)
        self.assertEqual(len(inserted_vectors[0]), embedd.EMBEDDING_DIMENSION)
        document_call = model.encode_calls[0]
        self.assertNotIn("prompt_name", document_call[1])
        self.assertIs(document_call[1]["normalize_embeddings"], True)

    async def test_ocr_pdf_enters_same_file_provenance_ingestion_pipeline(
        self,
    ) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()
        ocr_text = "스캔된 한국어 PDF 문서입니다. OCR provenance test."
        pdf_content = build_text_pdf([[]])
        ocr_session = Mock()
        ocr_session.extract_page_text.return_value = ocr_text
        insert = Mock(return_value=embedd.PersistedDocument(27, [73]))

        with (
            patch.object(embedd, "load_tokenizer", return_value=tokenizer),
            patch.object(embedd, "load_model", return_value=model),
            patch.object(embedd, "insert_chunks", insert),
            patch.object(
                file_extraction.pdf_ocr,
                "PdfOcrSession",
                return_value=ocr_session,
            ),
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
                                "client\\path\\scan.pdf",
                                pdf_content,
                                "application/pdf",
                            )
                        },
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"]["source_type"], "file")
        self.assertEqual(response.json()["source"]["source_name"], "scan.pdf")
        self.assertEqual(response.json()["source"]["filename"], "scan.pdf")
        ocr_session.extract_page_text.assert_called_once_with(0)
        insert.assert_called_once()
        source, chunking, vectors = insert.call_args.args
        self.assertEqual(source, embedd.SourceDocument("file", "scan.pdf", ocr_text))
        self.assertEqual(chunking.chunks, [ocr_text])
        self.assertEqual(len(vectors), 1)
        self.assertNotIn("prompt_name", model.encode_calls[0][1])
        self.assertIs(model.encode_calls[0][1]["normalize_embeddings"], True)

    async def test_ocr_errors_are_sanitized_and_do_not_insert(self) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()
        insert = Mock()
        cases = [
            (
                pdf_ocr.OcrEngineUnavailableError(
                    "PDF OCR is unavailable because the OCR engine is not installed"
                ),
                503,
                "OCR engine is not installed",
            ),
            (
                pdf_ocr.OcrLanguageUnavailableError(
                    "PDF OCR requires Korean and English OCR language data"
                ),
                503,
                "Korean and English",
            ),
            (
                pdf_ocr.OcrTimeoutError(
                    "PDF OCR exceeded the 30-second page timeout"
                ),
                504,
                "30-second page timeout",
            ),
            (
                pdf_ocr.OcrRenderError("A PDF page could not be prepared for OCR"),
                422,
                "prepared for OCR",
            ),
        ]

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
                    responses = []
                    for error, expected_status, expected_detail in cases:
                        with patch.object(
                            file_extraction,
                            "extract_document",
                            side_effect=error,
                        ):
                            response = await client.post(
                                "/rag/v1/embed",
                                files={"file": ("scan.pdf", b"pdf", "application/pdf")},
                            )
                        responses.append(
                            (response, expected_status, expected_detail)
                        )

        for response, expected_status, expected_detail in responses:
            self.assertEqual(response.status_code, expected_status)
            self.assertIn(expected_detail, response.json()["detail"])
            self.assertNotIn("/private", response.text)
        insert.assert_not_called()
        self.assertEqual(model.encode_calls, [])

    async def test_markdown_enters_existing_ingestion_pipeline_unchanged(self) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()
        markdown = (
            "# 한국어 제목\n\n"
            "첫 번째 문단입니다.\n\n"
            "- 목록 하나\n"
            "- 목록 둘"
        )
        insert = Mock(return_value=embedd.PersistedDocument(23, [33]))

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
        self.assertTrue(response.json()["ok"])
        self.assertTrue(response.content.endswith(b"\n"))
        self.assertFalse(response.content.endswith(b"\n\n"))
        self.assertIn(markdown, tokenizer.encoded_texts)
        insert.assert_called_once()
        source, chunking, inserted_vectors = insert.call_args.args
        self.assertEqual(source, embedd.SourceDocument("file", "document.md", markdown))
        self.assertEqual(chunking.chunks, [markdown])
        self.assertEqual(len(inserted_vectors), 1)
        self.assertEqual(len(inserted_vectors[0]), embedd.EMBEDDING_DIMENSION)
        document_call = model.encode_calls[0]
        self.assertNotIn("prompt_name", document_call[1])
        self.assertIs(document_call[1]["normalize_embeddings"], True)

    async def test_docx_enters_existing_file_provenance_ingestion_pipeline(
        self,
    ) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()

        def configure(document) -> None:
            document.add_heading("DOCX 제목", level=1)
            table = document.add_table(rows=2, cols=2)
            table.cell(0, 0).text = "Name"
            table.cell(0, 1).text = "Value"
            table.cell(1, 0).text = "온도"
            table.cell(1, 1).text = "24"
            document.add_paragraph("마지막 문단")

        content = build_docx(configure)
        extracted = "DOCX 제목\n\nName\tValue\n온도\t24\n\n마지막 문단"
        insert = Mock(return_value=embedd.PersistedDocument(28, [74]))

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
                                "client\\path\\project.DOCX",
                                content,
                                "application/vnd.openxmlformats-officedocument."
                                "wordprocessingml.document",
                            )
                        },
                    )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"]["source_type"], "file")
        self.assertEqual(payload["source"]["source_name"], "project.DOCX")
        self.assertEqual(payload["source"]["filename"], "project.DOCX")
        insert.assert_called_once()
        source, chunking, vectors = insert.call_args.args
        self.assertEqual(
            source,
            embedd.SourceDocument("file", "project.DOCX", extracted),
        )
        self.assertEqual(chunking.source_text, extracted)
        self.assertEqual(len(chunking.chunks), len(vectors))
        self.assertNotIn("prompt_name", model.encode_calls[0][1])
        self.assertIs(model.encode_calls[0][1]["normalize_embeddings"], True)

    async def test_docx_errors_are_sanitized_before_model_or_database_work(
        self,
    ) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()
        insert = Mock()
        empty_docx = build_docx()

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
                    malformed = await client.post(
                        "/rag/v1/embed",
                        files={
                            "file": (
                                "broken.docx",
                                b"not a DOCX",
                                "application/zip",
                            )
                        },
                    )
                    empty = await client.post(
                        "/rag/v1/embed",
                        files={"file": ("empty.docx", empty_docx, "application/zip")},
                    )
                    legacy = await client.post(
                        "/rag/v1/embed",
                        files={"file": ("legacy.doc", b"legacy", "application/msword")},
                    )
                    with patch.object(file_extraction, "MAX_DOCX_UPLOAD_BYTES", 4):
                        excessive = await client.post(
                            "/rag/v1/embed",
                            files={"file": ("large.docx", b"12345", "application/zip")},
                        )

        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(
            malformed.json()["detail"], "Uploaded DOCX could not be read"
        )
        self.assertEqual(empty.status_code, 400)
        self.assertIn("no extractable text", empty.json()["detail"])
        self.assertNotIn("word/document.xml", empty.text)
        self.assertEqual(legacy.status_code, 415)
        self.assertIn("legacy .doc is not supported", legacy.json()["detail"])
        self.assertEqual(excessive.status_code, 413)
        self.assertEqual(
            excessive.json()["detail"],
            "Uploaded DOCX exceeds supported processing limits",
        )
        insert.assert_not_called()
        self.assertEqual(model.encode_calls, [])

    async def test_direct_text_uses_shared_pipeline_title_and_fallback(self) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()
        insert = Mock(
            side_effect=[
                embedd.PersistedDocument(24, [34]),
                embedd.PersistedDocument(25, [35]),
            ]
        )
        first_text = "  첫 줄은 그대로 유지됩니다.\n\n둘째 문단입니다.  "
        second_text = "자동 제목 원본\n\n추가 내용"

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
                    titled = await client.post(
                        "/rag/v1/embed/text",
                        json={
                            "text": first_text,
                            "title": "  직접 입력 제목  ",
                            "max_chunk_tokens": 100,
                        },
                    )
                    fallback = await client.post(
                        "/rag/v1/embed/text",
                        json={"text": second_text},
                    )

        self.assertEqual(titled.status_code, 200)
        titled_source = titled.json()["source"]
        self.assertEqual(
            titled_source,
            {
                "document_id": 24,
                "source_type": "text",
                "source_name": "직접 입력 제목",
                "filename": None,
                "size_bytes": len(first_text.encode("utf-8")),
                "character_count": len(first_text.strip()),
                "token_count": len(first_text.strip()),
            },
        )
        self.assertEqual(titled.json()["chunking"]["max_chunk_tokens"], 100)
        self.assertEqual(fallback.status_code, 200)
        self.assertEqual(
            fallback.json()["source"]["source_name"],
            "Direct text: 자동 제목 원본",
        )
        self.assertIsNone(fallback.json()["source"]["filename"])
        self.assertEqual(insert.call_count, 2)
        self.assertTrue(
            all(call.args[0].source_type == "text" for call in insert.call_args_list)
        )
        self.assertTrue(
            all("prompt_name" not in kwargs for _, kwargs in model.encode_calls)
        )

    async def test_direct_text_rejects_empty_before_embedding_or_database(self) -> None:
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
                        "/rag/v1/embed/text",
                        json={"text": ""},
                    )
                    whitespace = await client.post(
                        "/rag/v1/embed/text",
                        json={"text": " \n\t "},
                    )

        self.assertEqual(empty.status_code, 422)
        self.assertEqual(whitespace.status_code, 422)
        insert.assert_not_called()
        self.assertEqual(model.encode_calls, [])

    async def test_long_direct_text_respects_request_local_chunk_limit(self) -> None:
        tokenizer = FakeTokenizer()
        model = FakeModel()
        insert = Mock(
            side_effect=lambda source, chunking, vectors: embedd.PersistedDocument(
                26,
                list(range(40, 40 + len(chunking.chunks))),
            )
        )
        document = "긴 한국어 직접 입력 문서입니다. " * 30

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
                        "/rag/v1/embed/text",
                        json={"text": document, "max_chunk_tokens": 100},
                    )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreater(payload["chunking"]["chunk_count"], 1)
        self.assertTrue(
            all(count <= 100 for count in payload["chunking"]["chunk_token_counts"])
        )
        source, chunking, vectors = insert.call_args.args
        self.assertEqual(source.source_type, "text")
        self.assertEqual(len(chunking.chunks), len(vectors))

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
                                "document.doc",
                                b"text",
                                "application/msword",
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
                            "Uploaded PDF contains no extractable or "
                            "OCR-recognizable text"
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
        self.assertIn("OCR-recognizable", no_text_pdf.json()["detail"])
        insert.assert_not_called()
        self.assertEqual(model.encode_calls, [])

    def assert_timing_fields(
        self,
        timing: dict[str, object],
        expected_fields: set[str],
    ) -> None:
        self.assertEqual(set(timing), expected_fields)
        for value in timing.values():
            self.assertIsInstance(value, float)
            self.assertGreaterEqual(value, 0)


if __name__ == "__main__":
    unittest.main()
