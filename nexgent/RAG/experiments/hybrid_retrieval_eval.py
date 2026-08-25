#!/usr/bin/env python3
"""Run a read-only vector/lexical/RRF experiment on the fixed RAG benchmark."""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK_PATH = BASE_DIR / "docs" / "rag-retrieval-evaluation.md"
DEFAULT_OUTPUT_PATH = Path("/tmp/rag-hybrid-retrieval-20260824.json")
VECTOR_CANDIDATES = 20
LEXICAL_CANDIDATES = 20
RRF_K = 60

# These legacy rows were manually validated against the fixed expected answers
# and evidence. Empty sets represent questions whose complete answer is split
# across chunks, so no single current source chunk is sufficient.
SUFFICIENT_EVIDENCE_ROW_IDS: dict[str, frozenset[int]] = {
    "MD-Q01": frozenset({33}),
    "MD-Q02": frozenset({39}),
    "MD-Q03": frozenset({48}),
    "MD-Q04": frozenset({38}),
    "MD-Q05": frozenset(),
    "MD-Q06": frozenset({37}),
    "MD-Q07": frozenset({43}),
    "MD-Q08": frozenset({45}),
    "MD-Q09": frozenset({43}),
    "MD-Q10": frozenset({46}),
    "PDF-Q01": frozenset({54}),
    "PDF-Q02": frozenset({54}),
    "PDF-Q03": frozenset({55}),
    "PDF-Q04": frozenset({56}),
    "PDF-Q05": frozenset({58}),
    "PDF-Q06": frozenset({54}),
    "PDF-Q07": frozenset({55}),
    "PDF-Q08": frozenset({57}),
    "PDF-Q09": frozenset({58}),
    "PDF-Q10": frozenset(),
}

LEXICAL_CORPUS_SQL = """
SELECT
    embeddings.id,
    embeddings.context,
    embeddings.document_id,
    documents.source_type,
    documents.source_name,
    embeddings.chunk_index,
    embeddings.source_start_character,
    embeddings.source_end_character,
    embeddings.token_count
FROM rag.embeddings AS embeddings
LEFT JOIN rag.documents AS documents
    ON documents.id = embeddings.document_id
ORDER BY embeddings.id;
"""

PROHIBITED_SQL = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|TRUNCATE|MERGE|COPY|CALL)\b",
    re.IGNORECASE,
)
TOKEN_RE = re.compile(
    r"\d+(?:[.,]\d+)*(?:[가-힣]+)?"
    r"|[A-Za-z][A-Za-z0-9_.+\-/=]*"
    r"|[가-힣]+"
)
ASCII_RE = re.compile(r"[a-z]")
DIGIT_RE = re.compile(r"\d")


@dataclass(frozen=True)
class BenchmarkQuestion:
    """One immutable benchmark definition parsed from the canonical document."""

    question_id: str
    source_set: str
    category: str
    query: str
    expected_answer: str
    evidence: str


@dataclass(frozen=True)
class CorpusRow:
    """One searchable embedding row without its stored vector payload."""

    row_id: int
    context: str
    document_id: int | None
    source_type: str | None
    source_name: str | None
    chunk_index: int | None
    source_start_character: int | None
    source_end_character: int | None
    token_count: int | None


@dataclass(frozen=True)
class LexicalCandidate:
    """One row ranked by the experimental lexical token/substring score."""

    row: CorpusRow
    score: float
    matched_tokens: tuple[str, ...]
    query_token_count: int
    full_query_substring: bool


def assert_read_only_sql(sql: str) -> None:
    """Reject any experimental SQL containing a mutating operation."""
    statement = sql.strip()
    if not statement.upper().startswith(("SELECT", "WITH")):
        raise ValueError("Experimental SQL must begin with SELECT or WITH")
    match = PROHIBITED_SQL.search(statement)
    if match:
        raise ValueError(f"Mutating SQL keyword is forbidden: {match.group(0)}")


def load_benchmark(path: Path = DEFAULT_BENCHMARK_PATH) -> list[BenchmarkQuestion]:
    """Load only the first fixed definition tables, never historical results."""
    questions: list[BenchmarkQuestion] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Category breakdown"):
            break
        if not (line.startswith("| MD-Q") or line.startswith("| PDF-Q")):
            continue
        cells = [cell.strip() for cell in line.split("|")]
        questions.append(
            BenchmarkQuestion(
                question_id=cells[1],
                source_set=cells[2],
                category=cells[3],
                query=cells[4],
                expected_answer=cells[5],
                evidence=cells[6],
            )
        )

    expected_ids = [f"MD-Q{index:02d}" for index in range(1, 11)] + [
        f"PDF-Q{index:02d}" for index in range(1, 11)
    ]
    if [question.question_id for question in questions] != expected_ids:
        raise ValueError("Expected the canonical ordered 20-question benchmark")
    return questions


def normalize_text(value: str) -> str:
    """Normalize Unicode/case/whitespace without linguistic stemming."""
    normalized = unicodedata.normalize("NFC", value).casefold()
    return " ".join(normalized.split())


