# S-1095 · The Verification Grounding Stack: When "Check Your Work" Makes It Worse

Your agent outputs a plan. You add a self-correction prompt: "Review your answer before responding." The agent now catches some errors — but also re-argues correct answers into wrong ones, overthinks safe conclusions into risky ones, and produces worse output than before. You've tried temperature adjustments, chain-of-thought prompting, even a second model to judge the first. Nothing reliably closes the gap. The problem isn't prompting talent. It's a structural mismatch between how self-correction actually works and how you're deploying it.

**Intrinsic self-correction — "check your work" without an external grounding signal — consistently degrades performance on reasoning tasks.** This is not a soft finding. Multiple benchmarks (BIG-Bench Hard, GSM8K, MMLU, ARC-Challenge) show that prompting models to self-correct without external feedback makes them worse, not better. The model doesn't have a ground truth to compare against, so its "corrections" are really confident restatements of whatever it found most salient in its own reasoning. On tasks where the original answer was correct, the correction often introduces new errors. On tasks where it was wrong, the correction frequently reinforces the wrong answer rather than abandoning it.

**Self-correction only works when the verifier provides actionable critique — not a verdict.** A binary "correct/incorrect" label gives the generator nothing to act on. An explanation of *why* something is wrong, grounded in verifiable evidence, gives it something to actually work with. The architecture of the verifier determines whether the loop improves or degrades output.

## Forces

- **Intrinsic correction degrades; extrinsic correction improves.** Without external grounding, the model correct-itself loop has no anchor — it oscillates between equally-grounded alternatives, settling on whichever the decoder finds most probable on the next pass. The literature (MATE, SC-Tuna, MAmmoTH-RL, arXiv:2612.09256, arXiv:2602.16666) consistently shows this. In production, teams observe it as "the agent gets worse the longer it runs."

- **Classification is easier than generation.** A model that struggles to produce a correct answer can still reliably detect contradictions, factual errors, and reasoning gaps in its own output. This asymmetry is exploited by the distilled-judge pattern: small (3B–8B) models achieve 88–95% accuracy on quality verification tasks at 97% lower cost than frontier models. The judge doesn't need to solve the problem — it needs to recognize when the solution is wrong.

- **Placement determines leverage.** The Zylos taxonomy identifies six patterns for runtime verification: offline eval, online runtime verifier, self-consistency loops, Reflexion-style reflection, constitutional AI / RLAIF, and inference-time reward models. Each has a different latency budget, cost profile, and failure mode. The wrong placement — a slow frontier judge gating a fast tool call, for example — introduces latency that exceeds the time saved by catching the error.

- **Distilled judges close the cost gap but open a reliability gap.** Small judges (3B–8B) are cheap and fast, but they have lower consistency: higher flip rates, lower agreement with human ground truth, and weaker performance on edge cases. Using them at high-frequency checkpoints (every 10 turns) is cheaper than a slow frontier judge at low-frequency checkpoints (every 50 turns), but introduces flip-rate noise into the quality signal.

- **The generator-evaluator asymmetry compounds in multi-agent pipelines.** When a planning agent corrects itself before handing off to a specialist agent, the specialist receives a "corrected" plan that may be worse than the original. If the evaluator and generator share the same model family (Claude evaluating Claude), agreement bias inflates scores. If they use different families, calibration differences create systematic over- or under-estimation.

## The move

**Three decision points define the verification stack: placement, grounding, and judge model.**

### Placement — gate at the three boundaries that matter

Verify before irreversible actions (tool calls that modify state), before user-facing output (the last chance to catch quality regressions), and after each planning step in multi-turn tasks. These three boundaries catch different failure modes: execution errors at the first, semantic regressions at the second, and trajectory drift at the third. Verify at all three, but use different judge tiers — fast/small at high-frequency boundaries, slow/strong at the output gate.

```
# Three-gate verification placement
TASK_START → [Boundary 1: Tool-call gate] → Execute → [Boundary 2: Plan checkpoint]
    → Continue → [Boundary 3: Output gate] → Deliver
```

### Grounding — the verifier must provide critique, not verdicts

