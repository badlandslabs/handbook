# S-1388 · The A2A Context Fidelity Stack — When Your Agent Hands Off a Task and the Receiver Loses the Thread

Your researcher agent spent 12 minutes analyzing a codebase, building a mental model of the user's architecture, identifying the critical path, and deciding to flag three specific functions as risky. It hands the task to your writer agent via A2A. The writer agent receives: "Summarize the security analysis findings." It has no idea what the codebase is, what the researcher found, or why those three functions matter. The protocol delivered the message. The context didn't travel with it. This is the A2A context fidelity problem — the gap between what A2A's Task Card transports and what an agent actually needs to work with.

## Forces

- **A2A delivers task state, not reasoning state.** The protocol moves a Task object, a work product, and a status. The intermediate hypotheses, rejected paths, and implicit context that made the work product correct stay with the sender.
- **Context bloat is the path of least resistance.** The naive fix is "send more context." At 3 handoffs in a pipeline, each agent carrying forward the full conversation history burns tokens and drowns the receiver in noise — it gets too much, not too little.
- **Agent Cards solve discovery, not comprehension.** An agent can discover that a colleague agent has a `code-review` skill via the Skill Manifest. It cannot discover that this agent's code review style is aggressive about null-safety and indifferent to naming conventions.
- **The 57% multi-agent failure rate is partly a handoff problem.** Cross-team studies consistently find that coordination failures — not individual agent quality — drive most multi-agent pipeline breakdowns. A2A closes the protocol layer; the semantic layer is unsolved.
- **Streaming breaks synchronous context transfer.** A2A's push model delivers results incrementally. The receiver may start work before the full context is available, creating race conditions where early steps use wrong assumptions.

## The Move

The stack has five layers. Each addresses a different failure mode in A2A handoff fidelity.

### 1. Structured Task Payload (the `metadata` field, not just `artifacts`)

A2A Tasks accept a `metadata` field. Most teams leave it empty or copy the user's prompt verbatim. The right pattern: a structured handoff summary with typed fields the receiver can parse.

```json
{
  "taskId": "t-44921",
  "metadata": {
    "handoffReason": "code-analysis",
    "senderRole": "researcher",
    "intentSummary": "Flagged 3 functions with SQL injection risk",
    "confidenceLevel": "high",
    "keyArtifacts": ["fn:authenticate_user", "fn:query_builder", "route:/admin"],
    "rejectedPaths": ["considered static analysis, insufficient for dynamic SQL"],
    "nextAgentRole": "writer",
    "expectedOutputFormat": "markdown-report-for-security-team"
  }
}
```

The receiver's system prompt includes: *"Read the `metadata.handoffReason` and `intentSummary` fields before starting work. Treat `keyArtifacts` as authoritative. Treat `rejectedPaths` as off-limits for reconsideration."*

This is not prompt injection — it's structured metadata the protocol already supports. The field exists. Use it.

### 2. The Context Budget at the Handoff Boundary

Before sending, the sender applies context compaction to the handoff payload. Three tiers:

- **Full pass-through** — only for single-hop, high-stakes tasks where fidelity outweighs cost
- **Compressed summary** — sender summarizes its reasoning chain in 3–5 bullets before transmitting (apply this 80% of the time)
- **Reference-only** — sender writes findings to a shared artifact store and sends only a pointer; receiver fetches on demand

```python
def compact_handoff(agent_output: dict, budget_tokens: int = 2048) -> dict:
    summary = summarize_reasoning_chain(agent_output["steps"], max_tokens=budget_tokens // 4)
    key_decisions = extract_decisions(agent_output["steps"])
    artifacts = write_artifacts_to_store(agent_output["artifacts"])
    return {
        "summary": summary,
        "keyDecisions": key_decisions,
        "artifactRefs": artifacts,
        "originalStepsCount": len(agent_output["steps"])
    }
```

The budget is per-handoff, not per-pipeline. Each hop re-budgets independently.

### 3. Skill Manifest with Behavioral Annotations

The Agent Card's Skill Manifest lists capabilities. Add behavioral metadata that speaks to *how* the skill works, not just *that* it exists.

```json
{
  "name": "code-review",
  "description": "Security-focused code review",
  "behavioralNotes": {
    "focus": ["sql-injection", "auth-bypass", "input-validation"],
    "ignores": ["naming-conventions", "code-style"],
    "outputFormat": "structured-finding-list",
    "confidenceThreshold": 0.7
  }
}
```

Sender agents query the receiver's Agent Card *before* drafting the handoff payload. If the writer agent's `code-review` behavioral notes say it ignores naming conventions, the researcher agent doesn't waste tokens explaining the naming issue — it drops it from `keyArtifacts` and saves the space.

### 4. Typed Task Card Schema for Cross-Team Handoffs

When agents belong to different teams or ownership domains, the handoff must be machine-readable at the schema level — not just human-readable in a text field.

Define a domain-specific `TaskCard` schema for your organization:

```typescript
interface TaskCard {
  id: string;
  originatingSystem: string;
  owner: string;
  intent: string;          // what "done" means
  constraints: string[];   // non-negotiable boundaries
  inputs: { name: string; type: string; source: string }[];
  outputs: { name: string; type: string; destination: string }[];
  escalationPath: string;
  ttl: string;             // "this task is stale after 24h"
}
```

The sender fills the card. The receiver validates it against its own capabilities before accepting. A capability mismatch returns a `TaskRejected` with a reason — rather than silently accepting work the receiver can't do well.

### 5. Streaming-Aware State Propagation

A2A supports push delivery of partial results. When a sender streams findings incrementally, the receiver must handle partial context — not wait for completion, but update its mental model as results arrive.

```python
async def streaming_handoff_receiver(task_id: str, event_stream):
    accumulated_context = {}
    pending_dependencies = set()

    async for event in event_stream:
        if event.type == "artifact":
            accumulated_context[event.artifact_key] = event.data
            # Immediately incorporate into working context if dependency satisfied
            if event.artifact_key in pending_dependencies:
                update_agent_context(event.artifact_key, event.data)
                pending_dependencies.remove(event.artifact_key)

        elif event.type == "intent_update":
            # Sender changed direction — invalidate what we already processed
            if event.reason == "pivot":
                accumulated_context.clear()
                pending_dependencies = set(event.new_dependencies)

        elif event.type == "completion":
            # Final validation pass with full accumulated context
            validate_and_finalize(accumulated_context)
```

The critical rule: **never start consequential work on a partial artifact**. The sender signals `intent_update` type events so the receiver can distinguish "more data coming" from "I was wrong about what data mattered."

## Receipt

> Verified 2026-07-20 — Researched against A2A Protocol v1.0 spec (a2a-protocol.org), Jangwook's A2A+MCP hybrid architecture guide, Zylos Research protocol analysis, and A2A GitHub types.ts schema. The `metadata` field, Agent Card, and push event stream are all confirmed in the v1.0 spec. Context compaction tiers and typed Task Card schemas are architectural patterns applied to the protocol — not protocol features themselves. Verified no existing handbook entry covers this specific angle (checked S-1040 "Protocol Gap," S-1042 "Protocol Stack," S-1104 "Three-Layer Protocol Stack" — all cover MCP+A2A coexistence, not handoff fidelity).

## See also

- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement across agent boundaries
- [S-1040 · The Protocol Gap](s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — MCP vs A2A layer distinction
- [S-1023 · The Recovery Ladder](s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — when agents believe they succeeded but didn't
