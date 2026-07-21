# S-1398 · The Calibration Gap Stack — When Your Agent Says It's Sure but It's Not

A GPT-5.2-Codex agent given 100 SWE-Bench-Pro tasks predicts it will succeed on 73. It completes 35. That 38-point gap is not a model defect — it is a systemic property of how autonomous agents reason about their own capabilities. And in production pipelines where agents write to databases, send emails, and merge code, the calibration gap has a price tag measured in silent failures, cascading errors, and decisions nobody caught in time.

This is the calibration gap: the disconnect between what an agent believes it can do and what it actually accomplishes. Unlike human expert confidence (roughly well-calibrated over repeated tasks), LLM agents exhibit systematic miscalibration — expressing high confidence on wrong answers and moderate confidence on correct ones. The failure is invisible because agents don't hedge; they assert.

## Forces

- **Confidence compounds in multi-agent pipelines.** When Agent A passes output to Agent B, Agent B receives it as natural-language assertion. No metadata says "this has 35% actual accuracy." The downstream agent treats high-confidence wrong output identically to high-confidence correct output — and compounds the error.
- **Agents optimize for task completion, not honest signaling.** The training signal rewards finishing tasks, not admitting uncertainty. An agent that says "I don't know" gets scored lower on task completion than one that guesses confidently and happens to be right.
- **Miscalibration is invisible in single-agent runs and catastrophic in multi-agent ones.** You can manually review a single agent's outputs. You cannot manually review every hop in a pipeline of 5 agents each making 20 calls.
- **Eval pass-rates mask the gap.** An eval suite that measures task success will show 74% for the agent above. It will not tell you that the agent's own confidence annotations predicted 38% of those failures.

## The move

**Calibration gating**: add an explicit uncertainty layer between agent output and downstream action.

Three techniques, increasing in cost and reliability:

### 1. Structured Confidence Annotation

Prompt the agent to emit a structured confidence judgment alongside every non-trivial output. Require it, don't suggest it.

```python
@dataclass
class AgentOutput[T]:
    result: T
    confidence: float           # 0.0–1.0, explicit
    uncertainty_signal: str     # free text: what could go wrong
    abstain: bool               # true = do not trust this output
    confidence_basis: list[str] # which inputs/retrieved_chunks grounded this

def calibrate(output: AgentOutput, threshold: float = 0.7) -> bool:
    """Gate: only proceed if confidence exceeds threshold."""
    return output.confidence >= threshold and not output.abstain
```

**Key**: the `abstain` flag is the agent's escape hatch. Without it, agents always produce something — confidence approaches 1.0 for all outputs, even wrong ones.

### 2. Self-Verification Loop

Ask the agent to verify its own output before committing. Different prompt framing, same model.

```python
def self_verify(task: str, draft: str, n_checks: int = 3) -> tuple[bool, str]:
    """Multi-turn self-check: re-derive from scratch, compare to draft."""
    checks_passed = 0
    for _ in range(n_checks):
        rederive = agent.complete(
            f"Task: {task}\n"
            f"Given this draft answer: {draft}\n"
            f"Re-derive the answer independently. "
            f"Does your re-derivation match the draft? "
            f"Rate agreement 0–1 and explain any divergence."
        )
        if rederive.confidence >= 0.8 and rederive.agreeance_score >= 0.85:
            checks_passed += 1

    # Require majority vote for high-stakes outputs
    return checks_passed >= n_checks // 2 + 1, draft
```

**Calibration insight**: I-CALM (arXiv:2604.03904) shows that explicit reward schemes (+2 correct, −2 wrong, +0 abstention) shift agent behavior toward honest abstention in black-box settings. The abstain policy must be aligned with incentives, not just instructions.

### 3. Uncertainty Quantification via Sampling

For critical outputs, run multiple samples at temperature > 0 and measure agreement. Low agreement = high uncertainty.

```python
def ux_sample(prompt: str, n: int = 5) -> tuple[float, list[str]]:
    """Self-consistency scoring: run N samples, measure agreement."""
    samples = [agent.complete(prompt, temperature=0.7) for _ in range(n)]
    # Lexical similarity via containment score
    scores = []
    for i, a in enumerate(samples):
        for b in samples[i+1:]:
            scores.append(text_overlap(a.result, b.result))
    avg_agreement = mean(scores) if scores else 0.0
    # Low agreement → high uncertainty → abstain
    return avg_agreement, [s.result for s in samples]

def gate_on_uncertainty(prompt: str, threshold: float = 0.75) -> AgentOutput:
    agreement, samples = ux_sample(prompt)
    if agreement < threshold:
        return AgentOutput(
            result=samples[0].result,
            confidence=agreement,
            uncertainty_signal=f"Low agreement ({agreement:.2f}) across {len(samples)} samples",
            abstain=True,
            confidence_basis=["self-consistency sampling"]
        )
    # Return consensus result
    return AgentOutput(
        result=samples[0].result,
        confidence=agreement,
        uncertainty_signal="",
        abstain=False,
        confidence_basis=[f"{len(samples)}-way self-consistency"]
    )
```

### 4. Multi-Agent Confidence Relay

In a pipeline where Agent B receives from Agent A, Agent B must independently assess Agent A's output, not trust it.

```python
async def agent_b_trust_check(
    task: str,
    agent_a_output: str,
    context: list[str]
) -> AgentOutput:
    """Agent B independently verifies Agent A's output."""
    critique = await agent_b.complete(
        f"Task: {task}\n"
        f"Context: {context}\n"
        f"Agent A produced: {agent_a_output}\n"
        f"Critique: Is Agent A's output correct given the task and context? "
        f"Rate confidence 0–1. Identify any factual errors or reasoning gaps."
    )
    return critique

# Use: Agent B only acts on agent_a_output if its own confidence >= 0.8
# This breaks the compounding failure chain
```

**The compounding math**: With 95% per-step accuracy across 10 steps, task success is 0.95¹⁰ = 60%. With miscalibration, agents escalate far less often than they should — they believe they're more accurate than they are. The calibration gap makes the compounding worse: the system trusts high-confidence wrong outputs at every step.

## Receipt

> Verified 2026-07-20 — Research synthesis from: Zylos Research (2026-04-18) on LLM calibration and UQ in production agents; AgentMarketCap (2026-04-09) on the 38-point confidence gap in SWE-Bench-Pro; arXiv:2604.03904 (I-CALM, April 2026) on abstention via reward framing; ICML 2025 position paper on UQ for LLM agents requiring a dedicated agentic benchmark suite. Confidence-based gating (threshold=0.7) achieves precision ~0.95 with 70% display rate per arXiv:2510.13750. Self-consistency sampling (5 samples, threshold=0.75) as implemented above. The compounding failure math is from 2025 multi-agent system failure analysis.

## See also

- [S-998 · The Capability Ceiling](s998-the-capability-ceiling-stack-when-your-agent-ships-but-stalls-on-hard-tasks.md) — eval design failures that mask what agents can actually do
- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — why eval pass-rates don't predict production reliability
- [S-1065 · The Inter-Agent Trust Escalation Stack](s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — trust propagation across agent hops without verification
- [F-97 · Output Field Confidence Annotation](forward-deployed/f97-output-field-confidence-annotation.md) — per-field confidence scores on structured extraction outputs
