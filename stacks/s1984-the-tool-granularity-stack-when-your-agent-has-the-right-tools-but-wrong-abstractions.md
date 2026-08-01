# S-1984 · The Tool Granularity Stack — When Your Agent Has the Right Tools but Wrong Abstractions

[Your agent has web search, a code interpreter, a filesystem tool, and an API client. The task is "find our top 5 competitors and summarize their pricing." The agent spends 40 minutes making 200 API calls because it doesn't have a "batch competitor analysis" tool. It gets rate-limited on call 87. It has all the right primitive capabilities and zero of the right composed ones. This is a tool granularity problem: you gave your agent hands, not workflows.]

## Forces

- **Primitive tools are safe but verbose.** Every operation is a discrete tool call with its own result parsing, error handling, and retry logic. The agent spends more tokens reasoning about *how* to chain tools than doing the actual work.
- **Coarse tools are powerful but brittle.** A single "do competitor analysis" tool works until the API changes, the output format shifts, or the task has a novel edge case — then the agent has no visibility into what went wrong.
- **Tool count is a lie.** Teams often benchmark on "how many tools does your agent have" rather than "how well do those tools map to task shapes." An agent with 50 tools that each do one thing loses to an agent with 5 tools that do the right things.
- **LLMs hallucinate tool parameters, not just outputs.** When a tool's schema is complex, the model invents plausible-looking parameters that pass validation but produce garbage. The tool executes successfully and the agent acts on bad data.
- **Security and capability trade off at every level.** Sandboxed code execution is safe but slow and stateless. Direct filesystem access is powerful but enables path traversal. You can't give your agent full capability without full risk.

## The move

**Design tools at the task-solution grain, not the operation grain.** Start with the most atomic safe primitive, then compose upward only where you observe the agent repeatedly chaining the same sequence.

1. **Audit your current toolset by observing call chains.** Log every 3+ tool sequence that executes without user intervention. If you see the same 4-tool chain running 50 times a day, that chain is a tool. The agent should not have to reconstruct it from primitives every time.

2. **Three tiers of tool abstraction.** Level 1: atomic primitives (search, fetch URL, execute Python, read file). Level 2: domain-composed (analyze competitor, extract structured data, run QA check). Level 3: task-specific (full competitor report, end-to-end form fill, job application). Ship Level 1 for flexibility, Level 2 for reliability, Level 3 only when the task is fully characterized.

3. **Give tools honest schemas, not "describe everything" prompts.** A tool with 20 parameters where the agent only needs 3 is worse than a tool with 3 parameters. The model fills the rest with plausible guesses. Fewer, more specific parameters > many optional ones.

4. **Sandbox everything that writes, constrain everything that reads.** Filesystem writes, API POSTs, and code execution go into isolated sandboxes (E2B, gVisor, container-per-agent). Web fetch and search can be direct. Reads from internal systems get allowed-list filtering before the data reaches the agent.

5. **Make tool failure visible and actionable.** When a tool fails, the error should tell the agent *what happened* and *what to try instead*, not just "tool call failed." Tools that return `{"status": "error", "message": "rate limited, retry in 30s"}` enable the agent to self-correct. Tools that return `{"error": true}` don't.

6. **Treat MCP as your tool contract layer.** Model Context Protocol (Anthropic, Nov 2024) is now the standard for agent-to-tool connection. One MCP server implementation connects to thousands of tools. Don't bake tool logic into the agent — decouple it. If you change your search provider, the agent should not notice.

## Evidence

- **Anthropic engineering post:** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." Their recommendation: start with LLM API + minimal tool definitions, compose only when the pattern recurs. — [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **GitHub repo:** Browser Use (107K stars, Oct 2024) provides 6 high-level tool capabilities — form fill, data extract, QA automation, web scrape — that map directly to task shapes, rather than exposing raw CDP/Playwright primitives. — [browser-use/browser-use](https://github.com/browser-use/browser-use)
- **HN production thread:** "We sandbox AI agents in production — per-agent isolation (gVisor), default-deny egress with proxy-only outbound, deterministic filespace sync, and audit logs for every tool call." The insight: the agent got full capability by getting constrained capability safely. — [HN: We Sandbox AI Agents in Production](https://news.ycombinator.com/item?id=46810589)
- **AliveMCP guide:** "The core challenge: unsanitized LLM-provided input reaching an external system. LLMs generate structured output but are not security-aware. A model asked to 'read user's SSH keys' may generate `../../../home/user/.ssh/id_rsa` as the answer. The MCP server must reject this before it reaches the OS." — [Building Real-World MCP Tools](https://alivemcp.com/blog/mcp-server-real-world-tools-guide)
- **Intuned (YC S22):** Built on Claude Agent SDK, uses Playwright-based TypeScript/Python with managed infrastructure. The agent layer is decoupled from the execution layer — the same agent runs locally or in the cloud without tool signature changes. — [Launch HN: Intuned](https://news.ycombinator.com/item?id=48445171)

## Gotchas

- **"We have 40 tools" is not a differentiator.** Teams that ship 40 loosely-defined tools spend more time debugging tool-call loops than teams that ship 5 well-defined ones. Count tool *quality*, not quantity.
- **Tool descriptions are prompt injection surfaces.** If the tool's description includes example inputs or edge-case behavior the model wasn't told about, the model may treat those as instructions rather than examples.
- **Sandboxing adds latency.** E2B cold starts are ~150ms. For a single tool call this is fine; for an agent making 200 calls in a loop, it adds 30 seconds. Profile before assuming sandboxing is free.
- **Version skew between tool and agent is silent.** When your search API changes its response schema, the agent silently adapts its parsing to match the new shape — but only if it gets feedback. If the tool always returns 200, the agent assumes success. Make tools return semantic status, not just HTTP status.
