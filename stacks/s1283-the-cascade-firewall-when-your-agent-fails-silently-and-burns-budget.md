# S-1283 · The Cascade Firewall — When Your Agent Fails Silently and Burns Budget

Your agent runs in production. The tool API times out. The agent retries — naively, immediately, and repeatedly. Forty-seven thousand tokens later, your monitoring tool shows no alert because it logged every call as a successful API interaction. The traces are technically valid. The outcome is a catastrophe. This is the cascade firewall pattern: layered error handling that prevents a single failure from becoming a budget event.

## Forces

- **Agents fail non-deterministically** — a tool timeout isn't a crash; it's a silent retry opportunity that a naive agent takes. Without explicit guardrails, the agent interprets "no result" as "try again with a slight variation," burning tokens until context or budget runs out. (Alan West, DEV Community, May 2025 — https://dev.to/alanwest/why-your-ai-agent-loops-forever-and-how-to-break-the-cycle-12ia)
- **Error propagation is the central bottleneck** — a single failure cascades through planning, memory, and action modules. Without explicit error taxonomy and containment, one bad tool result poisons the agent's reasoning for the rest of the session. (Zylos Research, January 2026 — https://zylos.ai/research/2026-01-12-ai-agent-error-handling-recovery/)
- **Monitoring tools show what happened, not whether it worked** — LangSmith, LangFuse, Arize, and Helicone surface traces, latency, and token counts. They do not answer "is my agent healthy right now?" An agent burning through retries logs every call as a successful tool invocation. (Ceyhun Aksan, DEV Community, March 2026 — https://dev.to/ceaksan/an-ai-agent-got-stuck-in-a-loop-the-monitoring-tools-saw-nothing-1ai)
- **Tool parameter hallucination is distinct from tool hallucination** — the agent calls the right tool by name but with fabricated parameters (non-existent IDs, invalid enum values, wrong date formats). This doesn't produce an error — it produces a silent wrong result that the agent accepts and continues from. (Harsh Rastogi, Modelia.ai, March 2026 — https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

## The Move

Build a layered defense stack: each layer catches what the previous layer missed, and every layer has a hard budget.

### Layer 1 — Classify before acting
Give the agent an explicit error taxonomy. Map every failure mode to a category before deciding what to do:

- **Transient** (network timeout, 429 rate limit): retry with backoff
- **Semantic** (tool returned empty, wrong schema, hallucinated params): do not retry the same tool; escalate to fallback
- **Structural** (context overflow, invalid tool call syntax): halt and surface to human
- **Behavioral** (agent has repeated the same action N times): hard stop, increment failure counter

(Harsh Rastogi / Modelia.ai — https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

### Layer 2 — Hard budgets on every retry path
Never retry without limits. Each retry tier has explicit budgets:

- Tier 1: immediate retry × 1 (transient blips)
- Tier 2: exponential backoff with jitter × 3 (rate limits, brief outages)
- Tier 3: wait for user/operator decision (semantic failures, structural failures)

Budgets are not prompts — they are enforced at the framework level, not passed to the LLM. A ReAct agent with a retry instruction in its system prompt will still ignore it under stress. Budget enforcement must live outside the agent's reasoning loop. (Zylos Research — https://zylos.ai/research/2026-01-12-ai-agent-error-handling-recovery/)

### Layer 3 — Tool input validation gate
Before executing any tool call, validate parameters against the tool's schema. Catch hallucinated parameters at the calling layer — not inside the agent. This prevents the "wrong tool, right call" failure class entirely.

```python
def validate_tool_params(tool_name: str, params: dict) -> None:
    schema = TOOL_SCHEMAS[tool_name]
    for key, spec in schema.items():
        if spec.get("required") and key not in params:
            raise ToolParamMissingError(f"{tool_name} missing required param: {key}")
        if key in params and not isinstance(params[key], spec["type"]):
            raise ToolParamTypeError(f"{tool_name} param {key} has wrong type")
```

(Harsh Rastogi — https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

### Layer 4 — Stateful checkpointing with rollback
Use LangGraph's checkpoint API or Microsoft Agent Framework's checkpoint/resume primitives. On failure, the agent can resume from the last validated checkpoint rather than restarting from scratch. Checkpoints go to durable storage (PostgreSQL in production; SQLite is fine for dev). (ombharatiya/ai-system-design-guide, December 2025 — https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md; vasuthasankaran/langgraph-production-patterns, 2026 — https://github.com/vasuthasankaran/langgraph-production-patterns/blob/main/readme.md)

### Layer 5 — Explicit stop conditions in the prompt — AND hardcoded budget
Vague instructions like "be thorough" or "verify carefully" tell the agent to keep going. Pair every soft stop condition in the prompt with a hard budget:

- Soft: "Stop after finding 3 relevant sources"
- Hard: `max_tool_calls_per_session = 10` — enforced outside the prompt

Motion is not progress. The agent keeps moving, but the system isn't progressing. Hard budgets prevent this. (Modexa, Medium, February 2026 — https://medium.com/%40Modexa/the-agent-loop-problem-when-smart-wont-stop-ccbf8489180f)

## Evidence

- **Real-world incident:** A ReAct-style customer support triage agent called `search_knowledge_base` 73 times in one session, burning 47,000 tokens. No alert fired. The agent was following its instructions faithfully — it interpreted 72 failed searches as "search harder." Fix: add an explicit "already searched this" tracking set and a hard `max_calls_per_tool` budget. (Alan West — https://dev.to/alanwest/why-your-ai-agent-loops-forever-and-how-to-break-the-cycle-12ia)
- **LangGraph production patterns:** Enterprise teams using LangGraph with Azure OpenAI implement interrupt/resume with external approval for high-stakes actions (e.g., purchase orders over a threshold), SQLite checkpoints in dev graduated to PostgreSQL in production. This pattern enables the graph to pause indefinitely, survive restarts, and resume from the last checkpoint rather than re-executing from the beginning. (vasuthasankaran/langgraph-production-patterns — https://github.com/vasuthasankaran/langgraph-production-patterns/blob/main/readme.md)
- **n8n reliability toolkit:** Open-source community project (MIT license) implementing retry logic, model fallback chains (OpenAI → OpenRouter → Anthropic), output validation via Pydantic schemas, and error isolation so a single tool failure doesn't crash the pipeline. Documents the four silent killer failure modes: no retry, no fallback, no validation, no monitoring. (jerryLee18/n8n-ai-agent-reliability-toolkit — https://github.com/jerryLee18/n8n-ai-agent-reliability-toolkit)

## Gotchas

- **Retrying at the framework level is not the same as retrying in the prompt.** A prompt instruction "if the tool fails, try again" will be ignored under load. Budget enforcement must be structural — it cannot live inside the agent's reasoning.
- **Empty results are ambiguous.** A tool returning `[]` could mean "no matches found" or "the tool failed silently." Treat empty results as a distinct failure category with a separate recovery path (fallback tool, not retry).
- **Checkpointing alone doesn't prevent loops.** If the agent checkpoints every step but still has no stop condition, it will checkpoint its way into a budget exhaustion event. Checkpoints must pair with budgets.
- **The loop detection metric is call count per tool per session — not error rate.** LangSmith and LangFuse surface latency and error rates. They do not surface "this tool was called 73 times with semantically similar queries." Instrument this specifically.
