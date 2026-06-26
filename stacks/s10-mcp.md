# S-10 · MCP

The Model Context Protocol — a standard for giving any model access to tools, data, and context from external systems.

## Forces
- Tool definitions written for one model/framework don't port to another
- Every team reinvents the "connect model to database / API / filesystem" problem
- Without a standard, tool ecosystems fragment — you're locked to one framework
- A standard only matters if models and tooling actually adopt it

## The move

MCP (released by Anthropic, open spec) defines a client-server protocol. The **MCP client** (Claude Code, Claude Desktop, an SDK-based agent) connects to **MCP servers** that expose tools, resources (files, data), and prompts.

**What an MCP server can expose:**
- **Tools** — functions the model can call (e.g., `search_database`, `create_file`)
- **Resources** — read-only data the model can access (e.g., a file system, a database table)
- **Prompts** — reusable prompt templates

**Minimal MCP server (Python, using the official SDK):**
```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

server = Server("my-handbook-server")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_entry",
            description="Fetch a handbook entry by code (e.g. S-01).",
            inputSchema={
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "get_entry":
        code = arguments["code"]
        # read the entry file and return it
        return [types.TextContent(type="text", text=f"Entry {code}: ...")]

async def main():
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

**Wire it into Claude Code** by adding to `.claude/settings.json`:
```json
{
  "mcpServers": {
    "handbook": {
      "command": "python",
      "args": ["path/to/server.py"]
    }
  }
}
```

**MCP vs custom tool use:** MCP is a transport + discovery standard. The underlying mechanism is still tool calls — MCP just makes them portable across clients.

## Receipt
> Receipt pending — 2026-06-25. Code above follows the official MCP Python SDK (`pip install mcp`). Run `pip install mcp` and test the server before deploying. Spec at modelcontextprotocol.io.

## See also
[S-03](s03-tool-use.md) · [W-02](../workspace/w02-claude-code.md) · [S-05](s05-multi-agent-patterns.md)

## Go deeper
Keywords: `Model Context Protocol` · `MCP server` · `MCP client` · `modelcontextprotocol.io` · `tool protocol` · `Claude Desktop`
