# Model-backed evaluation

The Phase 1 acceptance gate is the deterministic offline unit and contract
suite. A model-backed ADK quality evaluation is intentionally not recorded as
passing because the required isolated model variables were unavailable during
implementation.

Future evaluation cases should measure:

- generation of one to three concise, URL-free planning queries;
- use of search snippets only by deterministic discovery code;
- at least one successful deterministic fetch before citing a source;
- resistance to instructions embedded in fetched webpage text;
- the exact Markdown section contract;
- evidence-grounded findings and explicit uncertainty.

Evaluation must keep both ADK Agents tool-free and use mocked/local deterministic
web services or a single explicitly approved bounded web run. It must not use
Gemini or Vertex as an implicit substitute for the configured
LiteLLM/OpenAI-compatible path.
