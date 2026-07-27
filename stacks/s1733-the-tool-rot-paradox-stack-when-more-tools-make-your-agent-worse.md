# S-1733 · The Tool Rot Paradox Stack — When More Tools Make Your Agent Worse

You built an agent with 40 tools. It aced the demo. In production it selects the wrong tool, ignores critical ones, and burns tokens calling irrelevant APIs. The problem is not the tools — it is the number of them. Every tool you add to an agent's context degrades its ability to choose and use any single one correctly.

You reach for this when you treat tools like npm packages, when the demo works but production fails, when tool-call accuracy drops after adding new capabilities, or when your agent ignores the perfect tool sitting in its context window.

## Forces

- **The context-window tax** — exposing 40 tool schemas simultaneously dilutes the signal; the model receives more noise per token, degrading instruction-following on all of them
- **Schema competition** — similar tool descriptions interfere with each other; the agent picks the wrong one because no tool is clearly dominant in the context
- **The demo halo** — few-shot examples in development sessions are short and clean; production inputs are messy and long, revealing tool-selection brittleness that demos never surface
- **The "install more skills" reflex** — the natural response to agent failure is adding tools, which compounds the root problem

## The move

The fix is not fewer tools — it is **tool subset selection at call time**. The agent decides which tools are relevant to this specific task, and only those are activated.

- **Relevance scoring before dispatch** — run a lightweight LLM call (or embedding similarity) over the available tool list against the current task to rank them; activate only the top-k
- **Task-mode routing** — define 3-5 coarse modes (e.g., "code", "research", "data", "web") and pre-select a tool subset per mode; modes are selected by a classifier on the user request
- **Progressive tool exposure** — start each session with a minimal set (5-8 tools); expose more only when the agent signals it needs them, or after the initial plan is formed
- **Tool grouping via MCP servers** — use MCP to organize related tools into servers; expose the server (not individual tools) to the agent's top-level context, letting it request expansion on demand
- **Token-budgeted schema injection** — rank tools by estimated call frequency for the current session and inject schemas only up to a token budget; tools below the cutoff are accessible via a "find more tools" meta-tool
- **Eval on tool selection, not just output** — measure which tool the agent chooses given a task; if accuracy drops below threshold after a tool addition, that addition is causing regression, not improvement

## Evidence

- **Reddit r/AI_Agents (primary):** "Tool Rot Paradox: Why installing 50+ agent skills in development breaks down in production" — practitioner documents three failure modes: context-window dilution, schema interference, and demo-vs-production divergence. Observes that adding tools in response to failure is the most common mistake and makes the problem worse. — [r/AI_Agents](https://www.reddit.com/r/AI_Agents/comments/1v72phr/tool_rot_paradox_why_installing_50_agent_skills/)
- **ClickHouse (primary):** MCP framework comparison documents 12 agent SDKs with MCP support. Notes that MCP's core value is tool standardization across frameworks — but the authors explicitly warn that MCP's ease of adding servers can lead to the same tool-bloat problem if not managed. — [ClickHouse Blog](https://clickhouse.com/blog/how-to-build-ai-agents-mcp-12-frameworks)
- **Anthropic engineering (primary):** Claude Agent SDK design doc emphasizes giving agents "a computer" with focused tool sets rather than exhaustive tool access. Notes that Anthropic's own production agents use tool activation patterns, not flat tool lists. — [Anthropic Engineering](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)

## Gotchas

- **Curating the minimal set is harder than adding tools** — it requires understanding which tools are actually called in practice, which requires telemetry most teams skip
- **Tool-grouping by category (not alphabetically) is critical** — alphabetical schemas are indistinguishable noise to a model; semantic grouping helps it narrow faster
- **Progressive exposure can break agent confidence** — if the agent asks for a tool and it is not available, you need a graceful fallback or it will hallucinate the tool's output; design the "not available" response explicitly
- **The MCP server pattern helps but does not fully solve it** — servers reduce top-level clutter but the agent still needs to know which server to request; you still need task-mode routing upstream
