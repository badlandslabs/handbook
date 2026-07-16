# S-1067 · The Hallucination Laundry Problem: When Shared State Converts One Agent's Error Into Everyone's Fact

Your multi-agent research pipeline just published a report recommending a 42% infrastructure cost reduction. The number checks out — every agent agreed on it. The number never existed. One agent hallucinated "42%" during synthesis. It wrote the claim to the shared knowledge base. Every downstream agent read it, accepted it as authoritative, and reasoned from it. The pipeline produced a self-consistent, internally coherent, completely fabricated report. No agent raised an error. The shared state laundered a hallucination into a verified fact.

## Situation

You run a multi-agent research pipeline: three parallel agents scan different data sources, post findings to a shared blackboard, and a synthesizer agent reads the aggregated state to produce a final report. One agent, synthesizing from a low-quality source, generates a plausible-sounding but fabricated statistic — "42% lift." It posts this to the shared blackboard with a confidence score of 0.87. The downstream synthesizer reads the blackboard, treats the 42% as a sourced claim, and incorporates it into the final deliverable. The client receives a report citing a number that was never in any source. The pipeline logged success at every step.

## Forces

- **Shared state erases epistemic provenance.** In a message pool or blackboard architecture, every agent reads every entry. A hallucinated entry from one agent gets the same surface appearance as a well-sourced entry — structured fields, confidence scores, timestamps. Without reading the chain-of-citation, downstream agents cannot distinguish ground truth from confabulation.
- **Confidence scores create false equivalence.** Agents often write confidence scores alongside claims. A hallucination with 0.87 confidence looks identical in format to a well-sourced claim with 0.87 confidence. Formatting parity creates epistemic parity — the system makes no structural distinction.
- **The blackboard is a single point of trust.** In a multi-agent pipeline with a shared workspace, the blackboard becomes the ground truth by construction. Agents trust it because they must — there is no alternative. This architectural trust is not earned; it is assumed. When a write is wrong, the entire system believes it.
- **No agent re-derives when a citation is present.** Agents that would naturally re-verify a raw claim will not re-verify the same claim that appears in shared state with a citation attached. The citation acts as an authority signal even when it points to another agent's output.
- **Concurrent writes compound the problem.** Multiple agents writing to shared state simultaneously means each agent's read view may differ at any moment. One agent may have already written a false entry; another agent reads and acts on it before any consistency check runs. The failure is not a race condition — it is a belief divergence.

## The move

### 1. Attach provenance to every write, not just every claim

Every entry in shared state must carry metadata answering: who wrote this, when, under what prompt, and what source did they cite? If the source is another agent's output rather than an external data source, flag it as a *derived claim* with an explicit derivation chain.

```python
@dataclass
class ProvenancedEntry:
    entry_id: str
    author_agent: str          # which agent wrote this
    schema_version: str        # of the entry format
    claims: list[Claim]
    citations: list[dict]      # [{source: str, type: "external"|"agent", agent_id: str}]
    derivation_chain: list[str] # list of entry_ids this was derived from
    write_timestamp: datetime
    verification_status: Literal["unverified", "verified", "failed", "derived"]

class Claim:
    text: str
    confidence: float          # NOT used as a proxy for truth
    source_context: str         # actual excerpt or reasoning
```

### 2. Require an independent verification gate on derived claims

Any entry whose citations include another agent's output (type: "agent") must pass through a lightweight verification step before being treated as a source by downstream agents. The verifier is a separate, small model call — not the original agent — checking: does the cited source actually support this claim?

```python
async def verify_derived_claim(entry: ProvenancedEntry) -> VerificationResult:
    """Gate: any entry citing agent output must pass this before downstream use."""
    for citation in entry.citations:
        if citation["type"] == "agent":
            source_entry = await blackboard.get(citation["entry_id"])
            # Cross-check: does source_entry actually contain the claimed fact?
            verdict = await verifier.check(
                claim=entry.claims[0].text,
                source=source_entry.raw_content,
                mode="entailment"
            )
            if verdict.entailment_score < 0.7:
                await blackboard.flag(entry.entry_id, status="failed")
                raise VerificationFailed(
                    f"Claim '{entry.claims[0].text[:50]}' not supported by source"
                )
    return VerificationResult(passed=True)
```

