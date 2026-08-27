# Test Agent OpenAI-Compatible Tool Calling

Date: 2026-08-27

## Implemented

A standalone `test-agent/` Google ADK prototype was scaffolded with
`agents-cli` 1.4.1. The agent uses ADK `LiteLlm` to send OpenAI-compatible
requests to `http://192.168.0.17:8000/v1` with the served model name
`gemma-4-31b`.

The agent initially registered two Python function tools:

- `get_weather(city)`: deterministic New York weather data.
- `get_current_time(city)`: live New York time using `zoneinfo`.

Both tools return explicit error dictionaries for unsupported cities. The
agent instruction requires tool use for time and weather questions and forbids
inventing unavailable data.

## Update — 2026-08-27: keyless web search

The agent now also registers `web_search(query)`, backed by the `ddgs` 9.16.x
base package. DDGS is a lightweight public-web metasearch library and requires
no search API key. Each invocation uses moderate safe search, a ten-second
provider timeout, and a fixed maximum of five results.

The tool returns structured titles, URLs, and snippets. Empty queries, provider
errors, and empty result sets return explicit error dictionaries. Search
content is treated as untrusted data; the agent is instructed not to follow
instructions from titles or snippets and to include relevant result URLs in
its answer.

## Architecture and configuration decisions

- The API base, API key, and served model name come from `OPENAI_API_BASE`,
  `OPENAI_API_KEY`, and `TEST_AGENT_MODEL`.
- The model name is prefixed with `openai/` internally so LiteLLM uses its
  OpenAI-compatible provider path.
- The API key is absent from versioned files. `.env` is ignored by Git and its
  generated local value is blank.
- Sampling temperature is zero for reproducible tool selection; the output
  limit is 2,048 tokens.
- Cloud telemetry is opt-in through `OTEL_TO_CLOUD=true`. Local startup does
  not require Google Application Default Credentials.
- The generated HTTP/A2A integration server port can be overridden with
  `TEST_SERVER_PORT`; it remains 8000 by default.
- Evaluation uses a local deterministic metric that checks the trace for the
  expected function call arguments and successful function response. It does
  not require a Google-hosted LLM judge.

## Commands

Install dependencies and run code checks:

```bash
cd test-agent
uv sync
uv run pytest tests/unit
TEST_SERVER_PORT=18090 uv run pytest tests/integration
agents-cli lint
```

Once the server supports Gemma 4 tool parsing, inspect a live call:

```bash
cd test-agent
export OPENAI_API_KEY="your-api-key"
agents-cli run -v "What is the weather in New York? Use the available tool."
```

Inspect a live web-search call:

```bash
agents-cli run -v \
  "Search the web for the official Python documentation and give me two relevant links. You must use web_search."
```

Run the focused evaluation:

```bash
agents-cli eval run \
  --dataset tests/eval/datasets/basic-dataset.json \
  --config tests/eval/eval_config.yaml
```

## Validation performed

- `uv sync`: completed successfully with Python 3.12 and Google ADK 2.8.0.
- `uv run pytest tests/unit`: 6 tests passed. ADK emitted one upstream
  deprecation warning for `BaseAgentConfig`.
- `agents-cli lint`: Ruff checks, Ruff formatting, codespell, and ty passed.
- Direct `web_search("Python programming language official documentation")`:
  succeeded with five results, including `python.org` and `docs.python.org`.
- Live weather prompt: the model called `get_weather`, received a successful
  response, and returned the tool-grounded 25°C/77°F answer.
- Live web-search prompt: the model called `web_search` with query
  `official Python documentation`, received five results, and returned two
  relevant official Python URLs.
- Evaluation inference: 2/2 cases completed and saved full function-call and
  function-response traces to `artifacts/traces/web-search`.
- Local deterministic grading: both cases scored `1.0`; summary mean was
  `1.0`, with 2 valid cases and 0 errors.
- Direct ADK runner integration: passed.
- HTTP SSE, A2A streaming, and agent-card integration: 3/3 passed on isolated
  port 18090. The first attempt used the default port 8000 and could not bind
  because an unrelated process already occupied it; no process was stopped.

Earlier on 2026-08-27, automatic and forced tool calls were rejected because
the vLLM process lacked Gemma 4 tool parsing. That serving issue has since been
resolved; the successful weather and web-search traces above confirm the model
now emits valid tool calls.

## vLLM tool-calling configuration

The vLLM process requires Gemma 4 tool parsing. Per the
[official vLLM Gemma 4 guide](https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html),
the relevant serving arguments are:

```text
--enable-auto-tool-choice
--tool-call-parser gemma4
--reasoning-parser gemma4
--chat-template examples/tool_chat_template_gemma4.jinja
```

The repeatable verification command is:

```bash
cd test-agent
OPENAI_API_KEY="your-api-key" agents-cli run -v \
  "What is the weather in New York? Use the available tool."
```

Success requires a function call, its successful function response, and a final
natural-language answer.

## Known limitations and remaining verification

- DDGS relies on public third-party search backends. Result quality and
  availability can vary, and providers may rate-limit requests.
- The tool returns search snippets only; it does not fetch or verify full page
  contents.
- `agents-cli eval grade` 1.4.1 initializes Google credentials even for a local
  code metric in this environment. Validation used the same Agent Platform SDK
  evaluator locally with anonymous placeholder credentials; no remote judge was
  called.
