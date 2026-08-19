# S-2874 · The MCP Tool Bloat Stack — When Your Agent Consumes More Tokens on Tool Metadata Than on the Actual Task

You built a capable agent. You gave it good tools — a file system, a database, a search API, email, calendar, code execution. But before it does any meaningful work, it has already consumed 50,000+ tokens on tool definitions, intermediate results, and context-passing overhead. The tool ecosystem — the thing that makes it an agent — is now the primary cost and latency bottleneck. MCP (Model Context Protocol) standardized how agents discover and call tools; it did not solve what happens at scale.

## Forces

- **Descriptive schemas reduce hallucinations but inflate tokens.** Full descriptions, parameter constraints, and usage notes help the model pick the right tool. They also mean each of your 50 tools costs 1,000–3,000 tokens per session before it fires once.
- **Loading all tools upfront is the default and the mistake.** MCP clients traditionally pass all registered tool definitions into context. With 5–15 MCP servers each exposing 10–30 tools, this is not a header — it is the payload.
- **Code execution as tool calling reshapes the security model.** Anthropic's November 2025 post shows the fix: have the model write code that calls tools instead of emitting natural-language tool calls. This is dramatically more efficient. It is also a fundamentally different trust boundary.
- **MCP's open ecosystem introduces adversarial tool surfaces.** MSB (MCP Security Bench, ICLR 2026) demonstrates 12 attack types — name collision, preference manipulation, prompt injection in tool descriptions, out-of-scope parameter injection — that exploit the fact that tools are now composable, natural-language-described objects. Models that are better at tool use are more vulnerable to these attacks.

## The move

**On-demand tool discovery over upfront registration.** Load only the tool definitions the agent actually needs for the current step. A task-planning phase identifies required capabilities; only those MCP servers or tool subsets get registered for subsequent turns. This keeps context consumption constant regardless of how many tools are available in the ecosystem.

**Strip schemas to disambiguation minimum.** Anthropic's MCP code execution post recommends keeping parameter types and descriptions that eliminate ambiguity between similar tools — but cutting boilerplate that only sounds helpful. `search_customers` vs `get_customer` vs `update_customer` needs clear disambiguation text; a long list of enum values does not need prose for each option.

**Batch tool calls via code execution.** Rather than one inference pass per tool invocation (each generating a full round-trip with context accumulation), have the model write a short script that calls multiple tools in sequence and returns a structured result. Anthropic showed this pattern dramatically reduces token waste and latency for sequential data operations. The model reasons once about the orchestration, executes many tools cheaply.

**Pre-materialize cross-system context.** Runtime tool calls compound latency when agents need data from multiple systems to assemble a single response. A pre-materialized context layer — a lightweight data bridge that syncs frequently-accessed entities (customer records, product data, recent transactions) into a local store — means the agent fetches from one place instead of chaining 4 API calls. Airbyte's production AI guidance calls this the primary cost lever for enterprise-scale agents.

**Gate MCP servers, not just tools.** MSB's attack taxonomy shows that a malicious MCP server can exploit name collisions with benign servers, inject prompt instructions into tool descriptions, and manipulate preference rankings. Trust the MCP server identity, not just the tool interface. At minimum: validate server provenance, scope tool permissions per server, and do not let MCP servers set their own display priority.

## Evidence

- **Anthropic engineering blog (Nov 2025):** "Code execution with MCP" — direct tool calls consume 50,000+ tokens before an agent reads a request; code-execution-based tool calling reduces this dramatically; Anthropic ships `batch tool` and on-demand tool discovery as the production pattern. — [URL](https://www.anthropic.com/engineering/code-execution-with-mcp)

- **GitHub discussion on MCP token overhead (May 2026):** luwei-will (context-mode/Claude Code plugin) measured 11 MCP tools consuming 5–15× more tokens than minimal type-only schemas. A single tool definition with full description, examples, and constraints can run 2,000–3,000 tokens; this compounds linearly with the number of active MCP servers. — [URL](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/2812)

- **ICLR 2026 — MCP-Bench (Wang et al., arXiv:2508.20453):** Evaluated 9 LLMs across 28 MCP servers, 250 tools, 10 domains. Key finding: tool-calling capability does not scale linearly with model size — orchestration, parameter precision, and cross-tool coordination are distinct capabilities. Also produced: a taxonomy showing how complementary tools (designed to work together) enable realistic multi-step tasks that isolated API benchmarks miss. — [URL](https://arxiv.org/abs/2508.20453)

- **ICLR 2026 — MSB: MCP Security Bench (Zhang et al.):** 12 attack types against the MCP tool-use pipeline: name collision, preference manipulation, prompt injection in tool descriptions, out-of-scope parameter injection, user impersonation, false-error escalation. 2,000 attack instances across 9 agents, 10 domains, 405 tools. Counterintuitive result: models with stronger tool-calling capability are *more* vulnerable to these attacks — better instruction-following is a double-edged sword when the instructions are adversarial. — [URL](https://mlanthology.org/iclr/2026/zhang2026iclr-mcp)

## Gotchas

- **Parallel tool calls are not the same as batching.** Sending 4 tool results concurrently looks efficient but each still accumulates tokens in context. True batching requires the model to emit one "batch tool" call that encodes multiple operations — reducing round-trips and context growth.
- **On-demand discovery adds latency on the first call.** The tradeoff is real: dynamic loading means the first task step waits for tool registration. For long-running sessions with repeated tool use, it wins. For single-shot tasks, upfront loading may be cheaper.
- **Code execution for tool calling is not sandboxed by default.** When the model writes code that calls tools, that code runs with the agent's permissions. The model can generate arbitrary Python/JavaScript that makes unintended tool calls. You need output validation on the generated code before execution — something the natural-language tool call path gives you for free.
- **MSB shows the security surface grows with the ecosystem.** More MCP servers = more attack surface. A curated list of verified servers with cryptographic identity is safer than the open registry model, but limits your access to the growing MCP ecosystem. This tradeoff is not yet resolved in the tooling.
