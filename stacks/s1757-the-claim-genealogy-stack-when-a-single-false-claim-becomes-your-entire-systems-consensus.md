# S-1757 · The Claim Genealogy Stack — When a Single False Claim Becomes Your Entire System's Consensus

Your four-agent coding team has been running for six hours. Architect approved the architecture. Developer implemented it. Reviewer validated it. QA wrote the tests. Everything looks correct — until the release build fails in production, and the post-mortem reveals the architect made a wrong claim at step one, and every subsequent agent independently "confirmed" it because they only checked consistency with the previous agent, not consistency with reality.

This is the **Claim Genealogy Problem**: in multi-agent pipelines, agents don't just pass outputs — they pass trust. A single false claim infects the entire system not because agents are bad, but because the message-passing layer is designed to propagate claims without verifying their ancestry. By round three, a wrong answer has been independently validated by every downstream agent, and the system has a strong, confident consensus around something that is entirely wrong.

## Forces

- **Transitive trust is the default.** When Agent B receives a message from Agent A, it treats A's output as context, not as a claim to be independently verified. By the time the claim reaches Agent D, it has been re-asserted three times by different agents — each re-assertion reads as corroboration even though none of them checked the original source.
- **Consensus inertia makes errors progressively harder to correct.** The longer a false claim lives in the system, the more agents have incorporated it into their own outputs. Rolling back the claim means rolling back three agents' worth of work. The cost of correction grows with each round, creating pressure to accept the false consensus rather than unwind it.
- **Every agent validates consistency, not correctness.** An agent checking whether a claim matches the preceding agent's output is validating consistency, not truth. If Agent A says "use SQLite" and Agent B implements it, Agent B's implementation is consistent with A's claim even if both are wrong.
- **The message-passing layer has no concept of claim provenance.** Standard multi-agent frameworks (AutoGen, CrewAI, LangChain, LangGraph, MetaGPT, Camel) pass messages without attaching cryptographic or logical provenance metadata. There is no lineage trail that lets Agent D know that its foundational assumption came from a single unverified source three hops back.
- **5 of 6 frameworks hit 100% error infection within 3 rounds.** In a controlled study across six frameworks, injecting a single false claim into a four-agent pipeline caused every downstream agent to adopt it within three message-passing rounds. The single exception only failed because its architecture accidentally created a verification checkpoint in the message path.

## The move

### 1. Attach a provenance header to every inter-agent claim

Every message that asserts a fact — a design decision, a tool selection, a code recommendation, an analysis result — gets a lightweight header:

```json
{
  "claim_id": "c-7a3f",
  "parent_claims": ["c-1b2c"],
  "assertion": "use SQLite for the caching layer",
  "agent": "architect",
  "verifiable": true,
  "verification_hint": "SQLite suitability for concurrent multi-process cache workloads"
}
```

The `parent_claims` field is the critical addition. It encodes the genealogy — not just "this message came from Agent B" but "this claim traces back to claim c-1b2c from Agent A." Downstream agents can now traverse the lineage.

### 2. Gate inter-agent handoffs on verification depth

At each handoff boundary, the receiving agent must do more than read the message — it must verify the root claim against an external source. The verification does not need to be expensive: a web search, a schema check, a reference lookup. It needs to be **independent** of the pipeline's own outputs.

```python
def handoff_gate(claim, max_depth=3):
    lineage = trace_ancestry(claim.claim_id)
    depth = len(lineage)
    
    if depth > max_depth and not claim.verified:
        # Flag for independent verification before proceeding
        return RouteToHumanReview(claim, lineage)
    
    if not claim.verifiable:
        return AcceptWithTag(claim, provenance="unverified_root")
```

The key parameter is `max_depth` — the number of propagation rounds before an unverified claim requires an explicit checkpoint. In practice, `max_depth=2` catches most cascades. `max_depth=1` is conservative and adds latency but eliminates transitive-trust risk entirely.

### 3. Implement the genealogy graph middleware

