# S-2625 · The Agent Toolbox Stack — When Your Agent Can Reason but Cannot Act

Your agent writes brilliant plans and produces nothing. It can describe exactly how to query your database, calculate the revenue figure, and format the email — but it has no way to do any of those things. The model is not the problem. The tools are the problem. Agents fail not because they lack intelligence but because the interface between reasoning and action is poorly designed.

## Forces

- **More tools do not mean better agents.** A 300-tool MCP manifest trains the model to ignore most of them. Adding tools without an interface strategy degrades selection quality and burns tokens on definitions that never get called.
- **JSON tool calling has a hidden token ceiling.** Each tool definition costs 550–1,400 tokens in the context window before a single action executes. A 50-tool agent consumes tokens on definitions before the task even starts. For large tool sets this is prohibitive.
- **Browser agents fail at the rendering layer, not the reasoning layer.** Most browser automation failures are not model errors — they are state errors. The agent reasons correctly from a screenshot taken before a modal appeared or a dropdown rendered.
- **Sandbox security and agent autonomy are in tension.** Running untrusted AI-generated code requires isolation, but isolation imposes latency, limits GPU access, and complicates networking. The choice of sandbox shapes the entire agent's capability envelope.

## The Move

The move is **intentional tool interface design** — treating tools as an Agent-Computer Interface (ACI), not a function API. Five tool modalities cover most production use cases; pick the right one per task, not a single approach everywhere.

**1. Use JSON tool calling for simple, atomic, single-step actions.**
Querying a specific database field, toggling a flag, confirming a date. Low cognitive complexity, predictable output. The right baseline for things that should not fail.

**2. Use MCP for cross-vendor SaaS and shared services.**
MCP (Model Context Protocol) is the production standard for connecting agents to Google Drive, Slack, GitHub, and similar services. Anthropic reported **98.7% token reduction** for a Google Drive → Salesforce workflow using MCP with on-demand tool loading instead of loading all tool definitions upfront. The tradeoff: tool manifests grow with every new MCP server, so use on-demand loading and namespace tooling carefully.

**3. Use code execution (PTC — Programs as Tools) for multi-step orchestration inside a sandbox.**
Instead of a sequence of individual tool calls, give the agent a sandbox with a Python or shell environment. The agent writes and executes a small program that composes multiple operations. Reported gains of **up to 20%** on benchmark tasks (CodeAct, 2025). Token cost: two meta-tools (`bash`, `write_file`) instead of dozens of individual calls. Sandboxes use gVisor (Modal), Firecracker (E2B, Vercel), or Kata Containers — isolation is non-negotiable since the code is untrusted.

**4. Use CLI/bash tools for dev workflows and local operations.**
Near-zero token overhead. `git`, `docker`, `npm`, shell pipelines. Agents already reason about command structure well. CLI tools are the fastest path to giving an agent operational capability.

**5. Use agent-specific browsers (not CDP) for web interaction.**
Standard Chrome DevTools Protocol fails for agents because JavaScript and rendering continue between agent actions — modals appear, dropdowns render, alerts fire. The Agent Browser Protocol (ABP, GitHub: theredsix/agent-browser-protocol, March 2026) forks Chromium to freeze JavaScript execution and rendering after each action, giving the agent a consistent view of every page state. The model is not the bottleneck here; the stale screenshot is.

**6. Design tools as ACIs, not functions.**
Anthropic's engineering guidance (September 2025): tools for agents need meaningful context in their output (not raw API dumps), clear namespaced boundaries, idempotent operations, token-efficient responses (paginate, filter, truncate), and descriptions written as agent instructions — not API docs for human developers.

## Evidence

- **Engineering blog:** Anthropic's code execution with MCP analysis reports 98.7% token reduction for cross-service workflows using on-demand tool loading instead of upfront manifests — [Anthropic Engineering, Nov 2025](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Technical analysis + benchmark:** The Agent Browser Protocol (ABP) identifies that the majority of browser-agent failures are state-staleness problems, not model failures — freezing JS/rendering after each action eliminates modal-blocking, autocomplete-overlay, and dynamic-reflow failure classes — [HN discussion, March 2026](https://news.ycombinator.com/item?id=47336171); [GitHub: theredsix/agent-browser-protocol](https://github.com/theredsix/agent-browser-protocol)
- **Code execution benchmark:** CodeAct paper (2025) reports up to 20% task improvement from code-execution tool calling over equivalent JSON tool-call sequences across benchmark tasks — [slavadubrov blog, March 2026](https://slavadubrov.github.io/blog/2026/03/24/ai-agent-tool-use)
- **Sandbox infrastructure:** Modal's engineering documentation on code execution sandboxes: gVisor isolation, 50,000+ concurrent sessions, SOC 2 Type II and HIPAA compliance — [Modal Blog, May 2026](https://modal.com/resources/best-code-execution-sandboxes-tool-calling-ai-agents)
- **MCP production deployments:** Lucidworks documents ConfigAssist chatbot reducing hallucination through MCP-connected retrieval; Frigade AI uses MCP tool-calling SDK to let product-exploration agents take actions (invite colleague, retrieve billing) on users' behalf — [Lucidworks, November 2025](https://lucidworks.com/blog/real-world-examples-of-mcp-in-action-from-chatbots-to-enterprise-copilots); [HN Show, July 2025](https://news.ycombinator.com/item?id=44733892)

## Gotchas

- **Adding MCP servers without on-demand loading balloons token cost.** Every MCP server you connect adds its full tool manifest to the context window. A 10-server MCP setup can consume more tokens on definitions than on actual task execution. Always use on-demand or lazy-loading of tool definitions.
- **Standard CDP-based browser automation fails silently and nondeterministically.** The same agent action on the same page can succeed or fail based on timing of dynamic content. ABP-style freezing is the correct solution; retry loops on CDP are a workaround that masks the real problem.
- **Code execution sandboxes vary wildly on isolation, compliance, and GPU.** gVisor (Modal) and Firecracker (E2B) offer strong isolation but differ on SOC 2 compliance and GPU access. For regulated industries, sandbox compliance certifications matter as much as capability. E2B's 24-hour session limit also constrains long-running research agents.
- **JSON tool calling is not "free" — it costs tokens per definition.** Teams new to agentic systems often underestimate the context cost of large tool manifests. A 100-tool manifest at 800 tokens per definition = 80,000 tokens before the model says hello. Use tools sparingly and namespace aggressively.
