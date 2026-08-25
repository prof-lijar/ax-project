# RAG Documentation

This directory contains the current implementation and operational references
for the RAG service. Dated retrieval measurements remain in the evaluation
document; Git history carries superseded implementation detail.

## Document map

- [RAG server](rag-server.md) — Canonical API, extraction, schema, provenance,
  data-administration, configuration, systemd operation, and service limits.
- [RAG vector search](rag-vector-search.md) — Chunking, embedding, persistence,
  exact cosine retrieval, and search-quality research status.
- [RAG UI integration](rag-ui-integration.md) — `/rag` workspace behavior,
  direct browser routing, database controls, and Chat-page RAG Agent UX.
- [RAG retrieval evaluation](rag-retrieval-evaluation.md) — Immutable 20-question
  definition, vector baselines, and experimental lexical/RRF evidence.
- [RAG Chat Agent](../../agents/docs/rag-chat-agent.md) — Dedicated grounded-chat
  endpoint, graph, prompt, sources, streaming, and Phase 1 limits.
