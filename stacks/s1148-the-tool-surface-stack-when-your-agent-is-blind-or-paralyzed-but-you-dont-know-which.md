# S-1148 · The Tool Surface Stack — When Your Agent Is Blind or Paralyzed but You Don't Know Which

You give your agent 40 MCP tools. It fails anyway. You give the same agent 3 tools. It succeeds. The problem was never the model — it was that you handed a reasoning engine a pile of APIs and called it a tool strategy. The tool surface is not an extension of your agent. It is the agent's sensory and motor system. Get it wrong and you have a brilliant mind with no eyes and no hands.

## Forces

- **Tool count is not capability.** Giving an agent more tools doesn't make it more capable — it makes it more uncertain. A 5-server MCP setup can consume 72,000+ tokens in tool definitions alone (Anthropic), leaving less room for actual work and increasing the odds the model picks the wrong tool.
- **The browser is the hardest tool and teams underestimate it.** Most browser-agent failures aren't model failures — they're state synchronization failures. Modal dialogs appear after the last screenshot, dynamic filters reflow the page, autocomplete dropdowns cover target elements. The Agent Browser Protocol (ABP) project measured that 9 out of 10 browser failures stem from stale UI state, not from the model misunderstanding the task.
- **Tool security is the forgotten dimension.** When agents can call APIs, modify databases, process refunds, or send emails, the tool itself becomes the authorization boundary. Most teams apply prompt-level guards but never instrument the tool-call layer — so a perfectly benign prompt can produce a destructive tool call.
- **The filesystem is your agent's working memory and it's ephemeral by default.** Coding agents that write files, install dependencies, and generate git history lose everything when the session stops. AWS documented this explicitly: "Your coding agent spends twenty minutes scaffolding a project and everything disappears when the session ends."
- **Three tool categories dominate production use** (from MCP registry analysis across 500+ servers): **web scraping/search** (Hacker News, Brave Search, Brave API, Firecrawl), **filesystem operations** (read/write/list), and **API integrations** (GitHub, Slack, database connectors). Everything else is niche.
- **Tool design shapes what questions the agent can even ask.** If your agent doesn't have a search tool, it can't research. If it doesn't have a code execution tool, it can't verify. The tool surface defines the agent's effective cognitive reach — not the model's reasoning depth.

## The move

The tool surface is an architectural decision, not a feature checklist.

- **Start with three tools, not thirty.** Filesystem (read/write), web search, and code execution cover 80% of useful agent tasks. Add tools only when a failure trace points to a missing capability — not preemptively.
- **Instrument tool calls at the call layer, not the prompt layer.** Guardrails on the LLM boundary miss tool results, intermediate calls, and state mutations. Add authorization checks, rate limits, and DLP filters directly on the tool invocation path (e.g., AgentWacht for MCP: policy-driven auth, RBAC, argument validation, and audit).
- **Treat the browser as a state machine, not a screenshot stream.** Use dedicated browser automation tools (Playwright MCP, ABP's freeze-and-synchronize approach) that account for modal timing, dynamic reflow, and async updates. Vanilla screenshot-to-LLM pipelines fail reliably on complex web apps.
- **Persist the filesystem explicitly.** If your agent does meaningful work in a session, make session state durable. AWS Bedrock AgentCore Runtime, Terminal Use's workspace persistence, and similar platforms treat the filesystem as a first-class concern — not a side effect.
- **Design tool descriptions for the model's decision, not the developer's documentation.** Anthropic's Tool Use Examples feature (72% → 90% accuracy improvement) demonstrates that concrete usage demonstrations in the tool schema dramatically outperform exhaustive JSON schema documentation.
- **Separate tool discovery from tool availability.** Anthropic's Tool Search Tool reduces tool token overhead from 72K to ~8.7K for 50+ tools by letting the model search for relevant tools on demand rather than receiving all definitions upfront. This architectural pattern (discover-then-execute) scales to large tool libraries without bloating context.

## Evidence

- **Anthropic engineering post:** Documented that a 5-server MCP setup consumes 72,000+ tokens in tool definitions, driving their Tool Search Tool feature. Their Programmatic Tool Calling reduces token overhead by 37% and eliminates intermediate context pollution. Tool Use Examples improved complex parameter handling accuracy from 72% to 90%. — https://www.anthropic.com/engineering/advanced-tool-use (November 24, 2025)
- **Agent Browser Protocol (ABP) Show HN:** Open-source Chromium fork for agent browser automation. Found that "most browser-agent failures aren't about model misunderstanding — it's that the model reasons from stale state." Achieved 90.5% average on Online Mind2Web benchmark. Identified 5 common failure categories (modal timing, reflow, autocomplete, alerts, downloads) that are all state problems, not reasoning problems. — https://news.ycombinator.com/item?id=47336171
- **AWS Bedrock AgentCore Runtime blog:** Introduced managed session storage and `InvokeAgentRuntimeCommand` for persistent filesystem state across agent sessions. Explicitly documents the ephemeral filesystem as a production blocker for coding agents. — https://aws.amazon.com/blogs/machine-learning/persist-session-state-with-filesystem-configuration-and-execute-shell-commands/ (April 2, 2026)
- **Toolradar MCP registry analysis:** Documents 500+ MCP servers across 8 categories. Confirms three dominant production tool categories: web scraping/search, filesystem, and API integrations (GitHub, Slack, databases). Notes that "most AI agent projects fail not because the LLM is bad, but because the tooling around it is wrong." — https://toolradar.com/blog/ai-agent-tools-stack-2026
- **Frigade Show HN:** Built an agent that observes authenticated web app API calls to auto-generate MCP tools. Identified that "even very modern software tends to have a spider web of confusing APIs and services that AI agents simply cannot use out of the box." — https://news.ycombinator.com/item?id=48847834
- **Terminal Use (YC W26) Launch HN:** "Vercel for filesystem-based agents." Built deployment infrastructure specifically for agents that read/write files, recognizing that packaging, sandboxing, streaming, and state persistence around filesystem tools are distinct engineering problems from the agent logic itself. — https://news.ycombinator.com/item?id=47311657

## Gotchas

- **Preloading 50 tools is a pessimization, not a feature.** The model wastes context reasoning about irrelevant tools and gets worse at picking the right one. Use on-demand tool discovery instead.
- **Tool security and tool quality are two separate problems.** Teams that add authorization often skip argument validation — so an agent with legitimate access can still pass malformed parameters that corrupt data or bypass business logic.
- **Sandboxing code execution tools is table stakes but often missing.** Without isolation (Docker, microVMs, WASM), an agent that executes code can read arbitrary files, exfiltrate data, or escape the sandbox. Cursor, Claude Code, and Terminal Use all use isolation layers.
- **Tool naming and schema quality directly affects model accuracy.** Vague descriptions ("search the web") produce worse results than specific ones with input/output examples. Anthropic's data is clear: usage demonstrations outperform schema documentation.
- **The tool surface is not static.** As agents interact with real systems, you'll discover tools that are missing, tools that are too broad (too dangerous), and tools that need sub-tool decomposition. Treat the tool inventory as a living system, not a one-time setup.
