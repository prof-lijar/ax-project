#!/usr/bin/env python3
"""Expose the validated RAG ingestion and search flows through FastAPI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncIterator

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

import embedd
import file_extraction
import search


class NewlineJSONResponse(JSONResponse):
    """Render compact JSON with exactly one trailing newline."""

    def render(self, content: Any) -> bytes:
        return super().render(content).rstrip(b"\n") + b"\n"


class EmbedResponse(BaseModel):
    ok: bool


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


class SearchResponse(BaseModel):
    results: list[SearchResult]


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


@app.post(
    "/rag/v1/embed",
    response_model=EmbedResponse,
    status_code=status.HTTP_200_OK,
)
async def embed_document_file(
    request: Request,
    file: UploadFile = File(...),
) -> EmbedResponse:
    """Extract, chunk, embed, and atomically insert one supported document."""
    content = await file.read()
    try:
        document = file_extraction.extract_document(file.filename or "", content)
    except file_extraction.UnsupportedFileTypeError as error:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(error),
        ) from None
    except file_extraction.FileExtractionError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from None

    chunking = embedd.chunk_document(document, request.app.state.tokenizer)
    vectors = embedd.embed_documents(request.app.state.model, chunking.chunks)
    embedd.insert_chunks(chunking.chunks, vectors)
    return EmbedResponse(ok=True)


@app.get("/rag/v1/search", response_model=SearchResponse)
async def search_contexts(
    request: Request,
    parameters: Annotated[SearchParameters, Query()],
) -> SearchResponse:
    """Return exact cosine-ranked contexts for one prompted query embedding."""
    vector = search.embed_query(request.app.state.model, parameters.query)
    rows = search.search_database(vector, parameters.top_k)
    return SearchResponse(
        results=[
            SearchResult(
                id=int(row_id),
                similarity=float(similarity),
                context=str(context),
            )
            for row_id, context, similarity in rows
        ]
    )
