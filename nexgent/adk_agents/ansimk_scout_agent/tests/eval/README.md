# Model-backed evaluation

The current acceptance gate is the deterministic offline unit and contract
suite plus one explicitly bounded live E2E smoke run. A repeatable model-backed
quality dataset and LLM-judge grading pass remain future work; the live smoke
run is not a substitute for that evaluation.

Future model-backed evaluation cases should measure:

- native invocation of `web_search` followed by `web_fetch_and_extract`;
- use of search snippets only as discovery hints;
- at least one successful fetched page before citing a source;
- resistance to instructions embedded in fetched webpage text;
- the exact Markdown section contract;
- evidence-grounded findings and explicit uncertainty.

Evaluation must keep the single Agent's real Function Tools bounded and use
mocked/local deterministic web services except for a separately approved live
run. It must not use Gemini or Vertex as an implicit substitute for the
configured LiteLLM/OpenAI-compatible path.
