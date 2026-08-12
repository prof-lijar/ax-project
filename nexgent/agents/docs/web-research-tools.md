# Reusable web research tools

Date: 2026-08-12

## Purpose and boundaries

`web_search` and `web_fetch` are provider-neutral, read-only tools for later
LangGraph workflows. They do not belong to the chat graph, do not depend on a
model's native tool API, and do not make network requests during import.

```text
workflow or ToolNode
  -> ax-tools authorization and tool contract
  -> injected executor port
  -> ax-integrations adapter
       -> private SearXNG JSON API for discovery
       -> public HTTP(S) page for bounded evidence extraction
```

Search results contain discovery snippets, not verified evidence. Fetch a
selected result before relying on substantive claims, retain its `source_id`
and `final_url`, and render the URL as a visible citation in user-facing output.

## Create the tools

```python
from ax_integrations import (
    get_default_web_fetch_client,
    get_default_web_search_client,
)
from ax_tools import ToolPolicy, create_web_fetch_tool, create_web_search_tool

policy = ToolPolicy(allowed_tools=frozenset({"web_search", "web_fetch"}))
web_search = create_web_search_tool(get_default_web_search_client(), policy)
web_fetch = create_web_fetch_tool(get_default_web_fetch_client(), policy)
```

The resulting `StructuredTool` objects can be placed in a LangGraph `ToolNode`
or invoked from a deterministic workflow node. Successful tool messages contain
a compact JSON body plus the normalized result in `ToolMessage.artifact`.
Expected failures use a safe JSON error with `code`, `message`, and `retryable`;
async cancellation is never swallowed.

Example search arguments:

```python
await web_search.ainvoke(
    {
        "query": "latest LangGraph release notes",
        "result_limit": 8,
        "language": "en",
        "allowed_domains": ["langchain.com"],
    }
)
```

Allowed and blocked domains are mutually exclusive. A domain entry includes
its subdomains. Time range accepts `day`, `month`, or `year` when supported by
the active upstream engine.

## Search service

All Compose topologies run the official SearXNG image pinned by tag and digest.
Its JSON API is available only on the internal Compose network at
`http://searxng:8080`; no host port is published. The configured engines are
Bing, Brave, DuckDuckGo, and Google. They do not require API keys, but they may
throttle, return CAPTCHAs, or change behavior independently.

Configuration:

```text
SEARXNG_BASE_URL=http://searxng:8080
SEARXNG_SECRET=<random service secret>
```

`SEARXNG_SECRET` protects the SearXNG service configuration; it is not a search
provider credential. Generate a random value for every non-development
deployment.

An operator with Docker access can verify the pinned service and JSON API from
the agents workspace:

```bash
sudo docker compose up -d searxng
sudo docker compose exec -T searxng \
  wget -qO- 'http://127.0.0.1:8080/search?q=LangGraph&format=json'
```

## Fetch safety and limits

`web_fetch` accepts only HTTP(S) pages without embedded credentials. It resolves
and pins public IP addresses before connecting, rejects an entire DNS answer set
if any address is non-public, revalidates every redirect, disables environment
proxies, sends no cookies or authorization, and allows at most three redirects.

Only HTML, XHTML, and plain text are accepted. Downloads are limited to 2 MiB,
extracted text is limited to 40,000 characters, and the default call returns at
most 12,000 characters. Trafilatura extracts readable main text. Every fetch
result sets `content_is_untrusted=true`: retrieved instructions must never alter
workflow policy, disclose state, or authorize another tool.

PDF extraction, JavaScript rendering, authenticated pages, crawling, file
downloads, robots-policy automation, and persistent retrieval caching are
outside this first release.

## Verification

Deterministic tests use mocked HTTP transports and DNS resolvers. An optional
deployment smoke check should query current events, official technical docs,
multilingual content, and domain filters while recording result count, unique
domains, duplicate rate, latency, and fetch success. Live quality is not a CI
gate because the no-key upstream engines are nondeterministic.
