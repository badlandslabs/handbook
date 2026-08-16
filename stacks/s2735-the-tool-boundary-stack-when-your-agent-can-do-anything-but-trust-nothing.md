# S-2735 · The Tool Boundary Stack — When Your Agent Can Do Anything but Trust Nothing

You give your agent a browser, a code executor, and an API key. It can do almost anything — and that's the problem. Every tool you expose is an attack surface, a cost multiplier, and a potential failure point. The teams that deploy agents reliably in production all share one habit: they treat the tool boundary as a security-critical interface, not an extension of the model's terrible judgment about risk.

## Forces

- **The LLM is a smart proposer, not a safe executor.** A model will call `delete_all_users()` if the prompt implies it's the right move. Execution safety belongs on the app side of the tool boundary, not inside the tool definition.
- **Every tool is a cost vector.** Browser automation can cost $0.08–$0.50 per task depending on provider. Code execution in a sandbox adds latency and memory overhead. An agent that loops on a tool call burns money silently — no crash, no log line, just a bigger bill.
- **Tool results are external input.** You validate API responses from untrusted sources. You should validate tool results the same way. The model does not know the difference between "the filesystem returned an error" and "the model hallucinated a file listing."
- **The MCP convergence changes the math.** With OpenAI adopting Anthropic's Model Context Protocol in March 2025, and the Linux Foundation's Agentic AI Foundation taking stewardship in December 2025, tool interface fragmentation is finally decreasing. One protocol, multiple providers.

## The move

**Design the tool boundary as a zero-trust interface. Validate everything, authorize destructives, enforce budgets.**

### 1. Enforce schema validation at the boundary — not inside the tool

Define every tool's input contract in JSON Schema. Reject extra keys server-side using `additionalProperties: false` (OpenAI/OpenAI-compatible) or `extra="forbid"` (Pydantic). The LLM may pass unexpected parameters; your executor must refuse them before execution, not during.

```python
# Pydantic model at the tool executor boundary
class DeleteFileInput(BaseModel):
    file_path: str
    model_config = ConfigDict(extra="forbid")  # reject unknown params
```

This is confirmed across multiple sources: the mental model is that the LLM is the "smart proposer," and validation belongs on the application side.

### 2. Make every destructive tool idempotent or gated

Write an idempotency key into every write operation. On retry, check the key before executing. For irreversible operations — file deletion, database writes, API posts — add a human-confirmation gate or a dry-run mode. Never let the agent retry a destructive call blindly with exponential backoff; you will get the delete-then-panic-then-retry behavior.

From production design guidance: *"Guard destructive operations with an allowlist + human-confirmation gate."*

### 3. Give browsers as environments, not as one-shot tools

The shift in 2025–2026: agents need stable, programmable browser environments — not single-shot scraping calls. Four tools dominate production usage:

| Tool | Best for | Tradeoff |
|------|----------|----------|
| **Browserbase** | Cloud-hosted browser fleet, multi-session management | Cost, latency vs local Playwright |
| **Skyvern** | Workflow-oriented browser automation with retry logic | Less flexible for novel interactions |
| **Browser Use** (open-source) | Custom pipelines, local/self-hosted | Requires more infra investment |
| **Playwright + managed service** | Control + scalability, code-first teams | Config overhead |

The critical insight: *"Browser agents work best when they are a component in a larger system, not when they are deployed as the system."* Treat the browser as a navigation layer feeding deterministic downstream processes, not as the whole agent.

### 4. Adopt MCP as the tool protocol

MCP adoption as of 2026 is substantial and growing:

- **10,000+** active public MCP servers (Anthropic, December 2025)
- **9,652** servers in the official registry (May 2026)
- **97M+** monthly SDK downloads (Anthropic)
- **41%** of surveyed software organizations in limited or broad MCP production (Stacklok 2026 report — replaces the previously circulated but unsourced "78%" claim)

OpenAI adopted MCP across its Agents SDK, Responses API, and ChatGPT desktop in March 2025. In December 2025, Anthropic donated MCP to the Linux Foundation's Agentic AI Foundation (AAIF), backed by AWS, Google, Microsoft, OpenAI, Bloomberg, and Cloudflare. This is vendor-neutral infrastructure now.

