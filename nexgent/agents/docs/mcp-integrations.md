# MCP development and integration

The workspace has a reusable Model Context Protocol client boundary for remote
Streamable HTTP servers. Server discovery and protocol calls live in
`ax-integrations`; conversion to LangChain tools and authorization live in
`ax-tools`. No workflow receives MCP tools automatically.

The implementation uses the official Python SDK's high-level client and custom
HTTP-client path. This supports environment-backed authorization headers while
keeping credentials outside prompts, graph state, artifacts, logs, and the
checked-in registry. See the official [Python client
documentation](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/index.md)
and [transport configuration
guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/transports.md).

## Registry

Checked-in server metadata is stored in `config/mcp_servers.json`. The registry
is strict: unknown fields are rejected, URLs cannot contain credentials, and
headers can only refer to environment variables. The default registry path can
be replaced with `MCP_SERVERS_CONFIG`.

```json
{
  "servers": {
    "another_server": {
      "transport": "streamable_http",
      "url": "https://mcp.example.com/mcp",
      "headers": {
        "Authorization": {
          "env": "ANOTHER_MCP_BEARER_TOKEN",
          "prefix": "Bearer "
        }
      },
      "connect_mode": "auto",
      "tool_risks": {
        "lookup": "read"
      }
    }
  }
}
```

`connect_mode` should remain `auto` for new servers. Use `legacy` only when a
handshake-era server does not support the modern discovery probe. Tool risks
must be classified explicitly as `read`, `write`, or `destructive`; an
unclassified tool is discoverable through the development CLI but cannot be
converted into an agent tool.

## Configured database server

`db_mcp_server` is registered at `http://192.168.0.11:8001/mcp`. Its bearer
token is stored only in the ignored root `.env` as
`DB_MCP_SERVER_BEARER_TOKEN`, alongside `OPENAI_API_KEY`. `.env.example`
contains an empty placeholder.

The live development check on 2026-08-13 negotiated protocol `2025-11-25`
with `db-mcp-server` version `1.29.0` and discovered these tools:

- `server_info`
- `server_status`
- `list_schemas`
- `list_tables`
- `describe_table`
- `find_columns`
- `get_relationships`
- `preview_table`
- `query_data`
- `explain_query`

The server declares a read-only policy, and all ten tools are classified as
`read` in the registry. Classification does not grant access: each workflow
must still include the generated namespaced tool name in its `ToolPolicy`.
The final end-to-end check adapted all ten live schemas and successfully called
only the explicitly allowlisted `server_info` tool.

## Development commands

List configured servers without making a network connection:

```bash
uv run --frozen ax-mcp list
```

Load the ignored `.env`, connect, and print non-secret server and tool metadata:

```bash
uv run --frozen --env-file .env ax-mcp inspect db_mcp_server
```

The CLI never prints resolved headers. Connection and protocol failures are
mapped to safe structured errors.

## Exposing tools to a workflow

Tool discovery and calls reuse a pooled HTTP client. Remote names are
namespaced so different servers cannot silently overwrite one another. The
discovered JSON Schema is validated locally before a call, and the common tool
policy enforces risk and allowlisting.

```python
from ax_integrations import load_mcp_registry
from ax_tools import ToolPolicy, create_mcp_tools, mcp_tool_name

registry = load_mcp_registry()
client = registry.create_client("db_mcp_server")
definitions = await client.list_tools()

allowed = {
    mcp_tool_name("db_mcp_server", "list_schemas"),
    mcp_tool_name("db_mcp_server", "list_tables"),
}
tools = create_mcp_tools(
    definitions,
    client,
    ToolPolicy(allowed_tools=frozenset(allowed)),
)

# Keep `client` for the workflow/application lifetime, then close its pool.
await client.aclose()
```

Successful and failed MCP tool results are marked as untrusted external data.
Cancellation propagates to the SDK transport. There is no automatic retry for
tool calls because the client cannot assume a remote operation is idempotent.

## Adding another MCP server

1. Add one server entry to `config/mcp_servers.json`.
2. Add only empty secret placeholders to `.env.example`; put real values in
   the ignored `.env` or the deployment secret store.
3. Run `ax-mcp inspect <server>` and review every discovered schema and
   description.
4. Classify each tool's risk in the registry. Leave uncertain tools
   unclassified so exposure fails closed.
5. Add only the tools required by a workflow to that workflow's allowlist.
6. Add deterministic adapter/policy tests and a deployment-owned live
   readiness check.
