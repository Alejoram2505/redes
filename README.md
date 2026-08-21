# Plant Energy MCP Server

`plant-energy-mcp` is a local Model Context Protocol (MCP) server for a small industrial energy-management scenario. It exposes deterministic tools for inspecting equipment, recording cumulative meter readings, calculating consumption, detecting threshold alerts, and producing an energy report.

This repository implements MCP manually on JSON-RPC 2.0. It does **not** use FastMCP, an MCP SDK, or any framework that hides the protocol exchange.

## Current partial-delivery scope

This delivery contains only the student-defined local MCP server required for the first partial submission:

- MCP protocol version `2025-11-25`
- local `stdio` transport
- one JSON message per line
- `initialize` and `notifications/initialized`
- `ping`, `tools/list`, and `tools/call`
- JSON-RPC errors for parse failures, invalid requests or parameters, unknown methods, and internal failures
- five industrial energy tools
- an executable subprocess demo and automated integration tests

It does not include a remote MCP server, cloud deployment, packet capture, Wireshark analysis, a user interface, or the final OSI/TCP-IP report.

## Architecture

```text
MCP client / demo.py
        |
        | line-delimited JSON-RPC 2.0 over stdin/stdout
        v
plant_energy_mcp/server.py       stdio transport only
        |
plant_energy_mcp/protocol.py     parsing, lifecycle, dispatch, errors
        |
plant_energy_mcp/tools.py        tool schemas and input validation
        |
plant_energy_mcp/service.py      business rules and demo state
```

Human-readable shutdown information is written to `stderr`. Protocol responses are the only content written to `stdout`.

### Folder structure

```text
plant_energy_mcp/   server package
tests/              subprocess integration tests
demo.py             reproducible MCP session harness
.env.example        safe configuration template
README.md           setup, protocol, tools, and demo documentation
```

## Requirements

- Python 3.10 or newer
- No third-party Python packages

## Installation

Clone the private repository, enter this project directory, and optionally create an isolated environment.

### PowerShell

```powershell
git clone <PRIVATE_REPOSITORY_URL>
cd <REPOSITORY_NAME>
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m unittest discover -v
```

### POSIX shell

```bash
git clone <PRIVATE_REPOSITORY_URL>
cd <REPOSITORY_NAME>
python3 -m venv .venv
. .venv/bin/activate
python -m unittest discover -v
```

There is no dependency installation command because the project uses only the Python standard library.

## Environment variables

The current local server requires no environment variables. `.env.example` documents this explicitly. Do not commit `.env`, API keys, credentials, production meter readings, or other sensitive data.

## Run the MCP server

```bash
python -m plant_energy_mcp
```

The process waits for one-line JSON-RPC messages on `stdin`. Closing `stdin` terminates it cleanly.

## Run the tests

```bash
python -m unittest discover -v
```

The tests start the actual server as a subprocess and verify the lifecycle, all five tools, JSON-only stdout, input validation, major JSON-RPC errors, and clean shutdown.

## Run the demonstration

```bash
python demo.py
```

Expected milestones in the output are:

1. `initialize` returns protocol version `2025-11-25` and server name `plant-energy-mcp`.
2. `tools/list` returns five tool definitions and their JSON Schemas.
3. `calculate_consumption` returns `220.0 kWh` and `55.0 kWh/hour` for `press-01`.
4. `detect_usage_alerts` returns `status: normal` for that period.
5. The server exits with code `0` after the harness closes `stdin`.

## MCP server specification

The transport uses UTF-8-compatible, newline-delimited JSON. Each input and output message occupies exactly one line. Requests follow JSON-RPC 2.0 and responses preserve the request `id`.

### Lifecycle

The required order is:

```text
initialize request
initialize response
notifications/initialized notification (no response)
ping, tools/list, or tools/call requests
```

Requests for tools before the lifecycle completes return server error `-32002`.

### Supported methods

| Method | Purpose |
|---|---|
| `initialize` | Negotiate the MCP protocol version and server capabilities. |
| `notifications/initialized` | Confirm that the client completed initialization; it produces no response. |
| `ping` | Confirm that the initialized server is responsive. |
| `tools/list` | Discover tool names, descriptions, and input schemas. |
| `tools/call` | Validate arguments and execute one tool. |

### JSON-RPC errors

