# S-2313 · The Tool Surface Stack — When Your Agent Has a Hundred Tools and Uses Three

You built a comprehensive tool suite. GitHub, Jira, Slack, Postgres, Redis, S3, SendGrid, twelve internal APIs, and a custom ML inference endpoint. Your agent *can* do anything. In practice it ignores 90% of them, hallucinates the right tool name but wrong parameters, and when it finally calls the database tool it drops a table. The problem isn't tool count. It's that you treated tools like an API spec instead of a UX problem. [S-2308](s2308-the-specialization-split-stack-when-one-agent-is-not-enough.md) covers agent specialization. This entry covers how to design the tools those agents actually call.

## Forces

- **Software dev tools dominate even harder than they dominate supply.** 67% of MCP tools target software development, but they account for 90% of downloads. The long tail of specialized domain tools (legal, finance, healthcare) exists but almost nobody downloads it — revealing a massive supply/demand mismatch. Teams building domain-specific agents waste months building tools nobody will use.
- **Tool cardinality is a red herring; tool quality is the real variable.** Agents with 10 well-designed tools consistently outperform agents with 100 poorly-described ones. The constraint isn't the number of tools — it's the quality of tool descriptions, parameter schemas, and error handling.
- **Tool capability and tool risk are in tension.** The tools that make agents most useful — file writes, API calls, database writes, email send — are also the tools most likely to cause damage. Over-restricting tools defeats the purpose; under-restricting invites catastrophe.
- **MCP's ecosystem is real but lumpy.** The standard has 10,000+ public servers, but the top 10 by stars cover 80% of real usage. Most tool-building effort is wasted on tools that will never be called.

## The Move

**Design your tool surface as a constrained, opinionated API — not a feature-complete one.**

### Curate ruthlessly, not comprehensively

- Start with the minimum viable tool set: file read, file write, shell/terminal, web search. These three cover ~80% of real-world agent tasks per MCP usage data.
- Add tools only when you observe a repeated failure pattern — the agent trying to do something it can't — not in advance "for completeness."
- Track which tools get called in production. If a tool has >0% definition in your context but 0 actual invocations over 30 days, cut it.

### Write tool descriptions as if for a distracted intern, not a spec reviewer

- First sentence: what the tool *does* in plain language (e.g., "Searches the internal knowledge base and returns the top 5 relevant documents" — not "Performs a semantic search over the vector database using cosine similarity.")
- Second sentence: when to call it and when not to.
- Parameter schema: name → type → one-line purpose. Avoid nested objects unless necessary — flat schemas have lower hallucination rates on parameter names.

```python
# Bad: verbose, technical, no guidance
def query_database(sql: str, timeout: int = 30, retry: bool = True):
    """Execute a SQL query against the production database."""
    pass

# Good: scoped, clear intent, clear guardrails
def run_query(sql: str) -> list[dict]:
    """Run a read-only SQL query against the analytics database.
    
    Use this to: fetch metrics, look up records, aggregate data.
    Do NOT use for: writes, schema changes, or administrative operations.
    
    Args:
        sql: A SELECT statement. No INSERT/UPDATE/DELETE allowed.
    Returns:
        Up to 1000 rows as a list of dicts.
    """
```

### Separate perception tools from action tools — and restrict the latter

- **Perception tools** (read-only): web search, database queries, file read, API GET calls. Safe to expose broadly.
- **Action tools** (state-changing): file write, database writes, API POST/PUT/DELETE, email send, code execution. Scope these to the narrowest possible action. "Send a Slack message to #alerts" is better than "Send an HTTP request."
- Use a tool wrapper that intercepts action tool calls and enforces a confirmation threshold (e.g., any write operation touching >10 rows requires a human-in-the-loop pause).

### Match tool granularity to the agent's decision level

- **High-level tools** for generalist agents: `create_github_issue(title, body, labels)` — the agent decides what to create and drafts the content.
- **Low-level tools** for specialist agents: `append_to_file(path, content)` and `list_directory(path)` — the agent decides the exact sequence of file operations.
- Don't give a generalist agent raw SQL if you can give it a purpose-built report generator. Don't give a coding agent a "run any shell command" tool if you can give it `lint_file`, `format_file`, `run_tests`.

### Lazy-load tool definitions in MCP deployments

- Anthropic's engineering team documented that loading all tool definitions upfront consumes significant context tokens as tool count grows.
- Pattern: only load the tool schema into context when the agent's task description matches a trigger condition. A file-editing task triggers the filesystem tool schema; a question about GitHub triggers the GitHub tool schema.
- This requires a tool registry with task-based routing, but it pays for itself at 20+ tools.

### Design for tool error recovery

- Every tool should return a structured error with a recovery hint: `{error: "file_not_found", suggestion: "Check if the path exists with list_directory('/parent') first"}`.
- The agent can then self-correct without escalation. Without recovery hints, a failed tool call usually cascades into repeated failure.

## Evidence

- **Research paper:** Analysis of 177,436 MCP tools across 19,388 servers (Nov 2024–Feb 2026) found software dev tools are 67% of supply but 90% of downloads — revealing massive long-tail waste in domain-specific tool builds. Action tool share grew from 27% to 65% of downloads over the period, while perception tool share declined. — [arXiv:2603.23802, Stein (UK AI Security Institute / Oxford), March 2026](https://arxiv.org/abs/2603.23802)
- **Primary source (ecosystem):** MCP.Directory's March 2026 analysis of the most-installed MCP servers by stars and downloads found the top 5 are all software-dev-focused: GitHub (5.2k stars), filesystem operations, web search (with multi-provider fallback), database queries, and memory/knowledge bases. Zero domain-specific tools (legal, medical, financial) appear in the top 20. — [MCP.Directory Blog](https://mcp.directory/blog/most-popular-mcp-tools-2026)
- **HN primary source (browser automation):** Browser Use (YC W25, 259 HN points) — the top open-source browser agent library — achieves 87.4% on the Odysseys web agent leaderboard using a single focused tool: extract interactive elements from the current page, let the LLM decide the next action, execute via Playwright. The key design insight: the tool exposes *capabilities* (what can I do on this page?) rather than instructions (do X). — [GitHub: browser-use/browser-use](https://github.com/browser-use/browser-use), [HN Launch Thread](https://news.ycombinator.com/item?id=43173378)

## Gotchas

- **Tool name hallucination is the #1 failure mode in multi-tool agents.** If your agent has 20+ tools, it will occasionally call a tool that doesn't exist by combining names ("update_github_ticket" instead of "update_issue"). Mitigate by adding a "nearest valid tool" fallback in your tool router.
- **Defining a tool doesn't mean the agent will use it correctly.** You need few-shot examples in the system prompt showing the tool called with real parameters, not just the schema. Schema-only definitions achieve ~60% correct parameter use; schema + examples achieve ~85%.
- **Tool access control is not authentication.** Exposing a `delete_file` tool to an agent is not the same as securing it. Implement tool-level permission checks in the tool wrapper, not just in your MCP server config — agents can receive adversarial prompt injections that call tools with crafted parameters.
