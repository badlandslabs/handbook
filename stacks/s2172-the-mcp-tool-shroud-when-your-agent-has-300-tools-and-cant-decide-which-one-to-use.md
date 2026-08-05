# S-2172 · The MCP Tool Shroud — When Your Agent Has 300 Tools and Can't Decide Which One to Use

You've got 13,230+ MCP servers available. Every team that shipped an AI feature also shipped an MCP server for it. Your agent has access to a filesystem, three databases, a Slack integration, a GitHub integration, two vector stores, a Postgres playground, a Slack summarizer, a Stripe handler, a Jira connector, and a HN feed reader. When you ask it to "fix the billing issue," it spends the first four tool calls trying to figure out which tool even knows about billing.

This is the MCP tool shroud: abundance becoming a liability. The protocol that was supposed to solve the N×M integration problem has created a new one — the agent that can't commit to a tool.

## Forces

- **MCP's growth outpaced tooling discipline.** The protocol went from 100K to 97M+ monthly SDK downloads in 13 months (Nov 2024–Dec 2025). That growth produced 13,230+ public servers by March 2026. Nobody published an official curated registry or a quality gate, so the ecosystem is raw. — [OpenClaw MCP Guide](https://openclaw.direct/mcp-guide/model-context-protocol-examples)
- **More tools degrade agent selection accuracy.** Multiple independent sources (Chroma's context rot research, arxiv.org's memory survey, the MCP benchmark literature) confirm that tool count beyond ~15–20 meaningful tools causes non-trivial accuracy drops. The agent's tool-routing performance degrades before any single tool call fails.
- **MCP makes it trivially easy to add tools, which makes it trivially easy to oversupply.** Unlike custom integrations that require engineering effort, an MCP server ships as a config line. Teams add them speculatively. The marginal cost of one more tool is near zero; the marginal cost to the agent's decision quality is paid gradually and invisibly.
- **Loop detection is unsolved in MCP agents.** An Ask HN thread asking "how do you prevent MCP agents from looping in production?" sat unanswered for 41 minutes — not for lack of effort, but because no vendor has shipped a purpose-built solution. Agents re-call tools that partially succeeded or that self-correct and re-trigger. Without a loop-enforcement layer, a misconfigured MCP agent can exhaust resources indefinitely. — [Signals from Tomorrow / RADAR, 2026-03-13](https://signalstomorrow.com/posts/2026-03-13-mcp-agent-looping-in-production-and-the-emerging-t.html)
- **Security surfaces explode with tool count.** Every MCP server is an attack surface. An agent with filesystem + network + database access can chain those permissions into destructive operations. The "USB-C for AI" analogy works until you plug in a malicious peripheral.

## The move

The move is tool economy: curate a small, coherent tool surface, enforce explicit routing logic, and build loop detection into the agent harness rather than relying on the agent to self-correct.

**Specific tactics:**

- **Install MCP servers in two tiers: core (always-on) and contextual (task-scope).** Core tools (filesystem, web search, a memory store) stay loaded. Contextual tools (Jira, Stripe, Postgres) get dynamically registered per task and deregistered on completion. This is the pattern DBHub, Context7, and the Google MCP Toolbox use — token-efficient and scope-limited.
- **Pick from the proven trinity before adding anything.** Context7 (37K+ downloads, fetches up-to-date API docs to fight hallucinations), a filesystem server, and a memory store cover 95% of use cases. Every additional server needs a documented justification and a test that it doesn't degrade routing accuracy. — [Awesome MCP Servers, Dec 2025](https://github.com/hireblackout/awesome-mcp-servers)
- **Implement tool call rate limiting and deduplication at the harness level.** Don't rely on the LLM to notice it's calling the same tool repeatedly with minor variations. A middleware layer that tracks (tool_name, args_hash, result_similarity) and terminates or re-prioritizes after N similar calls within a window is the only reliable loop guard. This is the category nobody has shipped yet.
- **Use tool description engineering as a filter.** Every MCP tool ships with a description field. Write descriptions that are specific about preconditions and failure modes, not just what the tool does. Vague descriptions ("interacts with a database") get selected in wrong contexts. Precise ones ("executes read-only SELECT on the orders table; returns JSON array; requires orders_db connection") reduce misrouting.
- **Benchmark routing accuracy as tool count grows.** Track what percentage of tool selections are correct on a fixed eval set. Set a threshold (e.g., 95%) and treat any tool addition that drops below it as a regression. This is the only objective measure; subjective "seems fine" is not sufficient.

## Evidence

- **MCP ecosystem metrics:** 97M+ monthly SDK downloads (TypeScript + Python combined), 13,230+ public servers, adoption across Claude, ChatGPT, Cursor, Windsurf, Gemini, Microsoft Copilot, VS Code, Azure, and AWS. SDK downloads grew 970× in 13 months. — [OpenClaw MCP Guide](https://openclaw.direct/mcp-guide/model-context-protocol-examples) · [Xenoss Enterprise Analysis, Sep 2025](https://xenoss.io/blog/mcp-model-context-protocol-enterprise-use-cases-implementation-challenges)
- **MCP agent loop failure is unaddressed:** An Ask HN thread titled "How do you prevent MCP agents from looping in production?" received no responses for 41 minutes. Zero purpose-built tools exist for this. The failure manifests as re-calling tools that partially succeeded, triggering self-correcting operations that re-trigger themselves, and ambient tool calls where the agent keeps the tool "warm" by re-reading its output. — [Signals from Tomorrow / RADAR, 2026-03-13](https://signalstomorrow.com/posts/2026-03-13-mcp-agent-looping-in-production-and-the-emerging-t.html)
- **Top MCP server pattern:** DBHub (bytebase/dbhub, 3.3K+ GitHub stars) is the top-ranked Postgres MCP server for production use. Memory Vault (1.5K+ stars) handles cross-session state. The pattern that wins: minimal permissions, token-efficient responses, schema-aware query construction. The servers that lose: those that return raw dumps and let the agent figure out what matters. — [Skillselion MCP Rankings, Jul 2026](https://skillselion.com/best/postgres-mcp-servers)

## Gotchas

- **"We'll add tools later" is the start of the shroud.** Teams start with 5 tools, add 2 per sprint, and end up with 40. By the time routing accuracy degrades enough to notice, nobody remembers why half the tools were added.
- **Tool descriptions default to vendor boilerplate and get worse under pressure.** When teams do add tools, they copy-paste the MCP server's default description. These are written for discoverability, not for agent routing. Rewrite every tool description with routing context: what triggers it, what it needs, what it returns, and what it does NOT handle.
- **MCP server version drift is invisible.** A server that worked at v1.0 may have changed its schema at v1.3. If the agent's tool definition is cached, it operates with a stale contract. Pin server versions and re-validate on every dependency update.
- **Loop detection cannot be prompt-engineered away.** Adding "do not call this tool more than 3 times" to the system prompt does not work in production under load or when the agent has a legitimate multi-call reason. The enforcement must be at the execution harness level, not the prompt level.
