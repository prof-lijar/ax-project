#!/usr/bin/env python3
"""Expose the validated RAG ingestion and search flows through FastAPI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import PurePosixPath
import time
from typing import Annotated, Any, AsyncIterator, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

import embedd
import file_extraction
import pdf_ocr
import rag_data
import search


FRONTEND_ORIGIN = "http://192.168.0.18:5173"
CHUNK_PREVIEW_LIMIT = 10


class NewlineJSONResponse(JSONResponse):
    """Render compact JSON with exactly one trailing newline."""

    def render(self, content: Any) -> bytes:
        return super().render(content).rstrip(b"\n") + b"\n"


class EmbedSourceMetrics(BaseModel):
    document_id: int
    source_type: Literal["file", "text"]
    source_name: str
    filename: str | None
    size_bytes: int
    character_count: int
    token_count: int


class EmbedChunkPreview(BaseModel):
    index: int
    token_count: int
    character_count: int
    source_start_character: int
    source_end_character: int
    overlap_with_previous_tokens: int
    context: str


class EmbedChunkingMetrics(BaseModel):
    max_chunk_tokens: int
    chunk_count: int
    chunk_token_counts: list[int]
    preview_truncated: bool
    chunks: list[EmbedChunkPreview]


class EmbedTiming(BaseModel):
    chunking: float
    embedding: float
    total: float


class EmbedResponse(BaseModel):
    ok: bool
    source: EmbedSourceMetrics
    chunking: EmbedChunkingMetrics
    timing_ms: EmbedTiming


class DirectTextRequest(BaseModel):
    text: str
    title: str | None = None
    max_chunk_tokens: int = Field(
        default=embedd.MAX_CHUNK_TOKENS,
        ge=embedd.MIN_CONFIGURABLE_MAX_CHUNK_TOKENS,
        le=embedd.MAX_CONFIGURABLE_MAX_CHUNK_TOKENS,
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must be a non-empty string")
        return value

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = value.strip()
        return title or None


class SearchParameters(BaseModel):
    query: str
    top_k: int = Field(default=search.DEFAULT_TOP_K, ge=1, le=search.MAX_TOP_K)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query must be a non-empty string")
        return query


class SearchResult(BaseModel):
    id: int
    similarity: float
    context: str
    document_id: int | None
    source_type: Literal["file", "text"] | None
    source_name: str | None
    chunk_index: int | None
    source_start_character: int | None
    source_end_character: int | None
    token_count: int | None


class SearchTiming(BaseModel):
    query_embedding: float
    database_search: float
    total: float


class SearchResponse(BaseModel):
    results: list[SearchResult]
    timing_ms: SearchTiming


class RagDataStatsResponse(BaseModel):
    embedding_rows: int
    document_rows: int
    legacy_embedding_rows: int
    provenance_embedding_rows: int


class DeleteRagDataRequest(BaseModel):
    confirmation: Literal["DELETE"]


class DeleteRagDataResponse(BaseModel):
    deleted_embedding_rows: int
    deleted_document_rows: int


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own one tokenizer and embedding model for this server process."""
    app.state.tokenizer = embedd.load_tokenizer()
    app.state.model = embedd.load_model()
    try:
        yield
    finally:
        del app.state.tokenizer
        del app.state.model


app = FastAPI(
    title="Nexgent RAG Server",
    version="1",
    lifespan=lifespan,
    default_response_class=NewlineJSONResponse,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=False,
    allow_methods=["DELETE", "GET", "POST"],
    allow_headers=["Accept", "Content-Type"],
)


@app.post(
    "/rag/v1/embed",
    response_model=EmbedResponse,
    status_code=status.HTTP_200_OK,
)
async def embed_document_file(
    request: Request,
    file: UploadFile = File(...),
    max_chunk_tokens: int = Form(
        default=embedd.MAX_CHUNK_TOKENS,
        ge=embedd.MIN_CONFIGURABLE_MAX_CHUNK_TOKENS,
        le=embedd.MAX_CONFIGURABLE_MAX_CHUNK_TOKENS,
    ),
) -> EmbedResponse:
    """Extract, chunk, embed, and atomically insert one supported document."""
    total_started = time.perf_counter()
    try:
        content = await _read_uploaded_file(file)
        document = file_extraction.extract_document(file.filename or "", content)
    except (
        pdf_ocr.OcrEngineUnavailableError,
        pdf_ocr.OcrLanguageUnavailableError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from None
    except pdf_ocr.OcrTimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(error),
        ) from None
    except pdf_ocr.PdfOcrError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from None
    except file_extraction.UnsupportedFileTypeError as error:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(error),
        ) from None
    except file_extraction.DocxResourceLimitError as error:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(error),
        ) from None
    except file_extraction.FileExtractionError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from None

    filename = _safe_basename(file.filename or "")
    source = embedd.SourceDocument(
        source_type="file",
        source_name=filename,
        text=document,
    )
    return _ingest_source(
        request,
        source,
        filename=filename,
        size_bytes=len(content),
        max_chunk_tokens=max_chunk_tokens,
        total_started=total_started,
    )


@app.post(
    "/rag/v1/embed/text",
    response_model=EmbedResponse,
    status_code=status.HTTP_200_OK,
)
async def embed_document_text(
    request: Request,
    payload: DirectTextRequest,
) -> EmbedResponse:
    """Chunk, embed, and atomically insert one directly submitted text source."""
    total_started = time.perf_counter()
    source = embedd.SourceDocument(
        source_type="text",
        source_name=(
            payload.title
            if payload.title is not None
            else embedd.generated_text_source_name(payload.text)
        ),
        text=payload.text,
    )
    return _ingest_source(
        request,
        source,
        filename=None,
        size_bytes=len(payload.text.encode("utf-8")),
        max_chunk_tokens=payload.max_chunk_tokens,
        total_started=total_started,
    )


