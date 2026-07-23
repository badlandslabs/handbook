# S-1535 · The Context Compression Stack — When Your Tool Definitions Cost More Than Your Model

You added 40 MCP tools. Your agent now has proper web search, database access, calendar, Slack, and file operations. The first task runs fine. By task 12, the context window is 80% full — and the model is spending 34% of its tokens on tool definitions and intermediate results, not on reasoning. The invoice for model API calls is modest. The invoice for the architecture you chose is not.

## Forces

- **Naive MCP integration is a token leak.** When agents load all tool definitions and pass every intermediate result through context, the overhead compounds multiplicatively across multi-step tasks. A 200-token tool definition × 40 tools × 8 steps = 64,000 tokens of pure overhead.
- **Tool-first design was the right starting point, then it became the ceiling.** The MCP ecosystem grew fast (thousands of servers since November 2024) because tool-first was the right abstraction for 10–20 tools. At 100+ tools, every tool in context becomes drag.
- **Direct tool calls are atomic but inefficient.** One tool call, one result, one context insertion per step. There is no batching, no filtering, no local computation to reduce what flows back to the model.
- **The context window is shared real estate.** Every token spent on tool metadata is a token unavailable for reasoning, memory retrieval, or actual work. The allocation is zero-sum.

## The Move

Instead of giving the agent direct MCP tool access, give it a code execution environment and a lightweight tool SDK. The agent writes a script that calls multiple tools internally, aggregates results, and returns a compressed summary. This moves tool interaction off the context-critical path.

**The concrete pattern:**
1. Give the agent one tool: `execute_code(lang, script)` — a sandboxed code runner with MCP SDK bindings
2. The agent writes Python/TypeScript that imports the MCP client library, batches multiple tool calls, and returns only the aggregated result
3. Tool definitions are described once in the SDK (not in context) and referenced by the script the agent writes
4. Raw tool outputs stay in the code sandbox; only the script's return value flows back to the model

**Architectural constraints:**
- The code runner must be sandboxed (no file system or network access beyond what the MCP tools provide)
- Tool SDKs must be pre-initialized in the sandbox environment — the agent does not install packages, it writes import statements
- The return value from `execute_code` must be aggressively filtered: only the data the next reasoning step needs should be included
- Error handling lives inside the script, not as a separate tool-call retry loop

## Evidence

- **Engineering post:** Anthropic published "Code execution with MCP" (Nov 4, 2025), describing exactly this pattern — agents write code against MCP tool SDKs rather than calling tools directly, handling "more tools while using fewer tokens." They explicitly benchmark the token reduction from this approach. — [Anthropic Engineering](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **GitHub (19K stars):** `context-mode` by mksglu implements context window optimization for AI coding agents, achieving 98% tool output reduction by sandboxing raw results in a code execution layer rather than routing them through context. — [GitHub](https://github.com/mksglu/context-mode)
- **Practitioner analysis:** Multiple HN and Reddit threads (2025–2026) on "bad MCP design costs your agent 5x more tokens" document that naive MCP implementations with verbose tool schemas and unfiltered responses systematically outperform poorly-designed alternatives on token efficiency by 3–5×. A key finding: tool descriptions that include example outputs generate significantly more context bloat than minimal schema definitions. — [HN via penportal.net](https://hacker-news.penportal.net/item/48407391)
- **arXiv preprint:** "A Practical Guide for Designing, Developing, and Deploying Production-Grade Agentic AI Workflows" (Dec 2025, Old Dominion University / Deloitte / IcicleLabs.AI) recommends "tool-first design over MCP" and "pure-function invocation" as two of nine core best practices — validating that the industry has already identified naive MCP tool-calling as a production liability. — [arXiv:2512.08769](https://arxiv.org/pdf/2512.08769)

## Gotchas

- **The sandbox is a security boundary, not just a performance trick.** If the agent can write arbitrary code in the sandbox, you need to scope what the SDK bindings can access. The code runner should only have MCP tool imports, not raw HTTP or OS calls.
- **Batching can hide failures.** A script that calls 10 tools and returns only the last result will silently drop 9 intermediate errors. Each tool call inside the script needs its own error handling that surfaces to the aggregator.
- **SDK binding lag breaks the agent's mental model.** If the SDK version in the sandbox differs from the MCP server version, the agent writes calls that fail with cryptic errors. Pin SDK versions and surface version mismatches as explicit tool errors, not generic script failures.
- **This pattern trades context for latency.** Code execution adds a round-trip (model → script → results → model). For single-step tasks, it's net negative. The compression pays off only at 5+ tool calls per step or when tool definition overhead exceeds ~2,000 tokens.
