# S-2700 · The Handoff Stack — When Your Agent Must Decide Whether to Pass the Conversation or Hold It

Every multi-agent architecture eventually hits the same fork: should a specialist agent take control of the conversation, or should the orchestrator stay in charge and call specialists as bounded subroutines? Getting this wrong produces either agents that hand off and never come back, or orchestrators so overloaded with context they call the wrong specialist every time. The handoff stack is the decision framework production teams use to make this call explicitly, consistently, and with observable boundaries.

## Forces

- **Context ownership is a zero-sum game.** When control passes to a specialist, the original context can degrade; when the manager retains it, the specialist works blind without it
- **Fault isolation vs. traceability.** Handoffs create clean failure boundaries — a crashed specialist doesn't kill the manager — but they also break the causal trace unless you instrument the handoff itself
- **Framework defaults hide the trade-off.** OpenAI Agents SDK and Anthropic Claude SDK both expose handoff primitives, but neither tells you which pattern fits your latency and accuracy constraints
- **Teams default to one pattern everywhere.** The "always handoff" and "always agents-as-tools" camps each ship brittle systems until they learn the selection criteria

## The Move

The canonical decision: **handoff** when a specialist should own the entire branch of the conversation end-to-end; **agents-as-tools** when the manager needs to stay in control, synthesize across specialists, or return a unified answer to the user.

### Handoff Pattern
- **Use when:** a specialist domain is deep, isolated, and self-contained (e.g., a code-review agent that owns the full review loop, a legal-agent that drafts and revises contracts independently)
- Control transfers fully to the specialist; the orchestrator waits for a result
- Handoff includes a structured context bundle: task description, user intent, constraints — not just the conversation history
- Set explicit termination conditions in the handoff contract so the specialist knows when to return control

### Agents-as-Tools Pattern
- **Use when:** the orchestrator must synthesize across multiple specialists, maintain a unified user-facing response, or route dynamically based on intermediate results
- Specialists are invoked as bounded tool calls — they do their piece and return a result object to the manager
- Manager retains full conversation state and decides what to do with each specialist result
- Best for pipelines where the final answer is an aggregate (e.g., research summary that combines web search, data analysis, and synthesis)

### Hybrid: The Orchestrator-Worker Hierarchy
- **Use when:** tasks are long-horizon, multi-staged, and require planning before execution
- Orchestrator (planner agent) breaks down the goal, creates a task graph, delegates to worker agents, and monitors completion
- Workers have narrow tool sets focused on one domain (code search, file editing, testing, deployment)
- Workers return results up the hierarchy; orchestrator decides next steps — this is the dominant pattern in enterprise coding agents (Cosine at re:Invent 2025, Anthropic's multi-agent research system)
- Single context window per agent — workers don't share state except through orchestrator messages, preventing blast-radius failures

### Error Handling Across Both Patterns
- **Layer 1:** Tool-level validation — validate tool call arguments before execution (type checking, permission scoping)
- **Layer 2:** Guardrails — validate agent outputs before they propagate (output shape, safety filter, domain constraints)
- **Layer 3:** Orchestrator-level retry budgets — set max retry counts per specialist; if exceeded, fall back to a default or escalate to human
- Never let a worker agent crash silently — every handoff should have a timeout and a dead-letter destination

## Evidence

- **Engineering blog (CODERCOPS, Feb 2026):** Documented the orchestrator-worker hierarchy with Claude SDK as the production standard for multi-agent systems — specifically citing tool confusion and context overflow as the failure modes that force decomposition beyond single agents — [Multi-Agent Orchestration with Claude Agent SDK and MCP: A Production Architecture Guide](https://blog.codercops.com/blog/multi-agent-orchestration-claude-sdk-mcp-2026)
- **HN Ask HN thread (Aug 2026):** Production teams overwhelmingly report building custom orchestration layers even when starting with LangGraph or CrewAI — one respondent (segnondy): "there's absolute 0 framework out there that's good enough for serious work" — [Ask HN: How are you orchestrating multi-agent AI workflows in production?](https://news.ycombinator.com/item?id=47660705)
- **arXiv paper (Dec 2025):** Nine production patterns from enterprise deployments including handoff, sequential, concurrent, group-chat, and plan-first — also documents the layered error-handling approach (tool validation → guardrails → orchestrator retry) as the standard production defense-in-depth model — [A Practical Guide for Designing, Developing, and Deploying Production-Grade Agentic AI Workflows](https://arxiv.org/pdf/2512.08769)
- **OpenAI Agents SDK docs (2025):** Explicit pattern matrix: handoffs for "a specialist should take over the conversation," agents-as-tools for "a manager should stay in control and call specialists as bounded capabilities" — [Orchestration and handoffs](https://developers.openai.com/api/docs/guides/agents/orchestration)

## Gotchas

- **Handoffs without termination conditions create zombie conversations.** If the specialist has no explicit signal for "I'm done," it keeps generating — set a return trigger in the handoff contract
- **Agents-as-tools without result schemas produce unstructured returns.** Define the expected output shape for every specialist before invoking it; otherwise the manager receives prose it must parse, which is unreliable at scale
- **The orchestrator becomes the bottleneck.** In hierarchical systems, the orchestrator's context window fills with accumulated worker results; implement periodic context summarization or truncation
- **Framework handoff primitives don't include observability.** Both OpenAI Agents SDK and Claude SDK handoff mechanisms are execution primitives only — you must add your own tracing (e.g., LangSmith, Phoenix) to make failures debuggable