### 5. Sandbox code execution with defense in depth

For agents that execute code (Python, Bash), the isolation architecture is non-negotiable in production. Two recent CVEs highlight why:

- **CVE-2025-31133** — runc container escape
- **CVE-2025-52881** — container runtime vulnerability

In multi-tenant environments running untrusted code, these aren't theoretical. Use CNCF-aligned sandboxing (gVisor, firecracker microVMs, or equivalent). Control state persistence: perpetual standby preserves filesystem/memory; time-capped sessions force state rebuilds after expiration. Target resume latency under 100ms to match Jakob Nielsen's response-time threshold.

### 6. Instrument tool calls for cost and loop detection

Every tool call should log: timestamp, tool name, input hash, output size, and duration. Budget per-session costs. Set a maximum tool-call count and a maximum cost-per-task threshold — both of which trigger a circuit break, not a graceful degradation. The self-evaluation circuit breaker problem (S-2734) shows what happens without hard caps: 47 iterations overnight, $4,217 bill, no crash.

## Evidence

- **Engineering blog (Tomoda Hinata, June 2026):** Production design for tool use — LLM as smart proposer, app as executor; JSON Schema validation at boundary; idempotency + human-confirmation gates for destructive tools — [tomodahinata.com/en/blog/ai-agent-tool-use-function-calling-production-design](https://tomodahinata.com/en/blog/ai-agent-tool-use-function-calling-production-design)
- **Research analysis (Zylos Research, April 2026):** MCP adoption, BFCL V4 benchmark for agentic function-calling, Anthropic's architectural advantage — direct tool chaining vs re-prompting on every step — [zylos.ai/research/2026-04-07-tool-use-function-calling-standards-benchmarks](https://zylos.ai/research/2026-04-07-tool-use-function-calling-standards-benchmarks)
- **Practitioner report (ThinSlices, 2025):** Browser agents as system components, not standalone agents; the four dominant tools (Browserbase, Skyvern, Browser Use, Playwright); "agent as user, not parser" paradigm shift — [thinslices.com/insights/browser-use-ai-agents](https://www.thinslices.com/insights/browser-use-ai-agents-how-autonomous-web-automation-actually-works-in-production)
- **MCP official blog (March 2026):** 2026 roadmap — transport scalability, agent-to-agent communication, enterprise governance; MCP moved beyond local tools to production — [blog.modelcontextprotocol.io/posts/2026-mcp-roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap)
- **Adoption report (Digital Applied, May 2026):** 10K+ public servers, 97M+ monthly SDK downloads, 41% orgs in production (Stacklok 2026) — verified metrics replacing the unsourced 78% claim — [digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol](https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol)
- **Infrastructure analysis (Blaxel AI, 2026):** Production runtime tools, sandbox isolation requirements, CVE-2025-31133 and CVE-2025-52881, resume latency targets — [blaxel.ai/blog/ai-agent-runtime-tools-production-workloads](https://blaxel.ai/blog/ai-agent-runtime-tools-production-workloads)

## Gotchas

- **Don't validate tool inputs inside the tool definition JSON Schema.** The LLM can often work around schema constraints. Validate in your executor at runtime with Pydantic, with `extra="forbid"` to reject unknown parameters.
- **Don't give agents raw scraping endpoints when they need a browser.** Scrapers return static HTML, break on login sessions, and have selector rot. If the task requires understanding real page state, the browser layer wins — accept the 50ms-to-several-second latency tradeoff.
- **Don't retry destructive tool calls blindly.** If you implement exponential backoff, make it conditional on idempotency. A `delete_file()` call that fails and retries is a real deleted file, not a cached API response.
- **Don't skip the hard cost cap.** Budget limits and tool-call count limits are not "nice to have." They are the only thing between you and an accidental $4,000 overnight bill.
- **Don't trust the tool result more than you trust the model.** Both are external input in the context of your executor. Validate search results, database queries, and API responses the same way you validate user input.
