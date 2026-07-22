# S-1482 · The Tool Attenuation Stack — When More Tools Make Your Agent Dumber

Your agent has 47 tools. You've connected every MCP server, wired in every API, given the agent full access to GitHub, Slack, the filesystem, and the cloud. The agent can do anything. In practice, it picks the wrong tool 86% of the time. You added tools to increase capability. You decreased it. The teams that solved this stopped asking "how do I give the agent more tools" and started asking "which tools does this task actually need right now."

## Forces

- **Tool definitions are not free tokens.** Every tool schema — name, description, parameters, types — consumes context window space before the agent does any real work. A typical MCP server with 20+ tools can consume nearly 25% of a 200k context window at every inference call. This overhead degrades the agent's actual reasoning.
- **LLM tool selection accuracy collapses past a threshold.** Baseline tool selection accuracy with a large tool set was measured at **13.62%** in a production benchmark — not 80%, not 60%. Retrieval-augmented tool selection exposing only the top-N relevant tools improved this to 43%, with no change to tools or model.
- **MCP has made tool proliferation trivially easy, which is the problem.** GitHub MCP ships ~50 tools, Playwright ships 24+, Chrome DevTools ships 26+. Teams wire up every server "just in case" and end up with 60–100 tools loaded at every inference regardless of what the agent is actually trying to do.
- **Token overhead compounds with tool results.** Each tool call and its result travels through the context window. More tools means more opportunities for the agent to chain incorrect calls, each propagating error forward.
- **Anthropic's core recommendation:** "Start with the simplest solution. Agents trade latency and cost for task performance — only add complexity when the complexity is warranted."

## The Move

The core technique: **contextual tool attenuation** — exposing only the tools relevant to the current task, with the right level of abstraction.

### Narrow the visible toolset at reasoning time

- Route a RAG (retrieval-augmented generation) query against the agent's available tool catalog before each inference, returning only the top 5–10 most relevant tool schemas. This was measured at 3x accuracy improvement over no routing (13.62% → 43%) in a production system.
- Group related tools into **toolkits** that expose one cohesive interface rather than individual primitives. Instead of 12 separate GitHub API calls, expose a `github_issues` toolkit with a single `list_issues()` call that handles pagination and filtering internally.

### Expose MCP servers as code APIs, not direct tool calls

- Anthropic's recommended pattern: present MCP servers as code APIs the agent can write against, rather than loading all tool definitions upfront. The agent writes Python that calls the MCP server — tool selection happens at the code level, not the schema level. This reduces per-call token overhead dramatically for complex interactions.
- Use tool groups to scope which MCP servers are active per conversation or task type. An agent working on code review should not have Slack and monitoring tools in scope.

### Start minimal, compose as needed

- Give the agent the smallest viable tool surface initially. Add tools only when the agent demonstrably fails because it lacks capability — not in anticipation of future need.
- Anthropic's Claude Code architecture demonstrates this: a single-threaded master loop with a disciplined, tightly-scoped set of developer tools (shell, file edit, git, search). The five design values are human decision authority, safety/security/privacy, reliable execution, debuggability/transparency, and long-horizon task support — in that priority order.

### Gate expensive operations explicitly

- The single highest-leverage line in any production agent: wrap every tool that can spend money, send a message, or modify a database row in a `RequireApprovalInTheLoopMiddleware`. Keep humans in the loop for irreversible actions regardless of how confident the agent is.
- Implement permission escalation patterns — agents can request access to escalated tools, and a human approves or denies within the same conversation context.

### Design tool schemas for model comprehension

- Keep parameter structures flat. Nested dictionaries and complex types invite the model to hallucinate parameter values. Prefer string-enum parameters with explicit allowed values.
- Write tool descriptions as action verbs describing what the tool does and what it returns. Avoid abstract technical descriptions — the model needs to understand the semantic effect of calling the tool.

## Evidence

- **Engineering Blog:** Anthropic's "Code Execution with MCP" (Nov 2025) documents the token overhead problem with direct tool definitions and recommends the code-API pattern as a solution. — [modelcontextprotocol.io](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Engineering Blog:** Anthropic's "Building Effective Agents" (Dec 2024) establishes the core principle that the most successful implementations use simple, composable patterns — and explicitly recommends starting with minimal tools and adding complexity only when warranted. — [anthropic.com](https://www.anthropic.com/engineering/building-effective-agents)
- **Independent Blog:** tianpan.co's "The Over-Tooled Agent Problem" (April 2026) reports a production benchmark where baseline tool selection accuracy was 13.62% with a large tool set, improving to 43% with RAG-based tool selection — a 3x improvement from reducing tool visibility alone. — [tianpan.co](https://tianpan.co/blog/2026-04-19-over-tooled-agent-problem)
- **Engineering Blog:** kvg.dev's "Stop Drowning Your Agent in Tools" (Jan 2026) by Kurtis Van Gent (Google Cloud) documents specific MCP server tool counts and their overhead: GitHub ~50 tools, Playwright 24+, Chrome DevTools 26+, each consuming significant context at every inference call. — [kvg.dev](https://kvg.dev/posts/20260110-tool-bloat-ai-agents)
- **arXiv Study:** "Dive into Claude Code: The Design Space of Today's and Future AI Agent Systems" (arXiv:2604.14228, revised July 2026) analyzes Claude Code's architecture — single-threaded master loop with tightly-scoped developer tools — and identifies five core human values driving the design: human decision authority, safety/security/privacy, reliable execution, debuggability/transparency, long-horizon task support. — [arxiv.org/abs/2604.14228](https://arxiv.org/abs/2604.14228)
- **Research Survey:** Anthropic's "2026 State of AI Agents Report" (Material Research survey, 500+ technical leaders) found 57% of organizations deploy agents for multi-stage workflows and 81% plan to tackle more complex use cases in 2026 — a trajectory that makes tool management increasingly critical at scale. — [anthropic.com](https://resources.anthropic.com/hubfs/The%202026%20State%20of%20AI%20Agents%20Report.pdf)
- **NIST Consortium:** "Lessons Learned from the Consortium: Tool Use in Agent Systems" (NIST, August 2025) — ~140 experts identified that no comprehensive taxonomy of agent tools exists across the AI supply chain, confirming that tool classification and scoping remain open problems in production deployments. — [nist.gov](https://www.nist.gov/news-events/news/2025/08/lessons-learned-consortium-tool-use-agent-systems)

## Gotchas

- **Tool bloat hides as a good practice.** Connecting every MCP server "for flexibility" is the most common and most damaging mistake. The flexibility is an illusion — the agent gets worse at using any of them.
- **RAG-based tool selection adds latency.** Retrieving relevant tool schemas before each inference is not free. The accuracy gains (3x in benchmarks) typically outweigh the latency cost, but profile for your specific tool catalog size.
- **Tool result handling is where agents lose the thread.** Even with perfect tool selection, agents frequently mishandle results — discarding partial outputs, failing to chain related calls, or giving up after one failed attempt. Plan for result-handling patterns, not just tool selection.
- **Permission gating must be integrated, not bolted on.** Adding approval middleware after the fact creates race conditions and UX friction. Design it into the tool-calling loop from the start.
