# S-1940 · The Tool Surface Stack — When Your Agent Has the Keys but Not the Map

You've given your agent a browser, a code executor, and three APIs. It can technically do the job. But it spends half its tokens deciding which tool to use, calls them in the wrong order, and crashes silently when one returns an unexpected shape. The capability is there. The control isn't. This is the tool surface problem — not what tools your agent has, but whether it understands the full terrain between them.

## Forces

- **More tools widen the blast radius.** Every tool is a potential failure mode. A 20-tool agent can fail in 20× more ways than a 2-tool agent, but most teams measure and test only the happy paths.
- **Tool descriptions are the agent's map.** When a tool's description is vague or generic, the agent has to guess at its purpose, inputs, and failure modes — and guesses cost tokens, time, and correctness.
- **Deterministic tools beat probabilistic ones.** APIs with known response shapes beat vision-based page scraping every time. But the web is full of cases where only a browser works.
- **State bleeds between tool calls.** The browser shows one page; by the time the agent clicks, a modal appeared. The database query returns; the agent assumes it's the same one from three steps ago. Tool loops feel agentic but often hide fragile implicit state.

## The Move

Give agents a **minimal, well-described tool surface** — not every capability you can imagine, but the smallest set that reliably covers the mission:

- **Prefer structured tools over vision for deterministic pages.** If an API or known endpoint exists, use it. Browser automation is for the messy 20% where nothing else works. Browser-Use GitHub (107k stars) specifically calls this out: use deterministic primitives first, add agent reasoning only where the web gets unpredictable.
- **Write tool descriptions as task briefs, not API docs.** Include: what the tool does, when to use it, what it returns, and the three most common failure modes. The agent reads these before every call — make them count. Compare: `"Query the CRM database"` vs `"Query HubSpot contacts by company domain. Returns up to 100 contacts with name, email, role. Fails with 403 if the API key is stale; returns empty array if no matches exist — do not treat empty as an error."`
- **Scope tools to atomic actions, not workflows.** One tool per step. A `book_flight` tool that internally sequences search → select → pay is a workflow, not a tool. Split it: `search_flights`, `select_flight`, `execute_payment`. Atomic tools compose; monolithic tools cascade.
- **Expose a retry protocol for every tool.** Agents need to know when a failure is retryable. Wrap tool responses with a `retryable: bool` and `suggested_alternative: string` field so the agent can self-correct without escalating to the user.
- **Use MCP as the tool integration layer.** The Model Context Protocol (Anthropic, Nov 2024) reached 97M+ monthly SDK downloads and 13,230+ public servers by early 2026. The N×M problem — N models × M tools — becomes N+M. Pick a tool integration standard and commit; MCP is the current leader in production adoption.
- **Instrument tool calls at the metadata level.** Log: which tool, when, input shape, output shape, latency, error type. Patterns in tool selection reveal where the agent gets lost — repeated `search` calls before a `click` often mean the agent doesn't trust the search results.

## Evidence

- **GitHub repo (browser-use):** The most-starred browser automation library for AI agents (107k stars) explicitly recommends starting with deterministic, structured tools before reaching for vision-based browser control. Their production use cases cluster in three categories: form filling, data extraction, and QA automation — each an explicit workaround for missing APIs. — [browser-use/browser-use README](https://github.com/browser-use/browser-use)

- **HN post (agent-browser-protocol):** A practitioner forked Chromium to build the Agent Browser Protocol (155 HN points, 55 comments) after diagnosing that most browser-agent failures come from **stale state** — the agent reasons from a screenshot that no longer reflects the live page. The fix: freeze rendering after every action, capture resulting state, return screenshot + structured summary before the next agent decision. "The result is that browser interaction starts to feel more like a multimodal chat loop." — [Show HN: Open-source browser for AI agents | Hacker News](https://news.ycombinator.com/item?id=47336171)

- **Blog post (Kypros Vassiliou, May 2026):** After surveying production browser-agent setups, the practical takeaway crystallized: "Use deterministic browser primitives first, then add agent reasoning only where the web gets messy." Playwright is becoming the default browser control layer, MCP makes it easier to expose structured interfaces, and hosted browser infrastructure (Browserbase, Browserless) is a distinct emerging category. — [Browser Automation for AI Agents in 2026: What Actually Works](https://kvassiliou.com/tech/browser-automation-ai-agents-2026)

## Gotchas

- **Over-tooling creates decision paralysis.** An agent with 15 tools spends significant context reasoning about which one to use. Start with 3-5 and add only when you have a specific failure case that demands a new tool.
- **Tool output shapes drift silently.** An API changes its response schema; the agent's next prompt still asks for the old field. Add schema assertions to your tool wrappers — fail loudly when the response shape doesn't match expectations.
- **Vision-based tools are brittle by design.** Screenshot → click loops work in demos and break on CAPTCHAs, dynamic ad loading, and race conditions. If you're building production agents, budget for stealth browser infrastructure (proxy rotation, fingerprint management) before you call it done.
- **MCP servers are not all equal quality.** The 13,230+ MCP servers in the ecosystem vary wildly in reliability, security, and documentation. Treat third-party MCP servers like third-party APIs: read the source, test the error paths, don't deploy blindly.
