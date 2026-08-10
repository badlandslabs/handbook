# S-2428 · The Tool Definition Stack — When the Model Is Right But the Schema Is Lying

Your agent fails. The model is capable. The tool works when you call it manually. But the agent misroutes, miscalls, or misinterprets the result. You blame the LLM. You switch models. The failure persists. The problem was never the model — it was the contract between the model and the tool. Every production failure that looks like a hallucinated argument or a wrong tool choice is, on closer inspection, a schema failure: under-specified types, missing enums, ambiguous descriptions, undocumented error envelopes, and tools that retry into their own side effects.

## Forces

- **Tool definitions are not documentation — they are a wire protocol.** A function schema consumes 150–400 tokens and is the primary signal the model uses for tool selection and argument construction. Teams treat it like a docstring. It isn't.
- **More tools destroy accuracy.** When Writer instrumented their RAG-MCP benchmark, tool selection accuracy was 13.62% with no retrieval — not 60%, not 80%. With retrieval-augmented tool selection exposing only the relevant subset, accuracy jumped to 43%. The same model, same tools, different visible definitions. Beyond a surprisingly low threshold, adding tools to an LLM agent does not increase capability — it destroys it.
- **Errors are the most under-designed part of any tool.** Bare string errors force the model to guess failure type from phrasing. "Account not found" and "service temporarily unavailable" both produce "please try again" — correct for one, wrong for the other. The refund incident (process_refund retried on timeout, no idempotency key, refund executed 5 times) was not a model failure. It was an error-design failure.
- **Schema drift is silent and semi-permanent.** When a dependency update changes a tool's response format, the tool still works — but the interface contract has silently shifted. A retry without prompt adjustment will fail identically. Teams don't discover these until production.
- **The tool layer has most of the actual risk.** The model is rarely the source of a production incident. The tool is. Coinbase deploying with OpenAI Agents SDK proved the point: the framework gets you started, but the schema is where production breaks.

## The Move

**Design tool schemas as typed contracts, not docstrings. Keep them few, use retrieval to subset them at call time, and make every error structured and idempotent.**

### Schema design

- **Name tools imperatively and specifically** — `fetch_customer_orders` not `get_data`. The verb-noun pattern gives the model a clear action signal.
- **Use enums for all constrained string fields** instead of free-text with a description. If a field has 5 valid values, list all 5. The model will pick one instead of inventing one.
- **Write descriptions for parameters, not just for the function.** Every parameter description should answer: what does this field mean, what values are valid, what happens if I get it wrong? One sentence per parameter minimum.
- **Return structured error objects** with four fields: `error: true`, `errorCategory` (one of: validation, transient, auth, schema_drift), `isRetryable: boolean`, `message: string`. This replaces guesswork with a deterministic recovery path. An AWS sample pattern shows this directly — the model no longer interprets phrasing, it reads a field.
- **Set `required` arrays correctly.** Mark fields truly required. Missing required fields are a schema failure, not a model failure.

### Tool management at scale

- **Never load all tool definitions upfront.** Anthropic's MCP engineering post documents 50,000+ token tool definition loads. Use retrieval to surface only relevant tools per task context. Dynamic tool loading is the production standard, not the exception.
- **Apply least privilege to tool permissions, not just data.** A tool called `delete_user` should not exist unless the agent needs it. Tools that exist but shouldn't be called are a governance gap, not a model gap.
- **Cap tool loops with an explicit `max_turns` upper bound.** When an LLM keeps calling tools and doesn't converge, an unbounded loop burns cost and availability simultaneously. Raise a runtime exception on cap hit — the signal "it didn't converge" is itself operationally important.

### Idempotency and retry safety

- **Every tool that has side effects must accept an idempotency key.** Without one, a retry on timeout is a double execution. The refund case is the canonical example; it applies to any write operation.
- **Distinguish retryable from non-retryable failures explicitly.** A `validation` error is never retryable. A `transient` error should carry a backoff hint. The error category drives the retry policy, not the model.

## Evidence

- **Blog post (Tian Pan / tianpan.co):** Tool selection accuracy drops to 13.62% with no retrieval when agents face a large tool set — rises to 43% with retrieval-augmented tool selection exposing only the relevant subset. Direct benchmark from Writer's RAG-MCP testing. — [tianpan.co/blog/2026-04-19-over-tooled-agent-problem](https://tianpan.co/blog/2026-04-19-over-tooled-agent-problem)
- **Engineering blog (Anthropic, Nov 2025):** MCP at scale creates 50,000+ token tool definition loads. Solution: load tools on demand via retrieval, filter data before it reaches the model. — [anthropic.com/engineering/code-execution-with-mcp](https://www.anthropic.com/engineering/code-execution-with-mcp)
- **AWS sample (aws-samples/sample-agentic-design-patterns):** Structured error classification pattern replaces bare string errors with `errorCategory`, `isRetryable`, and `message` — makes agent recovery behavior deterministic rather than contingent on model interpretation. — [github.com/aws-samples/sample-agentic-design-patterns/blob/main/patterns/07-structured-error-classification/README.md](https://github.com/aws-samples/sample-agentic-design-patterns/blob/main/patterns/07-structured-error-classification/README.md)
- **Engineering blog (MetaCTO, July 2026):** Refund tool retried on transient timeout with no idempotency key — executed 5 times. Root cause was not model hallucination but a production tool-calibration failure. — [metacto.com/blogs/ai-agent-tool-calling-production](https://www.metacto.com/blogs/ai-agent-tool-calling-production)
- **Survey (Cleanlab, Aug 2025):** 95 production AI teams. Only 5% cite accurate tool calling as a top challenge — not because tool calling is solved, but because teams are still building the scaffolding to even measure it. 70% of regulated enterprises rebuild their AI agent stack every three months or faster. — [cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)

## Gotchas

- **Describing what a tool does is not the same as constraining what it accepts.** A 200-word function docstring does nothing if the parameter schema has no enums and no type constraints. The schema is the contract; the description is the explanation.
- **Retrieval-augmented tool selection is not optional at scale.** Without it, you are deliberately degrading accuracy to 13%. If you have more than ~10 tools, you need a tool retrieval layer. MCP with dynamic loading is the standard implementation path.
- **Retry logic without idempotency keys converts transient failures into data corruption.** This is the single most common production tool mistake. Add idempotency keys to every write tool before it ships.
- **Schema versioning is invisible to the model.** When you change a tool's response format, existing sessions still have the old schema in context. You need a schema version field and a session invalidation strategy.
