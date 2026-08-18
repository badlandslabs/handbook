# S-2818 · The Tool Schema Contract Stack — When Your Agent Picks the Right Tool and Constructs the Wrong Arguments

Your agent calls the correct tool 90% of the time. But 1-in-5 of those calls carries a malformed argument — a string where an integer belongs, a boolean written as the string `"false"`, a required field omitted. The tool fires, returns garbage, and the agent spends the next three turns confused. The fix isn't a better model. It's a schema contract that enforces the boundary between model output and code execution.

## Forces

- **The LLM is a提案者, not an执行者.** Models propose tool calls; they never execute them. This gap means every output from the model must be treated as a request from an untrusted client — validated before it touches your system.
- **Schema mismatches are the top failure mode, not reasoning errors.** A 1.4M-invocation production audit found 31% of failures were schema mismatches, outranking ambiguous tool selection (17%) and hallucinated tool names (4%). The model isn't confused — your schema is ambiguous.
- **Per-step reliability compounds destructively.** At 95% per-step reliability, a 20-step agent workflow succeeds only 35.8% of the time. A 3–15% per-call failure rate from network timeouts and rate limits is structural, not incidental.
- **Silent failures are the dominant mode.** Most tool call failures produce no exception, no crash, no alert. The agent moves on with garbage data. Without instrumentation on every layer of the delegation chain, you won't know the action never happened.

## The move

**Treat every tool call as an untrusted API request. Validate before you execute. Then normalize and retry.**

### Schema-first tool definition

- Define tool schemas in a schema-first language (Zod, Pydantic, JSON Schema) — not prose descriptions. LLMs are next-token predictors trained on human-readable text; they follow format better when the format is explicit and enforced.
- Generate schemas from OpenAPI specs or Zod using `openapi-zod-ts` or `hey-api` — bootstrap once, own the schema file, never let a regen clobber your extensions.
- Use the tool's `description` field for *why*, not *how*. Name parameters for clarity, not brevity. `searchQuery` beats `q`; `maxResults` (integer, min=1, max=100) beats `limit`.

### Runtime validation at the boundary

```typescript
// Model produces — may look valid but types are wrong
{ "query": "OAuth errors", "limit": "10", "includeDrafts": "false" }

// "10" silently works; "false" evaluates as truthy → drafts leak
// Validate at the boundary, not after execution
const SearchInput = z.object({
  query: z.string().min(1),
  limit: z.number().int().min(1).max(100),
  includeDrafts: z.boolean(),
});
```

- Apply Zod or Pydantic parsing *before* calling the tool. Coerce types where the model is predictably wrong (string→int), reject where it matters (wrong enum values).
- Return structured error messages on validation failure — feed the specific error back to the model so it can self-correct within the same turn.

### Provider abstraction

- OpenAI uses `tools[{ function: { name, description, parameters: {...} } }]` with `tool_calls` on the response. Anthropic uses `tools[{ name, description, input_schema: {...} }]` with `content` blocks mixing `text` and `tool_use`. Abstract this difference behind a single adapter so your tool definitions are provider-agnostic.

### Bounded retry with exponential backoff

- Wrap every tool call in a retry loop capped at 2–3 attempts. Use exponential backoff (100ms → 200ms → 400ms) for transient failures (rate limits, timeouts). Use circuit breakers for persistent failures — if an API is down, stop hammering it.
- Retry on *specific* error types (timeout, 429, 5xx), not on all errors. A 400 Bad Request will not resolve with a retry.

### Tool selection clarity

- Give each tool a single, specific purpose. A `searchAndSummarize` tool does two things; agents split it 17 different ways. A `webSearch` tool and a `summarizeText` tool compose predictably.
- Avoid tool name verbosity. `search_docs` is clearer than `searchDocumentsWithinUserAccessibleRepository`. Name-based tool selection degrades when names are long or ambiguous.

### Instrument the full delegation chain

- A tool call traverses: LLM → orchestration layer → tool executor → connector → OAuth provider → upstream API. Each hop is an independent failure surface. Log the entry and exit of every layer.
- Instrument: call frequency, error rates by tool, error rates by error type, retry rates, context window utilization per call.

### Constrain execution surfaces

- Use read-only tools by default. If a tool must write (file system, APIs, messaging), scope it to specific directories or endpoints. Sandbox code execution. A `run_query` tool that accepts arbitrary SQL will eventually receive arbitrary SQL.
- For browser agents: prefer tools that execute JavaScript in a shared logged-in context over tools that drive a separate browser instance. Shared session eliminates the "agent fights human for tabs" problem (Ego Lite's core insight).

## Evidence

- **Field study:** BIPI audited 1.4M production tool invocations across three clients over six weeks. Schema mismatches: 31%, parameter pollution: 22%, ambiguous tool selection: 17%, runaway loops: 11%, hallucinated tool names: 4%. Fixing schema validation, tool naming, and bounded retries addresses ~80% of failures. — [BIPI Field Notes: Production Tool-Use Failures](https://bipi.in/blog/ai-agent-tool-failure-modes)
- **Engineering post:** Tian Pan (Oct 2025) analyzed production agent flakiness and found the primary cause is argument construction, not reasoning or tool selection. Schemas are cheap to fix; the fix surfaces as runtime validation at the model→execution boundary. — [Tool Use in Production: Function Calling Patterns That Actually Work](https://tianpan.co/blog/2025-10-12-tool-use-function-calling-patterns)
- **Reliability math:** At 95% per-step reliability, a 10-step workflow succeeds 35.8% of the time. At 20 steps: 12.8%. Tool calls fail 3–15% of the time even in well-engineered systems due to network timeouts and rate limits. — [Scalekit: Tool Call Failures in Production](https://www.scalekit.com/blog/tool-call-failures-production)
- **Tool standard:** MCP (Model Context Protocol) — JSON-RPC 2.0 over stdio/SSE — has become the de facto open standard for AI-to-tool connectivity, with official SDKs in TypeScript, Python, Kotlin, and Java, and support from Claude Desktop, Cursor, Continue, and VS Code. — [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), [MCP Resources](https://github.com/cyanheads/model-context-protocol-resources)
- **Browser agent pattern:** Ego Lite (11.6k GitHub stars) is a macOS browser designed for agents and humans to share a logged-in session, solving the problem where browser automation frameworks need a separate browser and logins don't carry cleanly. — [CitroLabs/ego-lite](https://github.com/CitroLabs/ego-lite)

## Gotchas

- **Silent failures will own you.** Without per-layer instrumentation, you won't know a tool call silently failed. The agent continues; the user gets no output. Every tool invocation must emit a structured result or error, never swallow an exception.
- **Schema descriptions drift.** When an API changes but the tool description doesn't, the model continues generating arguments for the old schema. Treat tool schemas as versioned artifacts, not living docs.
- **Coercion masks a leaky abstraction.** Coercing `"10"` → `10` is fine; coercing `"admin"` → `false` for a role field is dangerous. Be explicit about what you coerce and what you reject.
- **Over-instrumenting tools changes behavior.** Adding too many tools to one agent causes context window exhaustion and degraded tool selection. Keep the active tool set small; use MCP for dynamic discovery of additional tools as needed.
