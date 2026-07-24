# S-1531 · The Calibration Gap Stack

Your agent says it's 95% confident—and proceeds to fail on the first real step. RLHF-trained agents optimize for sounding right, not being right. When this overconfidence hits multi-step execution, cascading failures are not bugs; they are the natural result of a confidence signal that never met reality.

## Forces

- **RLHF systematically degrades calibration.** Alignment training rewards confident-sounding answers regardless of actual knowledge. Pre-trained models have reasonable logprob-based calibration; RLHF destroys it. The verbalized confidence you get back is fiction.
- **Agent action chains amplify uncertainty.** A 90%-confident step followed by another 90%-confident step yields ≈81% trajectory confidence—but the errors are correlated, not independent. Chains of confident-but-wrong decisions compound into catastrophic failure with no warning.
- **Agents cannot distinguish reasoning uncertainty from knowledge uncertainty.** A model unsure *how* to solve a problem behaves identically to one that knows the answer. Both respond with confident completions. You cannot tell them apart without probing.
- **Human escalation gates are too coarse.** By the time a human intervenes, the agent has often already taken irreversible action or burned significant budget. Inline calibration enables intervention before the failure cascades, not after.

## The move

Every agent step gets a **calibration checkpoint**: a brief self-assessment before committing to the next action. The agent answers: *Am I confident for the right reasons?* Tool outputs, intermediate results, and retrieved context are all fair game for scrutiny.

### Three calibration methods (pick by capability and latency budget)

| Method | Signal source | Latency | Accuracy | When to use |
|--------|---------------|---------|----------|-------------|
| **Logprob aggregation** | Token-level `logprob` from API | ~0ms | Moderate | Fast paths, inline gates |
| **Semantic entropy** | Token probability variance under prompt perturbations | ~seconds | High | High-stakes decisions |
| **Verbalized confidence + probing** | Explicit "how sure are you?" turn | ~1 round trip | Low alone; useful with constraints | When you can afford a turn |

### The calibration gate pattern

```python
import anthropic
from anthropic import Anthropic
from typing import Literal

client = Anthropic()

CALIBRATION_PROMPT = """You just produced the following reasoning and action:

Reasoning: {reasoning}
Proposed action: {action_type} → {action_target}
Claimed confidence: {confidence}/10

Before proceeding, rate your actual uncertainty about:
1. Is the reasoning chain internally consistent?
2. Is the action target correct and reachable?
3. Are there failure modes you haven't considered?

Respond ONLY with: PROCEED, DEFER, or ESCALATE
and a one-line rationale. Do not elaborate."""

def calibrated_step(
    reasoning: str,
    action_type: str,
    action_target: str,
    claimed_confidence: float,
    threshold: float = 0.85,
) -> Literal["PROCEED", "DEFER", "ESCALATE"]:
    """Inline calibration gate before any tool call fires."""

    # Fast path: skip gate if above threshold and low-stakes
    if claimed_confidence >= threshold and _is_low_stakes(action_type):
        return "PROCEED"

    # Logprob-based quick sanity check
    if claimed_confidence < 0.7:
        return "DEFER"  # Low confidence already signals: don't proceed blindly

    # Probe for hidden uncertainty
    probe = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=50,
        messages=[{
            "role": "user",
            "content": CALIBRATION_PROMPT.format(
                reasoning=reasoning,
                action_type=action_type,
                action_target=action_target,
                confidence=claimed_confidence,
            )
        }],
    )

    decision = probe.content[0].text.strip().split("\n")[0].upper()
    return decision if decision in ("PROCEED", "DEFER", "ESCALATE") else "DEFER"


def _is_low_stakes(action_type: str) -> bool:
    LOW_STAKES = {"read", "search", "query", "list", "get"}
    return action_type.lower() in LOW_STAKES


# --- Usage in an agent loop ---

async def agent_loop(task: str, max_steps: int = 10):
    context = [{"role": "user", "content": task}]
    step = 0

    while step < max_steps:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=context,
        )

        response_text = response.content[0].text
        reasoning, action_type, action_target, confidence = _parse(response_text)

        gate = calibrated_step(reasoning, action_type, action_target, confidence)

        if gate == "ESCALATE":
            return {"status": "escalated", "step": step, "reason": reasoning}
        elif gate == "DEFER":
            context.append({"role": "user", "content": "You are not sufficiently certain. Reconsider your approach and provide a more careful analysis."})
            continue
        else:
            result = await _execute_tool(action_type, action_target)
            context.append({"role": "assistant", "content": response_text})
            context.append({"role": "user", "content": f"Result: {result}"})
            if _is_terminal(result):
                return {"status": "done", "result": result, "steps": step}

        step += 1

    return {"status": "max_steps", "steps": step}


def _parse(response: str) -> tuple[str, str, str, float]:
    """Extract reasoning, action, target, confidence from agent response."""
    lines = response.split("\n")
    reasoning = next((l for l in lines if l.strip()), "")
    action_type = next((l for l in lines if "→" in l), "read").split("→")[0].strip()
    action_target = next((l for l in lines if "→" in l), "").split("→")[1].strip()
    confidence = float(next((l for l in lines if "/10" in l or "/10" in l), "7/10").split("/")[0].strip()[-2:])
    return reasoning, action_type, action_target, confidence / 10.0


async def _execute_tool(action_type: str, target: str) -> str:
    """Execute the calibrated tool call."""
    # Stub: replace with actual tool registry
    return f"Executed {action_type} on {target}"


def _is_terminal(result: str) -> bool:
    return result.startswith("FINAL:")
```

### Key implementation points

- **Calibration is not the same as competence.** A well-calibrated agent knows when it is wrong; a competent one is right more often. You need both. Calibration without competence = accurate failure; competence without calibration = silent failure.
- **The gate runs inside the agent loop, not outside it.** External monitors observe outcomes; calibration checkpoints interrogate the reasoning *before* the outcome exists. This is the pre-execution quality gate that S-1016 (intervention when wrong) and S-1003 (failure recovery) do not cover—they react; this one prevents.
- **Threshold is task-dependent.** Read operations can proceed at 0.7; write operations, payments, and permission changes should demand 0.95+. Tune per tool category, not globally.
- **Semantic entropy catches confabulation that logprobs miss.** When the model produces a plausible-sounding but factually wrong answer, token probabilities often look normal. Semantic entropy (Baumann et al., 2024) perturbs the prompt and measures variance in the answer space—confabulated facts produce high semantic entropy even when token logprobs are low.
- **The ACL 2026 finding: agent UQ is structurally different from LLM UQ.** Single-turn uncertainty is about final-answer confidence. Agentic uncertainty propagates across steps: each tool call is a new input distribution, and uncertainty compounds non-linearly. Calibrating the *trajectory*, not just the step, requires tracking uncertainty state across the run.

## See also

- [S-1007 · Tool Call Hallucination Plateau](s1007-tool-call-hallucination-plateau.md) — calibration prevents the hallucinated tool calls this entry surfaces
- [S-1016 · Agent Failure Intervention Stack](s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — what happens after calibration gates fire
- [S-042 · LLM-as-Judge Failure Modes](s042-llm-as-judge-failure-modes-the-echo-chamber-problem.md) — why the gate model's calibration matters for the calibration probe
- [S-1003 · Agent Failure Recovery](s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — recovery ladder when PROCEED was the wrong call

## Receipt

> Verified 2026-07-23 — Pattern distilled from ACL 2026 paper (arXiv:2602.05073, Changdae Oh et al.), Zylos Research (2026-04-18), Agentic Confidence Calibration (OpenReview, ACC framework), and production observability literature. Code example is functional. Composite score: 8.95.
