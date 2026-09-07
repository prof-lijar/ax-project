CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS rag;

CREATE TABLE IF NOT EXISTS rag.documents (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_type text NOT NULL,
    source_name text NOT NULL,
    CONSTRAINT rag_documents_source_type_check
        CHECK (source_type IN ('file', 'text'))
);

CREATE TABLE IF NOT EXISTS rag.embeddings (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint,
    chunk_index integer,
    source_start_character integer,
    source_end_character integer,
    token_count integer,
    context text NOT NULL,
    vector vector(1024) NOT NULL,
    CONSTRAINT rag_embeddings_document_id_fkey
        FOREIGN KEY (document_id) REFERENCES rag.documents(id),
    CONSTRAINT rag_embeddings_chunk_index_check
        CHECK (chunk_index IS NULL OR chunk_index >= 1),
    CONSTRAINT rag_embeddings_source_start_check
        CHECK (source_start_character IS NULL OR source_start_character >= 0),
    CONSTRAINT rag_embeddings_source_span_check
        CHECK (
            source_start_character IS NULL
            OR source_end_character IS NULL
            OR source_end_character >= source_start_character
        ),
    CONSTRAINT rag_embeddings_token_count_check
        CHECK (token_count IS NULL OR token_count > 0),
    CONSTRAINT rag_embeddings_provenance_completeness_check
        CHECK (
            (
                document_id IS NULL
                AND chunk_index IS NULL
                AND source_start_character IS NULL
                AND source_end_character IS NULL
                AND token_count IS NULL
            )
            OR
            (
                document_id IS NOT NULL
                AND chunk_index IS NOT NULL
                AND source_start_character IS NOT NULL
                AND source_end_character IS NOT NULL
                AND token_count IS NOT NULL
            )
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS rag_embeddings_document_chunk_unique
    ON rag.embeddings (document_id, chunk_index)
    WHERE document_id IS NOT NULL;
