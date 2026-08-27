# Plant Energy MCP Host

## Overview

This CC3067 Networks Project 1 implements a terminal chatbot that connects a real LLM API to three MCP servers: the official Filesystem server, the official Git server, and the custom `plant-energy-mcp` industrial energy server. The project implements its host, JSON-RPC client, local MCP server, and Streamable HTTP adapter manually. It does **not** use FastMCP or an MCP SDK for those components. The two course-required official servers retain their own upstream dependencies.

The industrial scenario monitors cumulative energy readings for plant equipment, calculates consumption, detects threshold alerts, and creates deterministic reports.

## Current evidence status

| Capability | Status |
|---|---|
| Custom local MCP over stdio | Implemented and tested |
| Manual stdio/HTTP MCP clients | Implemented and tested |
| Session conversation and tool loop | Tested with a fake LLM |
| OpenAI/Anthropic API adapters | Implemented; live test requires the student's key/model |
| Official Filesystem + Git isolated demo | Tested locally |
| Custom remote transport | Tested on localhost; Docker build blocked because Docker Desktop was stopped; cloud deployment pending authorization |
| Wireshark evidence | Procedure ready; capture pending Wireshark and a deployed URL |

No cloud resource is created by the repository commands unless the user explicitly runs the deployment command.

## Architecture

```text
Terminal user
    -> mcp_host chatbot (session history and confirmation policy)
       -> OpenAI or Anthropic API
       -> manual MCP client -> official Filesystem server (restricted demo_workspace)
       -> manual MCP client -> official Git server (restricted demo repository)
       -> manual MCP client -> plant-energy-mcp
                              |- stdio subprocess
                              `- Streamable HTTP /mcp (same dispatcher and tools)
```

Important paths:

- `mcp_host/`: terminal host, LLM adapters, audit log, configuration, and manual MCP clients.
- `plant_energy_mcp/`: protocol dispatcher, tools, business service, stdio server, and HTTP server.
- `demos/`: isolated official-server demo and local/remote parity demo.
- `tests/`: deterministic tests that require no API key or Internet.
- `docs/FINAL_REPORT.md`: project specification and evidence ledger.
- `docs/PRESENTATION_GUIDE.md`: short presentation script.

## Requirements

- Python 3.11 or newer (tested with Python 3.13.1).
- Git.
- Node.js and npm/npx for the official Filesystem server (tested with Node 22.14.0 and npx 10.9.2).
- `mcp-server-git` for the official Git server.
- Docker for the optional container workflow (Docker 28.1.1 was detected, but its daemon was not running during verification).
- An OpenAI or Anthropic API key and model identifier for a live LLM test.
- Wireshark for the real network capture; it was not installed in the verification environment.

## Installation

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-official-mcp.txt
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-official-mcp.txt
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

The project code uses the Python standard library. `requirements-official-mcp.txt` installs only the official Git MCP server and its upstream dependencies. The Filesystem server is obtained by its official npx command when it starts.

`.env` is a reference file only; this project does not automatically load it. Export the values in the current shell, or use a trusted environment loader. Never commit `.env`.

OpenAI example:

```powershell
$env:LLM_PROVIDER = "openai"
$env:LLM_API_KEY = Read-Host "LLM API key"
$env:LLM_MODEL = "your-provider-model-id"
$env:LLM_BASE_URL = "https://api.openai.com/v1"
```

Anthropic uses `LLM_PROVIDER=anthropic` and the provider's model identifier. No model name or key is hardcoded because availability depends on the student's account.

## Run

Local custom server alone (stdio expects JSON-RPC lines on stdin):

```powershell
python -m plant_energy_mcp
```

Chatbot with the custom local server:

```powershell
python -m mcp_host --servers plant-local
```

Chatbot with all local servers:

```powershell
python -m mcp_host --servers plant-local,filesystem,git
```

Commands inside the chatbot are `/help`, `/tools`, `/log`, and `/exit`. The history exists only in the active process. Failures from one MCP server are reported without intentionally closing the other clients. Tool names that imply writing, adding, committing, deleting, moving, or recording require confirmation.

## Official Filesystem and Git servers

The Windows Filesystem command used by the host is:

```powershell
cmd /c npx -y @modelcontextprotocol/server-filesystem "<project>\demo_workspace"
```

The allowed root is never the user's home directory. The Git server uses the activated `mcp-server-git` console command (or `uvx mcp-server-git`) and receives only `<project>/demo_workspace/git_repo`.

Run the reproducible isolated demo:

```powershell
python -m demos.filesystem_git_demo
```

It creates a new uniquely named repository under ignored `demo_workspace/`, creates its README via Filesystem MCP, stages it with `git_add`, and commits it with `git_commit`. It never deletes or commits to the main repository.

## Custom server specification

Server name: `plant-energy-mcp`. Protocol version: `2025-11-25`.

| Tool | Parameters | Side effect |
|---|---|---|
| `list_equipment` | optional `area` | No |
| `record_energy_reading` | `equipment_id`, ISO-8601 `timestamp`, nonnegative `energy_kwh` | Session memory write |
| `calculate_consumption` | equipment and two recorded timestamps | No |
| `detect_usage_alerts` | equipment and two recorded timestamps | No |
| `get_energy_report` | optional `area` | No |

Complete JSON Schemas are returned by `tools/list` from `plant_energy_mcp/tools.py`. Invalid parameters use JSON-RPC `-32602`; unknown methods use `-32601`; unexpected internal failures return `-32603` without a traceback.

Handshake example:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"demo","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
```

