# S-2790 · The Context Drift Stack — When Your Multi-Agent System Hallucinates but No Model Is Broken

Your two-agent pipeline was individually validated. Agent A is accurate at 94%. Agent B is accurate at 92%. Together they should be at least as good. They aren't — joint accuracy drops to 71%, and neither agent can explain the errors. The models are fine. The prompts are fine. The failure is in the interface between them.

This is **context drift**: the divergence of internal knowledge states between concurrently operating agents. When agents enter collaborative tasks with mismatched or stale representations of shared world state, their joint reasoning produces contradictions that manifest as hallucination — regardless of how capable each agent is individually.

## Forces

- **The collaboration penalty** — more agents should mean more capability, but multi-agent pipelines routinely underperform single-agent baselines because each agent reasons from a different reality
- **Asynchronous information updates** — Agent A updates a shared fact; Agent B has already committed to the old value in its working context
- **The contamination paradox** — the naive fix (full broadcast synchronization) is *worse* than doing nothing: indiscriminately sharing context increased hallucination rates by 34% over no-sync in the travel planning domain
- **You can't detect what you can't measure** — context drift is invisible in standard eval; agents report high individual confidence while producing wrong joint outputs
- **The failure is in the interface, not the model** — upgrading to a better model does not close the gap; you need a coordination primitive

## The move

### 1. Measure context divergence with CDS

The **Context Divergence Score** (CDS) is a lightweight scalar that quantifies knowledge-state discrepancy between agent pairs across three dimensions:

| Dimension | What it captures | Example drift |
|---|---|---|
| **Spatial** | Different beliefs about the same environment | Conflicting location data, file state |
| **Temporal** | Information from different timestamps | One agent read the DB before the other's write committed |
| **Task** | Inconsistent task histories or goals | Agent A thinks the task is "refund"; Agent B thinks it's "exchange" |

CDS is computed by prompting a judge model: *"Given Agent A's state summary and Agent B's state summary, rate divergence from 0 (identical) to 1 (completely contradictory) on [spatial/temporal/task] dimension."* This is cheap — one extra API call per synchronization cycle.

### 2. Use selective synchronization, not full broadcast

The **Shared State Verification Protocol (SSVP)** is the counter-intuitive fix: agents exchange compressed state summaries, compute CDS, and *only* synchronize when divergence is above a threshold. Full broadcast is harmful because it propagates the agent's local errors into the shared context — the contamination effect.

The SSVP decision loop:

```
for each agent_pair in pipeline:
    summary_a = compress(agent_a.working_context)
    summary_b = compress(agent_b.working_context)
    cds = judge.divergence_score(summary_a, summary_b)

    if cds > SYNC_THRESHOLD:
        reconcile(agent_a, agent_b, cds)
        log(f"SYNC triggered: CDS={cds:.2f}")
    else:
        proceed_without_sync()
        log(f"No sync needed: CDS={cds:.2f}")
```

In the travel planning domain, SSVP reduced hallucination rate to 0.463 (−5.9% vs. no-sync, *d* = 0.30) using **58% fewer API calls** than full broadcast. Full broadcast achieved HR = 0.704 — worse than no-sync at all. In the software domain, all conditions converge to low HR (<0.2), confirming contamination is domain-specific: it hits hardest in tasks where a single erroneous shared belief cascades across multiple evaluation dimensions.

### 3. Detect drift before it cascades

Context drift follows a three-stage propagation pattern:

1. **Seed divergence** — one agent holds a stale or incorrect fact (e.g., wrong flight time)
2. **Reasoning contamination** — a second agent builds on the wrong fact and reaches a plausible-but-wrong conclusion
3. **Output hallucination** — the final output is confident, fluent, and wrong, with no error signal

The intervention window is between stages 1 and 2. Check CDS at every handoff boundary, not just at the pipeline exit. A `handoff_gate` that blocks the next agent until CDS is below threshold catches most cascades.

### 4. Design handoff contracts

A handoff contract specifies what must be in every inter-agent message: verified facts, source timestamps, and the CDS at time of handoff. If the receiving agent's CDS spikes above threshold upon receipt, it must flag — not silently proceed with stale data.

```
class HandoffMessage:
    payload: dict
    source_agent: str
    timestamp: datetime
    facts_verified: list[str]      # claims confirmed against ground truth
    cds_at_send: float             # divergence score at handoff time
    knowledge_cutoff: datetime      # "I last checked state at X"
```

### 5. Set cascade-aware timeouts

In single-agent systems, a timeout means the task failed. In multi-agent systems, a timeout often means an agent is waiting for another agent that has drifted off-task. Set per-agent timeouts that account for expected CDS growth — if an agent hasn't reported in N seconds *and* CDS is trending up, escalate rather than retry.

## Receipt

> Verified 2026-08-17 — arXiv:2606.21666v1 (Rodrigues, Celabe, June 2026) provides the primary empirical results: SSVP vs. no-sync (HR 0.463, d=0.30) and SSVP vs. full broadcast (p=0.0005, d=1.47) in travel planning domain, n=30 per condition, Claude Haiku. Cascade radius data from arXiv:2608.05263v1 (OrchestraBench, Chen et al., Anote, August 2026): 0.9→4.7 across depths 3–7. CDS threshold of 0.3–0.5 reported as practical operating range per protocol description.

## See also

- [S-2788 · The Silent Handoff Stack](s2788-the-silent-handoff-stack-when-your-a2a-protocol-succeeds-but-nothing-happens.md) — protocol-level handoff failure (complementary: this entry covers knowledge-state handoff failure, S-2788 covers task-state handoff failure)
- [S-1023 · The Recovery Ladder](s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — step-level vs. system-level recovery; CDS-based gates fit the "detect before propagate" tier
- [S-1001 · The Runtime Enforcement Gap](s1001-the-runtime-enforcement-gap-when-your-verification-scores-are-green-but-your-agent-just-gave-away-1-2m.md) — measurement vs. enforcement; CDS is a pre-handoff enforcement instrument