| Code | Meaning |
|---:|---|
| `-32700` | Invalid JSON / parse error |
| `-32600` | Invalid JSON-RPC request |
| `-32601` | Unknown method |
| `-32602` | Invalid method or tool parameters |
| `-32603` | Internal error with implementation details suppressed |
| `-32002` | MCP lifecycle has not completed |

## Tool reference

### `list_equipment`

Lists the deterministic equipment catalog. Optional `area` must be `Forming` or `Utilities`.

```json
{"area":"Utilities"}
```

### `record_energy_reading`

Records a cumulative reading for the current process session. The timestamp must include a timezone, be later than the latest reading, and be unique. The cumulative value cannot decrease.

```json
{"equipment_id":"press-01","timestamp":"2026-08-20T13:00:00Z","energy_kwh":12770}
```

### `calculate_consumption`

Subtracts two existing cumulative readings and calculates the average use per hour. Both timestamps must exactly match recorded readings.

```json
{"equipment_id":"press-01","start_timestamp":"2026-08-20T08:00:00Z","end_timestamp":"2026-08-20T12:00:00Z"}
```

Example structured result:

```json
{"equipment_id":"press-01","start_timestamp":"2026-08-20T08:00:00Z","end_timestamp":"2026-08-20T12:00:00Z","consumption_kwh":220.0,"average_kwh_per_hour":55.0}
```

### `detect_usage_alerts`

Uses the same three period parameters as `calculate_consumption` and compares the result with the configured equipment threshold.

### `get_energy_report`

Summarizes consumption from the first to latest reading for every item. Optional `area` accepts `Forming` or `Utilities`.

```json
{}
```

## Manual JSON-RPC example

Start `python -m plant_energy_mcp`, then paste each JSON object as a single line:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"manual-client","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"calculate_consumption","arguments":{"equipment_id":"press-01","start_timestamp":"2026-08-20T08:00:00Z","end_timestamp":"2026-08-20T12:00:00Z"}}}
```

The notification intentionally has no response. Every other line returned on `stdout` is a valid JSON-RPC response.

## Five-minute demo scenario

1. Explain that cumulative industrial meter readings must be converted into understandable consumption and alerts.
2. Show the four-layer architecture above.
3. Run `python demo.py` to demonstrate initialization, discovery, consumption, and alert evaluation.
4. Send a `tools/call` with an unknown `equipment_id` to show a controlled `-32602` response.
5. Run `python -m unittest discover -v` and show the passing subprocess tests.

## Data and reset behavior

The equipment and seed readings are fictional demonstration fixtures. New readings live only in process memory. Restarting the server restores the original deterministic dataset; no files or databases are modified.

## Security considerations

- The server never evaluates code, invokes a shell, accesses the network, or reads arbitrary paths.
- Tool inputs reject unknown fields, wrong types, missing values, invalid equipment, invalid time order, decreasing cumulative values, and excessive meter values.
- Client errors do not expose stack traces, filesystem paths, or secrets.
- All demo data is fictional and contains no credentials or personal information.
- `stdout` is reserved for protocol JSON; human-readable messages use `stderr`.

## Limitations

- State is in memory and is not shared between server processes.
- Consumption requires timestamps that exactly match recorded readings; interpolation is intentionally out of scope.
- Thresholds are static demonstration values, not engineering recommendations.
- No authentication is implemented because this delivery uses a local child process over `stdio`.
- The server is not yet connected to an LLM or a chatbot.

## Pending items for the complete "First part"

These items are not implemented in this partial delivery and must be confirmed with the instructor:

- connect a chatbot to an LLM API using credentials loaded from the environment;
- preserve conversational context within a session;
- display a correlated, secret-free MCP request/response interaction log;
- integrate the official local Filesystem server with explicit allowed directories;
- integrate the official local Git server;
- invoke this custom local server from the chatbot using natural language.

## Publication checklist

Before the private GitHub submission:

```bash
python -m unittest discover -v
python demo.py
git status --short
git diff --check
git log --oneline --decorate -n 15
```

Verify the repository remains private and grant the instructor and teaching assistants access manually. This project does not publish, change repository visibility, rewrite history, or push automatically.

## References

- Model Context Protocol specification, version `2025-11-25`: <https://modelcontextprotocol.io/specification/2025-11-25>
- JSON-RPC 2.0 specification: <https://www.jsonrpc.org/specification>
