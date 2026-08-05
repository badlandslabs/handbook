# S-2190 · The Hallucination Cascade Stack — When One Bad Output Becomes Your Entire System's Consensus

Agent A generates a report. Agent B edits it. Agent C translates it. Agent D sends it to the customer. The customer flag: the order ID doesn't exist.

Nobody fabricated that ID. Agent A hallucinated it from a training pattern. Agent B read the number, checked its spelling, and confirmed it was consistent with surrounding text. Agent C never questioned the digits. Agent D delivered it with confidence. Each agent was individually rational. The pipeline was collectively wrong. This is the hallucination cascade: errors that don't just persist through multi-agent chains — they transform, become more believable, and become undetectable at every handoff.

## Forces

- **Agents verify style, not facts.** A receiving agent in a sequential pipeline checks whether an input is well-formed, coherent, and consistent with the preceding text. It does not check whether the referenced entities actually exist. Hallucinated numbers pass this check more often than real ones, because real data often contains inconsistencies the model detects and flags.
- **State transformation degrades detectability.** Raw numerical facts → derived computations → narrative prose → invisible conclusions. Each transformation makes the error harder to catch. A fabricated number is interrogatable. A derived metric based on that number is not.
- **Each agent infuses social credibility.** The downstream agent treats the upstream agent's output as a cited source. A paragraph attributed to "the data team" carries more weight than a paragraph from a single LLM. Multi-agent pipelines create an invisible citation chain that compounds authority without adding evidence.
- **The 200-OK success criterion poisons the eval.** Every agent in the chain returns a 200 OK. The pipeline looks healthy. The cost and latency metrics are nominal. The only failure is semantic — and it's buried in a summary that nobody re-checks.

## The move

### 1. Measure cascade risk before the pipeline runs

Not all multi-agent pipelines have equal cascade risk. The key variable is **transformation depth** — how many times the output is reinterpreted rather than simply passed through.

| Depth | Risk Level | Example |
|-------|-----------|---------|
| 0 | Raw generation | Agent produces output, human reviews |
| 1 | Light editing | Editor agent checks grammar and tone |
| 2 | Structural transformation | Analytics agent computes metrics from raw data |
| 3+ | Narrative synthesis | Writer agent turns metrics into prose |

Depth 2+ pipelines require mandatory boundary gates regardless of per-step accuracy.

### 2. Install boundary verification gates

The intervention point is the agent-to-agent handoff, not the final output. At each boundary:

```
Before agent B processes agent A's output:
1. Extract factual claims (entities, IDs, dates, quantities)
2. Spot-check each claim against the authoritative source
3. If any claim fails verification → flag upstream output, halt pipeline
4. Attach provenance receipt to verified claims
```

In practice, this means adding a lightweight verification agent at each boundary:

```python
class CascadeGate:
    def __init__(self, tolerance: float = 0.0):
        # tolerance = fraction of unverified claims allowed (0.0 = strict)
        self.tolerance = tolerance

    def verify_handoff(self, upstream_output: str, pipeline_id: str) -> GateResult:
        claims = extract_factual_claims(upstream_output)
        results = []
        for claim in claims:
            verified = self._verify_against_source(claim)
            results.append({"claim": claim, "verified": verified})

        unverified = [r for r in results if not r["verified"]]
        if len(unverified) / len(results) > self.tolerance:
            return GateResult(
                status="BLOCK",
                upstream_output=upstream_output,
                failed_claims=unverified,
                gate=f"cascade-{pipeline_id}",
            )
        return GateResult(
            status="PASS",
            provenance_receipt=self._issue_receipt(results),
        )

    def _verify_against_source(self, claim: Claim) -> bool:
        if claim.type == "entity_id":
            # Verify entity exists in authoritative system
            return entity_exists(claim.value, claim.system)
        elif claim.type == "quantity":
            # Re-execute computation or verify against DB
            return verify_numeric(claim)
        elif claim.type == "date":
            return verify_temporal(claim)
        return True  # Can't verify — treat as unknown

# Integration with LangGraph pipeline
def build_pipeline():
    graph = StateGraph(PipelineState)
    graph.add_node("generator", agent_a)
    graph.add_node("cascade_gate", CascadeGate(tolerance=0.0).verify_handoff)
    graph.add_node("editor", agent_b)

    graph.add_edge("generator", "cascade_gate")
    graph.add_conditional_edges(
        "cascade_gate",
        lambda result: "BLOCK" if result.status == "BLOCK" else "editor",
    )
    graph.add_edge("editor", END)
    return graph.compile()
```