The middleware wraps the message-passing layer of whatever framework you're using. It intercepts outgoing claims, assigns `claim_id`s, attaches parent lineage, and stores the graph in a local audit store.

```python
# Geneaology middleware intercepts message-passing
class GeneaologyMiddleware:
    def __init__(self, store: ClaimStore, max_depth=2):
        self.store = store
        self.max_depth = max_depth
    
    def on_claim(self, agent_id, assertion, parent_ids):
        claim = Claim(
            id=generate_id(),
            agent=agent_id,
            assertion=assertion,
            parent_ids=parent_ids,
            depth=1 + max(p.depth for p in self.store.get(parent_ids)) if parent_ids else 0
        )
        self.store.add(claim)
        
        if claim.depth >= self.max_depth and not claim.verified:
            trigger_verification(claim)  # external check
        
        return claim
    
    def verify_claim(self, claim_id):
        """Stub: replace with real verification (web search, DB lookup, etc.)"""
        claim = self.store.get(claim_id)
        # External verification logic here
        verified = external_verify(claim.assertion)
        self.store.update(claim_id, verified=verified, verifier="external")
        return verified
```

This raises the defense rate from 32% to 89% without changing the underlying agent architecture.

### 4. Design verification checkpoints at fan-out boundaries

In fan-out pipelines — where one orchestrator dispatches to N specialist agents — the fan-out point is the highest-value verification checkpoint. Before distributing work, the orchestrator should verify that the root task description is accurate and complete. Any error at this point multiplies by N downstream.

```
Orchestrator
  └── verify(task_description)  ← checkpoint
  ├── Agent A (subtask_1)
  ├── Agent B (subtask_2)
  └── Agent C (subtask_3)
```

If the task description itself contains a false premise (misread user intent, corrupted RAG retrieval, hallucinated requirement), catching it before fan-out prevents N independent validations of a wrong premise.

### 5. Add a "consensus alarm" for convergent drift

Monitor for consensus inertia: when all agents in a pipeline begin producing outputs that are mutually consistent but reference the same root claim, that's a warning signal. Mutual consistency is expected in a correct pipeline — but if it derives from a single unverified root, it's a false consensus trap.

```python
def consensus_drift_score(claims):
    root_claims = {c.root_id for c in claims}
    if len(root_claims) == 1:
        # All outputs trace to single root — check if root is verified
        root = claims[0].get_root()
        if not root.verified:
            return CONSENSUS_DRIFT_ALARM
    return OK
```

## Receipt

> Verified 2026-07-28 — Research: "From Spark to Fire" (Xie et al., arXiv:2603.04474, March 2026) tested six frameworks (AutoGen, CrewAI, LangChain, LangGraph, MetaGPT, Camel) with a four-agent pipeline and a single injected false claim. 5 of 6 hit 100% adoption within 3 rounds. The exception (LangGraph variant) only worked because its rigid state-machine topology accidentally created a verification gate at step 2. The genealogy graph middleware raised detection rate from 32% to 89%. Context: Antler Digital (May 2026) quantifies the 17x trap — a 5% single-agent error rate becomes a 52% system failure rate in a 10-agent shared-state pipeline. The CSA research note on the Hugging Face breach (July 16, 2026) independently confirms the pattern: a false premise in an agent's input caused it to propagate incorrect trust chains across infrastructure components. Coverage gap: S-1750 (Conflict Resolution) addresses parallel agents disagreeing; S-1009 (Agentic RCA) addresses diagnosing failures after they propagate. Neither addresses the root cause — that the propagation itself is unconstrained and the claim lineage is invisible.

## See also

- [S-1750 · The Conflict Resolution Stack](s1750-the-conflict-resolution-stack-when-your-parallel-agents-disagree-on-the-answer.md) — parallel agents disagreeing, downstream of this pattern
- [S-1009 · The Agentic RCA Stack](s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) — diagnosing cascade failures after they propagate
- [S-1005 · The AI SRE Stack](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — Type III cascade as a reliability failure category
