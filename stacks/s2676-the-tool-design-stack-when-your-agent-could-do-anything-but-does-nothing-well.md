# S-2676 · The Tool-Design Stack — When Your Agent Could Do Anything but Does Nothing Well

You've got 47 tools. The agent ignores 44 of them, misuses 2, and the last one does the wrong thing. Sound familiar? The failure is almost never the model — it's the tools. This stack covers what tools agents actually use in production, what tool design looks like from primary sources, and the specific mistakes that make tools useless for non-deterministic systems.

## Forces

- **The tool buffet problem** — giving agents everything "just in case" causes context bloat, hallucination spikes, and tool-selection failures. More tools don't help; the right tools do
- **Designed for humans, not agents** — most tools are built as developer APIs with implicit assumptions about determinism, error handling, and contract behavior that don't hold in agentic loops
- **The stale-state failure mode** — agents often understand what to do but operate on outdated page state, leading to wrong clicks, failed forms, and silent failures that look like success
- **Context window is a finite resource** — each tool's name, description, and schema competes for space that matters for reasoning

## The Move

Design tools for non-deterministic systems, not deterministic ones. Then give the agent exactly what it needs to succeed — no more.

### Tool design principles (cross-confirmed: Anthropic, browser-use community, Frigade)

- **Name verbs, not nouns.** `create_issue`, `send_email`, `fetch_page` — the agent acts on things. `issue_tool`, `email_client` mislead it toward selecting rather than executing
- **Descriptions explain the action and side effects.** State what changes in the world: "Creates a Jira issue in project PROJ-123. Returns the issue key and URL. May take 5–10 seconds." Avoid "helper function for issue creation"
- **Input schemas are strict contracts.** The agent can pass unexpected types. Define `type`, `required`, `enum`, and `default` for every parameter — don't leave ambiguity that the model has to guess
- **Return structured, minimal data.** Return only what the next step needs. Full API responses bloat context; sparse returns force the agent to work harder to assemble meaning
- **Design for retry, not just success.** Agents will fail mid-execution. Each tool should fail with clear, parseable error messages that give the agent enough to course-correct
- **Group related tools behind one interface.** Rather than 8 file tools, one `file_operations` tool with a `command` parameter (read/write/list/delete) reduces tool-selection overhead

### The tool stack that ships in production

1. **Browser automation** (browser-use, agent-browser-protocol, mcp-server-browser-use) — the dominant web tool. Browser Use (MIT, #1 on Odysseys leaderboard at 87.4%) is the reference implementation. The Agent Browser Protocol (155 HN points) takes a different bet: freeze JS after every action to solve stale-state failures. These are not the same approach
2. **Code execution** (sandboxed: E2B, Daytona, clawool) — run untrusted agent code in isolation. Clawk's pattern: disposable Linux VM with the project toolchain, secrets stay on host, disk is the only loss on failure
3. **MCP as the integration protocol** (modelcontextprotocol.io) — Anthropic explicitly recommends MCP (September 2025) for connecting agents to tools. Frigade auto-generates MCP servers by reverse-engineering a web app's own API calls (Show HN, ~2025). Browser-use ships a native MCP server; Saik0s/mcp-browser-use has 958 GitHub stars as the community wrapper
4. **Tool retrieval** (Ratel) — when you genuinely need 50+ tools, use retrieval-augmented tool selection rather than dumping all names. Ratel's approach: hybrid BM25 + semantic retrieval, progressive disclosure per turn. The agent keeps the full catalog; only relevant tools surface

### The minimum viable tool set (from production reports)

Most successful single-agent setups use 3–5 tools: a web browser, a code interpreter, a file read/write pair, and one domain-specific API. Expand only when the agent demonstrably fails without the new tool.

## Evidence

- **Anthropic Engineering Blog (September 2025):** "Writing effective tools for AI agents" — the canonical source on tool design for non-deterministic systems. Core thesis: tools are contracts between deterministic systems and agents, requiring fundamentally different design than developer APIs. Describes a build-and-test prototype loop with Claude optimizing its own tools. — [URL](https://www.anthropic.com/engineering/writing-tools-for-agents)
- **browser-use GitHub / Launch HN (February 2025):** YC W25 company, MIT license, #1 on Odysseys benchmark at 87.4% (200 long-horizon web tasks). Cross-confirmed by multiple MCP server wrappers (Saik0s/mcp-browser-use, 958 stars; JovaniPink/mcp-browser-use, 61 stars). — [URL](https://github.com/browser-use/browser-use)
- **Hacker News, Show HN — Agent Browser Protocol (2025):** 155 points, 55 comments. Distinct approach: freeze JS execution after each action to solve stale-state — "the model often understands correctly; the real issue is the agent is reasoning from stale state." Cross-confirmed the problem exists across all browser-agent approaches. — [URL](https://news.ycombinator.com/item?id=47336171)
- **Hacker News, Show HN — Frigade (2025):** Reverse-engineering web apps into MCP servers by observing their own API calls. "Auto-generated MCP server that self-updates as the host app changes." Confirms MCP as the production integration standard. — [URL](https://news.ycombinator.com/item?id=48847834)
- **Hacker News, Show HN — Ratel (2025):** Tool/skill retrieval to solve context bloat. "Let your agent keep its full catalog, but progressively disclose only the few that actually matter for each turn." Confirms the tool-buffet problem is real enough to spawn dedicated solutions. — [URL](https://news.ycombinator.com/item?id=48936491)

## Gotchas

- **Tool descriptions are not docstrings.** Writing "this tool does X" is not a description — it's a label. The agent needs context: when would it call this, what does the world look like after, what can go wrong, what does success look like
- **Returning too much data is as harmful as returning too little.** A tool that returns 50 fields for a task that only needs 2 is a context-bloating liability. Be surgical
- **Sandboxing is not optional for code execution.** Giving an agent direct shell access to the host is not a gotcha — it's a known incident waiting to happen. E2B, Daytona, or clawk-style disposable VMs are the baseline
- **MCP server count is not the goal.** Having 200 MCP tools is not better than having 5 well-designed ones. The failure mode is tool-paralysis, not tool-hunger
- **Stale state is the invisible browser-agent killer.** Browser Use and ABP solve it differently (element extraction vs. JS-freeze). Pick the approach that matches your reliability requirements — element extraction is faster, JS-freeze is more correct
