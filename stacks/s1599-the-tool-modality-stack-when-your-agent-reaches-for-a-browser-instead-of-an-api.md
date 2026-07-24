# S-1599 · The Tool Modality Stack — When Your Agent Reaches for a Browser Instead of an API

Your agent needs to act on a web app. You can give it the vendor's API — fast and precise, but it breaks the moment the schema changes. Or you can give it a browser — resilient to UI changes, but slower, more expensive, and less deterministic. You could also give it a shell — powerful, but a security nightmare. Most teams make this decision ad-hoc, on gut feel, and discover they picked wrong at the worst possible moment. This is the stack for choosing the right tool modality for the right task — and for combining them into a system that's more reliable than any single approach.

## Forces

- **API tools are precise but fragile.** A tool that calls `GET /invoices?status=pending` is exact. It breaks permanently the day the vendor deprecates that endpoint, adds pagination, or changes the auth scheme. Every schema change is an incident.
- **Browser tools are resilient but unreliable.** A browser agent can navigate the same UI a human uses, which means it survives most UI changes without intervention. It also means the agent can encounter popups, captchas, rate limits, and session timeouts that no API ever had.
- **The paradigm is shifting to browser-first.** Browser Use (GitHub: browser-use/browser-use, 106K stars) and the Agent Browser Protocol (ABP) show teams abandoning hardcoded API integrations in favor of self-updating browser tools that auto-adapt to interface changes.
- **The ABP finding cuts against intuition.** The arXiv paper "Building Browser Agents" (2511.19477, Nov 2025) found that the primary failure mode in browser agents is not model misunderstanding — it's **reasoning from stale state**: a modal appears after the last screenshot, a filter reflows the page, an autocomplete dropdown covers the target. Solving state staleness (ABP freezes JS between each action) boosted success from ~50% to 85%.
- **Computer use costs real money.** A 10-minute browser-use flow runs $0.50–€2 per execution. API calls cost fractions of a cent. For high-frequency tasks, the cost gap is decisive.

## The Move

The core move is **tiered tool modality by task volatility**, not by preference:

- **API tools** for stable, high-frequency, transactional operations — anything that runs dozens of times per day and won't change.
- **Browser automation** for volatile interfaces, one-off tasks, or when no API exists — and budget for the cost and failure rate.
- **Code execution** only in sandboxed environments with strict resource limits and no network access.
- **Combine them in a fallback chain**: use the API first, fall back to browser if the API call fails or the tool is unavailable.

### Specific patterns that survive in production:

- **Frigade's reverse-engineering approach** — a browser-based agent watches the target app call its own internal APIs, then auto-generates reusable tools from the observed calls. The tools stay current because they're regenerated from live traffic. (HN: "Show HN: Reverse-engineering web apps into agent tools", 96 points, Jul 2025 — https://news.ycombinator.com/item?id=48847834)
- **ABP's freeze-between-actions** — before each agent action, freeze JavaScript execution and rendering completely. This eliminates the stale-state failure mode and is the single highest-leverage architectural decision for browser agents.
- **Human-approval gates on irreversible actions** — browser agents can prepare everything (fill forms, compose messages, draft payments) and then pause before committing. The workflow transitions to `awaiting_human` and the caller approves or rejects. (HN discussion on agent-browser-protocol, Jul 2025)
- **Specialized over general-purpose** — the arXiv paper argues that safety should be enforced through code (programmatic constraints on what the agent can do) rather than through LLM reasoning about what's safe. A specialized tool that can't execute arbitrary code is safer than a general browser that can.
- **API-then-browser fallback** — attempt the API call first. On failure (auth error, 404, rate limit), escalate to browser automation. This gives you precision when the API works and resilience when it doesn't.

## Evidence

- **arXiv paper (primary):** "Building Browser Agents: Architecture, Security, and Practical Solutions" (2511.19477) — ABP achieves ~85% success on WebGames vs ~50% for prior browser agents. Key finding: "Model capability does not limit agent performance; architectural decisions determine success or failure." Security finding: "Prompt injection attacks make general-purpose autonomous operation fundamentally unsafe." — https://arxiv.org/abs/2511.19477
- **HN post (primary):** "Show HN: Reverse-engineering web apps into agent tools" by Frigade — browser agent inside authenticated web app watches API calls, auto-generates tools as MCP servers, self-updates when the host app changes. 96 points, 40 comments. — https://news.ycombinator.com/item?id=48847834
- **HN post (primary):** "Show HN: Open-source browser for AI agents" (Agent Browser Protocol) — Chromium fork that freezes JS between each agent action, achieving 90.5% on Online Mind2Web benchmark. 155 points, 55 comments. — https://news.ycombinator.com/item?id=47336171
- **HN post (primary):** "Launch HN: Browser Use (YC W25)" — open-source browser automation library, 106K GitHub stars. Enables LLMs to control browsers via element-level action lists. — https://news.ycombinator.com/item?id=43173378
- **Anthropic engineering blog:** "Code execution with MCP: building more efficient agents" — on token consumption from loading all tool definitions upfront and how code execution lets agents handle more tools with fewer tokens. — https://www.anthropic.com/engineering/code-execution-with-mcp
- **Industry post:** "Agents That Drive the Computer: Patterns That Work" (jacar.es) — well-prompted agent on known interface: 70–90% success; unexpected modals and redesigns drop this significantly; cost per flow: $0.50–€2. — https://jacar.es/en/agents-that-drive-the-computer-patterns-that-work

## Gotchas

- **Browser automation is not a replacement for APIs — it's a fallback.** Using a browser to fill out a form that has an API endpoint behind it is wasteful when the API works, and catastrophic at scale. Treat browser tools as resilient last resort, not default.
- **The stale-state problem is architectural, not promptable.** Telling the agent "check if a modal appeared" in the system prompt doesn't solve the problem. You need to freeze the DOM between actions (ABP approach) or implement explicit state-verification steps after every navigation.
- **Browser tools make security harder, not easier.** Prompt injection via third-party content is a real attack surface in browser agents. The arXiv paper's conclusion: specialized constrained tools outperform general browsing because safety is enforced in code, not left to the model's judgment.
- **Cost compounds at scale.** A 10-minute browser flow at $1 each sounds fine. At 1,000 runs per day, it's $1,000/day. Audit your automation frequency before committing to browser-as-default.
- **Human-approval gates are not optional for irreversible actions.** Form submissions, payments, message sends, and data deletions should always pause for human confirmation in production systems. The boundary between reversible and irreversible is where trust in agents is won or lost (HN discussion, Jul 2025).
