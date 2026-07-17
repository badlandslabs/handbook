# S-1208 · The Cascading Corruption Stack — When One Wrong Fact Derails Your Entire Agent Run

Your agent completes a 25-step research task. The final report is polished, citations appear formatted correctly, and the reasoning chain is coherent. Except the agent hallucinated a company's founding year in step 3, and every subsequent inference — market timing analysis, competitive positioning, growth trajectory — built on that wrong date. The output is confidently, systematically wrong. No exception was raised. Nothing retried. This is **cascading context corruption**, and it is the most dangerous failure mode in long-running agents because it looks exactly like success.

## Forces

- **Agents fail semantically, not just mechanically.** Try-catch, retry logic, and circuit breakers handle mechanical failures — timeouts, rate limits, tool errors. They do not handle a model that reaches a wrong conclusion, treats it as ground truth, and builds a plausible structure on top of it. The system never sees an error.
- **Confidence is decoupled from correctness.** A model that hallucinates a founding year or misreads an API response produces output with the same confidence markers as accurate output. Without an explicit belief-state layer, you cannot distinguish the two at the point of failure — only at the point of damage.
- **Derived conclusions become invisible premises.** When step N uses the output of step N-1 as input, the agent is not retrieving a fact — it is inheriting a conclusion. If step N-1 was wrong, step N amplifies rather than corrects it. The error compounds silently.
- **Coherence is not correctness.** Long context windows produce outputs that read as well-reasoned precisely because the model weaves the wrong premise into a consistent narrative. The more steps, the more coherent the output — and the more confident the failure.
- **Traditional observability misses it entirely.** An agent that outputs a 5,000-word report with correct syntax and plausible structure has succeeded by every metric your infrastructure collects. You discover the failure when a human reads the output and catches the wrong date — days after the bill arrived and the downstream decision was made.

## The move

### 1. Epistemic Checkpoints — Assert Belief States, Not Just Outcomes

At each reasoning milestone, the agent writes an explicit belief-state assertion before proceeding:

```
BELIEF: [key conclusion]
SOURCE: [tool call / document / derivation]
CONFIDENCE: [high / medium / low]
ON: [step reference]

If CONFIDENCE = low: flag for verification before proceeding to next step.
```

This is not a prompt instruction — it is a structured checkpoint that your orchestration layer can read and act on. Low-confidence beliefs trigger a verification step (re-query the source, consult a second tool, surface to human) rather than proceeding silently.

### 2. Divergence Detection — Compare Beliefs Against Ground Truth

Periodically compare the agent's active beliefs against verifiable ground truth:

```python
def check_belief_divergence(beliefs: list[Belief], ground_truth: dict) -> list[Divergence]:
    divergences = []
    for b in beliefs:
        if b.key in ground_truth and b.value != ground_truth[b.key]:
            divergences.append(Divergence(belief=b, truth=ground_truth[b.key]))
    return divergences

# Alert if any divergences exceed the tolerance threshold
if divergences and any(d.severity > threshold for d in divergences):
    halt_and_surface(divergences)
```

For beliefs that cannot be cross-checked against ground truth (opinion, inference, future projection), flag them as **unverified** and attach a provenance trail so downstream consumers know the epistemic status.

### 3. Causal Tracing — Trace Wrong Outputs Back to Originating Corruption

When a final output is wrong, causal tracing walks the reasoning chain backward to find the originating error:

```
Output N (wrong conclusion)
  ← Step N-1 (used corrupted belief as input)
    ← Step N-2 (produced corrupted intermediate)
      ← Step N-3 (ingested wrong API response) ← ORIGIN
```

Build this trace automatically from your agent's execution log. The originating corruption is rarely at the step closest to the visible failure — it is usually 3-5 steps earlier, where the agent made an assumption that was never verified.

### 4. The Corrupt-Premise Gate — Stop Propagation, Not Just Detection

A divergence detector that only alerts is a post-mortem tool. The gate acts at runtime:

```python
def execute_with_corruption_gate(step: Step, active_beliefs: list[Belief]) -> StepResult:
    # Re-derive critical facts from authoritative sources before use
    for b in active_beliefs:
        if b.type == CRITICAL and b.confidence < HIGH:
            verified = authoritative_rederive(b.key)
            if verified.value != b.value:
                log(f"Corruption detected at belief {b.key}: {b.value} != {verified.value}")
                return HALT_AND_REASON(step, corrected_belief=verified)
    return step.execute()
```

**Critical facts** are premises that, if wrong, invalidate more than N downstream steps. Define the blast-radius threshold per domain: in financial analysis, any monetary figure is critical; in research synthesis, any cited fact is critical; in code generation, any API contract assumption is critical.

### 5. Provenance Trail — Every Belief Knows Its Source

Embed a lightweight provenance map in agent state:

```python
Belief(key="company_founding_year", value=1987, source="web_search:query=XYZ founding year",
       derived_from=["step_3_tool_result"], verified=False, divergence_score=0.0)
```

This makes causal tracing a log query, not a debugging session. When the output is wrong, you query the provenance trail for beliefs with `divergence_score > 0` or `verified = False` and get the chain in one pass.

### 6. Trust Calibration — Tell the Agent What It Doesn't Know

Instruct the agent to distinguish between retrieved facts and derived conclusions, and to surface uncertainty explicitly:

```
DISTINGUISH: facts ("The company was founded in 1987 per document X") from
             conclusions ("Based on founding date, the company predates the market").
             Label the latter as "derived, unverified" in your response.
```

This does not eliminate hallucination — it makes it visible. A report where the agent honestly marks 3 derived conclusions as unverified is more trustworthy than one where it confidently states all 25 steps as fact.

## Receipt

> Verified 2026-07-16 — Concept sourced from Tian Pan (tianpan.co, April 2026). Pattern independently corroborated by arXiv:2603.25764 ("Confident and Wrong: Silent Semantic Failures in Coding Agents," Snowflake AI Research, June 2026), which documents systematic submit-rate vs. resolve-rate divergence across 1,750 trajectories — the submit rate overstates success because it measures completion, not correctness. The approach combines belief-state checkpoints (novel structural pattern) with causal tracing and provenance trails adapted from the academic literature.

## See also

- [S-1008 · The Orchestration Pattern Match Stack](s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md) — Architecture determines which failure modes are reachable
- [S-1009 · The Agentic RCA Stack](s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) — RCA methodology for semantic failures
- [S-1016 · The Agent Failure Intervention Stack](s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — Green-lit failures that are wrong, not broken
- [S-1022 · The Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — Longitudinal corruption vs. acute corruption