Example conversation (LLM wording varies):

```text
You> Which equipment is above its usage threshold?
Bot> [calls plant_local__get_energy_report]
Bot> compressor-01 is above its configured threshold; the other two are normal.
You> Which plant area is it in?
Bot> It is in Utilities.
```

## Remote server and container

Run locally:

```powershell
$env:PLANT_MCP_HOST = "127.0.0.1"
$env:PORT = "8080"
python -m plant_energy_mcp.http_server
```

In another terminal:

```powershell
$env:PLANT_MCP_REMOTE_URL = "http://127.0.0.1:8080/mcp"
python -m demos.local_remote_parity_demo
```

The health endpoint is `GET /health`; MCP uses `POST /mcp`. `GET /mcp` deliberately returns 405 because this implementation does not offer a standalone SSE listening stream. The server validates `Origin`, authentication, body size, `Content-Type`, both required `Accept` types, protocol version, session identifier, and JSON-RPC structure. A non-loopback bind requires `PLANT_MCP_AUTH_TOKEN`.

Container verification:

```powershell
docker build -t plant-energy-mcp:local .
docker run --rm -p 8080:8080 -e PLANT_MCP_AUTH_TOKEN=replace-with-a-random-demo-token plant-energy-mcp:local
```

Cloud Run preparation (do not run without authorization and a selected Google Cloud project):

```powershell
gcloud run deploy plant-energy-mcp --source . --region us-central1 --allow-unauthenticated --set-secrets PLANT_MCP_AUTH_TOKEN=plant-mcp-auth-token:latest
```

Create `plant-mcp-auth-token` in Secret Manager first, with IAM access limited to the Cloud Run service account. `--allow-unauthenticated` exposes the HTTP ingress, while the application still rejects `/mcp` without its bearer token; `/health` remains intentionally public. After deployment, set `PLANT_MCP_REMOTE_URL=https://REAL_URL/mcp`, configure the matching token, and run the parity demo.

## MCP audit log

All clients write `.runtime/mcp_interactions.jsonl` with UTC timestamp, server, transport, direction, method, correlation ID, duration, summary, and error code. Keys matching authorization, token, secret, password, or API-key patterns are replaced with `[REDACTED]`; project-root paths are replaced with `[PROJECT_ROOT]`; long content is truncated. Use `/log` in the chatbot to show the last 20 records.

## Tests and checks

```powershell
python -m unittest discover -v
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m compileall -q plant_energy_mcp mcp_host demos
git diff --check
```

The unit/integration suite does not need Internet, an LLM key, or cloud resources. The official-server and live-LLM demos are deliberately separate.

## Wireshark procedure

1. Deploy the server and resolve its hostname with `Resolve-DnsName <host>` (Windows) or `dig <host>`.
2. Select the active Wi-Fi/Ethernet interface, not loopback, when calling the cloud URL.
3. Use capture filter `host <resolved-ip> and tcp port 443`. Start capture before running the parity demo.
4. Use display filter `dns or tcp.port == 443 or tls or http2`. Identify DNS, TCP handshake, TLS setup, encrypted application data, and close packets.
5. To inspect owned-client TLS legitimately, set `SSLKEYLOGFILE` before starting Python and configure Wireshark at Preferences > Protocols > TLS > (Pre)-Master-Secret log filename. Do not capture or publish bearer tokens.
6. Record only values actually observed in `docs/FINAL_REPORT.md`; sanitize the capture before sharing.

JSON-RPC is normally encrypted inside TLS and cannot be read merely by filtering HTTP. For a localhost learning capture, use the loopback adapter and display filter `http and tcp.port == 8080`, but this does not replace cloud evidence.

## Security, limitations, and troubleshooting

- Demo data is in memory and resets per server session.
- The host does not execute arbitrary shell commands. External server commands are fixed in `mcp_host/config.py`.
- Official server access is restricted to the ignored demo workspace.
- Authentication is a demonstration bearer token; production should use the cloud provider's identity layer and secret store.
- A live LLM response is unverified until the student configures a valid provider key/model.
- Cloud latency, public URL, IP addresses, and packet details are intentionally not invented.

Common issues:

- `LLM_API_KEY is missing`: export `LLM_API_KEY` and `LLM_MODEL` in the same terminal.
- `No module named mcp_server_git`: activate `.venv` and install `requirements-official-mcp.txt`.
- npx registry/cache error: confirm Internet access, npm proxy settings, and retry the official command.
- `HTTP 401`: client and remote server tokens differ.
- `Unknown or expired MCP session`: call `initialize` again and retain `MCP-Session-Id`.
- PowerShell blocks activation: use `Set-ExecutionPolicy -Scope Process Bypass`, then activate again.

## Sources

- [MCP 2025-11-25 transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [Official Filesystem MCP server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)
- [Official Git MCP server](https://github.com/modelcontextprotocol/servers/tree/main/src/git)
- [JSON-RPC 2.0 specification](https://www.jsonrpc.org/specification)
