# S-1490 · The Browser-as-Primary-Tool Stack — When Websites Are Built for Humans, Not LLMs

When your agent needs to interact with the real web — filling forms, navigating auth flows, scraping dynamic content — and every website fights you in different ways.

## Forces

- **The web is a human interface, not an API.** Most sites have no documented endpoints. The browser is the universal interface, but it's also stateful, slow, and changes between observation and action.
- **Vision-based page reading is expensive and fragile.** Screenshots per step cost tokens and miss DOM structure; DOM extraction is cheaper but breaks on dynamically loaded content.
- **Benchmarks don't reflect reality.** WebVoyager tests 643 tasks across 15 sites; the real web has 1.1 billion sites and tasks that break every week. An agent scoring 95% on a benchmark may still fail your specific use case.
- **State divergence is the silent killer.** The browser continues updating (modals, dropdowns, navigation) between the agent's observation and its next action. A click on "Submit" fires before a validation spinner resolves — agent acts on stale state.

## The move

Give your agent a browser as the primary tool, then solve the four failure modes systematically.

- **DOM extraction over screenshots for structured pages.** Extract the interactive element tree with IDs, labels, and xpaths; present it as a numbered list to the LLM. This is 10-50x cheaper than vision-per-step and produces deterministic rerun capability. Use vision only as fallback for CAPTCHAs, canvas, or dynamically rendered content.
- **Freeze the state after every action.** Fork Chromium (ABP approach) or implement post-action waits that capture a stable snapshot before returning control to the agent. This eliminates the #1 cause of "clicked wrong button" failures.
- **Plan around authentication flows, not through them.** OAuth, 2FA, and session cookies are the hardest failures in browser agent benchmarks. For production use cases, prefer authenticated headless browsers with pre-seeded sessions over asking the agent to navigate login flows.
- **Set per-task step budgets with semantic exits.** Browser agents can loop indefinitely on complex multi-step forms. Hard cap at 15-25 steps; on exit, serialize partial state (URL, form values, error message) so a human or supervisor can resume.
- **Classify page types before acting.** A shopping cart page, a SaaS dashboard, and a government form all require different strategies. Build a lightweight page classifier that routes to domain-specific sub-prompt templates rather than asking the LLM to infer from raw HTML.
- **Monitor on a live benchmark, not a static one.** Web Bench (5,750 tasks, 452 sites) is the current best — but still a fraction of production variety. Track your agent's success rate on your actual 10-20 target sites with versioned task definitions; re-run monthly.

## Evidence

- **GitHub repo (Browser Use):** #1 on Odysseys leaderboard at 87.4% average accuracy, 105k+ stars, outperforms OpenAI Operator and Claude Computer Use on standard benchmarks — [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)
- **Benchmark gap (YC/Skyvern Web Bench):** WebVoyager tests 643 tasks across 15 sites; Web Bench covers 5,750 tasks across 452 sites and finds browser agents still struggle most with authentication, form filling, and file downloading — [webbench.ai](https://webbench.ai) / [github.com/Halluminate/WebBench](https://github.com/Halluminate/WebBench)
- **Architecture pattern (ABP):** Agent Browser Protocol freezes JavaScript execution and rendering after every action, capturing stable page state before returning control to the agent — addresses state-divergence as the leading failure mode — [HN Show HN, July 2026](https://news.ycombinator.com/item?id=47336171)
- **Real-world production uses (Skyvern/Web Bench):** Browser agents in production as of 2026: job applications, invoice downloading, IRS SS4 filings, marketplace postings — [Y Combinator Launch](https://www.ycombinator.com/launches/NdK-web-bench-a-new-way-to-compare-ai-browser-agents)

## Gotchas

- **xpaths break when the site redesigns.** Extract stable selectors (ARIA labels, data-testids) alongside xpaths; use them as fallback when structural selectors return null.
- **Headless mode ≠ headless reality.** Some sites serve different HTML to headless browsers. Use a real Chromium instance with a standard user agent to reduce detection and behavioral differences.
- **Multi-tab flows are unreliable.** Most browser agent frameworks are single-tab. If your use case requires opening links in new tabs and coordinating across them, implement tab-aware state tracking or use a framework with explicit multi-tab support.
- **The benchmark winner isn't your winner.** Browser Use leads on Odysseys; Claude Computer Use (Anthropic) leads on complex multi-step reasoning tasks. Test on your specific use cases, not leaderboards.
