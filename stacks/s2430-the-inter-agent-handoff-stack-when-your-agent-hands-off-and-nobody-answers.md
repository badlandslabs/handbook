# S-2430 · The Inter-Agent Handoff Stack — When Your Agent Hands Off and Nobody Answers

Your researcher agent surfaces a JSON blob of relevant findings and POSTs it to the code-generator agent via A2A. The generator starts writing Python. The researcher spent 12 minutes on this. The generator has no idea what problem it's solving — it saw a blob of text and started typing. The result compiles. It's completely wrong. The handoff worked. The meaning didn't.

## Forces

- **Handoff integrity is not the same as delivery integrity.** HTTP 200 confirms the payload arrived. It says nothing about whether the receiving agent decoded the intent, recognized the task, or had the context to act on it. Most handoff failures are semantic, not transport.
- **Agents are not microservices.** A REST endpoint receiving JSON deserializes it into typed fields. An agent receiving text has to *reason* about what it means and what to do. That reasoning step can succeed (valid text) while the task fails (wrong task).
- **The handoff surface grows quadratically.** Two agents = one handoff. Six agents = fifteen pairwise handoffs. Each is a potential silence point. [S-1946 MAST](s1946-the-mast-framework-stack-when-your-multi-agent-system-fails-but-nobody-can-tell-you-why.md) identifies handoff failures as the primary failure mode in multi-agent pipelines, breaking 80% of production AI workflows.
- **Structured output helps at the tool layer but not the delegation layer.** [S-03 Tool Use](s03-tool-use.md) shows how JSON schemas anchor tool calls. But A2A task payloads carry arbitrary artifacts — code, summaries, structured records — that no schema validates before the agent reasons over them.
- **The receiving agent starts working before you know it received anything.** Async A2A tasks (States: `submitted` → `working` → `completed`) give you a status machine, but a `working` state with zero intermediate artifacts is indistinguishable from a hanging agent.
- **Context pollution cuts both ways.** [S-2095 Context Drift](s2095-the-context-drift-stack-when-your-multi-agent-system-hallucinates-things-that-never-happened.md) covers drift within an agent. Handoff context pollution is the cross-agent version: the sender's accumulated context contaminates the receiver's starting state.

## The move

### 1. Treat handoffs as contracts, not payloads

A handoff is not a data transfer — it is a **task agreement** between two agents. Before the sending agent fires the delegation, it must emit a structured handoff record that the receiving agent can confirm against.

```json
// Handoff contract (A2A task push)
{
  "task_type": "code_generation",
  "problem_statement": "Given a CSV with columns [user_id, session_start, session_end], compute per-user session duration percentiles",
  "input_artifact": {
    "type": "csv_schema",
    "columns": ["user_id", "session_start", "session_end"],
    "expected_rows": "100K–5M"
  },
  "acceptance_criteria": [
    "Output is a JSON map of user_id → {p50, p90, p99} duration in seconds",
    "Handle null session_end as active session (exclude from percentile)",
    "Runtime < 30s on 5M rows"
  ],
  "handoff_ref": "h-7f3a91c2",
  "requires_confirmation": true
}
```

The receiving agent must respond with a `handoff_acknowledged` message that echoes back the `problem_statement` and `acceptance_criteria` before starting work. If it doesn't, the sending agent treats this as a handoff rejection and escalates.

### 2. Enforce handoff confirmation before work begins

In A2A, a task moves to `working` the moment the receiving agent picks it up. Use the `input_required` state as a gate: the receiving agent must POST back a structured acknowledgment before transitioning to `working`. If no acknowledgment arrives within the timeout window, the sender re-queues.

For custom delegation (direct API calls), this is a two-phase commit:

```python
# Phase 1: Propose handoff
response = agent_b.post("/tasks", json={"action": "propose", "contract": handoff_contract})
assert response.status_code == 202
handoff_id = response.json()["handoff_id"]

# Phase 2: Await acknowledgment
ack = agent_b.get(f"/tasks/{handoff_id}/ack", timeout=30)
if ack.status_code != 200:
    # Retry, escalate, or self-handle
    escalate_to_sender(handoff_id)
else:
    # Phase 3: Confirm work can start
    agent_b.post(f"/tasks/{handoff_id}/start")
```

### 3. Instrument artifact lineage

Every artifact produced by the receiving agent carries a `lineage` block:

```python
handoff_lineage = {
    "handoff_ref": "h-7f3a91c2",
    "sender_agent": "researcher-v3",
    "receiver_agent": "coder-v2",
    "problem_statement_hash": "sha256:abc123...",  # stable hash of the contract
    "input_artifact_ref": "artifact://artifacts/session-a/ research-output.json",
    "receiving_model": "claude-sonnet-4-20250514",
    "handoff_timestamp": "2026-08-10T14:23:01Z"
}
```

