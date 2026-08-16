# S-2715 · The Tool-Definition Overhead Stack — When Your Protocol Costs More Than Your Queries

[You connect five MCP servers — GitHub, Slack, Sentry, Grafana, Splunk — and before your agent does a single useful thing, 55,000 tokens have already been consumed by tool definitions. Then the agent calls one tool, gets a schema mismatch error, retries, compounds the error, and bills you $12,000 in an hour. The tool protocol that was supposed to extend your agent just broke it.]

## Forces

- **Tool definitions are loaded before the conversation starts.** MCP clients inject all connected tool schemas into context on every session. Five standard servers = ~55K tokens burned before the user says hello. One heavy configuration Anthropic saw reached 134K tokens — a third of a 200K context window, gone before work begins.
- **Tool execution accounts for 61% of all agent errors.** SIVARO's telemetry across 300 agent instances at 25 companies found that failures at the tool execution layer dwarfed model reasoning errors. The model is rarely the problem; the API is.
- **Schema defines structure but not behavior.** JSON Schema tells the agent what fields exist; it doesn't tell the agent what the API actually returns, what error codes mean, or which combinations of parameters are actually valid.
- **Token overhead and reliability pull in opposite directions.** Adding more tools makes the agent more capable but more expensive, slower, and more likely to hit schema mismatches. Stuffing the context with all tool definitions doesn't scale past ~50 tools.
- **Function hallucination is a distinct failure mode.** When an agent invents a tool call that doesn't exist, or calls a real tool with fabricated parameters, the failure is not incorrect text — it's an incorrect real-world action. Stanford research found 28–40% hallucination rates on specialized tasks for this mode.

## The Move

**Build tool definitions for discovery efficiency, not just capability coverage.**

- **Dynamic tool discovery over static injection.** Anthropic's November 2025 advanced tool use features introduced a Tool Search Tool pattern — the agent queries a tool registry at runtime rather than receiving all definitions upfront. Benchmarks show 85% token reduction versus static loading and 25% accuracy improvement. Apply this: connect a tool registry that the agent searches on demand, rather than passing all MCP schemas on every request.
- **Use tool use examples to anchor parameter expectations.** Anthropic found that providing 2–3 concrete examples of how a tool is called (not just the schema) improved parameter accuracy from 72% to 90% — an 18-point jump. Examples teach behavior that schemas cannot. Add a `examples` field to every tool definition, even when the schema is complete.
- **Implement nested timeout budgets, not flat retry loops.** Misar.blog's analysis: treating every LLM and tool call as a network call that will fail (1–3% of the time) and applying exponential backoff with jitter at each layer. A flat retry without backoff on a tool returning "retry later" can burn $12,000 in one hour. Budget time at the step level, not just the request level.
- **Validate tool responses against schema before returning them to the agent.** Schema drift — where a tool's implementation changes but the agent's definition doesn't — causes silent failures. The tool returns `{data: {value: string}}` but the agent was instructed to expect `{result: string}`. Catch the mismatch at the tool wrapper layer and surface it as an explicit error, not a silent field misread.
- **Set hard step-count guards per tool.** Agents can loop on a single tool indefinitely, especially when the tool returns partial results that look like progress. Cap the number of consecutive calls to the same tool (recommended: 3–5) and escalate or abort rather than continuing.
- **Screen screenshot resolution before browser use.** For agents with computer/browse access, Anthropic's May 2026 guidance: pre-downscale screenshots to fit API resolution limits before sending to the model. Claude 4.6 family maxes at 1568px long edge / 1.15MP total; Opus 4.7 at 2576px / 3.75MP. Images exceeding either limit get internally downscaled, causing coordinate misalignment that makes click targets miss.

## Evidence

- **Anthropic Engineering Blog:** Tool Search Tool reduced token consumption from ~77K tokens (traditional, 50+ MCP tools) to ~8K with dynamic discovery — an 85% reduction. Tool use examples improved parameter accuracy from 72% to 90% (18% absolute). Published November 24, 2025. — [URL](https://www.anthropic.com/engineering/advanced-tool-use)
- **SIVARO Practitioner Guide:** Across 300 agent instances at 25 companies, tool execution failures accounted for 61% of all agent errors. A single broken API cascaded silently for four hours at a major e-commerce platform, with 47% of customer-facing agents producing garbage responses while no alerts fired. Published July 29, 2026. — [URL](https://sivaro.in/articles/production-ai-agent-error-handling-a-practitioners-guide/)
- **Agents.NET / Vectara awesome-agent-failures:** Schema drift (tool definition diverging from implementation) and function hallucination (agent calling nonexistent tools or fabricating parameters) documented as distinct, common failure modes distinct from text hallucination. Vectara repo curates real-world production failure case studies from the community. — [URL](https://github.com/vectara/awesome-agent-failures)

## Gotchas

- **JSON Schema tells the model what fields exist, not how to use them.** Two tools with identical schemas can have different parameter requirements, rate limits, or error semantics. Schema parity does not equal behavioral parity.
- **Tool results accumulate in context regardless of relevance.** Even with tool discovery reducing upfront tokens, intermediate results from each tool call persist in the conversation context. Use programmatic tool calling to summarize or discard results that aren't relevant before the next step.
- **Connecting a new MCP server during a session doesn't re-inject definitions retroactively.** If the agent wasn't initialized with a tool, it can't discover it mid-session. Plan tool inventory at session start, not lazily.
- **Function hallucination rates on specialized tasks (28–40%) mean you cannot trust the model to never call a tool that doesn't exist.** Implement a validation guard at the tool execution layer that checks whether a called tool is actually registered before executing it.
- **Browser/computer use tools are fundamentally different from API tools.** They are perceptual and mechanical (click accuracy, screenshot interpretation) rather than logical. Optimizations that work for code-generation agents actively hurt UI automation agents.
