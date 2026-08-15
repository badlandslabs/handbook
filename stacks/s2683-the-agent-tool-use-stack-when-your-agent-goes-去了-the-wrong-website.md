# S-2683 · The Agent Tool-Use Stack

When your agent calls the right tool for the wrong site, with valid JSON, a 200 response, and a completely wrong result — and you have no idea it happened until a customer calls.

## Forces

- **Latency of state vs. speed of action.** Most browser-agent failures aren't about the model misunderstanding the page — they're about the model acting from stale state (ABP, 2026). By the time the agent reads the DOM, the page has changed.
- **Schema coupling is a double edge.** Tight tool schemas reduce hallucinated calls but amplify failures when real-world APIs diverge from spec.
- **Fallback chains collapse under load.** When a tool fails, retry + fallback logic is sensible in theory; in practice it compounds latency and token cost fast.
- **Tool count scales with capability and error rate.** More tools = more failure modes, more hallucinated calls, more edge-case combinations the agent must reason through.

## The Move

The key move is **synchronization-first tool design**: treat every tool call as a two-phase operation (observe → act) with explicit staleness checks, rather than trusting the LLM to infer correct state. Three concrete patterns from production systems:

- **Structured tool registries with minimal surface area.** Agents get only the tools they need for the current subtask, not a full menu. browser-use achieves this by exposing ~10-15 actions (click, type, extract, screenshot) that compose into any workflow. Reducing tool count from 50 to 15 drops error rates significantly (per practitioner reports in agentic-patterns repo).
- **Browser synchronization as a primitive, not an afterthought.** ABP (agent-browser-protocol, a Chromium fork) solves the stale-state problem by keeping the acting agent pixel-synchronized with the browser at every step. Result: 90.5% on Online Mind2Web, 85.51% on hard tasks. The insight: screenshot → act cycles are fragile because the DOM mutates between them. Instead, ABP maintains a live DOM diff stream the agent reads before each action.
- **Output validation as a first-class tool concern.** HTTP 200 does not mean the tool worked. Production agent teams (AgentReviews, May 2026) report that the most common failure mode is "malformed JSON returned as valid LLM output" — invisible to exception handling. Fix: pair every tool with a Pydantic validator that runs on the output, not just the input schema. For semantic correctness beyond schema, use LLM-as-judge on tool outputs.

## Evidence

- **GitHub README + HN discussion:** The agent-browser-protocol (ABP) repo explicitly frames stale state as the primary cause of browser-agent failures, not model capability. Outperforms standard Playwright-based approaches on Online Mind2Web benchmarks (90.5% avg). — [github.com/theredsix/agent-browser-protocol](https://github.com/theredsix/agent-browser-protocol) + [HN Show HN thread](https://news.ycombinator.com/item?id=47336171)
- **GitHub README (109K stars):** browser-use is the dominant open-source browser automation library for agents, with a focused action vocabulary (click, type, extract, scroll, screenshot) designed to reduce tool-call errors. — [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)
- **Blog post (AgentReviews, May 2026):** Documents the "200 OK but semantically wrong" failure mode as the most common in production agent deployments, recommends output validation + LLM-as-judge as the standard fix. — [agentreviews.dev — AI Agent Failure Recovery Methods](https://agentreviews.dev/blog/ai-agent-failure-recovery-methods/)

## Gotchas

- **Don't give agents a full API spec.** Agents hallucinate parameters when given dense schemas. Give them a minimal description of what the tool does and one example of a valid call. Expand only when the agent proves reliable with the subset.
- **Screenshot debugging lies.** A screenshot taken after an action shows the result of the action — not the state the agent was reasoning from. Log the DOM snapshot alongside every tool call so you can replay failures.
- **Tool timeouts need per-tool values, not global.** A web search returning in 5s is normal; a code execution timing out at 5s is a showstopper. Set timeout policies per tool category, not globally.
- **Code execution is the highest blast radius tool.** A single malformed `os.system()` call in a sandboxed exec tool can do real damage in multi-tenant environments. Require process-level isolation (containers, not just jailbreak prompts) for any code execution tool.
