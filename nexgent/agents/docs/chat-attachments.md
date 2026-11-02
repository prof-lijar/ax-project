# Chat attachments

Date: 2026-08-14

The one-turn `chat` graph accepts optional gateway-normalized document and image
artifacts. The gateway owns upload validation, document extraction, image
normalization, transient storage, and cleanup. Agent Server receives only
strict references and the graph reads them just before the provider request.

## Input contract

Each `ChatAttachmentRef` has this JSON shape:

```json
{
  "schema_version": "1",
  "attachment_id": "upload_123",
  "filename": "notes.pdf",
  "kind": "document",
  "media_type": "text/plain",
  "uri": "file:///run/ax-chat/upload_123/normalized.txt",
  "byte_size": 2048,
  "sha256": "<64 lowercase hexadecimal characters>"
}
```

Document media types are `text/plain`, `text/markdown`, and `text/csv`; the
stored bytes must already be normalized UTF-8 extracted text. Image media types
are `image/png`, `image/jpeg`, and `image/webp`; the stored bytes must already
be validated and normalized. A request may contain five files, 50 MiB per file,
50 MiB combined, and 100,000 document characters.

`uri` must be an absolute local `file://` URI reachable beneath the Agent
Server's absolute `AX_CHAT_ARTIFACT_ROOT`. The product backend and Agent Server
must mount the same private transient volume at paths that make those URIs
identical in both processes.

## Secure read and provider request

The reader rejects root symlinks, traversal, paths outside the root, symlinked
path components, non-regular files, missing files, size changes, declared-size
mismatches, and SHA-256 mismatches. It opens each component relative to the
trusted root with `O_NOFOLLOW`; file I/O runs off the async event loop.

For attachments, the model request contains a system instruction that labels
all attachment content untrusted. The user prompt is the first text part.
Documents become separately delimited text parts identified by attachment ID,
checksum, and their untrusted original filename. Each image is preceded by its
untrusted original filename and becomes a base64 data-backed `image_url` part only for a
model configured with `OPENAI_SUPPORTS_VISION=true`; vision is disabled by
default. The provider adapter rejects remote image URLs and malformed content
parts independently of the graph.

## Stream and state behavior

Attachment runs request only LangGraph `custom` stream mode so the runtime
cannot emit its initial state, which contains private artifact references.
Success emits the existing `response_delta` events followed by
`{"response_complete":"..."}`; the graph still returns `response` internally.
Safe attachment failures emit and return:

```json
{
  "error": {
    "schema_version": "1",
    "code": "vision_not_supported",
    "message": "Image attachments are not supported by the configured model.",
    "filename": "photo.png"
  }
}
```

Stable codes are `attachment_invalid`, `attachment_not_found`,
`attachment_too_large`, `attachment_integrity_error`, `attachment_unreadable`,
and `vision_not_supported`. Errors contain no filesystem path or file content.
Graph input retains reference metadata only while the node is active, then
clears the references from terminal state. The FastAPI proxy must use only
`custom` mode whenever attachments are present; text-only requests retain the
existing `custom` plus `values` contract. Raw bytes, extracted document text,
file URIs, and image data URLs are transient local values and never stream to
the client.

## Validation

Run from `agents/`:

```bash
uv run ruff check apps workflows packages tests
uv run pytest -q
uv run langgraph validate
```

Deterministic tests cover strict contracts, path containment, traversal and
symlink rejection, size and checksum integrity, document delimiting,
vision-disabled errors, multimodal provider payload shape, unchanged text-only
behavior, and absence of binary content from graph state/events. A deployment
must additionally complete a live image request before enabling vision.
