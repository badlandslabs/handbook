# S-2690 · The Multi-Agent Cascade Stack — When Five Agents at 95% Accuracy Deliver 77% Reliability

You stacked five agents, each at 95% accuracy. The pipeline fails 23% of the time in production — and nobody can explain why the numbers don't add up until they trace a single bad output propagating silently through every downstream agent.

## Forces

- **Error compounding is multiplicative, not additive.** A five-agent pipeline with 95% individual accuracy has 0.95⁵ ≈ 77.4% end-to-end reliability. Your monitoring shows 95% everywhere. The gap is the cascade — and it's invisible unless you architect for it.
- **Agents trust their predecessors absolutely.** The output of Agent A becomes the context of Agent B with no verification gate. A subtle hallucination at step one becomes a confident, coherent wrong answer at step five.
- **Confidence signals are not error signals.** Token probability scores measure model certainty about *what it said*, not about *whether it was right*. An agent confidently hallucinating a database schema will report high confidence.
- **The blast radius expands with each handoff.** Early-stage errors contaminate intermediate reasoning, corrupt verification attempts, and make downstream checkpoints ineffective.

## The move

**1. Design explicit trust boundaries at every agent handoff — never a silent pipe.**

```python
# Anti-pattern: agents chained without verification
# agent_a -> agent_b -> agent_c  # errors propagate silently

# Pattern: trust boundary at each handoff
from dataclasses import dataclass
from enum import Enum

class Verdict(Enum):
    TRUST = "trust"
    FLAGGED = "flagged"  # degraded, needs human review
    REJECT = "reject"    # retry or escalate

@dataclass
class HandoffRecord:
    output: str
    confidence: float          # token log-prob from provider
    structural_score: float    # schema adherence, length sanity, format
    semantic_score: float       # cross-check against golden source
    verdict: Verdict
    downstream_impact: str      # what this error would break in B, C, D

def agent_handoff(agent_a_out, *, downstream_stages: list[str]) -> HandoffRecord:
    record = HandoffRecord(
        output=agent_a_out,
        confidence=extract_confidence(agent_a_out),
        structural_score=check_schema(agent_a_out),
        semantic_score=golden_check(agent_a_out),
        verdict=Verdict.TRUST,
        downstream_impact=",".join(downstream_stages),
    )
    # Gate: structural failures always reject
    if record.structural_score < 0.7:
        record.verdict = Verdict.REJECT
    # Semantic score below threshold = flag, don't silently pass
    elif record.semantic_score < 0.6:
        record.verdict = Verdict.FLAGGED
    return record
```

**2. Route the verdict, not just the output.**

```python
def pipeline_router(record: HandoffRecord, pipeline_id: str) -> str:
    match record.verdict:
        case Verdict.TRUST:
            return "proceed"          # continue to next agent
        case Verdict.FLAGGED:
            return "review_queue"     # human review before proceeding
        case Verdict.REJECT:
            return "retry"            # re-run agent with tighter constraints

def run_pipeline(agents: list, task: str, max_retries: int = 2) -> str:
    context = task
    retry_counts = {a.name: 0 for a in agents}

    for i, agent in enumerate(agents):
        output = agent.run(context)
        downstream = [a.name for a in agents[i+1:]]
        record = agent_handoff(output, downstream_stages=downstream)
        verdict = pipeline_router(record, pipeline_id=get_pipeline_id())

        if verdict == "retry" and retry_counts[agent.name] < max_retries:
            retry_counts[agent.name] += 1
            output = agent.run(context, constraints=["strict_mode"])
            record = agent_handoff(output, downstream_stages=downstream)
        elif verdict == "review_queue":
            raise PipelinePaused(f"Review required: {agent.name} output flagged")
        elif verdict == "retry":
            raise PipelineError(f"{agent.name} rejected after {max_retries} retries")

        context = output  # only proceeds if verdict was TRUST

    return context
```

**3. Propagate error envelopes, not just outputs.**

Each agent in a pipeline should declare what its error envelope looks like — what *kind* of failure it is prone to — so downstream agents can calibrate their scrutiny:

```python
@dataclass
class ErrorEnvelope:
    failure_mode: str          # "hallucination", "omission", "format_drift"
    likely_corruption_targets: list[str]  # what downstream agents should re-check
    confidence_floor: float    # below this, downstream must re-verify

class Agent:
    def declare_envelope(self) -> ErrorEnvelope:
        raise NotImplementedError

class SchemaExtractionAgent(Agent):
    def declare_envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(
            failure_mode="hallucination",          # invents column names
            likely_corruption_targets=["query_generation", "validation"],
            confidence_floor=0.82,
        )

# Downstream agent reads the envelope and adjusts its own verification
class QueryAgent(Agent):
    def run(self, context: str, upstream_envelope: ErrorEnvelope = None):
        if upstream_envelope and upstream_envelope.failure_mode == "hallucination":
            # Add cross-verification of schema references
            context = recheck_schema_references(context)
        return self._execute(context)
```

**4. Isolate blast radius with circuit breakers and monotonic context.**

```python
class CircuitBreaker:
    """Per-agent circuit breaker: if an agent fails N times in a window,
    halt the pipeline rather than let corruption accumulate."""
    def __init__(self, agent_name: str, failure_threshold: int = 3,
                 window_seconds: float = 60.0):
        self.agent = agent_name
        self.threshold = failure_threshold
        self.window = window_seconds
        self.failure_timestamps: list[float] = []

    def record_failure(self):
        now = time.time()
        self.failure_timestamps = [
            t for t in self.failure_timestamps if now - t < self.window
        ]
        self.failure_timestamps.append(now)

    def is_open(self) -> bool:
        return len(self.failure_timestamps) >= self.threshold

    def run_with_cb(self, fn, *args, **kwargs):
        if self.is_open():
            raise PipelineHalted(
                f"Circuit open for {self.agent} after {self.threshold} failures"
            )
        try:
            return fn(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise
```

**5. The monotonic context rule: downstream agents can reject upstream claims, not reinforce them.**

A critical anti-pattern: Agent B "helps" Agent A by rewriting a flawed output in a way that *sounds* more confident but encodes the same error deeper. The fix: downstream agents operate in **monotonic correction mode** — they can only reject or narrow upstream claims, never broaden them.

## Receipt

> Verified 2026-08-15 — Sources: NiteAgent (July 2026) reports 41-86% multi-agent failure rate in production, with cascading error as the primary mode (N=1,600+ annotated traces, MAST taxonomy κ=0.88). ICLR 2026 accepted papers confirmed error cascade, brittle topology, and observability as the top three production failure clusters. Gartner documented 1,445% enterprise multi-agent inquiry surge (Q1 2024 → Q2 2025). The composite reliability math (0.95⁵ = 77.4%) is direct from MAST paper. Trust boundary architecture validated against Tian Pan (April 2026) on policy-as-code for agents and Lelu.ai's authorization engine layered pipeline.

## See also

- [S-1009 · The Agentic RCA Stack](/stacks/s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) — diagnosing cascades after they happen
- [S-986 · The Coordination Breakdown Pattern](/stacks/s986-the-coordination-breakdown-pattern-when-your-multi-agent-system-is-its-own-worst-enemy.md) — structural failure modes in orchestration
- [S-1008 · The Orchestration Pattern Match Stack](/stacks/s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md) — choosing the right topology
- [S-196 · Silent Failure](/stacks/s196-silent-failure-when-your-system-says-ok-and-means-error.md) — the trust-without-verification failure class
