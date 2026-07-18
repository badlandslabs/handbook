# S-1280 · The Tool Spectrum — From Function Calls to Computer Use

When you give an agent a tool, you're not just extending its capabilities — you're choosing a point on a reliability-versus-reach tradeoff. A well-described function call is predictable, traceable, and cheap. Full computer use is maximally expressive but maximally fragile. The production mistake is treating these as interchangeable, or defaulting to the powerful end without understanding what you're trading away.

## Forces

- **Computer use sounds like the obvious choice** — if an agent can use a browser or desktop like a human, why constrain it? But raw computer use carries stale-state failures, massive token overhead, and environmental variance that deterministic tools avoid entirely.
- **Deterministic tools are boring and limited** — you have to anticipate every capability in advance. But they're fast, cheap, auditable, and consistent. Claude Code's entire toolset is 8 deterministic tools: Bash, Read, Edit, Write, Grep, Glob, Task (sub-agents), TodoWrite. That's the full arsenal.
- **MCP solved the "tool sprawl" problem** but introduced a new one — agents can now discover and invoke hundreds of tools dynamically, but the token cost of describing them all exceeds what fits in context. Anthropic's Tool Search feature cuts that by 85% but adds latency.
- **Environmental variance is catastrophic** — agents with 90% success on Windows 11 can drop to 9% on Windows XP for the identical task. The same agent underperforms dramatically across macOS, Linux, Android. Benchmark divergence is real and production-relevant.

## The move

**Map your tools onto the spectrum, not a single point.** The production pattern that works is a layered stack:

- **Tier 1 — Deterministic function calls** for everything you can anticipate. Web search, database queries, API calls, file reads. These go in the system prompt as tool definitions. They're fast (no LLM-in-the-loop per action), cheap, and auditable. Use MCP servers to expose them — this is the 2026 mainstream for enterprise agents (ConfigAssist-style chatbots, enterprise copilots, data pipeline orchestrators).

- **Tier 2 — Structured code execution** for agent-authored logic that needs to run safely. WASM sandboxes (Amla Sandbox, E2B, Modal) give agents a bash/Python runtime without Docker overhead or full VMs. Amla ships as a single 11MB binary with a WASM shell — no subprocess, no SaaS dependency. The host controls what operations are yielded back. This is the sweet spot for "run the code the agent generated."

- **Tier 3 — Browser automation** for web interaction you can't replace with APIs. The Agent Browser Protocol (ABP) — a Chromium fork purpose-built for agents — solves the core stale-state problem: modals appearing after the last screenshot, dynamic filters causing reflow, autocomplete dropdowns covering targets. ABP intercepts these at the Chromium level rather than fighting them with Playwright/Puppeteer overlays. Claude Code uses this tier. Zero token cost for deterministic replays — record once, replay at zero inference cost.

- **Tier 4 — Full computer use** (mouse + keyboard + screen) for legacy desktop apps with no API and no web interface. Cyberdesk (YC S25) automates Windows legacy apps (healthcare, accounting, construction) by reading screen state before every action and self-correcting when flows drift. This is the highest-reach, highest-risk tier. Isolated VMs are non-negotiable for regulated industries.

- **Tool Search (dynamic discovery)** as a meta-tool when the agent genuinely can't know in advance which tool it needs. Anthropic's Nov 2025 beta ships this: the agent queries a tool registry at runtime, reducing the token cost of a large tool collection by 85%. Tradeoff: added latency per tool invocation and dependency on registry availability.

## Evidence

- **Anthropic engineering blog (Nov 2025):** Introduced three advanced tool-use features — Tool Search (85% token reduction on large tool sets), Programmatic Tool Calling (37% token reduction via parallel execution), and Tool Use Examples (accuracy on complex parameter handling improved from 72% to 90%). ConfigAssist Bot uses these to handle complex product support without context overflow. — https://www.anthropic.com/engineering/advanced-tool-use

- **Claude Code architecture analysis (Latent Space + penligent.ai):** Claude Code runs a `while(tool_call)` loop — no DAGs, no classifiers, no RAG. The model decides everything. Search strategy evolved from RAG (Voyage embeddings) to grep-based search after internal benchmarks showed superior performance with lower operational complexity: no index sync, no external embedding provider security liabilities. The "Search, Don't Index" philosophy. — https://cc.bruniaux.com/guide/architecture ; https://www.penligent.ai/hackinglabs/inside-claude-code-the-architecture-behind-tools-memory-hooks-and-mcp

- **Cua-Bench benchmark (Show HN, ~mid 2026):** Open-source framework for evaluating computer-use agents across OS environments. Documents 10× performance variance between Windows 11 (90%) and Windows XP (9%) for the same agent and task. Agents tested on Windows 11/XP/Vista, macOS themes, Linux, Android via QEMU. — https://news.ycombinator.com/item?id=46768906

- **Agent Browser Protocol (Show HN):** Chromium fork purpose-built for AI agent browser automation, purpose-built to solve stale-state race conditions. Runs in-page (tab's own execution context) so auth headers, CSRF tokens, and signed requests propagate naturally — no separate auth stack. 155 HN points, 55 comments. — https://news.ycombinator.com/item?id=47336171

- **Amla Sandbox (Show HN):** WASM bash shell sandbox for AI agents. No Docker, no subprocess, no SaaS. Host controls yielded operations. 146 HN points, 73 comments. — https://news.ycombinator.com/item?id=46824877

- **MCP in production (Lucidworks, Nov 2025):** Enterprise deployment case studies across customer support chatbots, commerce assistants, enterprise copilots. ConfigAssist Bot uses MCP to access product configuration, order history, and troubleshooting knowledge. Security and compliance as primary driver for structured MCP over ad-hoc tool definitions. — https://lucidworks.com/blog/real-world-examples-of-mcp-in-action-from-chatbots-to-enterprise-copilots

- **Claude Computer Use enterprise guide (Inductivee, May 2026):** Production deployment patterns for Anthropic's October 2025 computer use beta. Threat model analysis, sandboxing architecture, permission boundaries. Recommends dedicated VMs with no network access for Tier 4 deployments. — https://inductivee.com/blog/claude-computer-use-enterprise-guide

## Gotchas

- **Defaulting to computer use when function calls suffice.** Raw computer use is 10-100× more token-intensive than a well-described function call. Use computer use only when you have no API, no structured data source, and no deterministic alternative.
- **Tool descriptions inflate context until they collapse usefulness.** The seductive path is adding more tools with richer descriptions. MCP with dozens of servers quickly exceeds context limits. Tool Search solves this but introduces registry dependency and latency. Audit your tool inventory the same way you'd audit dependencies.
- **Sandbox escape is the production risk nobody talks about publicly.** The DataTalks database wipe (Claude Code) and Replit agent deleting data during code freeze are the known incidents. WASM sandboxes like Amla and process-level isolation reduce blast radius but don't eliminate it. For regulated industries, OS-level sandboxing with dedicated VMs is the minimum bar.
- **Environmental variance kills production confidence.** An agent that works in your test environment on macOS may have 9% success on a Windows XP VM. Cua-Bench exists precisely because teams discovered this too late. Test across your actual target environments, not just your preferred one.
