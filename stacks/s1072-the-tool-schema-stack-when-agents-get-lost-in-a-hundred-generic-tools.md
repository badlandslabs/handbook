# S-1072 · The Tool Schema Stack: When Agents Get Lost in a Hundred Generic Tools

You gave your agent 50 tools. It ignores half of them, hallucinates another quarter, and spends most of its token budget reading tool descriptions it never calls. The problem isn't the number of tools — it's that nobody designed the schema. Agents don't browse a menu; they pick from a prompt. Bad tool descriptions are bad prompts.

## Forces

- Agents read every tool's name and description before deciding which to call — a bloated tool list is a bloated context tax before a single action
- Generic tool names like `read_file` and `write_file` carry no domain intent; agents can't infer *when* to use them
- Every tool parameter is a decision the model must make; under-specified types let agents pass garbage; over-specified types create rigid schemas that break on real data
- The MCP ecosystem shipped 13,000+ servers in 18 months (Nov 2024 – mid-2026) — the tooling is there, the design discipline isn't
- Prompt injection via tool descriptions is real: a compromised tool can influence which other tools the agent calls

## The move

**Design tool schemas like you design prompts: for the model's decision, not your implementation.**

- **Name for intent, not action.** `check_invoice_status` beats `query_table`. The agent reasons about goals, not SQL.
- **Descriptions answer "when, not how".** "Reads a file from disk" tells the model nothing about timing. "Use to inspect code or configs before editing" tells it when to reach for it.
- **Few parameters, typed strictly.** Each optional parameter is a branch the model must evaluate. Prefer composable tools over one tool with ten options.
- **Curate the tool list per task, not per agent.** An agent that can browse the web, write code, and send emails doesn't need all three tool sets loaded simultaneously. Serve tools on demand via MCP dynamic discovery instead of dumping the full registry.
- **Scope tools to the agent's domain.** A code-review agent gets git and file tools. A data agent gets SQL and API tools. Generic catch-all tools are where agents go to get lost.
- **Mark destructive tools explicitly** in the description. Agents are bad at knowing what they shouldn't touch.

## Evidence

- **GitHub repo:** punkpeye/awesome-mcp-servers — 90,652 stars, 12,896 forks, cataloguing the MCP ecosystem. Top categories: filesystem, web search, GitHub, Slack — all narrowly scoped. — [github.com/punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers)
- **HN Launch (43173378):** Browser Use (YC W25) — browser-use.com open-source library became the dominant browser-agent tool, not because it has the most features, but because its tool schema (click, type, extract_text, get_html) maps directly to agent intent. — [news.ycombinator.com/item?id=43173378](https://news.ycombinator.com/item?id=43173378)
- **HN Show (47336171):** Agent Browser Protocol (ABP) — a Chromium fork with 155 HN points. Core insight from the author: most browser-agent failures aren't model errors, they're stale-state errors. The tool schema sends the agent a frozen screenshot + structured state summary after every action, eliminating the guesswork of "what does the page look like now?" — [news.ycombinator.com/item?id=47336171](https://news.ycombinator.com/item?id=47336171)
- **MCP Market / OpenClaw:** OpenClaw reported 13,000+ MCP servers in the wild by March 2026, up from ~100 at Anthropic's Nov 2024 launch. Official SDKs hit 97M monthly downloads. The ecosystem grew because MCP standardized *tool transport* — not tool design. The design problem is still unsolved. — [mcpmarket.com](https://mcpmarket.com/server/openclaw-1)

## Gotchas

- **Context window poisoning:** loading 80 tools into context before the agent's first call taxes the window and dilutes attention to the actual task tools
- **Tool hallucination** (calling tools that don't exist) is reduced by strict schema validation on the client side, not by better descriptions alone
- **Version skew:** MCP server version mismatches between client and server cause silent failures — tool responses that look valid but aren't what the agent expected
- **Cross-tool state:** agents that chain tools often assume state persists between calls; a read then a write may succeed individually but fail as a sequence if the agent doesn't capture intermediate output
