# S840 · The Tool-Giving Stack — When the Model Can Do Anything but Your Agent Can Only Do What You Let It

You have a capable model. You gave it tools. It ignores half of them, calls the wrong one with fabricated arguments, and freezes on tasks you thought were trivial. The problem isn't the model — it's what you put in its hands.

## Forces

- **More tools = more hallucination surface** — each additional tool increases the chance the model calls one with wrong arguments or invents one that doesn't exist.
- **Tool descriptions are the contract** — what the model knows about a tool is entirely what you wrote in the description and schema; the model cannot discover capabilities from the code.
- **Browser tools expose the hardest state problem** — web pages change continuously, auth sessions expire, and the model reasons from a screenshot of a frozen moment in time.
- **Code execution is the highest-leverage and highest-risk tool** — it unlocks tasks no other tool can, but untrusted execution is a critical vulnerability.
- **MCP is winning the integration standard war** — 9M+ monthly SDK downloads, 13K+ public servers, but the real power is multi-server orchestration, not individual servers.

## The Move

The core skill is **tool interface design**, not tool implementation. The LLM never sees your code — it sees a description, a name, a schema, and an output. Those four things determine whether the tool works.

**Constrain before you expand.** Start with the narrowest tool that solves the task. A `search_github_issues(repo, label)` tool outperforms a generic `bash` tool for GitHub tasks — the model can't misuse what it can't misinterpret.

**Descriptions are the prompt.** Every tool description should state: (1) what it does, (2) when to call it, (3) what the output looks like, and (4) common failure modes. Anthropic's Applied AI team recommends describing not just the tool but the *pattern* — "Use this when X, not when Y."

**Browser automation is its own category.** Three layers compete: raw computer use (Anthropic's Claude with X11/VNC in Docker, 90.5% on Mind2Web with Opus 4.6), purpose-built browsers (Agent Browser Protocol — a Chromium fork with freeze-then-capture that eliminates stale-state failures), and Playwright MCP (framework-agnostic, composable, best for integrating into existing stacks). Chrome memory overhead is the production bottleneck — ABP achieves 2x lower token usage and 2x faster execution than Playwright MCP per its benchmarks.

**Code execution requires a sandbox you control.** Amla Sandbox runs a WASM-based bash shell (~11MB, no Docker, no subprocess) with constrained tool access and full execution replay. Simonw called it "very cool" on HN. The alternative is ephemeral containers, but startup latency makes them impractical for multi-step agent tasks.

**The top MCP tool categories in production** (from LobeHub MCP marketplace and real HN deployments): filesystem operations, GitHub CRUD (PRs, issues, CI), Slack/messaging, database queries, and cloud fleet management. Fleet management commands (list instances, check health, deploy) account for the majority of MCP tool calls in production per OpenClaw data.

**Batch related tools.** If two tools always need each other, merge them. If a tool requires setup context (auth headers, a resource ID), provide that context automatically rather than making the model track it. Anthropic's tool design guidance explicitly recommends bundling preparatory steps into the tool itself.

## Evidence

- **Engineering Blog:** Anthropic's "Building Effective AI Agents" (Dec 2024) recommends starting with LLM APIs directly, avoiding framework abstractions that obscure prompts and responses. Their Applied AI team (Claude Code + enterprise deployments) found that tool descriptions that include when-not-to-use patterns reduce misuse by ~40%. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

- **Open-source Repo / HN Discussion:** Agent Browser Protocol (ABP) — a Chromium fork with MCP + REST baked into the browser engine, 155 HN points, 90.5% Mind2Web average. The core innovation: freeze JavaScript + virtual time after each action, then capture the resulting state. This eliminates the stale-state problem that causes most browser-agent failures. — [github.com/theredsix/agent-browser-protocol](https://github.com/theredsix/agent-browser-protocol) | [HN discussion](https://news.ycombinator.com/item?id=47336171)

- **Open-source Repo:** Browser Use — 104K GitHub stars, Python library that wraps any LLM (OpenAI, Google, Ollama for local) with browser automation. Production guidance explicitly calls out Chrome memory overhead and parallel agent management as the hard problem. Supports real Chrome profiles for auth, CAPTCHA handling via stealth browser fingerprinting, and Cloud API for managed browser sessions. — [github.com/browser-use/browser-use](https://github.com/browser-use/browser-use)

- **Show HN:** Amla Sandbox — WASM bash shell sandbox for AI agents, 146 HN points. No Docker, no subprocess, ~11MB. Agents get constrained tool access with full execution replay. Simonw (creator of Datasette) commented on HN: "This project looks very cool." — [github.com/amlalabs/amla-sandbox](https://github.com/amlalabs/amla-sandbox) | [HN discussion](https://news.ycombinator.com/item?id=46824877)

- **Developer Guide:** Xebia's comparison of n8n + MCP vs GitHub Copilot Agents found Playwright MCP outperforms browser-in-n8n for agentic tasks because it maintains browser context between actions. Copilot's integrated agent mode is easier for one-off tasks; n8n is better for saved, repeatable workflows. — [xebia.com/blog/ai-agents-with-mcp](https://xebia.com/blog/ai-agents-with-mcp)

## Gotchas

- **Don't give raw bash to production agents.** Foundation models are fluent with shell commands but will execute destructive commands under the right (wrong) prompt conditions. Always wrap with constrained tool definitions or WASM-level sandboxing.

- **Tool count above 10 degrades performance.** From Anthropic's Applied AI team findings: each additional tool increases the chance of an incorrect call. Audit your tool list and remove tools that overlap. The model doesn't benefit from options it can't distinguish.

- **Browser auth sessions expire mid-task.** Real browser profiles with saved logins solve this for browser-use; ABP's session management solves it at the engine level. Don't rely on the model to re-authenticate — build it into the tool lifecycle.

- **MCP servers are not all production-ready.** The 13K+ MCP servers include many hobby projects. LobeHub's marketplace (filesystem-mcp, github-mcp, slack-mcp) and Microsoft's official Playwright MCP are the current production-tier defaults. Evaluate stability, security posture, and maintenance activity before integrating.

- **LLM-as-tool-user has a reasoning gap.** The model reasons in a loop (action → result → reasoning → next action), but each reasoning step costs tokens. From r/LocalLLaMA production reports: a 4-step sequential task that should cost 500 tokens often costs 3-4K due to LLM reasoning between each step. Minimize this by making tool outputs self-explanatory and designing tools that return structured data the model can act on without additional interpretation.
