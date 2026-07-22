# S-1496 · The Tool-Contract Stack — When Your Agent Calls the Right Tool for the Wrong Reason

You wire up 10 tools. The agent picks the wrong one, or the right one with invented parameters, or calls a tool that doesn't exist. You add more descriptions, more examples. It gets marginally better but still fails in production. The tool infrastructure was never the problem. The tool contract — the way the agent understands what each tool does, when to use it, and what counts as a valid call — was underspecified from the start.

## Forces

- **The JSON schema is for machines, not models.** A parameter named `user_id` with type `string` tells the executor nothing about what format is valid, what happens if it's wrong, or why this parameter exists at all.
- **Tool descriptions dominate call accuracy.** Anthropic's engineering team found that the single highest-leverage change for reliable tool use was writing better tool descriptions — not better models, not more parameters, not guardrails around execution.
- **One bad call compounds.** At a 5% per-call failure rate — which practitioners actually observe even with frontier models — a 5-step task has a 23% task-level failure rate. Tool-call reliability is the bottleneck, not model reasoning.
- **Descriptions and schemas fight each other.** The JSON schema tells the model what to send. The natural-language description tells the model when to send it. If these are inconsistent, the model splits the difference and hallucinates.

## The move

**Write tools as typed contracts, not function definitions.** Treat each tool as a signed agreement between the agent and the executor, with three distinct layers:

- **Discovery layer** — what this tool can do and when to reach for it. Natural language. Specific about preconditions and postconditions. Example: "Use `send_email` when you have a complete draft ready to deliver. Do NOT use this to save a draft or schedule a future send — use `schedule_email` for those."
- **Schema layer** — exact parameter contract. Use `enum` for any field with a fixed set of values. Add `description` on every parameter. Constrain string formats (e.g., ISO 8601 for dates, RFC 5322 for emails). Never leave a parameter undocumented.
- **Validation layer** — never trust the model's output. Every tool executor must validate parameters against trusted server state before execution. The model can invent user IDs, price values, or permissions; your code must look these up independently.

**Design for the executor, not the model.** The QubitTool production guide puts it directly: "The JSON is not the security boundary. The executor is." Derive user identity, permissions, prices, and ownership from server state — not from the model's arguments.

**Separate read tools from write tools.** Reads can be retried freely. Writes need idempotency keys and explicit previews before commit. A refund tool and a purchase tool must not share a generic "transaction" name — the wrong one called with wrong values costs money.

**Use MCP (Model Context Protocol) for standardization.** Since Anthropic released MCP in November 2024, the ecosystem has grown to 9,652+ servers in the official registry, 97M+ monthly SDK downloads, and 41% of surveyed organizations in production with MCP servers. MCP standardizes tool discovery and invocation — implement once, connect to the full ecosystem. The protocol also makes tools auditable at the transport layer, which matters for the executor validation requirement.

**Minimize the toolbox.** Anthropic's production analysis found the most reliable implementations used the fewest tools necessary. A monolithic agent with 20 tools is harder to route reliably than one with 3–5 well-scoped tools. Add tools only when a distinct capability genuinely cannot be expressed with existing ones.

**Write descriptions that specify exclusion criteria.** Tell the model when NOT to use a tool, not just when to use it. "Use `search_database` to find existing records. Do NOT use it to create, modify, or delete records — use `update_record` or `delete_record` instead." This dramatically reduces tool-selection hallucination.

## Evidence

- **Engineering blog:** Anthropic's "Building Effective AI Agents" (December 2024) — the most-cited production findings in the field — found that the strongest predictor of tool-call reliability was the quality of tool descriptions, not model capability. They recommend writing tool descriptions that include preconditions, postconditions, and exclusion criteria. — [URL](https://www.anthropic.com/engineering/building-effective-agents)
- **Research survey:** The arxiv survey "Model Context Protocol (MCP): Landscape, Security Threats, and Future Research Directions" (March 2025) documents MCP's growth from a niche protocol to a production foundation: 9,652+ servers in the official registry, 15,926 GitHub topic repositories, 97M+ monthly SDK downloads, and 41% of surveyed organizations using MCP in production. — [URL](https://arxiv.org/html/2503.23278v2)
- **Engineering guide:** QubitTool's "LLM Tool Calling: Production Architecture and Safety" (February 2026) codifies the executor-validation principle: tool calls are untrusted model output even when strict schema mode guarantees their shape. Their production rule: derive all authorization, ownership, and business logic from server state, never from model-supplied arguments. — [URL](https://qubittool.com/blog/llm-function-calling-complete-guide)
- **Research taxonomy:** EmergentMind's "Tool-Use Hallucinations" (January 2026) documents the five subtypes — tool-selection hallucination, tool-usage hallucination, solvability hallucination, tool-induced myopia, and bypass — and notes that even frontier models fumble roughly one in twenty tool invocations in production, with compounding task-level failure rates. — [URL](https://api.emergentmind.com/topics/tool-use-hallucinations)

## Gotchas

- **Vague descriptions cause wrong-tool selection.** "Retrieves data" tells the model nothing about when to retrieve vs. create. Be specific about trigger conditions and data shapes.
- **Overly broad schemas cause hallucinated parameters.** If a parameter accepts any string, the model invents plausible-looking values. Use enums, format constraints, and minimum/maximum values to prune the hypothesis space.
- **Idempotency is not optional for write tools.** If a tool call is retried (which happens on network timeouts), a non-idempotent write creates duplicate records, incorrect balances, or double-sent messages. Add idempotency keys to every write operation.
- **Tool descriptions and JSON schemas can contradict each other.** If your description says a date must be ISO 8601 but the schema says `type: string` with no format, the model will guess wrong. Keep both layers consistent and over-constrained.
- **The executor is the security boundary.** Validating a tool call against the model's JSON output is not a security measure — it's a correctness measure. Authorization, authentication, and capability checks belong in the executor, not in the tool description.
