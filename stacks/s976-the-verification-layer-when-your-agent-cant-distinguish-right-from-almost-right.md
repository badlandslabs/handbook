# S-976 · The Verification Layer: When Your Agent Can't Distinguish Right from Almost Right

An agent that generates is not the same as an agent that knows what it generated is correct. The gap between producing an answer and verifying that answer is the difference between a system that ships confidently wrong output and one that catches itself. In 2026, the industry is converging on a new architectural primitive: a dedicated verification layer, separate from generation, that scores, decomposes, and gates outputs before they reach the user.

## Situation

A code-generating agent produces a function that passes all tests — except the test you actually care about, the one involving a race condition that only manifests under concurrent load. The agent has no way to know. It generated, it didn't verify. A research-synthesis agent produces a summary that reads coherently, cites three papers that don't exist, and scores 4.8/5 on an LLM judge. The judge is wrong, but nothing in your pipeline caught it. An agent tasked with triaging support tickets confidently routes a billing dispute to the wrong queue — wrong enough to frustrate the customer, correct enough that no automatic alarm fires.

These failures share a structure: the agent produced output that *looks* correct but isn't. The generation was competent. The verification was absent.

## Forces

- **Generation and verification are separate capabilities.** A model that generates well does not automatically verify well. Strong code-generating models often produce strong verifiers, but this correlation is not guaranteed and breaks at the boundaries — especially on novel task types, edge cases, and adversarial inputs.
- **LLM judges collapse to coarse scores.** Standard LM judges output 1–5 integer ratings, producing high tie rates (27% on Terminal-Bench) and poor discrimination between near-identical solutions. A single score hides which part of the output is wrong.
- **Agents can't self-correct what they can't detect.** Self-correction (S-561) requires a signal that the output is wrong. Without a verification layer, the correction loop has no trigger. Agents re-generate the same mistake with different wording.
- **Process reward beats outcome reward.** Outcome-only evaluation (pass/fail) gives no gradient. A verifier that decomposes criteria — did it handle the edge case? is the error message accurate? does the plan respect the constraint? — enables targeted revision, not blind regeneration.
- **Verification is now a proven scaling axis.** Stanford/NVIDIA research (2026) demonstrates verification as a distinct dimension from generation: separate scaling, separate training, separate tooling. State-of-the-art results on Terminal-Bench v2 (86.5%), SWE-bench Verified (78.2%), and MedAgentBench (73.3%) come from the verification-scaling approach, not generation-scaling alone.

## The move

**Add a dedicated verification layer between generation and delivery.** The verifier is a separate model call (or specialized verifier model) that scores output against task criteria, decomposes the score into per-dimension signals, and gates downstream actions.

```
# Minimal verification layer pattern
def verify(output: str, task: str, criteria: list[str], threshold: float = 0.8) -> dict:
    """
    Verify output against structured criteria.
    Returns per-criterion scores and a composite gate decision.
    """
    verifier_prompt = f"""Task: {task}
Output to verify: {output}
Evaluate against each criterion. Return JSON with:
  - "scores": {{"<criterion>": <0-1 score>}}
  - "verdict": "pass" | "revise" | "fail"
  - "reasoning": brief per-criterion explanation

Criteria:
{chr(10).join(f"- {c}" for c in criteria)}"""

    response = llm.complete(verifier_prompt, schema="verify_output")
    scores = response["scores"]
    composite = sum(scores.values()) / len(scores)
    
    return {
        "verdict": "pass" if composite >= threshold else "revise",
        "scores": scores,
        "composite": composite,
        "failed_criteria": [k for k, v in scores.items() if v < threshold],
    }

# Agent loop with verification gate
for step in agent.plan():
    output = agent.execute(step)
    result = verify(
        output=output,
        task=step.description,
        criteria=["correctness", "safety", "format", "completeness"],
        threshold=0.85,
    )
    if result["verdict"] == "fail":
        raise MaxRetriesExceeded(f"Step {step.id} failed verification: {result['failed_criteria']}")
    elif result["verdict"] == "revise":
        output = agent.revise(step, feedback=result["scores"], failed=result["failed_criteria"])
```

**Key design decisions:**

1. **Verifier model can differ from generator.** Smaller/faster models verify well on structured tasks (code correctness, format compliance). Frontier models verify better on open-ended reasoning. Routing matters.
2. **Criteria decomposition over monolithic score.** Instead of one 1–5 number, decompose into dimensions that map to actionable revision. "Correctness: 0.4, Safety: 0.9, Format: 0.8" tells the agent exactly what to fix.
3. **Probabilistic scoring via logit distribution.** Stanford's approach uses the full distribution of scoring-token logits, not just the expected value. This captures evaluation uncertainty — a low-confidence 0.7 is different from a high-confidence 0.7, and downstream logic should treat them differently.
4. **Verification as RL reward signal.** The per-dimension scores feed into a RL training loop (GRPO, SAC) as dense rewards, improving the generator over time. This closes the loop from evaluation to improvement.
5. **Repeated evaluation for hard tasks.** Verification can be run N times and the scores aggregated, trading compute for confidence. For high-stakes outputs, verify-then-revise-then-verify again.

## Receipt

> Verified 2026-07-11 — Stanford/NVIDIA arXiv:2607.05391v1 (2026): Terminal-Bench v2 86.5% (SOTA), SWE-bench Verified 78.2% (SOTA), RoboRewardBench 87.4%, MedAgentBench 73.3% (SOTA). Zylos Research (2026-04): 60% of bugs auto-resolved with structured observability + AI diagnostics. Arthur.ai (2026): 94% of production teams have "some observability" but gaps between "some" and "full tool-call-level traces" remain significant. LLM-as-a-Verifier framework available as open-source extension for Claude Code and Codex (cited in arXiv paper).

## See also

- [S-561 · The Self-Correction Gap](stacks/s561-the-self-correction-gap-when-agents-cant-self-heal.md) — agents that can't detect their own failures; the verification layer is the missing trigger
- [S-817 · The Trajectory Eval Stack](stacks/s817-the-trajectory-eval-stack-testing-the-path-not-the-answer.md) — process vs. outcome evaluation; verification layers enable process-level scoring
- [S-370 · Agent Chaos Engineering](stacks/s370-agent-chaos-engineering-fault-injection-testing.md) — fault injection tests verify that verification layers catch injected failures
- [S-523 · The Thinking Budget](stacks/s523-the-thinking-budget-reasoning-model-routing-in-agent-loops.md) — routing decisions benefit from pre-verification scoring to allocate compute
