# S-821 · The Production Failure Stack — Loop Detection, Circuit Breakers, and Cost Governors

You shipped an agent. It ran for 11 days. The invoice was $47,000. This is not a model problem — it is an infrastructure problem, and it is entirely predictable.

## Forces

- **Agent loops are the default behavior, not the exception.** A planning agent that re-evaluates its own output will do so indefinitely unless explicitly constrained. The LLM does not know when to stop — that contract must be enforced by the system around it.
- **Failure cascades are invisible in development.** Local testing with fixed context gives no signal about cost trajectory, token burn rate, or loop behavior under production load. Problems surface only under real usage, at real cost.
- **Retry logic is a double-edged sword.** A naive `except: retry` block will retry everything — including cases where retrying wastes money and compounds the problem. The taxonomy of failure types must precede the retry strategy.
- **The gap between demo and production is architectural.** Anthropic's own SDK documentation states it explicitly: "The distance between a working demo and a production agent is larger than most teams expect."

## The move

Structuring failure handling as a layered system, not a catch-all exception handler.

### 1. Classify failures before you respond to them

Group failures into four types, each demanding a different response:

| Failure type | Examples | Correct response |
|---|---|---|
| **Transient** | Rate limits (429), server errors (503), network timeouts | Retry with exponential backoff (base: 1s, cap: 60s, jitter) |
| **Persistent** | Provider outage, quota exhausted, invalid API key | Fallback to secondary model/provider, or surface error to user — do NOT retry |
| **Bad Input** | Content policy violation, malformed tool response | Skip and re-plan — retrying won't fix the cause |
| **Agentic** | Infinite loops, dead-end planning, tool misuse | Structural fix: step limit, state reset, or human handoff |

Do not use a single retry block for all four. Transient retry on a persistent failure burns money without solving the problem.

### 2. Enforce step-count guards on every agent loop

The observe → plan → act → evaluate → loop is the agent's natural structure. Without a hard step limit, it is an unbounded while loop.

- Set a configurable `max_steps` per agent (default: 10–20 for task agents, 5 for planning agents)
- Track step count in agent state, not in context — the LLM should not self-report its own iteration count
- On step-limit reached: log the full trajectory, surface a structured error, do not silently retry

The hamster-wheel failure — where the agent re-evaluates its own output endlessly — is the most expensive production failure mode and the most preventable.

### 3. Build circuit breakers at the tool and cost layer

Protect against cascading failures and runaway spend:

- **Cost circuit breaker:** Set a per-session and per-request spend cap. Track token consumption per agent turn. Fail fast when a single interaction exceeds threshold. The $47,000 invoice from Kusireddy (TowardsAI, Oct 2025) had no cost governor — the agent was allowed to run indefinitely.
- **Rate-limit circuit breaker:** Track consecutive 429s per provider. After 3 consecutive failures, switch to a fallback model or queue the request — do not retry in a tight loop.
- **Tool circuit breaker:** If a tool call consistently fails or times out, mark it degraded and reroute around it. A single misbehaving tool should not halt the entire agent.

### 4. Instrument the full trajectory, not just the output

Every agent turn should record: input state, tool calls made, responses received, output produced, and cost incurred. This data serves three purposes:

- **Debugging:** Reconstruct exactly why an agent took a wrong turn
- **Evaluation:** Measure whether new prompt versions actually reduce failure rates
- **Cost attribution:** Know which workflows, users, or agents are driving spend

OpenAI Agents SDK ships built-in tracing as a first-class primitive. Anthropic's SDK leaves durable state instrumentation as a developer responsibility. Budget engineering time for it.

### 5. Implement structured fallback routing

When the primary model or tool fails:

1. Attempt retry with backoff (transient failures only, max 2 retries)
2. Route to a smaller/faster model for the same task (fallback model routing)
3. Route to a simpler heuristic if the task is recoverable without the LLM
4. Surface a structured error with the full trajectory to the user — do not return a partial or misleading result

The fallback chain must be defined *before* production, not discovered during an outage.

## Evidence

- **HN Ask thread (Harper Labs, 2025):** Surveyed real teams shipping AI agents and found consistent failure patterns. Built a framework around 7 failure modes. Key insight: failure patterns are consistent enough across teams that systematic prevention works. — [news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)
- **TowardsAI production report (Kusireddy, Oct 2025):** Team ran 4 LangChain agents with A2A + MCP coordination. No cost governor, no step limit, no token estimation. Week 1 cost $127. By week 4 the invoice was $47,000. Root causes: unbounded agent loops, no context caching, no state persistence per agent. — [pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production](https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-nobody-tells-you-about-a2a-and-mcp-5f845848de33)
- **Plain English engineering analysis (Feroz, May 2026):** Stanford HAI research cited: 68% of enterprise AI agent failures in production trace to recovery loops rather than the original failed step. Core argument: "Most agentic AI failures are not model failures. They are engineering failures — predictable, repeatable, and entirely preventable." — [ai.plainenglish.io](https://ai.plainenglish.io/your-ai-agent-isnt-hallucinating-it-s-failing-by-design-9d6b28349817)
- **Agentbrisk failure taxonomy (March 2026):** Systematic breakdown of failure types with matched recovery strategies. Key finding: a naive `except: retry` is worse than no error handling because it retries persistent failures that cannot be resolved by retry. — [agentbrisk.com/blog/ai-agent-error-recovery-2026](https://agentbrisk.com/blog/ai-agent-error-recovery-2026)
- **Gartner projection (cited in multiple sources, 2025-2026):** Over 40% of agentic AI projects will be cancelled by end of 2027, citing spiraling costs, unclear business value, and inadequate risk management. — [preprints.org manuscript 202604.2147](https://www.preprints.org/manuscript/202604.2147)

## Gotchas

- **Adding more retry logic makes things worse.** Teams that add retry blocks without classifying failure types see cost double or triple because every persistent failure now generates a retry storm.
- **Step limits must be enforced by the system, not requested of the agent.** Asking an LLM to "stop after 5 steps" does not work — it will not reliably count its own steps. Enforce it in the agent loop controller.
- **Context caching does not substitute for memory.** Caching reduces cost on repeated context, but it does not help when an agent needs to resume an interrupted task. Agent state persistence (checkpointing) and session resume are separate concerns.
- **Guardrails are not optional for production.** OpenAI's Agents SDK ships guardrails as a built-in primitive because input/output validation and behavioral constraints are load-bearing for anything customer-facing. Teams that skip them ship a safety surface that external actors will probe.
- **The demo-to-production gap is architectural, not a matter of tuning.** Teams that succeed do not find better prompts — they build the infrastructure layer (state, cost tracking, circuit breakers, trajectory logging) first and then layer the LLM on top.
