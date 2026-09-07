BEGIN;

CREATE TABLE IF NOT EXISTS rag.documents (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_type text NOT NULL,
    source_name text NOT NULL,
    CONSTRAINT rag_documents_source_type_check
        CHECK (source_type IN ('file', 'text'))
);

ALTER TABLE rag.embeddings
    ADD COLUMN IF NOT EXISTS document_id bigint,
    ADD COLUMN IF NOT EXISTS chunk_index integer,
    ADD COLUMN IF NOT EXISTS source_start_character integer,
    ADD COLUMN IF NOT EXISTS source_end_character integer,
    ADD COLUMN IF NOT EXISTS token_count integer;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'rag.embeddings'::regclass
          AND conname = 'rag_embeddings_document_id_fkey'
    ) THEN
        ALTER TABLE rag.embeddings
            ADD CONSTRAINT rag_embeddings_document_id_fkey
            FOREIGN KEY (document_id) REFERENCES rag.documents(id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'rag.embeddings'::regclass
          AND conname = 'rag_embeddings_chunk_index_check'
    ) THEN
        ALTER TABLE rag.embeddings
            ADD CONSTRAINT rag_embeddings_chunk_index_check
            CHECK (chunk_index IS NULL OR chunk_index >= 1);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'rag.embeddings'::regclass
          AND conname = 'rag_embeddings_source_start_check'
    ) THEN
        ALTER TABLE rag.embeddings
            ADD CONSTRAINT rag_embeddings_source_start_check
            CHECK (
                source_start_character IS NULL
                OR source_start_character >= 0
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'rag.embeddings'::regclass
          AND conname = 'rag_embeddings_source_span_check'
    ) THEN
        ALTER TABLE rag.embeddings
            ADD CONSTRAINT rag_embeddings_source_span_check
            CHECK (
                source_start_character IS NULL
                OR source_end_character IS NULL
                OR source_end_character >= source_start_character
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'rag.embeddings'::regclass
          AND conname = 'rag_embeddings_token_count_check'
    ) THEN
        ALTER TABLE rag.embeddings
            ADD CONSTRAINT rag_embeddings_token_count_check
            CHECK (token_count IS NULL OR token_count > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'rag.embeddings'::regclass
          AND conname = 'rag_embeddings_provenance_completeness_check'
    ) THEN
        ALTER TABLE rag.embeddings
            ADD CONSTRAINT rag_embeddings_provenance_completeness_check
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
            );
    END IF;
END
$migration$;

CREATE UNIQUE INDEX IF NOT EXISTS rag_embeddings_document_chunk_unique
    ON rag.embeddings (document_id, chunk_index)
    WHERE document_id IS NOT NULL;

COMMIT;
