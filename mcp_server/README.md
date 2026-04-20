# learn-claude-code MCP server

A small Python MCP server that exposes a few workspace-safe tools:

- `hello(name)`
- `read_file(path, limit=200)`
- `write_file(path, content)`
- `run_bash(command, timeout=30)`
- resource: `workspace://readme`

## Setup

```bash
cd mcp_server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python server.py
```

## Register with Claude

Add this to `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "learn-claude-code": {
      "command": "python3",
      "args": ["/opt/tiger/learn-claude-code/mcp_server/server.py"]
    }
  }
}
```

## Notes

- File access is restricted to this repository.
- Bash commands run in the repository root.
- A few obviously dangerous shell patterns are blocked.
