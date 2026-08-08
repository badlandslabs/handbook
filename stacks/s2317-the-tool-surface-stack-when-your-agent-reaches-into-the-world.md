# S-2317 · The Tool Surface Stack — When Your Agent Reaches Into the World

Your agent has access to 847 MCP servers. The model uses 4: web search, file read, file write, and bash. That's not a failure of the ecosystem — it's the selection pressure. The tool surface you give an agent isn't a menu to browse; it's a boundary to reason within. This is the stack for deciding what lives at that boundary, how the agent discovers it, and why the canonical set is surprisingly small.

## Forces

- **The zoo paradox.** The MCP registry has hundreds of servers. The typical production agent uses 3-7 tools. The gap isn't ignorance — it's that every additional tool increases context overhead, hallucinated tool calls, and failure surface.
- **Browser automation eats the most budget.** Web interaction is the most expensive tool class: screenshot frames, DOM parsing, retry logic on anti-bot detection. Teams that skip a purpose-built browser tool spend 3-5x more on LLM tokens trying to parse raw HTML.
- **Security and capability trade at the boundary.** Filesystem access unlocks real work. It also unlocks real damage. The tool surface is where you negotiate between what the agent can do and what you're willing to let it do.
- **Cloud-hosted tools collapse the ops burden.** Browserbase, Jina Reader, and Firecrawl run headless infrastructure as a service. The tradeoff: vendor lock-in, per-call pricing, and stealth/anti-bot quality that varies. Self-hosted Playwright + proxies costs more engineering, less money per call.

## The Move

Define a tiered tool surface with explicit rationale at each layer:

**Tier 1 — Core (always on):**
- `web_search` or equivalent — the agent's window to fresh information. Jina Reader (`r.jina.ai/<url>`) for single-URL markdown conversion; free, instant, no API key. Firecrawl for site-wide crawls and structured extraction (JSON schema, `/map` discovery).
- `filesystem` — constrained to project-scoped directories via MCP's Roots system, not global fs access. The agent reads configs, writes outputs, and touches nothing outside its working boundary.
- `bash` / `code_execution` — sandboxed shell access for running scripts, tests, and CLI tools. Pair with a timeout budget (max 60s per call) and a working directory constraint.
- `memory` / `context_retrieval` — not a tool in the traditional sense, but the agent's ability to retrieve prior context is the implicit tool that makes everything else coherent across turns.

**Tier 2 — Task-specific (opt-in per agent):**
- `browser_automation` — Browserbase + Stagehand (MCP) for agents that must interact with JavaScript-heavy sites, fill forms, or navigate authenticated sessions. Stagehand abstracts Computer Use model outputs into Playwright commands. For self-hosted: Playwright with proxy rotation.
- `api_client` — typed HTTP client for calling specific external APIs (weather, CRM, payment). Don't expose a generic HTTP tool; give the agent a purpose-built wrapper with clear input/output schemas.
- `messaging` — Telegram Bot, Resend (email), Slack webhook. These are outbound channels. Inbound polling (e.g., `getUpdates`) creates duplicate-processing risk — the Ultralab fleet hit 18 duplicate messages in 3 minutes from polling conflicts.

**Tier 3 — Orchestration-only (agent calls agents, not raw tools):**
- When a task needs domain-specific capability (e.g., security scanning, code review), spawn a sub-agent with that tool set rather than giving the parent agent all tools at once. OpenClaw's multi-agent fleet model uses this: separate agents for content, lead gen, security, and ops — each with a minimal tool surface scoped to its job.

## Evidence

- **GitHub repository (official):** MCP's reference servers repo (89K stars, 11K forks) lists 5 canonical tool categories: filesystem, git, fetch (web content), memory (knowledge graph), and prompts. These are what the MCP steering group considers the minimum viable tool surface. — [github.com/modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
- **Show HN (production report):** A solo developer in Taiwan runs 4 OpenClaw agents for content, sales leads, security scanning, and operations at $0/month LLM cost using Gemini 2.5 Flash. Tool stack: Jina Reader (web research), Resend (email), Telegram Bot (inbound), and custom API calls. Each agent has 4-6 tools max. The quality gate (self-review → rewrite if score < 7/10) is a lightweight verifier that replaces a heavy evaluation pipeline. — [news.ycombinator.com/item?id=47296664](https://news.ycombinator.com/item?id=47296664)
- **GitHub (open source):** Browserbase's Stagehand — 23,762 GitHub stars — provides the dominant browser automation SDK for agents. The MCP server bridges Stagehand's natural-language `act`/`extract`/`observe` interface to any MCP client. Firecrawl vs Jina analysis (Use Apify, March 2026) confirms: Jina is the free-tier default for single-URL lookups; Firecrawl is the production choice for full-site crawls with structured extraction. — [github.com/browserbase/stagehand](https://github.com/browserbase/stagehand)
- **Survey (arXiv 2025):** A systematic survey of AI agent architectures formalizes the tool layer as `T` in the agent tuple `(πθ, M, T, V, E)`, noting: "a practical pattern is a tool-use policy that prioritizes low-cost tools (retrieval, search) before escalating to high-cost ones (code execution, browser automation)." Cost-ordered tool selection reduces median task cost by 40-60% in multi-step tasks. — [arxiv.org/html/2601.01743v1](https://arxiv.org/html/2601.01743v1)

## Gotchas

- **Tool docstrings are the API contract.** The model decides whether to call a tool based on its name + docstring. A vague docstring produces either missed calls or hallucinated invocations. Write every tool description as: what it does, what it returns, when to use it, and when not to.
- **Streaming tool outputs can overflow context.** A verbose `grep` result or a full-page screenshot can consume 10-50% of a context window. Pipe outputs through summary or truncation steps before returning them to the agent.
- **Rate limits on cloud tools propagate.** Jina Reader has rate limits on its free tier. Browserbase has per-minute session limits. If the agent loops on a failed tool call, it can exhaust rate limit budget before the loop detection fires.
- **Browser anti-bot detection burns tokens.** Sites that fingerprint headless browsers produce DOM that looks nothing like the rendered page the agent expects. Use stealth-mode proxies (Browserbase Verified Identity, or Oxylabs/residential proxies) or switch to Computer Use model outputs that screenshot the actual rendered frame.
- **Polling tools create duplicate-processing risk.** Telegram's `getUpdates` long-polling conflicts with gateway polling — the Ultralab fleet processed 18 duplicate messages in 3 minutes from this. Use webhook-based inbound (Telegram Bot webhook, Resend inbound relay) instead of polling wherever possible.