def _ingest_source(
    request: Request,
    source: embedd.SourceDocument,
    *,
    filename: str | None,
    size_bytes: int,
    max_chunk_tokens: int,
    total_started: float,
) -> EmbedResponse:
    """Run the one shared file/text ingestion path and build observability."""
    _, _, ingestion = embedd.ingest_document(
        source,
        request.app.state.tokenizer,
        request.app.state.model,
        max_chunk_tokens=max_chunk_tokens,
    )
    chunking = ingestion.chunking

    preview_chunks = []
    for chunk_offset, (context, token_count, span) in enumerate(
        zip(
            chunking.chunks[:CHUNK_PREVIEW_LIMIT],
            chunking.chunk_token_counts[:CHUNK_PREVIEW_LIMIT],
            chunking.chunk_spans[:CHUNK_PREVIEW_LIMIT],
            strict=True,
        )
    ):
        preview_chunks.append(
            EmbedChunkPreview(
                index=chunk_offset + 1,
                token_count=token_count,
                character_count=len(context),
                source_start_character=span[0],
                source_end_character=span[1],
                overlap_with_previous_tokens=(
                    0
                    if chunk_offset == 0
                    else chunking.overlap_token_counts[chunk_offset - 1]
                ),
                context=context,
            )
        )

    return EmbedResponse(
        ok=True,
        source=EmbedSourceMetrics(
            document_id=ingestion.persisted.document_id,
            source_type=ingestion.source.source_type,
            source_name=ingestion.source.source_name,
            filename=filename,
            size_bytes=size_bytes,
            character_count=len(chunking.source_text),
            token_count=chunking.source_token_count,
        ),
        chunking=EmbedChunkingMetrics(
            max_chunk_tokens=max_chunk_tokens,
            chunk_count=len(chunking.chunks),
            chunk_token_counts=chunking.chunk_token_counts,
            preview_truncated=len(chunking.chunks) > CHUNK_PREVIEW_LIMIT,
            chunks=preview_chunks,
        ),
        timing_ms=EmbedTiming(
            chunking=round(ingestion.chunking_ms, 3),
            embedding=round(ingestion.embedding_ms, 3),
            total=_elapsed_ms(total_started),
        ),
    )


@app.get("/rag/v1/search", response_model=SearchResponse)
async def search_contexts(
    request: Request,
    parameters: Annotated[SearchParameters, Query()],
) -> SearchResponse:
    """Return exact cosine-ranked contexts for one prompted query embedding."""
    total_started = time.perf_counter()
    embedding_started = time.perf_counter()
    vector = search.embed_query(request.app.state.model, parameters.query)
    query_embedding_ms = _elapsed_ms(embedding_started)

    database_started = time.perf_counter()
    rows = search.search_database(vector, parameters.top_k)
    database_search_ms = _elapsed_ms(database_started)
    return SearchResponse(
        results=[
            SearchResult(
                id=int(row_id),
                similarity=float(similarity),
                context=str(context),
                document_id=(None if document_id is None else int(document_id)),
                source_type=source_type,
                source_name=source_name,
                chunk_index=(None if chunk_index is None else int(chunk_index)),
                source_start_character=(
                    None if source_start is None else int(source_start)
                ),
                source_end_character=(None if source_end is None else int(source_end)),
                token_count=(None if token_count is None else int(token_count)),
            )
            for (
                row_id,
                context,
                similarity,
                document_id,
                source_type,
                source_name,
                chunk_index,
                source_start,
                source_end,
                token_count,
            ) in rows
        ],
        timing_ms=SearchTiming(
            query_embedding=query_embedding_ms,
            database_search=database_search_ms,
            total=_elapsed_ms(total_started),
        ),
    )


@app.get("/rag/v1/data/stats", response_model=RagDataStatsResponse)
async def rag_data_stats() -> RagDataStatsResponse:
    """Return row counts for the RAG-owned document and embedding tables."""
    try:
        counts = rag_data.get_data_stats()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to read RAG data statistics.",
        ) from error
    return RagDataStatsResponse(**counts.__dict__)


@app.delete("/rag/v1/data", response_model=DeleteRagDataResponse)
async def delete_rag_data(
    payload: DeleteRagDataRequest,
) -> DeleteRagDataResponse:
    """Delete every RAG document and embedding after exact confirmation."""
    try:
        deleted = rag_data.delete_all_data()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to empty the RAG database.",
        ) from error
    return DeleteRagDataResponse(**deleted.__dict__)


def _elapsed_ms(started: float) -> float:
    """Return compact monotonic elapsed milliseconds for API observability."""
    return round((time.perf_counter() - started) * 1000, 3)


async def _read_uploaded_file(file: UploadFile) -> bytes:
    """Bound only DOCX upload reads; preserve established handling for other files."""
    filename = file.filename or ""
    extension = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    if extension != ".docx":
        return await file.read()

    content = await file.read(file_extraction.MAX_DOCX_UPLOAD_BYTES + 1)
    if len(content) > file_extraction.MAX_DOCX_UPLOAD_BYTES:
        raise file_extraction.DocxResourceLimitError(
            "Uploaded DOCX exceeds supported processing limits"
        )
    return content


def _safe_basename(filename: str) -> str:
    """Normalize an untrusted client filename to a display-only basename."""
    return PurePosixPath(filename.replace("\\", "/")).name.strip()
