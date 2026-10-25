# MCP Integration

Rahat's gateway exposes a **Model Context Protocol** server so **any local,
MCP-compatible client** wired to an open-weight model (for example, an open-source
MCP client connected to Ollama) can query and act on the situation picture, entirely
on the local network. No proprietary service is required or assumed.

## One tool registry, two front doors
The Dispatcher agent and the MCP server both use `gateway/app/tools/registry.py`.
A tool is defined once (schema, tier, handler) and is exposed to:
- the **internal Dispatcher** (Ollama tool-calling), and
- **external MCP clients** (via this server).
Both pass through the same policy engine and audit log.

## Server
- Package: `gateway/app/mcp_server.py` (Python `mcp` SDK, `FastMCP`)
- Transports: `stdio` (local) and Streamable HTTP at `http://<station>:8001/mcp`
- Auth: bearer token with a scoped role (`read`, `coordinator`); HTTP binds to the LAN only.

## Resources
| URI | Description |
|---|---|
| `rahat://sitrep/latest` | Markdown situation report |
| `rahat://incidents/open` | Open incidents (JSON) |
| `rahat://map/obstructions` | Active blocked roads (GeoJSON) |
| `rahat://insights/bottlenecks` | Active bottlenecks |
| `rahat://agent/sessions/recent` | Recent Dispatcher sessions with traces |

## Tools
| Tool | Args | Tier | Scope |
|---|---|---|---|
| `list_incidents` | `status?, min_priority?, bbox?` | T0 | read |
| `get_incident` | `id` | T0 | read |
| `count_available_volunteers` | `skill?, center, radius_km` | T0 | read |
| `find_volunteers` | `incident_id, skills?, radius_km?` | T0 | read |
| `calculate_route` | `from, to, profile` | T0 | read |
| `get_resource_stock` | `kind?` | T0 | read |
| `detect_bottlenecks` | `area?` | T0/T1 | read |
| `propose_dispatch` | `incident_id, volunteer_ids[], reason` | T1 | coordinator |
| `report_obstruction` | `geometry, severity` | T1 | coordinator |
| `run_dispatcher` | `incident_id` | T1 | coordinator (runs the agent loop) |
| `send_assignment` | `assignment_id` | **T2** | coordinator + `human_confirmation_token` from the dashboard |

## Prompts
- `triage_brief`: "Summarize the top 5 incidents and recommended actions."
- `shift_handover`: "Write a handover note for the next coordinator."

## Example (FastMCP over the shared registry)
```python
from mcp.server.fastmcp import FastMCP
from app.tools.registry import registry, Caller

mcp = FastMCP("rahat")

for tool in registry.exposed(scope="mcp"):
    mcp.add_tool(tool.as_mcp(caller=Caller.mcp))   # policy + audit wrapped

@mcp.resource("rahat://sitrep/latest")
def sitrep() -> str:
    return svc.insights.latest_sitrep()
```

## Client config (stdio)
```json
{ "mcpServers": { "rahat": { "command": "python", "args": ["-m", "app.mcp_server"],
  "env": { "RAHAT_TOKEN": "<token>" } } } }
```
Use any MCP-capable client configured with a local Ollama model. The exact config format varies by client.

## Security
- Treat all incident text as untrusted. It is returned inside data fields, never as instructions.
- T1 tools are rate-limited and audited. T2 tools need a human confirmation token.
- No outbound network calls from the MCP server.
