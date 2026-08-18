# S-2808 · The Tool-Selection-Is-the-Failure Stack — Describing Tools to LLMs Correctly

When your agent calls the wrong tool, rephrases the system prompt, and it still picks the wrong one. Tool selection — not execution — is where agentic workflows break in production.

## Forces

- The model decides which tool to call primarily from the **description text** and **parameter names** — not from the system prompt, where most teams spend their debugging effort
- Tool definitions are context engineering: they occupy tokens, influence attention, and shape every downstream decision. A bad definition produces systematic failures across all tasks using that tool
- Adding more tools increases capability but compounds selection ambiguity — two similar tools with overlapping descriptions are a reliability trap
- Structured output enforcement varies by provider (OpenAI strict mode, Anthropic input_schema) — without it, models still produce best-effort tool calls even when the API contract says otherwise
- The gap between "can call a function" and "can use tools reliably across a multi-step workflow" is enormous and not bridged by better prompts

## The Move

Design tool definitions as precision context engineering, not descriptive documentation. The goal is unambiguous selection and parameter generation on every call.

**Be surgical about tool boundaries.** One tool per semantic action. If two tools share a similar domain, their descriptions must clearly state what each is NOT for — not just what it is for. The model needs disambiguation text, not more adjectives.

**Write descriptions that answer "which and why."** Include: what the tool does, when to call it, and explicitly when NOT to call it. Cross-reference similar tools by name in the description text — this is the primary disambiguation signal the model reads.

**Use required parameters only.** Optional parameters with no default confuse parameter construction. If a parameter is truly optional, give it a default in your schema and exclude it from required. Required + optional with no default = the model invents values.

**Validate before execution, not after.** Parse and validate the model's tool call arguments against the schema before any side effects. A malformed call that reaches your database is not a model failure — it is a validation gap.

**Enforce strict output where available.** OpenAI's strict mode (August 2024), Anthropic's input_schema, and Google's JSON mode all enforce schema adherence differently. Without enforcement, models produce best-effort calls. Use structured outputs for production tool calls.

**Design for the minimal tool surface.** Each additional tool adds selection candidates to every call. Prefer fewer, more capable tools over many narrow ones. If you have more than 15 tools, consider grouping them into a hierarchy or routing layer.

**Instrument at the tool-call level.** Log which tool was called, with what arguments, what came back, and whether the loop continued or terminated. The failure mode you cannot see is tool selection drift over time or on specific input distributions.

## Evidence

- **Hacker News (543 points):** Anthropic's "Building Effective AI Agents" post — the most-upvoted comment notes the highest-performing systems used simple composable patterns, not agent frameworks. Simon Willison: "The main lesson is that you don't need frameworks — just a loop." — [https://news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)

- **Research post (Adaline Labs):** On τ-bench, well-trained LLMs succeed on ~25% of agent tasks. The majority of failures trace to tool selection errors, not execution errors. Primary selection signals (in order): description text, parameter names, tool ordering — not the system prompt. — [https://labs.adaline.ai/p/ai-agent-tool-calling-failures](https://labs.adaline.ai/p/ai-agent-tool-calling-failures)

- **GitHub / real deployments:** Frigade built a browser-based agent that reverse-engineers web app API calls into auto-generated MCP tool definitions (called "recipes") — demonstrating that tool definitions are the critical integration layer, not the tool implementations themselves. — [https://news.ycombinator.com/item?id=48847834](https://news.ycombinator.com/item?id=48847834)

## Gotchas

- **System prompt debugging targets the wrong layer.** When a tool is called incorrectly, the reflex to adjust the system prompt is usually wrong. Adjust the tool description text — it is the primary selection signal.
- **Description length has a tradeoff.** Very long descriptions consume context window and reduce attention to other signals. Be precise but concise; the model processes descriptions as weighted features, not reading comprehension.
- **Tool ordering affects selection.** Tools earlier in the list have a positional advantage. When two tools are ambiguous, reordering the list is a real lever — not just a cosmetic one.
- **Schema strictness is provider-dependent.** Anthropic Claude will reject calls that don't match the input_schema. OpenAI's non-strict mode still produces best-effort calls. Test your provider's enforcement behavior before relying on it.