def lexical_tokens(value: str) -> tuple[str, ...]:
    """Return stable unique Korean, numeric, and technical identifier tokens."""
    seen: set[str] = set()
    tokens: list[str] = []
    for match in TOKEN_RE.finditer(normalize_text(value)):
        token = match.group(0).strip("._+-/=")
        if not token or (len(token) == 1 and not DIGIT_RE.search(token)):
            continue
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tuple(tokens)


def token_multiplier(token: str) -> float:
    """Give exact numeric and ASCII technical terms extra lexical weight."""
    if DIGIT_RE.search(token):
        return 2.5
    if ASCII_RE.search(token) or any(char in token for char in "._+-/="):
        return 1.75
    return 1.0


def corpus_document_frequencies(
    rows: Iterable[CorpusRow], query_tokens: Iterable[str]
) -> dict[str, int]:
    """Count chunks containing each query token as an exact substring."""
    tokens = tuple(query_tokens)
    frequencies = {token: 0 for token in tokens}
    for row in rows:
        context = normalize_text(row.context)
        for token in tokens:
            if token in context:
                frequencies[token] += 1
    return frequencies


def lexical_rank(
    query: str,
    rows: list[CorpusRow],
    limit: int = LEXICAL_CANDIDATES,
) -> list[LexicalCandidate]:
    """Rank chunks using experimental IDF-weighted token/substring coverage."""
    normalized_query = normalize_text(query)
    tokens = lexical_tokens(query)
    frequencies = corpus_document_frequencies(rows, tokens)
    active_tokens = tuple(token for token in tokens if frequencies[token] > 0)
    weights = {
        token: (math.log((len(rows) + 1) / (frequencies[token] + 1)) + 1.0)
        * token_multiplier(token)
        for token in active_tokens
    }
    total_weight = sum(weights.values())

    candidates: list[LexicalCandidate] = []
    for row in rows:
        context = normalize_text(row.context)
        matched = tuple(token for token in active_tokens if token in context)
        if not matched:
            continue
        matched_weight = sum(weights[token] for token in matched)
        coverage = matched_weight / total_weight if total_weight else 0.0
        full_query_substring = bool(normalized_query and normalized_query in context)
        full_query_bonus = total_weight if full_query_substring else 0.0
        score = matched_weight + coverage + full_query_bonus
        candidates.append(
            LexicalCandidate(
                row=row,
                score=score,
                matched_tokens=matched,
                query_token_count=len(active_tokens),
                full_query_substring=full_query_substring,
            )
        )

    candidates.sort(
        key=lambda candidate: (
            -candidate.score,
            -len(candidate.matched_tokens),
            candidate.row.row_id,
        )
    )
    return candidates[:limit]


def reciprocal_rank_fusion(
    vector_row_ids: list[int],
    lexical_row_ids: list[int],
    *,
    k: int = RRF_K,
) -> list[tuple[int, float, int | None, int | None]]:
    """Fuse ranks without mixing cosine and lexical score scales."""
    vector_ranks = {row_id: rank for rank, row_id in enumerate(vector_row_ids, 1)}
    lexical_ranks = {
        row_id: rank for rank, row_id in enumerate(lexical_row_ids, 1)
    }
    fused: list[tuple[int, float, int | None, int | None]] = []
    for row_id in vector_ranks.keys() | lexical_ranks.keys():
        vector_rank = vector_ranks.get(row_id)
        lexical_rank_value = lexical_ranks.get(row_id)
        score = 0.0
        if vector_rank is not None:
            score += 1.0 / (k + vector_rank)
        if lexical_rank_value is not None:
            score += 1.0 / (k + lexical_rank_value)
        fused.append((row_id, score, vector_rank, lexical_rank_value))
    fused.sort(
        key=lambda item: (
            -item[1],
            min(rank for rank in item[2:] if rank is not None),
            item[2] if item[2] is not None else math.inf,
            item[3] if item[3] is not None else math.inf,
            item[0],
        )
    )
    return fused


def first_sufficient_rank(
    question_id: str, candidates: list[dict], *, top_k: int = 5
) -> int | None:
    """Return the first manually validated sufficient row within Top-K."""
    sufficient_rows = SUFFICIENT_EVIDENCE_ROW_IDS[question_id]
    for rank, candidate in enumerate(candidates[:top_k], 1):
        if candidate["row_id"] in sufficient_rows:
            return rank
    return None


def rank_metrics(ranks: Iterable[int | None]) -> dict[str, int | float]:
    """Calculate Top-K and MRR, treating absent sufficient evidence as zero."""
    values = list(ranks)
    if not values:
        raise ValueError("At least one rank is required")
    top_1 = sum(rank == 1 for rank in values)
    top_3 = sum(rank is not None and rank <= 3 for rank in values)
    top_5 = sum(rank is not None and rank <= 5 for rank in values)
    mrr = sum(0.0 if rank is None else 1.0 / rank for rank in values) / len(values)
    return {
        "questions": len(values),
        "top_1": top_1,
        "top_3": top_3,
        "top_5": top_5,
        "mrr": round(mrr, 4),
    }


