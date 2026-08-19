#!/usr/bin/env python3
"""Minimal CUDA smoke test for Qwen3-Embedding-0.6B Korean retrieval."""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from importlib.metadata import version
from pathlib import Path

# PyTorch 2.13's optional native Triton kernels compile a helper against
# Python.h. The host intentionally has no Python development headers, so use
# standard CUDA operators for this dependency-isolated smoke test.
os.environ.setdefault("TORCH_DISABLE_NATIVE_JIT", "1")

import torch
from sentence_transformers import SentenceTransformer


MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "huggingface"
DEVICE = "cuda:0"
DTYPE = torch.bfloat16
LATENCY_REPEATS = 10

DOCUMENTS = [
    "서울은 대한민국의 수도이며 정치와 경제의 중심지입니다.",
    "제주도 한라산은 대한민국에서 가장 높은 산입니다.",
    "김치는 배추와 양념을 발효시켜 만드는 한국의 전통 음식입니다.",
    "파이썬은 데이터 분석과 인공지능 개발에 널리 사용되는 프로그래밍 언어입니다.",
    "태양광 발전은 햇빛을 전기에너지로 변환하는 재생에너지 기술입니다.",
]

QUERIES = [
    {"text": "한국의 수도는 어디인가요?", "expected_document": 0},
    {"text": "우리나라에서 가장 높은 산을 알려 주세요.", "expected_document": 1},
    {"text": "데이터 분석에 많이 쓰이는 코딩 언어는 무엇인가요?", "expected_document": 3},
]


def synchronize() -> None:
    torch.cuda.synchronize(0)


def elapsed_ms(operation) -> float:
    synchronize()
    started = time.perf_counter()
    operation()
    synchronize()
    return (time.perf_counter() - started) * 1000


