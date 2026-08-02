# S-2043 · The Agent Cost Ceiling Stack — When Your Agent Runs for 11 Days and Costs $47,000

Your agent is still running. It has been running for three days. Nobody touched it. It's burning $200/hour in API calls, looping on the same failed task, and producing nothing. There was no error. There was no alert. There was no circuit breaker. A team using LangChain with A2A coordination learned this cost $47,000 over four weeks before someone noticed the anomaly. The lesson isn't that the agent was broken. It's that you built the intelligence layer but forgot the safety layer.

## Forces

- **Agents fail silently, not loudly.** Traditional software crashes and throws stack traces. Agents return HTTP 200 with confident wrong answers, loop without raising exceptions, and accumulate context until the model halts.
- **Retry loops compound costs exponentially.** Every failed tool call that retries without backoff doubles your cost ceiling. Without per-tool failure tracking, the agent hammers the same broken endpoint until context exhaustion.
- **Irreversible actions happen before rollback is possible.** A `DROP TABLE` executes successfully. An S3 deletion completes. The agent "completed" the task. The damage is done.
- **Coordination failures cascade invisibly.** In multi-agent systems, specification failures account for ~42% of failures, coordination breakdowns for ~37%, and verification gaps for ~21% (Galileo, 2025).
- **The infrastructure layer is immature.** A2A and MCP are real, but the scaffolding — circuit breakers, cost ceilings, rollback checkpoints — doesn't ship with any framework.

## The move

Build the safety layer first, before the intelligence layer.

### 1. Cost ceiling per task, not per session

Set a hard token-and-dollar budget per agent task. Track cumulative cost at the orchestration layer. When the budget is exceeded, halt the agent, log the state, and escalate. This is the single highest-ROI safety investment — it turns runaway loops into finite, accountable tasks.

### 2. Per-tool circuit breakers

Wrap every external tool call in a circuit breaker that tracks consecutive failures per tool. After N failures, the breaker opens: subsequent calls to that tool return a fallback response instead of retrying. This prevents agents from burning tokens hammering a degraded endpoint.

Implementation: a simple state machine per tool with three states (closed, open, half-open) and configurable failure thresholds. This is tool-agnostic and framework-portable.

### 3. Irreversibility gates for destructive actions

Classify tool calls by reversibility. Destructive actions (DELETE, DROP, rm -rf, payment APIs, Slack channel deletion) require a pre-execution checkpoint and a human-in-the-loop gate above a cost or blast-radius threshold. The agent proposes the action; the gate confirms it. IBM STRATUS (research) uses command simulation before execution — run the tool in a sandbox first, validate the output matches intent, then execute in production.

### 4. Checkpoint and rollback per agent session

Store agent state snapshots at defined milestones: before major tool calls, after state-mutating operations, after every N steps. A checkpoint stores conversation history, tool call results, and external state references. On failure or budget breach, rollback to the last checkpoint instead of restarting from scratch. This preserves partial work and reduces token costs on recovery.

### 5. Explicit error taxonomy in agent instructions

Agents don't know what "failure" means unless you define it. Your system prompt must include an explicit taxonomy: which return codes from which tools constitute retriable failures vs. terminal failures, and what the fallback behavior is for each. This turns implicit error handling into explicit contract.

### 6. Tiered escalation ladder

Define five escalation levels for agent failures:
1. **Retry with backoff** — transient errors, rate limits, brief unavailability
2. **Circuit breaker open** — persistent tool failure → fallback or skip task
3. **Checkpoint rollback** — agent produced no progress in N steps → restore last checkpoint
4. **Human escalation** — irreversible or high-stakes failure → human review required
5. **Hard stop** — cost ceiling exceeded or safety boundary violated → terminate and alert

## Evidence

- **Case study:** A team running a four-agent LangChain A2A system for market research burned $47,000 over four weeks. Week 1: $127. Week 2: $891. Week 3: $6,240. Week 4: $18,400+. Root cause: no cost ceiling, no circuit breaker, no alerting on cost anomalies. The system had intelligence but no safety layer. — [Towards AI / Medium](https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-nobody-tells-you-about-a2a-and-mcp-5f845848de33)

- **Data:** Galileo (2025) analyzed multi-agent production deployments: ~42% of failures stem from specification failures (wrong task definition), ~37% from coordination breakdowns (agents sending malformed messages), ~21% from verification gaps (no output validation). Zylos Research found that comprehensive layered error handling (retries → fallbacks → circuit breakers) yields 24%+ improvement in task success rates. — [Zylos Research — AI Agent Error Handling & Recovery (2026-01-12)](https://zylos.ai/research/2026-01-12-ai-agent-error-handling-recovery)

- **Pattern catalog:** The Agent Patterns community (nibzard/awesome-agentic-patterns) documents the agent circuit breaker as an established pattern: wrap external tools with per-tool failure-tracking state machines that block calls during degraded states, preventing token waste on retry loops. Includes reference Python implementation. — [Agent Patterns — Agent Circuit Breaker](https://www.agentpatterns.ai/patterns/agent-design/agent-circuit-breaker)

## Gotchas

- **A retry loop doesn't raise an exception.** The agent keeps getting HTTP 200 responses — just wrong ones. You need structural cost tracking, not error-logging, to detect it.
- **Circuit breakers must be per-tool, not global.** A search API timeout should not block your email tool. Global breakers are too coarse-grained.
- **Checkpoint storage is not free.** Serializing full conversation state at every milestone inflates storage costs. Set checkpoints at semantic boundaries (after each sub-task), not at every turn.
- **Human-in-the-loop gates kill autonomy.** Use them only for irreversible, high-stakes, or high-cost actions. Gate everything and you've built a very expensive approval workflow, not an agent.
- **The 11-day loop will happen to you.** The team that burned $47K had no alerting on cost anomalies. Set up spend-per-agent alerts before you ship, not after.
