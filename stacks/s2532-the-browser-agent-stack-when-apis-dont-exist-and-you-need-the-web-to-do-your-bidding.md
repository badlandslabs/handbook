# S2532 · The Browser-Agent Stack: When APIs Don't Exist and You Need the Web to Do Your Bidding

You need to interact with a service that has no API — a government portal, a legacy web app, a competitor's site. Or you need an agent to autonomously navigate the web, verify UI state, or complete a multi-step workflow no API can touch.

## Forces

- **Cost vs. fidelity tradeoff** — screenshots give rich visual context but burn 1,500+ vision tokens per step; accessibility trees are cheap text but lose layout information
- **Generality vs. reliability** — screenshot-based agents (Claude Computer Use, OpenAI Operator) work on any UI; specialized agents break on edge cases but succeed far more often on their target surfaces
- **Autonomy vs. safety** — unconstrained browser agents are vulnerable to prompt injection; programmatic guardrails (specialized tools, deterministic fallbacks) outperform "smarter model" approaches
- **Determinism vs. flexibility** — the web is a moving target; agents need replay, recovery, and self-healing to be production-grade

## The Move

The architecture that actually works in production separates observation from action with a structured loop, uses the cheapest representation that suffices, and wraps web interaction in specialized tools rather than giving agents raw browser control.

**Core loop:**
- Agent receives current page state (accessibility tree ± screenshot ± DOM)
- Agent decides action (click, type, scroll, navigate) with element reference
- Action executes with verification
- Loop repeats until goal reached or max steps hit

**Choose your observation mode by task:**
- **Accessibility tree only** — fast, cheap (2–4× less tokens than screenshots), works for data-entry and form-filling where visual layout doesn't matter
- **Screenshot + vision** — general purpose, required when visual interpretation is needed (charts, graphs, CAPTCHA-adjacent UI, dynamic/CSS-heavy pages)
- **DOM + a11y hybrid** — best of both: structured element targeting via a11y refs, screenshot on-demand for visual verification

**Specialize instead of generalizing:**
- Build dedicated agents per target site (with knowledge of element structure, common failures, expected states)
- Give agents programmatic constraints (max steps, allowed domains, action allowlists) rather than relying on LLM reasoning for safety
- Use deterministic fallback scripts for known failure modes (cookie banners, modals, captchas, autocomplete dropdowns) before falling back to the LLM loop

**Production hardening:**
- Browser profile persistence (cookies, session state) across tasks
- Proxy rotation and stealth browsers for anti-bot targets
- Screenshot/DOM capture between every action step for debugging and replay
- Goal verification step — LLM or scripted check that the final state matches intent

## Evidence

- **GitHub README:** browser-use (MIT, open-source) reaches 108K GitHub stars in ~2 years, supports any LLM via provider abstraction (Gemini, Sonnet, Qwen, DeepSeek-R1, local via Ollama), ships with Playwright under the hood, and offers cloud hosting with stealth browsers and proxy rotation — [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)
- **HN Launch Post:** Browser Use (YC W25) launched Feb 2025 with claims of 3–4× better performance than OpenAI Operator using GPT-4o, ships multi-LLM support, deterministic replay, and cloud execution; HN discussion surfaced production security concerns around CDP debugging permissions as an exploit surface — [news.ycombinator.com/item?id=43173378](https://news.ycombinator.com/item?id=43173378)
- **arxiv paper (FillApp, Nov 2025):** "Building Browser Agents: Architecture, Security, and Practical Solutions" — tested browser agents on WebGames benchmark (53 tasks): ~85% success vs. ~50% for prior agents and 95.7% human baseline. Key finding: "model capability does not limit performance — architectural decisions determine success." Also found prompt injection makes general-purpose autonomous operation fundamentally unsafe; specialized tools with programmatic constraints outperform general intelligence — [arxiv.org/html/2511.19477](https://arxiv.org/html/2511.19477)
- **Technical comparison:** Prophet Chrome benchmarks accessibility-tree vs screenshot approaches; finds tree-only is 2–4× faster and cheaper per step due to token costs (~1,500 vision tokens burned per screenshot before any LLM reasoning); screenshots win only when visual interpretation is essential — [prophetchrome.com/blog/accessibility-tree-vs-screenshots-browser-ai](https://prophetchrome.com/blog/accessibility-tree-vs-screenshots-browser-ai)
- **Production architecture blog:** browser-use.com describes SQS-to-Lambda production architecture with the core `Agent` class: captures screenshot + DOM in parallel, sends both to LLM for action decision, executes, repeats. 4,000+ commits of real-world failure handling shaped the architecture — [browser-use.com/posts/production-architecture-browser-use](https://browser-use.com/posts/production-architecture-browser-use)
- **Anthropic Claude Computer Use:** Pixel-level screenshot approach via Anthropic API; general-purpose across desktop and web but at higher cost; fundamentally different from DOM-based approaches — [prismix.dev/guides/claude-computer-use](https://prismix.dev/guides/claude-computer-use)

## Gotchas

- **Prompt injection is not theoretical** — the arxiv security analysis demonstrates real exploit paths on general-purpose browser agents. Never give an untrusted page raw browser control in production without sandboxing and action allowlists.
- **CSS selector brittleness hasn't gone away** — it's been replaced by LLM brittleness. Agents misidentify elements on dynamic pages, autocomplete dropdowns, and modal overlays. Build explicit recovery logic, not "smarter prompts."
- **Vision token costs compound fast** — 20 steps × 1,500+ tokens/screenshot = 30,000 tokens just on pixels. If your task is form-filling on a structured site, accessibility tree alone is the right call. Save screenshots for verification only.
- **Anti-bot detection** — many sites block headless browsers and known automation fingerprints. Stealth browser profiles, proxy rotation, and human-like timing matter more than the agent's intelligence at scale.
- **Goal verification is the missing step** — most browser agents stop at "no more actions" rather than "did the task actually succeed." Always add an explicit check: does the resulting page state match the goal?