def main() -> int:
    package_versions = {
        name: version(name)
        for name in ("torch", "transformers", "sentence-transformers")
    }
    cuda_available = torch.cuda.is_available()
    environment = {
        "python": sys.version.split()[0],
        "packages": package_versions,
        "torch_cuda_build": torch.version.cuda,
        "cuda_available": cuda_available,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "torch_disable_native_jit": os.environ.get("TORCH_DISABLE_NATIVE_JIT"),
    }

    if not cuda_available:
        print(json.dumps({"environment": environment}, ensure_ascii=False, indent=2))
        raise RuntimeError("CUDA is not available to PyTorch")

    environment.update(
        {
            "gpu_name": torch.cuda.get_device_name(0),
            "bf16_supported": torch.cuda.is_bf16_supported(),
            "visible_gpu_count": torch.cuda.device_count(),
        }
    )
    if not environment["bf16_supported"]:
        print(json.dumps({"environment": environment}, ensure_ascii=False, indent=2))
        raise RuntimeError("The selected GPU does not report BF16 support")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats(0)

    synchronize()
    load_started = time.perf_counter()
    model = SentenceTransformer(
        MODEL_ID,
        device=DEVICE,
        cache_folder=str(CACHE_DIR),
        model_kwargs={"torch_dtype": DTYPE},
    )
    synchronize()
    model_load_ms = (time.perf_counter() - load_started) * 1000

    encode_options = {
        "batch_size": len(DOCUMENTS),
        "convert_to_tensor": True,
        "normalize_embeddings": True,
        "show_progress_bar": False,
    }

    # Warm up kernels without applying a query prompt to documents.
    model.encode(DOCUMENTS[:1], **encode_options)
    model.encode(
        [QUERIES[0]["text"]],
        prompt_name="query",
        **encode_options,
    )
    synchronize()

    document_latency_ms = elapsed_ms(
        lambda: model.encode(DOCUMENTS, **encode_options)
    )
    document_embeddings = model.encode(DOCUMENTS, **encode_options)

    query_texts = [query["text"] for query in QUERIES]
    query_latency_ms = elapsed_ms(
        lambda: model.encode(query_texts, prompt_name="query", **encode_options)
    )
    query_embeddings = model.encode(
        query_texts,
        prompt_name="query",
        **encode_options,
    )
    synchronize()

    single_query_latencies_ms = [
        elapsed_ms(
            lambda: model.encode(
                [query_texts[0]],
                prompt_name="query",
                **encode_options,
            )
        )
        for _ in range(LATENCY_REPEATS)
    ]

    document_norms = torch.linalg.vector_norm(document_embeddings, dim=1)
    query_norms = torch.linalg.vector_norm(query_embeddings, dim=1)
    similarities = query_embeddings @ document_embeddings.T

    rankings = []
    retrieval_passed = True
    for query_index, query in enumerate(QUERIES):
        ranked_indices = torch.argsort(similarities[query_index], descending=True)
        expected = query["expected_document"]
        top_index = int(ranked_indices[0].item())
        retrieval_passed &= top_index == expected
        rankings.append(
            {
                "query": query["text"],
                "expected_document_index": expected,
                "top1_passed": top_index == expected,
                "ranking": [
                    {
                        "rank": rank + 1,
                        "document_index": int(document_index.item()),
                        "score": round(
                            float(similarities[query_index, document_index].item()), 6
                        ),
                        "document": DOCUMENTS[int(document_index.item())],
                    }
                    for rank, document_index in enumerate(ranked_indices)
                ],
            }
        )

    norm_tolerance = 0.01
    document_norm_max_error = float(torch.max(torch.abs(document_norms - 1)).item())
    query_norm_max_error = float(torch.max(torch.abs(query_norms - 1)).item())
    normalization_passed = (
        document_norm_max_error <= norm_tolerance
        and query_norm_max_error <= norm_tolerance
    )
    finite_passed = bool(
        torch.isfinite(document_embeddings).all().item()
        and torch.isfinite(query_embeddings).all().item()
    )

    result = {
        "environment": environment,
        "model": {
            "id": MODEL_ID,
            "device": DEVICE,
            "dtype": str(DTYPE),
            "cache_directory": str(CACHE_DIR),
            "load_success": True,
            "load_latency_ms": round(model_load_ms, 2),
            "embedding_dimension": int(document_embeddings.shape[1]),
            "document_prompt": None,
            "query_prompt_name": "query",
        },
        "normalization": {
            "requested": True,
            "tolerance": norm_tolerance,
            "document_norms": [round(float(value), 6) for value in document_norms],
            "query_norms": [round(float(value), 6) for value in query_norms],
            "document_max_absolute_error": round(document_norm_max_error, 8),
            "query_max_absolute_error": round(query_norm_max_error, 8),
            "passed": normalization_passed,
            "all_values_finite": finite_passed,
        },
        "retrieval": {
            "similarity": "cosine via dot product of normalized embeddings",
            "all_expected_top1_passed": retrieval_passed,
            "queries": rankings,
        },
        "latency_ms": {
            "document_batch_size": len(DOCUMENTS),
            "document_batch": round(document_latency_ms, 2),
            "query_batch_size": len(query_texts),
            "query_batch": round(query_latency_ms, 2),
            "single_query_repeats": LATENCY_REPEATS,
            "single_query_mean": round(statistics.mean(single_query_latencies_ms), 2),
            "single_query_median": round(statistics.median(single_query_latencies_ms), 2),
            "single_query_min": round(min(single_query_latencies_ms), 2),
            "single_query_max": round(max(single_query_latencies_ms), 2),
        },
        "gpu_memory_mib": {
            "peak_allocated": round(torch.cuda.max_memory_allocated(0) / 1024**2, 2),
            "peak_reserved": round(torch.cuda.max_memory_reserved(0) / 1024**2, 2),
            "current_allocated": round(torch.cuda.memory_allocated(0) / 1024**2, 2),
            "current_reserved": round(torch.cuda.memory_reserved(0) / 1024**2, 2),
        },
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if normalization_passed and finite_passed and retrieval_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