If the output fails or the sender needs to retry with a different agent, the lineage block lets the new receiver understand what was already tried. Without this, retries restart from scratch.

### 4. Watch for the silent-acknowledgment pattern

The most dangerous handoff failure: the receiving agent accepts the task (`input_required` → `working`) but has no relevant context to act on it. It produces plausible-sounding output that satisfies the format but misses the problem.

Detect this with **artifact relevance scoring** — a lightweight LLM-as-judge call after the receiver completes:

```python
def score_handoff_relevance(handoff_contract, output_artifact):
    judge_prompt = f"""
    Task: {handoff_contract['problem_statement']}
    Acceptance criteria: {handoff_contract['acceptance_criteria']}
    Output: {output_artifact}

    Does the output directly address the problem statement and all acceptance criteria?
    Score 0-1. If < 0.7, flag for sender review.
    """
    score = llm.judge(prompt=judge_prompt)
    return score
```

This is not full evaluation — it's a fast sanity check. If the score is low, the sender re-handoffs with an explicit clarification, not just the original artifact.

### 5. Boundary handoffs at natural task seams

Not every agent interaction is a handoff. The distinction matters for where you enforce contracts:

| Pattern | Example | Contract needed? |
|---------|---------|-----------------|
| **Delegation** | Researcher → Coder | Yes — full handoff contract |
| **Consultation** | Orchestrator asks sub-agent for advice, keeps control | Partial — echo back the question |
| **Notification** | Agent A notifies Agent B of a completed task | No — fire-and-forget with delivery receipt |
| **Streaming** | Orchestrator streams context to a listening agent | Yes — acknowledgment per chunk after 70% context window |

[S-357 Long-Running Orchestration](s357-long-running-agent-orchestration-planner-worker-temporal-layers.md) covers the temporal patterns. Apply handoff contracts only at delegation seams, not every inter-agent message.

### 6. Handle the cascading timeout

When the receiving agent times out, the sender must not re-delegate to the same agent without a backoff. Track handoff attempt counts per receiver:

```python
handoff_tracker = {
    "h-7f3a91c2": {
        "receiver": "coder-v2",
        "attempts": 2,
        "last_failure": "timeout at 45s",
        "backoff_until": "2026-08-10T14:25:00Z"  # 2min exponential
    }
}

# Before re-delegating, check backoff
if datetime.utcnow() < handoff["backoff_until"]:
    # Try alternative receiver or surface to human
    route_to_alternative_receiver(handoff)
```

This directly addresses the MAST finding: Agent A timeout → Agent B blocked → cascade failure. The backoff tracker prevents re-hammering a failed receiver while providing an auditable reason for routing decisions.

## Receipt

> Verified 2026-08-10 — Research sourced from: Atlan "Multi-Agent Debugging: 7 Failure Modes" (Jul 24, 2026, citing MAST, Cemri et al. NeurIPS 2025); beam.ai "6 Multi-Agent Orchestration Patterns for Production" (Aug 10, 2026); Google Developers Blog "A2A one year in" (Jun 18, 2026); baeseokjae.github.io "MCP vs A2A Protocol 2026" (Apr 18, 2026); Zylos Research "Agent Interoperability Protocols 2026" (Mar 26, 2026). Handoff contract pattern is synthesized from A2A task state machine + two-phase commit semantics. Artifact relevance scoring pattern is a lightweight adaptation of the LLM-as-judge pattern from [S-451 LLM-as-Judge Failure Modes](s451-llm-as-judge-failure-modes.md).

## See also

- [S-1946 · The MAST Framework Stack](s1946-the-mast-framework-stack-when-your-multi-agent-system-fails-but-nobody-can-tell-you-why.md) — the underlying failure taxonomy (41-86.7% MAS failure rate, 14 named failure modes)
- [S-14 · A2A Protocol](s14-a2a-protocol.md) — the protocol layer this stack depends on (Agent Cards, task lifecycle)
- [S-918 · The A2A Trust Gap](s918-the-a2a-trust-gap.md) — what A2A does *not* cover (impersonation, card tampering, replay)
- [S-2095 · The Context Drift Stack](s2095-the-context-drift-stack-when-your-multi-agent-system-hallucinates-things-that-never-happened.md) — cross-agent context pollution (sibling problem)
- [S-357 · Long-Running Agent Orchestration](s357-long-running-agent-orchestration-planner-worker-temporal-layers.md) — temporal patterns for pause/resume on handoff boundaries
