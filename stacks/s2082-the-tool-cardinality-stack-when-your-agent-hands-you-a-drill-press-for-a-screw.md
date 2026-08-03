# S-2082 · The Tool Cardinality Stack

When your agent with 23 MCP tools calls the wrong one, hangs on tool selection, or runs up token costs with descriptions it never reads — the fix is not a better model. It is a smaller, sharper tool surface.

## Situation

Every team that connects an agent to real systems starts with the same impulse: give the agent everything it could ever need. GitHub, Postgres, Slack, filesystem, web search, a dozen REST APIs. The ecosystem makes this trivially easy — 17,000+ MCP servers publicly listed, each exposing one or more tools. But the data shows a consistent failure mode: adding tools past a threshold degrades performance, and most teams discover this only in production.

## Forces

- **Reach vs. precision** — you want the agent to have broad capability, but broad surfaces cause misfires on narrow tasks
- **Generality vs. bloat** — a generic filesystem tool covers everything; a specific `read-test-output` tool costs more to build but degrades context far less
- **Ease of addition vs. cost of inclusion** — MCP makes adding a tool a one-liner; the cost is paid at inference time, not at authoring time
- **Tool description overhead** — every tool in the agent's context window competes for selection; LLMs cannot "ignore" tools the way a human clears a workbench
- **Specialization premium** — software/IT tools dominate usage (90% of MCP downloads) but also dominate context bloat

## The Move

**Curate the tool surface ruthlessly, then specialize what remains.**

- **Count your active tools.** The Zuplo State of MCP survey (Dec 2025, n=92) found 70% of users run 2–7 MCP servers simultaneously. The Zuplo report and EclipseSource both flag 50+ servers as a performance degradation threshold. Know your number and treat it as a budget.

- **Split fat tools into lean ones.** A single `run_shell_command` tool that can do anything forces the model to reason about every possible shell operation. Split by task phase: `install_dependencies`, `run_tests`, `read_build_output`. Each narrower tool has a shorter description and a cleaner invocation contract.

- **Load tools on-demand, not upfront.** The arxiv study on 177,436 MCP tools (Stein, UK AI Security Institute / Oxford, March 2026) shows the ecosystem has pivoted from perception tools (27% in 2024) to action tools (65% in 2026) — but action tools also carry heavier context overhead. Instead of registering all tools at session start, wire a dynamic tool-loading step: agent identifies the task domain, then the orchestrator adds only relevant tools to the context.

- **Prioritize by download weight.** The MCP.Directory analysis (March 2026) found software/IT tools represent 67% of tools but 90% of downloads. The top servers by stars are GitHub, filesystem, Slack, and Postgres. Build your core set from this shortlist before adding anything niche.

- **Instrument tool selection.** Track which tools get called, how often, and whether they succeed. The NirDiamant/agents-towards-production repo (21K stars, June 2025) includes observability as a core architecture component — specifically logging tool selection decisions alongside outcomes. Prune tools that are never called or called incorrectly.

- **Scope tool descriptions to intent, not capability.** A description listing every parameter and edge case trains the model to reason about the full surface. Rewrite for the decision the model needs to make: "Use this when you need to find a specific file by name. Returns path and first 10 lines." Not: "This tool executes ls with optional flags for..."

## Evidence

- **Research paper:** "How are AI agents used? Evidence from 177,000 MCP tools" — 177,436 tools across 19,388 servers tracked Nov 2024 – Feb 2026, action tool share grew from 27% → 65%, software/IT tools are 67% of tools and 90% of downloads — [arXiv:2603.23802](https://arxiv.org/abs/2603.23802)

- **Industry survey:** Zuplo State of MCP (Dec 2025, n=92 technical professionals): 72% expect MCP usage to increase, 70% run 2–7 servers simultaneously, 49% cite developer productivity as primary ROI — [zuplo.com/mcp-report](https://zuplo.com/mcp-report)

- **EclipseSource:** "MCP and Context Overload: Why More Tools Make Your AI Agent Worse" (Jan 2026): the handyman analogy — LLMs cannot "clear away" tools they don't need, and the generic nature of third-party MCP servers means you often get far more than you need — [eclipsesource.com](https://eclipsesource.com/blogs/2026/01/22/mcp-context-overload/)

- **HN discussion:** Hacker News thread on "too many tools" problem with developer quote: "If you have 50 MCP servers enabled, your requests are probably degraded" — [HN item #42523088](https://news.ycombinator.com/item?id=42523088)

- **Popular tools catalog:** MCP.Directory analysis (March 2026): top MCP servers by stars are GitHub, filesystem, Slack, Postgres, browser automation — [mcp.directory/blog/most-popular-mcp-tools-2026](https://mcp.directory/blog/most-popular-mcp-tools-2026)

- **Production examples:** Devin uses sandboxed shell + editor + browser tools; SWE-Agent (Princeton) exposes `search_code`, `read_file`, `write_file`, `execute_bash`; Harvey (legal) uses case law retrieval, compliance checks, document analysis — [os.moda](https://os.moda/blog/ai-agent-examples-production)

- **Production framework:** NirDiamant/agents-towards-production (21K stars) covers tool integration as a named architecture component with observability, security guardrails, and evaluation — [github.com/NirDiamant/agents-towards-production](https://github.com/NirDiamant/agents-towards-production)

## Gotchas

- **The "capability paradox"** — teams add tools expecting better performance; the arxiv study and multiple blog posts document the inverse: more tools → lower accuracy, higher failure rates, and increased context costs. More is not more.

- **Context window is not free** — each tool description, parameter schema, and example consumes tokens on every call. A 50-tool agent pays for 50 descriptions even when it uses 3. The cost compounds with model price per token.

- **Tool descriptions are instructions** — poorly written descriptions are prompt injections in reverse: they tell the model to reason about capabilities it shouldn't need for the current task. Treat each description as a micro-prompt, not documentation.

- **MCP server discovery is too easy** — Anthropic's "Building Effective AI Agents" guide recommends defaulting to simplicity. MCP's plug-and-play nature makes it trivially easy to accumulate tools; discipline must be applied at the team/process level, not assumed from the tooling.

- **Security surface scales with tools** — Zuplo's survey found 50% of builders cite security as their top challenge. Every tool is an access vector. A tool the agent never uses is also a tool an attacker might target if the agent can be steered.