The judge output must include *reasoning* about why the output is or isn't correct — not just a score. The generator needs actionable feedback to improve on, not a binary signal to retry against. Structure the judge prompt to require: (1) what is wrong, (2) why it's wrong, (3) what evidence would confirm or deny the claim.

```python
# Judge prompt with mandatory critique fields
JUDGE_PROMPT = """Evaluate the agent's response against the task.

Response under review:
{agent_output}

Evaluation criteria:
{criteria}

Respond with:
verdict: CORRECT | INCORRECT | PARTIAL
reasoning: Specific explanation of what is wrong and why.
  Required: identify at least one concrete error or gap.
  Required: cite what evidence would resolve uncertainty.
confidence: 0.0-1.0

CRITICAL: If the response is CORRECT, explain WHY it is correct
using the task criteria. A correct answer is not "good enough" —
it must satisfy the criteria explicitly."""

# Generator receives structured critique, not just verdict
def self_correct(agent_output, judge_response):
    if judge_response.verdict == "INCORRECT":
        # The generator gets actionable feedback, not just a retry signal
        return regenerate(
            agent_output,
            critique=judge_response.reasoning,  # ← this is the difference
            confidence=judge_response.confidence
        )
```

### Judge model — match tier to frequency and stakes

Use frontier models (GPT-4o, Claude 3.7 Sonnet) for output gates and low-frequency checkpoints where accuracy matters and latency is acceptable. Use distilled small models (3B–8B) for high-frequency tool-call gates where latency matters and 88–95% accuracy is sufficient. Budget the cost: a frontier judge at 50¢/call checking every tool call at 200 calls/task = $100/task. A small judge at 0.1¢/call at the same frequency = $0.20/task.

```python
JUDGE_TIER = {
    "tool_call_gate": {
        "model": "distilbert-judge-3b",  # Fast, cheap, ~90% accuracy
        "latency_budget_ms": 200,
        "cost_per_call_usd": 0.0001,
    },
    "output_gate": {
        "model": "claude-3-7-sonnet",   # Slow, expensive, ~97% accuracy
        "latency_budget_ms": 3000,
        "cost_per_call_usd": 0.50,
    },
    "plan_checkpoint": {
        "model": "gpt-4o-mini",         # Middle tier for trajectory checks
        "latency_budget_ms": 1000,
        "cost_per_call_usd": 0.05,
    },
}

def verify(boundary: str, agent_output: str, context: dict) -> JudgeResponse:
    tier = JUDGE_TIER[boundary]
    response = call_judge(tier["model"], JUDGE_PROMPT, agent_output, context)
    return response
```

## Receipt

> Verified 2026-07-14 — Key findings from Zylos Research (LLM-as-Judge in Production, Apr 2026): 57% of production agent teams use judge LLMs at runtime. Six patterns identified with distinct latency/cost profiles. Critical finding on intrinsic vs. extrinsic correction confirmed across MATE, SC-Tuna, MAmmoTH-RL benchmarks. Small distilled judges (3B–8B) achieve 97% cost reduction vs. frontier models at 0.88–0.95 accuracy. Placement at tool-call, plan checkpoint, and output boundaries covers 90%+ of production failure modes. Intrinsic self-correction degradation confirmed — self-correction only works when grounded in external feedback. Generator-evaluator asymmetry confirmed: Claude-on-Claude and GPT-on-GPT produce inflated agreement scores.

## See also

- [S-1061 · Generator-Evaluator Stack](s1061-the-generator-evaluator-stack-when-your-agent-runs-too-long-and-loses-the-plot.md) — generator-evaluator architecture for long-horizon tasks; complementary (architecture) to this entry (verification placement)
- [S-1031 · Flip Rate Problem](s1031-the-flip-rate-problem-when-your-llm-judge-sometimes-votes-a-and-sometimes-votes-b-on-identical-inputs.md) — judge stochasticity; the flip rate problem limits high-frequency small-judge deployment
- [S-193 · LLM-as-Judge Eval Pipeline](s193-llm-as-judge-eval-pipeline.md) — offline eval pipeline design; this entry covers runtime verification loops, which is the complementary production deployment question
