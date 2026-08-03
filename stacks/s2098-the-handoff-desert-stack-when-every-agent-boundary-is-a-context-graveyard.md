# S-2098 · The Handoff Desert Stack — When Every Agent Boundary Is a Context Graveyard

You have a multi-agent system working beautifully on paper. The orchestrator routes correctly, each sub-agent produces sensible outputs, the final artifact looks plausible. Then you trace it back: Agent B received 30% of what Agent A knew. Agent C ran the same research query Agent A had already answered. Agent D never knew the task had already failed upstream. The context died at every boundary. This is not a prompt problem. This is a handoff problem — and it is the dominant failure mode of production multi-agent systems.

## Forces

- **Context does not survive boundaries.** Each agent's internal state — what it has tried, rejected, decided, and concluded — lives in its own context window. The handoff message carries only the surface output, not the execution history. The receiving agent has no idea what the previous agent already ruled out, which approaches failed, or what assumptions were made.
- **80% of multi-agent production failures trace to handoff points**, not to individual agent reasoning failures (AI Navigate, 2026). Systems can be architecturally sound and operationally broken — the coordination layer is the silent casualty.
- **Handoffs are lossy, unverifiable, and unrecoverable.** You cannot know if the receiving agent parsed the handoff correctly. You cannot replay it. You cannot confirm the transfer succeeded until the final output reveals the gap.
- **Naive handoff = redundant work.** Without a shared execution history, the receiving agent re-derives conclusions the sender already reached, burning tokens and time on work that was already done.
- **The 5-handoff cliff.** Research shows that after 3–5 sequential agent transfers, the original intent is typically unrecognizable in the final output — diluted through each lossy boundary (Agentmemo, 2026).

## The Move

### 1. The Agent Handoff Capsule (AHC)

The fundamental fix is treating a handoff as a first-class data structure, not a prose message. The **Agent Handoff Capsule** is a structured document that travels with the work across every boundary.

```json
{
  "capsule_id": "hc-7f3a9c",
  "origin_agent": "research-agent",
  "target_agent": "writer-agent",
  "task_summary": "Generate Q2 earnings brief for Acme Corp",
  "intent": "Produce a 500-word executive brief from raw earnings data",
  "execution_trace": [
    {
      "action": "fetch_10k",
      "status": "success",
      "output_hash": "sha256:a1b2c3...",
      "conclusion": "Revenue $47M (+12% YoY), EPS $2.31, raised FY guidance"
    },
    {
      "action": "fetch_call_transcript",
      "status": "success",
      "output_hash": "sha256:d4e5f6...",
      "conclusion": "CEO emphasized cloud migration; CFO flagged margin pressure in H2"
    },
    {
      "action": "fetch_comparables",
      "status": "failed",
      "reason": "Bloomberg API rate limit hit after 3 retries",
      "conclusion": "Abandoned — writer should use consensus estimates instead"
    }
  ],
  "rejected_approaches": [
    "Tried narrative format first; model hallucinated specific growth figures not in source. Switched to data-grounded format."
  ],
  "working_state": {
    "data_anchors": ["revenue", "EPS", "guidance"],
    "tone": "analyst-neutral",
    "audience": "C-suite, non-technical"
  },
  "handoff_acceptance_required": true,
  "retry_policy": {
    "max_retries": 2,
    "escalate_to": "orchestrator"
  }
}
```

### 2. The Handoff Acceptance Gate

Before the receiving agent proceeds, it must **accept** the capsule by validating its schema and confirming readiness. This creates a protocol-level acknowledgment:

```python
def accept_handoff(capsule: dict, receiving_agent_id: str) -> HandoffReceipt:
    required_fields = [
        "task_summary", "execution_trace",
        "intent", "handoff_acceptance_required"
    ]
    missing = [f for f in required_fields if f not in capsule]
    if missing:
        raise HandoffRejection(
            capsule_id=capsule["capsule_id"],
            reason=f"missing required fields: {missing}",
            rejecting_agent=receiving_agent_id
        )

    # Cross-check: did a prior agent already fail this task?
    for step in capsule["execution_trace"]:
        if step["status"] == "failed":
            log_warning(f"Prior agent failed: {step['action']} — {step['reason']}")

    return HandoffReceipt(
        capsule_id=capsule["capsule_id"],
        accepted_by=receiving_agent_id,
        accepted_at=datetime.utcnow().isoformat(),
        trace_length=len(capsule["execution_trace"]),
        integrity_hash=hash_capsule(capsule)
    )
```

### 3. The Execution Trace Only Pattern

Never hand off prose. Always hand off the **structured trace of what was done**. Prose summarization by the sending agent introduces re-hallucination risk — the sender accidentally re-interprets or infers conclusions the data doesn't support. The trace preserves the raw outputs; the receiver derives its own conclusions from them.

### 4. The 3-Hop Timeout

If a task has not reached its terminal agent within 3 handoffs, something is wrong with the decomposition. Set an orchestration-level timeout that triggers escalation:

```python
MAX_HOPS = 3

def route(agent: Agent, capsule: dict) -> None:
    capsule["hop_count"] = capsule.get("hop_count", 0) + 1
    if capsule["hop_count"] > MAX_HOPS:
        escalate_to_orchestrator(capsule,
            reason="max_hops_exceeded",
            current_depth=capsule["hop_count"]
        )
    next_agent = select_next_agent(agent, capsule)
    send_handoff(next_agent, capsule)
```

### 5. The Silent Failure Detector

Install a **completion-time baseline** per agent per task type. If a downstream agent completes suspiciously fast (e.g., the writer finishes in 8 seconds when the research phase took 40 minutes), it likely received corrupted or empty context and short-circuited:

```python
def detect_ghost_completion(agent_id: str, task_type: str, elapsed_seconds: float):
    baseline = get_baseline_duration(agent_id, task_type)
    if elapsed_seconds < baseline * 0.3:
        alert_oncall(
            f"Possible ghost completion: {agent_id} finished {task_type} "
            f"in {elapsed_seconds:.1f}s (baseline: {baseline:.1f}s). "
            f"Context may have been lost at handoff."
        )
```

## Receipt

> **Receipt pending — 2026-08-03** — Pattern drawn from AI Navigate (2026), Agentmemo Agent Handoff Protocol (2026), Atlan Multi-Agent Debugging Framework (2026), Zylos Research Multi-Agent Communication Protocols (2026), and the Agent Handoff Capsule (AHC) open specification. AHC has 340+ GitHub stars and active implementations in LangGraph and Google ADK as of Q2 2026. Production validation data from CallSphere (healthcare handoff latency, 2026) and SyncSoft AI (context transfer completeness benchmarks, 2026) confirm 3–5x reduction in inter-agent redundant work and 60% faster debugging via structured capsule traces.

## See also

- **[S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md)** — State disagreement at agent boundaries; this entry is the fix.
- **[S-1008 · The Orchestration Pattern Match Stack](s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md)** — Choosing the right coordination topology; handoff design follows from this.
- **[S-1088 · The Production Evaluation Stack](s1088-the-production-evaluation-stack-measuring-what-your-agent-actually-does-vs-what-it-says-it-did.md)** — Eval frameworks that catch handoff failures before production.
