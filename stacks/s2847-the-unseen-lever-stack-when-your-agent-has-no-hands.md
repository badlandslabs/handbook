# S-2847 · The Unseen Lever Stack — When Your Agent Has No Hands

An agentic system that cannot interact with the world is a very confident chatbot. Give it the right tools, and it can act. Give it the wrong ones, or the wrong descriptions, and it produces plausible failures that look like reasoning errors but are actually tool-call mistakes. The **Unseen Lever** problem: the tool layer is the most consequential part of any agentic stack, yet it is often an afterthought — bolted on, under-specified, and under-tested.

## Forces

- **Tool schema quality dominates function-calling accuracy** — vague names and parameter descriptions directly increase hallucinated calls. An agent calling the wrong tool produces a confident wrong answer, which looks like an LLM failure but is a tool-design failure.
- **Context window is finite and expensive** — loading 20 tool definitions consumes 11–28K tokens before the agent begins reasoning. At scale, this becomes a cost and latency problem, not just an efficiency one.
- **N×M integration sprawl** — without a shared protocol, connecting N AI models to M tools requires N×M bespoke integrations. Every custom tool adapter is a maintenance burden and a failure point.
- **Broad access equals broad risk** — giving agents file system, browser, or API access multiplies the blast radius of a mis-specified tool call. Security must be part of the tool interface design, not a post-hoc add-on.
- **The agent decides what tool to call, not when to stop calling it** — tools that return verbose or misleading results can cause agents to believe they have the information they need when they do not, producing silent failures.

## The move

**Design the tool layer as a first-class interface, not a plugin afterthought.** The specific tool categories are less important than the discipline of how you expose them.

**Five interface patterns cover most production tool use:**

1. **JSON function calling** — the baseline. Define tool schemas as structured JSON with explicit names, typed parameters, and concise descriptions. Keep descriptions under 50 words and parameters unambiguous. This is still the right choice for small, atomic, low-context tool sets.
2. **Code execution** — the agent writes code that calls tools inside a sandboxed runtime (Python interpreter, Node.js, etc.). For complex multi-step sequences, this is more token-efficient than a chain of individual tool calls. Anthropic's engineering team recommends agents write code to interact with MCP servers rather than issuing individual tool calls when workflows involve more than 2–3 steps.
3. **CLI tools** — wrap Unix-style executables as tools for local development and CI workflows. Agents can pipe outputs between CLI tools, making the tool interface composable without a protocol layer.
4. **Model Context Protocol (MCP)** — the emerging standard for connecting agents to external services. An MCP server advertises its tools over stdio (local) or HTTP (remote); the agent queries the server's tool manifest at startup. One integration unlocks the entire MCP server ecosystem — 13,000+ public servers as of early 2026. Anthropic built it, donated it to the Agentic AI Foundation, and it is now backed by OpenAI, Google, and Microsoft.
5. **Skills** — packaged instructions bundled with parameters that the agent decides when to invoke. Best for domain-specific reasoning patterns that need embedded context rather than raw function signatures.

**Six production tool categories** (per Neo4j's taxonomy, confirmed across multiple sources):

| Category | Purpose | Example | Risk |
|----------|---------|---------|------|
| Web search | Live facts, recent docs | Search API, browser agent | Low |
| Retrieval | Internal knowledge | Vector DB, knowledge graph | Low–Medium |
| Computation | Deterministic workflows | Code interpreter, math libs | Medium |
| File | Read/write persistence | Filesystem, object storage | Medium–High |
| Computer-use | Browser/UI automation | Screen agents, browser drivers | High |
| Business APIs | Workflow execution | Email, CRM, ticketing | High |

**Tool design rules that matter in production:**

- Names must be self-explanatory to a model that has never seen your codebase — `get_customer_by_id` not `gcbi`
- Descriptions should answer: what it returns, when to use it, what it does not do
- Parameter types must be strict — avoid `any` or unstructured JSON in params
- Errors must be recoverable — return structured error codes, not raw exceptions
- Version your tool schemas; breaking changes in tools break agents silently

## Evidence

- **Engineering blog:** Anthropic's team documented that writing code to call MCP tools is more token-efficient than individual direct tool calls for multi-step workflows, and released a reference implementation showing agents composing MCP calls via Python code rather than one-shot function invocations — [Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp), November 2025
- **Industry survey:** 79% of organizations piloted AI agents in 2025 (Grand View Research via Alice Labs), with tool schema quality identified as the single biggest determinant of function-calling accuracy — [AI Agent Tool Use Patterns](https://alicelabs.ai/en/insights/ai-agent-tool-use-patterns), May 2026
- **Community data:** MCP SDK downloads grew from 100K to 97M+ per month in under one year; 13,230+ public MCP servers exist as of February 2026, up from ~100 in November 2024. Company-operated servers grew 232% from August 2025 to February 2026 — [MCP Examples: 10 Real-World Use Cases](https://openclaw.direct/mcp-guide/model-context-protocol-examples), March 2026
- **Production stack:** A documented local agent production stack combines Ollama (LLM serving) + LangChain (orchestration) + Qdrant (vector memory), with known limitation: Ollama lacks continuous batching and stalls under high concurrency — [Best Local AI Agent Stack](https://markaicode.com/best/best-local-ai-agent-stack/), August 2026
- **Deployment pattern:** TrueFoundry's agentic AI cookbook demonstrates deploying agents as both FastAPI endpoints and MCP servers, with Docker containerization and gateway-based routing — [Agentic AI Deployment Cookbook](https://github.com/truefoundry/agentic-ai-deployment-cookbook), 2025

## Gotchas

- **Vague tool descriptions cause wrong calls** — the agent picks a plausible-sounding tool instead of the correct one. The failure looks like bad reasoning; the fix is better tool names and descriptions.
- **Token overhead kills context at scale** — passing 20+ tool definitions upfront is expensive. Use lazy loading (fetch the tool manifest once, call tools by reference) or code execution to batch interactions.
- **Verbose tool responses mislead agents** — a tool that returns more data than the agent needs can cause it to stop searching and produce a partial answer. Truncate, summarize, or paginate tool responses.
- **Supply chain risk in MCP servers** — Microsoft documented that poisoned tool descriptions in third-party MCP servers can cause agents to exfiltrate data. Validate tool manifests from untrusted sources and apply MCP's permission scopes.
- **Broad system access amplifies mis-calls** — a file write tool with a bad parameter can overwrite production data. Start with read-only tools and expand access incrementally with explicit error handling at each level.
