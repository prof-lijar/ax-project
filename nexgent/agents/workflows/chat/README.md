# Chat workflow

This workflow performs one LLM-backed chat-completion turn. It accepts a
non-empty `message` plus up to five optional `ChatAttachmentRef` values and
returns `response` or a safe attachment `error`. Provider configuration,
filesystem access, and HTTP behavior remain in `ax-integrations`; this module
owns only the minimal workflow state and graph topology. Attachment bytes,
extracted document text, and image data URLs never enter graph state or events;
attachment references are cleared from terminal state. Callers with attachments
must request only `custom` stream mode and use `response_complete` as the
terminal event so initial-state values cannot expose private file references.

The workflow uses asynchronous model I/O and is registered as `chat` in
`langgraph.json`. The deterministic `smoke` workflow remains available for
health checks that must not depend on model availability.

See [the attachment runtime guide](../../docs/chat-attachments.md) for the
reference schema, storage-root requirements, limits, error event shape, and
vision capability flag.
