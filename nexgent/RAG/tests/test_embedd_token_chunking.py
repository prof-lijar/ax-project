from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch


os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import embedd  # noqa: E402


class TokenChunkingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tokenizer = embedd.AutoTokenizer.from_pretrained(
            embedd.MODEL_ID,
            cache_dir=str(embedd.MODEL_CACHE),
            use_fast=True,
            local_files_only=True,
        )

    def text_with_at_least_tokens(self, sentence: str, minimum: int) -> str:
        sentences: list[str] = []
        while embedd.count_tokens(self.tokenizer, " ".join(sentences)) < minimum:
            sentences.append(sentence)
        return " ".join(sentences)

    def assert_lossless_result(self, result: embedd.ChunkingResult) -> None:
        if not result.chunks:
            self.assertEqual(result.source_text, "")
            self.assertEqual(result.source_token_count, 0)
            return

        self.assertEqual(result.chunk_spans[0][0], 0)
        self.assertEqual(result.chunk_spans[-1][1], len(result.source_text))
        covered_end = 0
        for index, ((start, end), chunk, tokens) in enumerate(
            zip(
                result.chunk_spans,
                result.chunks,
                result.chunk_token_counts,
                strict=True,
            )
        ):
            self.assertLess(start, end)
            self.assertLessEqual(start, covered_end)
            self.assertGreater(end, covered_end)
            self.assertEqual(chunk, result.source_text[start:end])
            self.assertTrue(chunk.strip())
            self.assertEqual(tokens, embedd.count_tokens(self.tokenizer, chunk))
            self.assertLessEqual(tokens, embedd.MAX_CHUNK_TOKENS)
            if index:
                previous_end = result.chunk_spans[index - 1][1]
                overlap = result.source_text[start:previous_end]
                self.assertTrue(result.chunks[index - 1].endswith(overlap))
                self.assertTrue(chunk.startswith(overlap))
                overlap_tokens = embedd.count_tokens(self.tokenizer, overlap)
                self.assertEqual(
                    overlap_tokens, result.overlap_token_counts[index - 1]
                )
                self.assertGreaterEqual(overlap_tokens, embedd.MIN_OVERLAP_TOKENS)
                self.assertLessEqual(overlap_tokens, embedd.MAX_OVERLAP_TOKENS)
                self.assertLess(overlap_tokens, result.chunk_token_counts[index - 1])
            covered_end = end
        self.assertEqual(covered_end, len(result.source_text))
        self.assertEqual(len(result.overlap_token_counts), len(result.chunks) - 1)

    def test_empty_input_produces_no_chunks(self) -> None:
        result = embedd.chunk_document("\n \t", self.tokenizer)

        self.assert_lossless_result(result)

    def test_short_document_remains_one_chunk(self) -> None:
        document = "짧은 한국어 문서는 하나의 청크로 유지됩니다."

        result = embedd.chunk_document(document, self.tokenizer)

        self.assertEqual(result.chunks, [document])
        self.assertEqual(result.overlap_token_counts, [])
        self.assert_lossless_result(result)

    def test_long_korean_document_has_bounded_chunks_and_overlap(self) -> None:
        paragraphs = [
            self.text_with_at_least_tokens(
                f"{number}번째 문단은 한국어 검색 문맥과 "
                "세부 정보를 설명합니다.",
                360,
            )
            for number in range(1, 5)
        ]
        document = "\n\n".join(paragraphs)

        result = embedd.chunk_document(document, self.tokenizer)

        self.assertGreater(len(result.chunks), 2)
        for tokens in result.chunk_token_counts[:-1]:
            self.assertGreaterEqual(tokens, embedd.MIN_CHUNK_TOKENS)
        self.assert_lossless_result(result)

    def test_paragraph_boundary_has_highest_priority(self) -> None:
        first = self.text_with_at_least_tokens(
            "첫 문단은 자연스러운 문단 경계를 검증합니다.", 340
        )
        second = self.text_with_at_least_tokens(
            "둘째 문단은 전체 문서를 충분히 길게 만듭니다.", 650
        )
        document = f"{first}\n\n{second}"

        result = embedd.chunk_document(document, self.tokenizer)

        self.assertEqual(result.chunk_spans[0][1], len(first))
        self.assert_lossless_result(result)

    def test_sentence_boundary_precedes_arbitrary_split(self) -> None:
        document = self.text_with_at_least_tokens(
            "한국어 문장 경계를 우선하여 청크를 나눕니다.", 950
        )

        result = embedd.chunk_document(document, self.tokenizer)

        self.assertGreater(len(result.chunks), 1)
        self.assertTrue(result.chunks[0].endswith("."))
        self.assert_lossless_result(result)

    def test_token_level_hard_split_without_natural_boundaries(self) -> None:
        document = "가나다라마바사아자차카타파하" * 300

        result = embedd.chunk_document(document, self.tokenizer)

        self.assertGreater(len(result.chunks), 1)
        self.assertEqual(result.chunk_token_counts[0], embedd.MAX_CHUNK_TOKENS)
        self.assert_lossless_result(result)

    def test_every_chunk_adds_new_source_content(self) -> None:
        document = self.text_with_at_least_tokens(
            "반복 실행에서도 무한 루프 없이 새로운 내용을 포함합니다.", 1800
        )

        result = embedd.chunk_document(document, self.tokenizer)

        ends = [end for _, end in result.chunk_spans]
        self.assertEqual(ends, sorted(set(ends)))
        self.assert_lossless_result(result)

    def test_interactive_documents_reuse_tokenizer_and_model(self) -> None:
        fake_model = object()
        load_tokenizer = Mock(return_value=self.tokenizer)
        load_model = Mock(return_value=fake_model)
        embed = Mock(side_effect=[[[0.1] * 1024], [[0.2] * 1024]])
        insert = Mock(side_effect=[[30], [31]])

        with (
            patch.object(
                embedd,
                "read_document",
                side_effect=[
                    ("첫 번째 문서입니다.", False),
                    ("두 번째 문서입니다.", True),
                ],
            ),
            patch.object(embedd, "load_tokenizer", load_tokenizer),
            patch.object(embedd, "load_model", load_model),
            patch.object(embedd, "embed_documents", embed),
            patch.object(embedd, "insert_chunks", insert),
            redirect_stdout(io.StringIO()),
        ):
            result = embedd.run_interactive_mode()

        self.assertEqual(result, 0)
        self.assertEqual(load_tokenizer.call_count, 1)
        self.assertEqual(load_model.call_count, 1)
        self.assertEqual(embed.call_count, 2)
        self.assertTrue(
            all(call.args[0] is fake_model for call in embed.call_args_list)
        )
        self.assertEqual(insert.call_count, 2)


if __name__ == "__main__":
    unittest.main()
