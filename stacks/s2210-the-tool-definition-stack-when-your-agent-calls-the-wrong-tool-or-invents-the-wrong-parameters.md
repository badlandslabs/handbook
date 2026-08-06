# S-2210 · The Tool Definition Stack — When Your Agent Calls the Wrong Tool or Invents the Wrong Parameters

Your agent is confidently calling `delete_database_table` when it meant `delete_record`. The parameters look right syntactically, so validation passes. The table gets dropped. The problem isn't the model reasoning — it's that the tool descriptions were written for humans reading documentation, not for models making selection decisions every turn.

## Forces

- **Tool descriptions are prompts.** The model reads the tool name, JSON schema, and free-text description on every turn — those three strings are the entire routing decision. The implementation, tests, and README are never seen.
- **97% of MCP tools have design smells.** February 2026 arxiv research across 856 real MCP tools found that nearly every tool has at least one quality issue — vague descriptions, missing enum constraints, ambiguous parameter names, or undocumented error envelopes. This is systematic, not random.
- **Tool-call hallucination has hit a plateau.** Despite 18 months of targeted fine-tuning, agents still misfire 3–7% of tool invocations in production. At 5 tool calls per task with a 5% per-call failure rate, task-level failure compounds to ~23% before retry logic. This is structurally different from general knowledge hallucination — it's about structured action, not facts.
- **More tools degrades performance.** Presenting an agent with 50+ tool descriptions simultaneously causes "choice overload" — model accuracy drops and context budget exhausts. Tool RAG and tool grouping are the emerging solutions.
- **Descriptions cost tokens every turn.** Verbose descriptions improve routing accuracy but inflate context costs. The economics of description length only made sense when providers charged per-token input — June 2025 billing changes shifted this calculus.

## The Move

Design tools as a contract between deterministic systems and non-deterministic agents — not as API documentation for humans.

- **Write descriptions as if briefing a new hire.** Every tool description should answer: what does this tool do, when should I use it, and what will I get back? Include concrete examples of inputs and outputs in the description text.
- **Treat the JSON schema as part of the prompt.** Schema types, required/optional flags, enum values, and descriptions are routing signals the model acts on. Missing `enum` constraints on a `status` field means the model invents values like `"completing"` instead of `"completed"`.
- **Keep tool names verb-object and unambiguous.** `search_products` beats `catalog_search`. When two tools overlap semantically, merge them or add a clarifying phrase: `search_products_by_name` vs `search_products_by_sku`.
- **Handle errors at the schema level.** Return structured error envelopes the model can branch on: `{ "ok": false, "error": "NOT_FOUND", "message": "Record 123 not found" }` rather than raw strings. The model can then reason about recovery.
- **Start with ≤10 tools per agent.** Group tools by task phase (research, draft, review) and expose only the relevant group per context window. Use tool RAG to dynamically retrieve the right subset from large catalogs.
- **Truncate long outputs proactively.** If a tool can return unbounded data (a full DB table, a long page), return the first N rows and a "truncated" signal with pagination hints. Agents that receive truncation signals use filters; agents that don't often retry the same call.
- **Test tools with the model, not just unit tests.** Deterministic unit tests validate the tool works. Model-in-the-loop tests validate the model picks the right tool with the right parameters. Run both.

## Evidence

- **Research paper:** "97% of MCP tools have at least one smell" — Three February 2026 arxiv papers on 856 real MCP tools cataloged systematic design failures in descriptions, schemas, and error handling. — [dikrana.dev](https://dikrana.dev/blog/tool-design-schema-is-the-prompt/)
- **Benchmark finding:** Berkeley Function Calling Leaderboard shows top models at ~87% accuracy, but production systems (adversarial inputs, real APIs) run 3–7% failure rates — a gap that compounds task-level. — [AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/12/ai-agent-tool-call-hallucination-plateau-2026)
- **Tool overload data:** "Choice overload: model accuracy degrades, prompts bloat with irrelevant tool descriptions" — Zylos Research, 2026-03-03. Tool-calling performance degrades with catalog size (Kate et al., 2025). — [Zylos Research](https://zylos.ai/research/2026-03-03-ai-agent-tool-use-optimization)
- **Protocol adoption:** MCP SDK downloads grew from 100K to 97M+ per month in just over a year. 13,230+ public MCP servers exist as of March 2026 (up from ~100 in Nov 2024). — [Anthropic / OpenClaw](https://openclaw.direct/mcp-guide/model-context-protocol-examples)
- **Schema standard divergence:** "Tool definitions across providers converge on JSON Schema, but field names, strict modes, and capability constraints differ in ways that matter when porting tools between systems." (OpenAI: `parameters`, Anthropic: `input_schema`, MCP: `inputSchema`). — [agentpatterns.ai](https://www.agentpatterns.ai/standards/tool-calling-schema-standards/)

## Gotchas

- **"Structural correct, semantically wrong" passes validation.** The tool call parses perfectly but solves the wrong problem (right endpoint, wrong ID, inverted filters). Schema validation can't catch this — you need trajectory-level evals.
- **Rich descriptions inflate context cost.** A 500-word description with examples is great for accuracy but burns tokens on every turn. The June 2025 billing change shifted the economics; test whether trimming description length hurts accuracy before paying the tax.
- **Error strings are invisible to schema validators.** Returning `{"error": "something went wrong"}` for every failure mode means the model can't branch on recovery. Define an error code enum the model can reason about.
- **Tool name collisions break routing silently.** Two tools named `search` with different scopes will confuse the model. Rename until the name alone is sufficient context.
- **Tool grouping helps but requires maintenance.** Dynamically exposing tool subsets by task phase is powerful, but each new phase needs a new group definition. Without a governance process, groups accumulate and overlap.
- **MCP's "USB-C for AI" promise hides the config burden.** Connecting an MCP server is one line, but making its tools actually work requires testing the schema, description quality, and error handling — not just the protocol handshake.
