from __future__ import annotations

import unittest

from experiments import hybrid_retrieval_eval as experiment


def row(row_id: int, context: str) -> experiment.CorpusRow:
    return experiment.CorpusRow(
        row_id=row_id,
        context=context,
        document_id=None,
        source_type=None,
        source_name=None,
        chunk_index=None,
        source_start_character=None,
        source_end_character=None,
        token_count=None,
    )


class HybridRetrievalExperimentTests(unittest.TestCase):
    def test_loads_exact_ordered_twenty_question_definition(self) -> None:
        questions = experiment.load_benchmark()

        self.assertEqual(len(questions), 20)
        self.assertEqual(questions[0].question_id, "MD-Q01")
        self.assertEqual(questions[-1].question_id, "PDF-Q10")
        self.assertEqual(
            questions[14].query,
            "2024년 광명시 AI·IoT 어르신 건강관리사업 참여자 수는 몇 명으로 보고됐나요?",
        )

    def test_tokenizer_preserves_korean_numbers_and_technical_identifiers(self) -> None:
        tokens = experiment.lexical_tokens(
            "광명시 2024년 920명 PostgreSQL archive.analysis_wardevaluation"
        )

        self.assertIn("광명시", tokens)
        self.assertIn("2024년", tokens)
        self.assertIn("920명", tokens)
        self.assertIn("postgresql", tokens)
        self.assertIn("archive.analysis_wardevaluation", tokens)

    def test_lexical_ranking_rewards_exact_numeric_and_entity_evidence(self) -> None:
        rows = [
            row(1, "광명시 건강관리사업은 어르신에게 기기를 제공합니다."),
            row(2, "2024년 광명시 사업 참여자는 정확히 920명이다."),
            row(3, "2025년 다른 사업 참여자는 1,198명이다."),
        ]

        ranked = experiment.lexical_rank(
            "2024년 광명시 사업 참여자는 몇 명인가요?", rows
        )

        self.assertEqual(ranked[0].row.row_id, 2)
        self.assertIn("2024년", ranked[0].matched_tokens)
        self.assertIn("광명시", ranked[0].matched_tokens)

    def test_rrf_uses_rank_only_and_supports_missing_candidates(self) -> None:
        fused = experiment.reciprocal_rank_fusion([1, 2, 3], [2, 4, 1], k=60)
        by_id = {item[0]: item for item in fused}

        self.assertAlmostEqual(by_id[1][1], 1 / 61 + 1 / 63)
        self.assertAlmostEqual(by_id[2][1], 1 / 62 + 1 / 61)
        self.assertEqual(by_id[3][3], None)
        self.assertEqual(by_id[4][2], None)
        self.assertEqual(fused[0][0], 2)

    def test_experimental_sql_is_select_only(self) -> None:
        experiment.assert_read_only_sql(experiment.LEXICAL_CORPUS_SQL)
        with self.assertRaisesRegex(ValueError, "forbidden"):
            experiment.assert_read_only_sql(
                "WITH removed AS (DELETE FROM rag.embeddings RETURNING id) "
                "SELECT id FROM removed"
            )

    def test_scoring_uses_first_sufficient_top_five_row_and_miss_zero(self) -> None:
        candidates = [{"row_id": row_id} for row_id in (50, 53, 48, 33, 37)]

        self.assertEqual(
            experiment.first_sufficient_rank("MD-Q03", candidates), 3
        )
        self.assertIsNone(
            experiment.first_sufficient_rank(
                "MD-Q03", [{"row_id": row_id} for row_id in (50, 53, 33, 37, 49)]
            )
        )
        self.assertIsNone(experiment.first_sufficient_rank("MD-Q05", candidates))
        self.assertEqual(
            experiment.rank_metrics([1, 2, 5, None]),
            {"questions": 4, "top_1": 1, "top_3": 2, "top_5": 3, "mrr": 0.425},
        )


if __name__ == "__main__":
    unittest.main()
