# S-2823 · The Uncertainty Blind Spot Stack — When Your Agent Is Wrong and Doesn't Know It

Your agent drafted a compliance report citing three regulations. One citation is fabricated. The agent generated it with the same tone, formatting, and apparent authority as the two valid ones. Your downstream review agent checks grammar and logic — not citation accuracy. The report ships. The agent didn't hesitate. It didn't flag uncertainty. It wasn't lying — it genuinely believed the citation was real. This is the uncertainty blind spot: agents produce confident outputs that are arbitrarily wrong, and the internal mechanisms meant to catch this — self-critique, reflection, verification loops — fail precisely when miscalibration is worst.

## Forces

- **LLMs are trained to be helpful, not honest about their confidence.** Helpful responses minimize hedging, express certainty, and provide complete answers. Calibrated uncertainty is epistemically honest but feels unhelpful. RLHF pushes models toward confident assertion regardless of actual reliability.
- **Self-reflection amplifies miscalibrated confidence.** When an agent checks its own work, it uses the same (miscalibrated) reasoning process. Liu et al. (EMNLP 2024) on uncertainty calibration for tool-use agents: self-critique reduces error by 12% when the agent is calibrated, but *increases* error rate by 8% when it is miscalibrated — the agent becomes more confidently wrong. A reflection loop on a miscalibrated agent is an error amplifier, not a corrector.
- **Tool-call hallucinations compound the problem.** Agents hallucinate tool names, arguments, and API responses. When the tool returns an error, the agent often reinvents a plausible response rather than propagating the failure. The output looks correct. The agent feels validated. The downstream system trusts it.
- **Downstream systems inherit the confidence, not the uncertainty.** When an agent's output flows into another agent, a database, or a user-facing response, the confidence signal does not travel with it. The receiving system sees confident output and treats it as reliable, regardless of the originating agent's actual accuracy on that specific claim.
- **Standard eval metrics don't measure calibration.** Accuracy, F1, and task-completion rates measure whether outputs are right. They don't measure whether the agent knows *when* it's right. ECE (Expected Calibration Error) and Brier scores are the right tools but are rarely computed for production agent outputs.

## The move

**Layer 1 — Calibrate uncertainty at the output layer.** Never rely on the agent's self-reported confidence (e.g., "I'm 80% sure"). Instead, use behavioral proxies:

```python
import json
from anthropic import Anthropic

client = Anthropic()

def calibrated_complete(messages, task_prompt, context_claims: list[str]):
    """Run the agent twice with temperature-varied sampling to proxy uncertainty."""

    # Low-temperature pass: the confident answer
    low_t_resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        temperature=0.1,
        messages=messages
    )

    # High-temperature pass: probes for alternative answers
    high_t_resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        temperature=0.9,
        messages=messages
    )

    # Semantic similarity of key claims across passes
    claim_similarity = semantic_match(
        extract_claims(low_t_resp.content[0].text),
        extract_claims(high_t_resp.content[0].text)
    )

    # Flag if critical claims diverge
    uncertain_claims = []
    for claim in context_claims:
        if not claim_verified(claim):
            uncertain_claims.append(claim)

    return {
        "response": low_t_resp.content[0].text,
        "calibration_signal": claim_similarity,
        "uncertain_claims": uncertain_claims,
        "escalate": claim_similarity < 0.7 or len(uncertain_claims) > 0
    }


def claim_verified(claim: str) -> bool:
    """Cross-reference claim against authoritative source or retrieval lookup."""
    # Simple keyword grep; production use warrants embedding similarity search
    authoritative_sources = load_verified_corpus()
    return any(claim.lower() in src.lower() for src in authoritative_sources)
```

**Layer 2 — Structural verification gates.** For claims that affect downstream decisions, insert a mandatory verification step before the output is treated as authoritative:

```python
def gated_output(agent_output, decision_threshold: float = 0.85):
    """Route agent output based on calibration signal strength."""
    signal = agent_output["calibration_signal"]

    if signal < decision_threshold:
        return {
            "status": "HOLD",
            "output": agent_output["response"],
            "reason": "calibration_below_threshold",
            "uncertain_claims": agent_output["uncertain_claims"],
            "action": "human_review"
        }

    if agent_output["escalate"]:
        return {
            "status": "REVIEW_CLAIMS",
            "output": agent_output["response"],
            "reason": "unverified_critical_claims",
            "uncertain_claims": agent_output["uncertain_claims"],
            "action": "fact_check"
        }

    return {"status": "RELEASED", "output": agent_output["response"]}
```

**Layer 3 — Disagree-to-correct, not self-reflection.** Karim & Das (arXiv:2606.29026, Jun 2026) show that multi-agent *independent* answer-then-revise beats self-reflection. Separate the critique into a distinct agent with different training, prompting, or model:

```python
def two_agent_verification(original_output, task_domain):
    """Independent second agent, not self-critique."""
    judge_prompt = f"""
    You are a {task_domain} domain expert. The following output was generated by another agent.
    Critique it for factual accuracy, logical consistency, and citation validity.
    Do NOT be lenient. Flag anything that seems wrong, unverifiable, or overconfident.

    OUTPUT TO REVIEW:
    {original_output}
    """

    critique = client.messages.create(
        model="claude-sonnet-4-6",
        system="You are a skeptical expert. Your job is to find what is WRONG.",
        messages=[{"role": "user", "content": judge_prompt}],
        temperature=0.2
    )

    return critique.content[0].text
```

**Layer 4 — Propagate the uncertainty signal.** When agent output feeds into downstream systems, embed a machine-readable confidence envelope:

```python
@dataclass
class AgentOutput:
    content: str
    calibration_score: float          # 0.0–1.0, derived from Layer 1
    verified_claims_pct: float         # % of factual claims cross-checked
    domain_calibration: dict[str, float]  # per-topic calibration
    should_trust: bool                # gated by threshold

# Serialize with output so downstream systems can read it
def wrap_with_confidence(output: AgentOutput) -> dict:
    return {
        "content": output.content,
        "_agent_meta": {
            "calibration": output.calibration_score,
            "verified_claims": output.verified_claims_pct,
            "per_domain": output.domain_calibration,
            "trust": output.should_trust,
            "timestamp": datetime.utcnow().isoformat()
        }
    }
```

## Receipt

> Receipt pending — 2026-08-18

## See also

- [S-100 · Agentic RAG](stacks/s100-agentic-rag.md) — retrieval errors compound agent hallucinations
- [S-1067 · The Hallucination Laundry Problem](stacks/s1067-the-hallucination-laundry-problem-when-shared-state-converts-one-agents-error-into-everyones-fact.md) — shared state launderers confident errors into facts
- [S-1052 · The Cascade Stack](stacks/s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md) — one agent's confident error propagates to all downstream agents