> Receipt pending — 2026-08-05

### 3. The provenance receipt pattern

When a gate passes, issue a machine-readable receipt:

```json
{
  "receipt_id": "prov-20260805-a3f9",
  "generator": "agent-a",
  "claims_verified": 12,
  "claims_failed": 0,
  "sources_checked": ["orders_db", "crm_api"],
  "upstream_hash": "sha256:abc123",
  "pipeline_stage": 1
}
```

Downstream agents receive this receipt alongside the content. If downstream behavior is suspicious, you can trace it to the specific upstream stage that failed to verify.

### 4. Govern by transformation depth, not accuracy

The goal is not to make each agent more accurate — it's to catch errors before they transform. A hallucinated number at stage 1 becomes invisible at stage 3. The fix is not better models; it's shallower transformation per stage and verification at every boundary.

```
High-risk pattern (common, dangerous):
  Generator → Editor → Writer → Sender
  (each step transforms, no verification until customer sees it)

Low-risk pattern (verified at every layer):
  Generator → [Gate: verify IDs exist] → Editor → [Gate: verify derived metrics]
    → Writer → [Gate: verify claims in prose] → Sender
```

## Tradeoffs

- **Latency cost.** Every gate adds a round-trip to verify against authoritative sources. For real-time pipelines this is a genuine tradeoff — balance against the cost of cascade failure.
- **Source dependency.** Gate verification requires authoritative systems to check against. If the authoritative source is also unreliable or slow, the gate becomes a bottleneck.
- **Over-gating.** Strict gates (tolerance=0.0) can halt pipelines on minor unverified claims. Start with tolerance=0.1 for non-critical pipelines, tighten as your verification infrastructure matures.

## Cascade risk triage

Ask these questions at pipeline design time:

1. Does any agent in this chain handle real-world entity IDs, quantities, or dates?
2. Does output transform between stages (raw → computed → prose → summary)?
3. Is there a human reviewing the final output before it affects the real world?
4. Would cascade failure be detectable before it causes harm?

If the answer to 1 and 2 is yes, and 3 is no — you need gates.

## Receipt

> Verified 2026-08-05 — Core pattern from arXiv:2606.07937 (Polytechnique Montréal, June 2026) "Hallucination Cascade: Analyzing Error Propagation in Multi-Agent LLM Systems" — 500 cascade experiments across 10 domains, 3 models (GPT-5.3, DeepSeek-V3, LLaMA-3-70B-Instruct). Key finding: per-boundary verification gates reduce hallucination score by 0.072 per stage. Formalization as first-order Markov process with per-boundary escape probabilities from ICML 2026 FAGEN "Hallucination Snowball" (Singh & Pawar). CSA MCP Tool Poisoning (July 2026) confirms the attack-surface parallel: server-supplied content treated as trusted creates the same cascade vulnerability. Code pattern follows LangGraph conditional edge + gate node architecture.

## See also

- [S-2188 · The Data Fragmentation Stack](s2188-the-data-fragmentation-stack-when-your-agent-decides-on-half-a-truth.md) — partial truth from missing systems vs. hallucinated truth from wrong generation
- [S-2189 · The Invisible Eval Stack](s2189-the-invisible-eval-stack-when-your-agent-always-passes-but-always-fails.md) — measuring the wrong things at the wrong level
- [S-2183 · The Agent Failure Recovery Stack](s2183-the-agent-failure-recovery-stack-when-your-agent-hangs-silently-and-bills-you-forever.md) — silent failures in multi-step pipelines
