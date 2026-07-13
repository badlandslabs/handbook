# S-1048 · The Tool Modality Stack — When Your Agent Calls a Tool Five Ways and You Picked the Wrong One

Your agent needs to interact with the outside world. You give it tools. But there are at least five fundamentally different ways to do this — JSON tool calls, MCP servers, CLI wrappers, Skills, and code execution — and the wrong choice at design time becomes a rewriting project at deployment time. Each modality has a distinct token cost profile, failure surface, and adaptability ceiling. You need to know which knob to turn.

## Forces

- **Token cost is a modality property, not an implementation detail.** JSON tool calls load every tool definition into every prompt. MCP servers can load on-demand but still flood context with intermediate results. Code execution does one-shot multi-step computation with zero intermediate round-trips. Choosing the wrong modality can mean 10–100x token overhead for the same workflow.
- **Adaptability and reliability trade off against each other.** CSS selector automation is near-100% reliable until the site redesigns — then it silently records wrong data forever. Computer-use agents handle layout changes gracefully but are 3–15× slower and cost 5–10× more per action. There is no universal winner.
- **The MCP ecosystem is now production-default but has a tool-discovery tax.** MCP became the de-facto standard for external services (OpenAI, Anthropic, Google Vertex all support it). But loading hundreds of tool definitions upfront — or even on-demand — creates token overhead that teams discover only in production cost reviews.
- **Code execution is the modal answer nobody writes down.** Anthropic measured a 98.7% token reduction on representative workflows when agents write and execute code instead of chaining JSON tool calls. The CodeAct paper reports 20% higher task success rates. Yet most agent tutorials still default to tool calling as the primary pattern.

## The Move

Match the tool modality to the workflow characteristics:

- **JSON tool calling** — use for a small, stable tool set (under ~20 tools) with simple, single-step operations. When you know all the tools upfront and the agent's job is to pick the right one, not compose a complex procedure.
- **MCP servers** — use for connecting to external services (Google Drive, Slack, databases) where a standard interface already exists. MCP is the right choice when the tool lives in another system you don't control and you want the ecosystem's tooling to handle auth, schema, and versioning.
- **CLI wrappers** — use for Unix operations, scripts, and command-line tools that already exist in your stack. CLI is the pragmatic choice for anything that already has a shell interface and doesn't need structured typed output.
- **Skills (instructed actions)** — use for repeatable expert procedures that don't fit a tool-call schema — a "draft a legal memo" skill or "run this onboarding sequence" that involves dozens of steps the model should execute in order.
- **Code execution** — use for multi-step data transformations, database queries, and any workflow where the agent needs to orchestrate multiple operations and produce a final result. Prefer this when the agent would otherwise make 5+ tool calls in sequence, because each round-trip carries both latency and token cost.
- **Computer use / browser agents** — use when the target system has no API and no stable UI structure, or when the workflow crosses multiple applications that don't expose programmatic interfaces. Accept the cost: 3–15 seconds/action, 5–10× more expensive, and ~80–90% success on read tasks dropping to 50–70% on write tasks.

Layer error classification into every tool call path. Separate transient failures (timeouts, 429s, 503s) from semantic failures (malformed output, hallucinated parameters, null result propagation). Transient failures get retry with backoff. Semantic failures get validation and fallback — never retry a semantic failure as if it were transient.

## Evidence

- **Engineering blog:** Anthropic measured 98.7% token reduction and CodeAct reports 20% higher task success rates when agents write and execute code instead of chaining JSON tool calls for multi-step workflows. — [Anthropic Engineering — Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **Benchmarking report:** WOWHOW benchmarked three computer-use systems (OpenAI Operator at 87% complex-site success / 58% WebArena, Google Mariner at 83.5% WebVoyager, Claude Computer Use at $0.24–$0.36/workflow). Practical reliability: 80–90% for read tasks, 50–70% for write tasks. — [WOWHOW — Computer-Use AI Agents 2026](https://wowhow.cloud/blogs/computer-use-ai-agents-browser-desktop-automation-2026)
- **Framework analysis:** ClickHouse compared 12 agent frameworks with MCP support, finding MCP adopted as de-facto standard across OpenAI, Gemini, and Vertex AI. Tool definition overhead remains the primary practical bottleneck in large tool sets. — [ClickHouse — How to Build AI Agents with MCP: 12 Framework Comparison (2025)](https://clickhouse.com/blog/how-to-build-ai-agents-mcp-12-frameworks)
- **Failure taxonomy:** ArXiv paper (2601.16280) establishes a 12-category tool call error taxonomy spanning initialization, planning, tool selection, and execution phases. Production tool call failure rates run 12–18% in real pipelines versus near-zero in benchmark environments. — [AgentMarketCap — Agent Tool Call Failures in Production 2026](https://agentmarketcap.ai/blog/2026/04/10/agent-tool-call-retry-failure-mode-handling-production-2026)

## Gotchas

- **Don't give an agent 200 MCP tools and expect it to route intelligently.** Even with on-demand loading, the agent must reason over which tool to call. At scale, this means building a routing layer — intent classification → toolset subset → tool selection — rather than dumping the full tool list.
- **Computer use is not a replacement for API access — it's a fallback for when APIs don't exist.** Teams adopt computer use expecting it to replace MCP integrations, then discover 5–10× higher per-task costs and 3–15 second latency per action. Use it where you have no other choice, not as the default browser automation path.
- **JSON tool call token overhead compounds silently.** A tool definition that seems small (50 tokens) becomes 50,000 tokens when the agent makes 1,000 tool calls across a session. Profile token consumption per modality before committing to a design, especially for high-volume agent pipelines.
- **CLI tools lack structured output guarantees.** If a CLI returns free-form text, the agent must parse it — and free-form parsing is a common source of semantic failures that retry logic won't catch. Wrap CLI calls with structured output guards.
