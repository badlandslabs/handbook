# S-1777 · The Frozen-State Browser Stack

Your agent opens a job board, reads three listings, and clicks "Apply" on the first one. The application form appears. The agent clicks "Upload Resume." A file picker dialog opens — invisible to the agent, blocking all further input. The agent retries the same click. Fails again. Reports success and moves on. The form was never submitted.

The model was fine. The page understanding was fine. The failure was a **race between the agent's state snapshot and the live page's reality** — and the page won.

## Forces

- **Browser automation tools give agents stale pictures of live pages.** Every screenshot and DOM dump is a snapshot of a moment that passed the moment the capture finished. Modals, dropdowns, overlays, and dynamic filters can all appear between capture and action, leaving the agent reasoning from a world that no longer exists.
- **The standard browser tool stack (Playwright MCP) trades completeness for liveness.** Playwright gives you the full DOM and full control — but the agent gets page state as of the last awaited operation, not as of the moment it needs to act. Filling in the gap requires either excessive action overhead (click → check → click → check) or a different architecture entirely.
- **Most browser-agent failure modes are predictable and structural, not model errors.** Modal blocks, autocomplete dropdown interference, file picker interrupts, `alert()`/`confirm()` dialogs, download completion detection — these are deterministic UI behaviors, not probabilistic LLM failures. They can be engineered around at the tool level, not patched at the prompt level.
- **The browser is the highest-stakes tool environment because it's adversarial.** Unlike internal APIs, the browser environment has anti-bot measures (Cloudflare, Turnstile, CAPTCHAs) explicitly designed to prevent automated access. A browser tool that can't pass these checks is a tool with a hard ceiling on its domain.

## The Move

**Freeze the browser state at the point of action, then capture it completely.** Instead of letting the agent act on a stale snapshot, engineer the tool layer to guarantee that every action-request is paired with a freshly frozen, post-action state capture — including compiled side effects (dialogs, downloads, permission prompts) that the normal rendering loop would miss.

Concrete implementation patterns:

- **Freeze-then-capture:** After each agent action (click, type, navigate), freeze JavaScript execution and DOM rendering *before* capturing state. This prevents race conditions with modals and async UI that appear between the action and the snapshot.
- **Side-effect compilation:** Along with the screenshot and DOM dump, return a structured list of notable events that occurred during the action loop: navigation events, file picker opens, permission prompts, alerts, download triggers. Don't let these silently interrupt the agent's reasoning loop.
- **MCP-native browser integration:** Bake MCP protocol support directly into the browser engine rather than wrapping Playwright over HTTP. Eliminates serialization overhead, reduces token use per action (ABP reports 2× fewer tool calls, 2× lower token usage vs. Playwright MCP), and gives the agent a chat-native interface to browser state.
- **Bot-detection bypass as a first-class feature:** Use real Chrome profiles with real session cookies, OAuth tokens, and MFA state. Tools like Agent360dk's browser MCP read Gmail login codes to solve 2FA automatically — the agent gets a fully authenticated browser session instead of a fresh incognito context that trips every anti-bot system.
- **Parallel DOM + visual capture:** Send both a structured DOM summary and a screenshot to the agent per action cycle. The DOM gives precision; the screenshot gives grounding. Together they reduce the action error rate vs. either alone.

## Evidence

- **GitHub (ABP):** The Agent Browser Protocol (a Chromium fork) achieves 90.53% on the Online Mind2Web benchmark using freeze-then-capture, compared to ~85% baseline for Playwright-based approaches. Authors note: "Most browser-agent failures aren't really about the model misunderstanding the page — the problem is that the model is reasoning from a stale state." — [github.com/theredsix/agent-browser-protocol](https://github.com/theredsix/agent-browser-protocol)
- **GitHub (Agent360dk):** The Agent360dk browser MCP drives a real, logged-in Chrome session from any AI agent (Claude Code, Cursor, VS Code) with 34 tools, reading emailed login codes from Gmail and solving CAPTCHAs. MIT license, local-only. — [github.com/Agent360dk/browser-mcp](https://github.com/Agent360dk/browser-mcp)
- **GitHub (real-browser-mcp):** A MCP server exposing puppeteer-real-browser as tools for AI agents, explicitly designed to bypass Cloudflare, Turnstile, and similar bot detection. — [github.com/qxZap/real-browser-mcp](https://github.com/qxZap/real-browser-mcp)
- **Anthropic Engineering (MCP):** MCP (Model Context Protocol) reached 8M+ downloads by April 2025, with 5,800+ community servers. Anthropic's own engineering blog notes that bundling code execution within the MCP tool layer reduces per-task context overhead by up to 98.7% vs. direct tool definitions — [anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)

## Gotchas

- **Freeze-then-capture adds ~100ms per action** (ABP measures ~100ms action overhead including screenshot). For high-frequency automation, profile whether this latency compounds into a bottleneck.
- **Bot-detection bypass tools risk TOS violations** on target sites. Know your environment — internal tools and authenticated sessions are fine; scraping Cloudflare-protected public sites is not.
- **Captured state is still a snapshot, not a stream.** The freeze-then-capture approach closes the race window, but the agent still isn't observing continuous page state. For pages with rapid updates (live data, real-time feeds), consider a separate streaming observation channel alongside the frozen captures.
- **Tool definitions still bloat context.** Even with a frozen-capture browser tool, the MCP ecosystem's growth (5,800+ servers) means agents can easily accumulate thousands of tool definitions. Anthropic recommends code-based tool invocation — write code that calls the tool, then let the agent execute it — to reduce context overhead vs. loading all definitions upfront.
