# test-agent

A minimal Google ADK agent that uses `gemma-4-31b` through an
OpenAI-compatible vLLM endpoint. It exposes deterministic weather and current
time tools for New York plus a keyless public web-search tool, so function
calling is easy to observe.

Web search uses the lightweight [`ddgs`](https://pypi.org/project/ddgs/)
metasearch library. It requires no search API key and returns at most five
titles, URLs, and snippets per call.

## Configure

Install dependencies:

```bash
uv sync
```

Set the API key in the ignored `.env` file or export it in your shell:

```bash
export OPENAI_API_KEY="your-api-key"
```

The non-secret defaults are:

```dotenv
OPENAI_API_BASE=http://192.168.0.17:8000/v1
TEST_AGENT_MODEL=gemma-4-31b
```

## Enable tool calling in vLLM

The vLLM server must support Gemma 4's tool-call protocol. Add these arguments
to the existing server command:

```text
--enable-auto-tool-choice
--tool-call-parser gemma4
--reasoning-parser gemma4
--chat-template examples/tool_chat_template_gemma4.jinja
```

For example, adapt the model path and existing serving options as needed:

```bash
vllm serve google/gemma-4-31B-it \
  --served-model-name gemma-4-31b \
  --enable-auto-tool-choice \
  --tool-call-parser gemma4 \
  --reasoning-parser gemma4 \
  --chat-template examples/tool_chat_template_gemma4.jinja
```

These flags require a vLLM release that includes the `gemma4` tool and
reasoning parsers.

## Verify tool calls

Run a single prompt with full event output:

```bash
agents-cli run -v "What is the weather in New York? Use the available tool."
```

A successful trace contains a `functionCall` for `get_weather`, followed by a
`functionResponse` whose status is `success`, and then the agent's final answer.

Verify web search:

```bash
agents-cli run -v \
  "Search the web for the official Python documentation and give me two relevant links. You must use web_search."
```

The trace should contain a `functionCall` for `web_search`, a successful
`functionResponse` with up to five results, and a final answer containing
result URLs.

Run the deterministic Python checks:

```bash
uv run pytest tests/unit
TEST_SERVER_PORT=18090 uv run pytest tests/integration
```

Run the focused behavioral evaluation after vLLM tool calling is enabled:

```bash
agents-cli eval run \
  --dataset tests/eval/datasets/basic-dataset.json \
  --config tests/eval/eval_config.yaml
```

For interactive testing, run `agents-cli playground`.

## Files

- `app/agent.py`: ADK agent and tool registration.
- `app/config.py`: environment-based LiteLLM configuration.
- `app/tools.py`: bounded keyless DDGS web-search tool.
- `tests/unit/test_agent.py`: deterministic tool and registration tests.
- `tests/eval/`: weather and web-search tool-call cases with a local
  deterministic metric.

This project is a local prototype and contains no deployment configuration.
