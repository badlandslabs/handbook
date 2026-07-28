# S-1726 · The A2A Task State Divergence Stack — When Your Agent Sends a Task and Never Knows If It Arrived

Your multi-agent pipeline runs on A2A. Your planner agent sends a task to a specialist, gets a `completed` status, and continues. The workflow looks clean. Two hours later the specialist's output is wrong — it processed the wrong account ID, ran against stale data, or never received the delegation context. The A2A protocol says the task is `completed`. Your business logic says the result is garbage. This gap — between what A2A reports and what actually happened — is the A2A Task State Divergence problem.

You reach for this when your multi-agent pipeline produces confident, traceable-looking outputs that are silently wrong, or when you can't tell whether a boundary failure is a timeout, a poison-pill output, or an agent that never received the work.

## Forces

- A2A's `Task` status field (`submitted → working → completed / failed / input-required / canceled / unknown`) is self-reported by the server agent — the protocol has no built-in acknowledgment from the receiving agent's downstream systems
- `LongRunningFunctionTool` in Google ADK has a documented bug where tasks never transition to `completed` despite successful execution, leaving clients polling `working` indefinitely (GitHub #4145, Jan–Feb 2026, still open)
- A2A v1.0.0 deliberately omits built-in authorization (see S-1722), which means a `completed` Task can represent work done under wrong credentials or wrong context
- A2A's `AgentCard` registry and identity verification proposals (issues #741, #1672) are open as of mid-2026 — agent discovery is manually configured, not cryptographically attested
- 86% of multi-agent pilots never reach production (AppScale, Jul 2026); the dominant failure mode is silent boundary failures at agent-to-agent handoffs, not LLM capability

## The move

**Verify the Task output, not just the status.**

```
mcp
# A2A Task State Verification — output receipt vs status receipt

# 1. The divergence: A2A reports completed, downstream is wrong
# The Task status field tracks protocol state, not business-logic outcome.

# 2. Always poll artifact presence, not just status
GET /a2a/tasks/{taskId}/artifacts
# If artifacts[] is empty after "completed" → state divergence

# 3. Three-state verification model
# State 1: Protocol state (A2A TaskStatus) — transport layer
# State 2: Delivery receipt (artifact present, schema-valid) — content layer
# State 3: Business outcome (output applied, downstream confirmed) — result layer

# 4. Trust only State 3 for business-critical workflows
# States 1 and 2 can diverge from reality in known failure modes:
#   - ADK LongRunningFunctionTool bug: status=completed, no artifact
#   - Timeout with partial result: status=working, artifact present but incomplete
#   - AgentCard spoofing: status=completed, wrong agent produced it

# 5. Schema-contract gating at the A2A boundary
# Define output schemas per role (planner vs specialist) and validate
# artifact shape before the orchestrator consumes it.
output_schema = {
  "required": ["accountId", "resultTimestamp", "confidence"],
  "constraints": {"accountId": "uuid_v4", "confidence": "float[0,1]"}
}
validate(artifact, output_schema)  # reject silently-wrong outputs
```

**AgentCard pinning over discovery.** Until issue #1672 (Agent Identity Verification) is resolved, manually pin AgentCards with SHA-256 hashes in your configuration. Dynamic discovery is a supply-chain risk — a compromised registry can serve a poisoned AgentCard that impersonates your billing agent.

**Dead-letter the Task, not just the agent.** When Task status is `failed` or `unknown`, the current agent should publish to a dead-letter queue (DLQ) with full Task history, not just retry locally. The downstream agent's failure may be a data problem that retrying locally amplifies.

**Propagate trace context across the A2A hop.** A2A preserves trace context across the network boundary (traceparent header in Task metadata), but S-1725 (attribution gap) documents that trace continuity breaks at the A2A→MCP boundary. Instrument both sides and correlate traces through the A2A `sessionId` as the join key.

**Timeout budgets per Task, not globally.** A2A tasks are long-running by design; a 30-second HTTP timeout on the client side doesn't mean the server agent times out — it means your client gives up waiting. Set per-Task deadline budgets and handle `working` status gracefully: partial results are better than silent failures.

## Receipt

> Verified 2026-07-27 — Google ADK GitHub #4145 confirms `LongRunningFunctionTool` + A2A Protocol produces tasks that never reach `completed` state despite successful function execution. GitHub issues #741 (Agent Registry) and #1672 (Agent Identity Verification) are open in the official A2A spec repository, confirming no built-in agent identity attestation. AppScale blog (Jul 22, 2026) reports 86% multi-agent pilot failure with silent boundary failures as the dominant mode. FutureAGI A2A guide confirms "silent delegation failure" as the primary 2026 production failure pattern. The three-state model (protocol state / delivery receipt / business outcome) is derived from analyzing the divergence between what A2A reports and what business systems confirm.

## See also

- [S-1722 · The Delegation Gap Stack](/stacks/s1722-the-delegation-gap-stack-when-your-a2a-agent-hands-off-a-task-and-its-credentials.md) — A2A credential delegation (what permissions travel with the Task)
- [S-1725 · The Attribution Gap Stack](/stacks/s1725-the-attribution-gap-stack-when-your-agent-fails-and-you-cant-tell-why.md) — trace attribution across agent boundaries
- [S-1724 · The Silent Delivery Stack](/stacks/s1724-the-silent-delivery-stack-when-your-agent-completes-but-nothing-reaches-the-user.md) — delivery confirmation vs completion confirmation
