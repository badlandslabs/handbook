# S-2255 · The Agent Tool Stack: When Your Agent Has No Hands But Wants to Use Them

Your agent is asked to book a flight, test a web app, write code, and check your calendar. It can't. It has no hands. The tool layer is where that changes — and where most agentic systems silently fail. This is about how practitioners actually connect agents to the world: browser automation, code execution sandboxes, MCP tool schemas, and the gaps between theory and production.

## Forces

- **Schema bloat taxes the context window.** MCP clients typically load all tool definitions upfront into context. A dozen tools with rich schemas can consume thousands of tokens per call — before the model does anything useful. Anthropic's engineering blog (Nov 2025) calls this "excessive token consumption" and proposes batching tool calls into a single code artifact. The model writes code that calls tools internally rather than the host repeatedly invoking each tool individually.
- **Browser state is a moving target.** Standard browser automation (Playwright, Selenium) exposes a websocket to the agent, but the DOM keeps changing between model reasoning and next action. The Agent Browser Protocol (ABP) fork of Chromium — 479 stars on GitHub, 155 HN points — freezes JavaScript execution after each action and captures the resulting state. The core claim: most browser-agent failures aren't about models misunderstanding pages; they're about reasoning from stale state.
- **Sandboxing is an afterthought until it's an incident.** Real HN threads (Ask HN "How are you sandboxing coding agents?", 46 points) reveal the gap between theory and practice: developers use git worktrees, devcontainers, or ad-hoc Docker setups. Nobody has a consistent story. Meanwhile, Runtime (YC P26, 103 HN points) and E2B both exist because "give the agent a VM" is the only answer that actually works for team-wide rollouts.
- **The tool schema itself is a prompt.** Anthropic's MCP spec treats tool `description` and `inputSchema` as behavioral directives the model reasons over. A poorly written description doesn't just cause errors — it shapes what the model attempts and how. This is distinct from SKILL.md poisoning (S-2254) but related: both are about trusting that the text injected into context is safe.

## The move

**Design tool interfaces as constrained APIs with behavioral descriptions, not freeform capabilities.**

- **Start with the minimal viable tool surface.** The browser-harness pattern (16,505 GitHub stars) uses exactly three components: a CDP daemon, a helpers.py with basic tools, and a SKILL.md. Agents can extend helpers.py during execution when they need a missing function. This is self-extending capability but with a stable harness boundary.
- **Use MCP as the protocol layer, not the abstraction layer.** The MCP spec defines how tools are described and invoked. Anthropic's code-execution-with-MCP approach shows the win: write code that calls multiple tools in one shot, rather than one tool call per context token. This reduces token consumption by batching.
- **Freeze state before the model reasons.** ABP's freeze-then-capture approach is the right model for any tool that produces observable state (browser, file system, UI). Capture the resulting state after each action, not just the action output.
- **Sandbox at the environment level, not the tool level.** HN practitioners converge on: Docker containers per task (most common), bubblewrap/Firejail for lightweight Linux namespace isolation, or cloud sandboxes (E2B, Modal, Daytona) for multi-tenant team use. Don't try to sandbox individual tool calls — isolate the entire execution environment.
- **Make tool descriptions do two jobs.** The description field should tell the model: (1) what the tool does, and (2) when to reach for it versus a similar tool. This is the routing logic, not a separate system prompt.
- **Self-healing over brittle schemas.** Browser-harness's approach — agent writes missing helpers during execution — is the pragmatic pattern. Tools that break and require manual redefinition create operational nightmares. Design for the agent to extend the tool surface, not just call it.

## Evidence

- **GitHub/Engineering Blog:** Anthropic engineering blog "Code execution with MCP: building more efficient AI agents" — describes the tool batching pattern and MCP context token problem with solution approach. Published Nov 4, 2025. — [URL](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **GitHub/Show HN:** Agent Browser Protocol (ABP) — theredsix/agent-browser-protocol — Chromium fork that freezes state after each action, 479 stars, 155 HN points. Solves stale-state problem in browser agents. — [URL](https://github.com/theredsix/agent-browser-protocol) | [HN](https://news.ycombinator.com/item?id=47336171)
- **GitHub/Launch HN:** Browser Use — browser-use/browser-use, 16,505 stars, MIT license, YC W25. Extractive element identification + structured action output pattern for browser automation. — [URL](https://github.com/browser-use/browser-use) | [HN](https://news.ycombinator.com/item?id=43173378)
- **GitHub/Launch HN:** Runtime (YC P26) — Sandboxed coding agents for teams. 103 HN points. Per-project isolated environments with agent permissioning for non-engineers. — [URL](https://news.ycombinator.com/item?id=48225040)
- **HN Ask Thread:** "How are you sandboxing coding agents?" — 46 points, 32 comments. Practitioner consensus on Docker, bubblewrap, Firejail, and cloud sandboxes. — [URL](https://news.ycombinator.com/item?id=46400129)
- **GitHub/Show HN:** Browser Harness — browser-use/browser-harness — Self-healing three-component harness (daemon + helpers.py + SKILL.md), 16,505 stars. — [URL](https://github.com/browser-use/browser-harness) | [HN](https://news.ycombinator.com/item?id=47890841)
- **Engineering Blog:** Elasticsearch Labs — "Agent memory on Elasticsearch" — Three-memory-type architecture (episodic, semantic, procedural) with R@10=0.89, zero cross-tenant leaks. — [URL](https://www.elastic.co/search-labs/blog/agent-memory-elasticsearch) | [HN discussion](https://news.ycombinator.com/item?id=48583703)

## Gotchas

- **Loading all MCP tools into context is the default and the mistake.** Anthropic explicitly calls this out as a production hazard. Lazy-loading or tool-batching is the fix.
- **Browser automation without state freezing is unreliable at scale.** Every production browser-agent deployment that uses raw Playwright/Selenium eventually hits a class of bugs where the model acts on a stale DOM. ABP's approach is more expensive (Chromium fork maintenance) but eliminates the failure mode.
- **Sandbox complexity scales with team size.** A solo developer using `npx claude-code` locally has no sandbox problem. A team of 20 non-engineers running agents against real codebases needs per-project isolation, permissioning, and audit logs — which is what Runtime and E2B solve. Don't under-scope the sandboxing for the actual deployment context.
- **Tool descriptions are interpreted as instructions.** A vague or misleading description doesn't just confuse the model — it redirects behavior. Treat every `description` field as a system prompt fragment.