def score_experiment(result: dict) -> dict:
    """Score all methods and categories from already retrieved candidate lists."""
    methods = ("vector", "lexical", "hybrid")
    per_question = []
    for run in result["runs"]:
        question = run["question"]
        ranks = {
            method: first_sufficient_rank(question["question_id"], run[method])
            for method in methods
        }
        per_question.append(
            {
                "question_id": question["question_id"],
                "category": question["category"],
                "ranks": ranks,
            }
        )

    overall = {
        method: rank_metrics(row["ranks"][method] for row in per_question)
        for method in methods
    }
    categories = sorted({row["category"] for row in per_question})
    by_category = {
        category: {
            method: rank_metrics(
                row["ranks"][method]
                for row in per_question
                if row["category"] == category
            )
            for method in methods
        }
        for category in categories
    }
    return {
        "scoring_rule": "first single sufficient-evidence chunk within Top-5",
        "per_question": per_question,
        "overall": overall,
        "by_category": by_category,
    }


def fetch_corpus(search_module: Any) -> list[CorpusRow]:
    """Read every current chunk in an explicitly read-only transaction."""
    assert_read_only_sql(LEXICAL_CORPUS_SQL)
    with search_module.psycopg.connect(**search_module.database_config()) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute(LEXICAL_CORPUS_SQL)
            return [CorpusRow(*row) for row in cursor.fetchall()]


def vector_candidates(search_module: Any, model: Any, query: str) -> list[dict]:
    """Use the unchanged production embedding and exact-cosine retrieval."""
    assert_read_only_sql(search_module.SEARCH_SQL)
    vector = search_module.embed_query(model, query)
    rows = search_module.search_database(vector, VECTOR_CANDIDATES)
    candidates = []
    for rank, row in enumerate(rows, 1):
        (
            row_id,
            context,
            similarity,
            document_id,
            source_type,
            source_name,
            chunk_index,
            source_start_character,
            source_end_character,
            token_count,
        ) = row
        candidates.append(
            {
                "rank": rank,
                "row_id": int(row_id),
                "cosine_similarity": float(similarity),
                "context": str(context),
                "document_id": None if document_id is None else int(document_id),
                "source_type": source_type,
                "source_name": source_name,
                "chunk_index": None if chunk_index is None else int(chunk_index),
                "source_start_character": (
                    None
                    if source_start_character is None
                    else int(source_start_character)
                ),
                "source_end_character": (
                    None if source_end_character is None else int(source_end_character)
                ),
                "token_count": None if token_count is None else int(token_count),
            }
        )
    return candidates


def run_experiment(output_path: Path) -> dict:
    """Execute the fixed read-only benchmark and write complete candidate data."""
    import search

    questions = load_benchmark()
    corpus = fetch_corpus(search)
    row_by_id = {row.row_id: row for row in corpus}
    model = search.load_model()
    runs = []

    for question in questions:
        vector = vector_candidates(search, model, question.query)
        lexical = lexical_rank(question.query, corpus)
        lexical_by_id = {candidate.row.row_id: candidate for candidate in lexical}
        vector_by_id = {candidate["row_id"]: candidate for candidate in vector}
        fused = reciprocal_rank_fusion(
            [candidate["row_id"] for candidate in vector],
            [candidate.row.row_id for candidate in lexical],
        )

        lexical_payload = []
        for rank, candidate in enumerate(lexical, 1):
            payload = asdict(candidate.row)
            payload.update(
                {
                    "rank": rank,
                    "lexical_score": candidate.score,
                    "matched_tokens": list(candidate.matched_tokens),
                    "query_token_count": candidate.query_token_count,
                    "full_query_substring": candidate.full_query_substring,
                }
            )
            lexical_payload.append(payload)

        hybrid_payload = []
        for rank, (row_id, rrf_score, vector_rank, lexical_rank_value) in enumerate(
            fused[:VECTOR_CANDIDATES], 1
        ):
            row = row_by_id[row_id]
            payload = asdict(row)
            payload.update(
                {
                    "rank": rank,
                    "rrf_score": rrf_score,
                    "vector_rank": vector_rank,
                    "lexical_rank": lexical_rank_value,
                    "cosine_similarity": (
                        vector_by_id[row_id]["cosine_similarity"]
                        if row_id in vector_by_id
                        else None
                    ),
                    "lexical_score": (
                        lexical_by_id[row_id].score
                        if row_id in lexical_by_id
                        else None
                    ),
                }
            )
            hybrid_payload.append(payload)

        runs.append(
            {
                "question": asdict(question),
                "vector": vector,
                "lexical": lexical_payload,
                "hybrid": hybrid_payload,
            }
        )

    result = {
        "experiment": "lexical token/substring ranking + reciprocal rank fusion",
        "production_search_unchanged": True,
        "database_read_only": True,
        "corpus_rows": len(corpus),
        "vector_candidates": VECTOR_CANDIDATES,
        "lexical_candidates": LEXICAL_CANDIDATES,
        "rrf_k": RRF_K,
        "runs": runs,
    }
    result["evaluation"] = score_experiment(result)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_experiment(args.output)
    print(
        f"Wrote {len(result['runs'])} read-only benchmark runs for "
        f"{result['corpus_rows']} rows to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