### 3. Treat confidence scores as calibration signals, not truth signals

Confidence scores from agents are measures of self-reported certainty, not objective accuracy. Do not use them as acceptance thresholds. Instead, route entries with confidence below a threshold to a critique agent — not as rejections, but as "needs peer review" signals.

```python
CRITIQUE_THRESHOLD = 0.75

async def handle_write(entry: ProvenancedEntry):
    if entry.claims[0].confidence < CRITIQUE_THRESHOLD:
        await blackboard.post(
            tag="needs_review",
            entry=entry,
            assignee="critic-agent"
        )
    await verify_derived_claim(entry)  # runs regardless
```

### 4. Implement a semantic freshness window for derived entries

Derived entries (those citing agent output) should have an explicit staleness window. After the window expires, the entry must be re-derived or re-verified before being used as a source. This prevents a hallucinated entry from accumulating trust over time simply by being unchallenged.

```python
FRESHNESS_WINDOW = timedelta(hours=2)

async def read_with_freshness(entry_id: str) -> ProvenancedEntry | None:
    entry = await blackboard.get(entry_id)
    if entry is None:
        return None
    age = datetime.now() - entry.write_timestamp
    if entry.verification_status == "derived" and age > FRESHNESS_WINDOW:
        # Must re-derive or expire
        await blackboard.expire(entry_id)
        return None
    return entry
```

### 5. Detect concurrent-write divergence with CRDT semantics

When multiple agents write to overlapping state concurrently, use a CRDT-aware write model: Last-Write-Wins (LWW) for timestamps and counters, but **semantic merge** for structured claims. Competing claims about the same entity are held as a conflict set rather than silently resolved — a human or arbitrator agent reviews before convergence.

```python
from dtelepathy import GCounter, LWWRegister, ORSet

# For shared task state: last-write-wins
task_status = LWWRegister[str](default="pending")

# For shared claims: semantic conflict set — no silent merge
claim_set: ORSet[str] = ORSet()  # each agent adds claims; all remain visible

async def add_claim(agent_id: str, claim_text: str):
    claim_set.add(claim_text)
    # Conflict check: if another agent added a contradictory claim
    # both remain visible. Await human resolution or arbitrator agent.
    if len(claim_set) > 1:
        await escalate_for_review(claim_set.members)
```

### 6. The "derived from agent" flag as a first-class alert

In the UI or trace dashboard, mark every shared-state entry with a clear visual indicator if its citations include agent output. This makes the propagation trace auditable: reviewers can follow the chain from the original external source through every agent's transformation.

## Receipt

> Verified 2026-07-13 — Research: Zylos Research (arxiv:distributed-state, 2026-03-17) confirmed CRDT patterns for multi-agent state sync; GitHub: GayanSamuditha/2026ai-engineering-from-scratch documented the "42% hallucination laundering" scenario; Sentry blog (April 2026) confirmed multi-agent observability fails at distributed state boundaries. Code patterns from nutstrut/verified-task (SAR protocol), Yjs (CRDT), dtelepathy libraries. The provenance + verification gate approach (steps 1-2) is structurally novel vs. existing entries S-1013 (handoff typed schemas) and S-368 (span tracing).

## See also

- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — handoff schema typing at agent boundaries
- [S-368 · Agent Span Tracing](s368-agent-span-tracing-observable-agent-sessions.md) — trace correlation across delegation boundaries
- [S-378 · Entity Grounding](s378-entity-grounding-knowledge-graphs-as-verifiable-memory.md) — knowledge graphs as a provenance layer
- [S-746 · Agentic Memory Confabulation](s746-agentic-memory-confabulation-the-self-reinforcing-false-belief-problem.md) — self-generated false beliefs, the single-agent version of this problem
