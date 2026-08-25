# RAG Chat workflow

`rag_chat` is a one-turn grounded-answer workflow. It sends the original user
question unchanged to the configured RAG server's existing read-only
`GET /rag/v1/search` endpoint with `top_k=5`. Empty results return a fixed
insufficient-context message without calling the generation model.

When evidence exists, the workflow places the original question and ordered
retrieved chunks in one user message beneath a dedicated system instruction.
Retrieved text is explicitly untrusted evidence and never becomes a system
message. The workflow streams the existing OpenAI-compatible chat adapter's
answer and appends a deterministic, Markdown-escaped source list from RAG
provenance.

The workflow does not ingest data, modify retrieval, retain conversation
history, accept attachments, enable Hybrid search, or add source links.
