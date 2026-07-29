# S-1793 · The Calibration Gate Stack — When Your Agent Knows Nothing but Acts Like It Knows Everything

Your agent answers a trivia question confidently. Wrong. Your agent calls an external API when it already had the answer in its weights. Wasted budget. Your agent refuses to use a tool it actually needed. Silent failure. These aren't three different problems — they're the same root cause: the agent has no calibrated sense of what it actually knows versus what it just sounds confident about. The fix is a calibration gate between the agent's decision to act and its actual capability.

## Forces

- **RLHF trains confidence, not calibration.** RLHF rewards responses that sound authoritative. The model learns that saying "I'm certain" gets higher ratings than "I'm not sure." The training signal is about perceived quality, not epistemic accuracy. The result is systematic overconfidence at exactly the knowledge boundary — where the model has enough training signal to generate a fluent answer but insufficient signal to generate a correct one.
- **Agents can't distinguish internal from external knowledge.** A model asked "What is the capital of France?" faces the same next-token problem whether it answers from weights or from a web search. The tool call decision looks identical from the inside. Without a metacognitive layer, the agent has no principled basis for choosing between solving from knowledge and reaching for external resources — so it defaults to whatever produced the first plausible-looking token sequence.
- **Calibration failures compound in chains.** In a 10-step reasoning chain, an overconfident step produces a plausible intermediate claim. Step 2 builds on it confidently. By step 10, the error has propagated into a coherent-seeming answer. The final output looks more confident than any individual step because the confidence signals have compounded without correction.
- **The Dunning-Kruger pattern is real in LLMs.** Sudipta Ghosh & Panday (arXiv:2603.09985, Feb 2026) empirically confirmed that LLMs exhibit Dunning-Kruger: they are worst-calibrated precisely in domains where pre-training coverage is thin. The model generates fluent, confident text in areas of genuine ignorance — not because it is lying, but because the architecture cannot distinguish fluent generation from reliable knowledge.

## The move

Build a calibration gate into the agent's action selection loop. The gate intercepts tool calls and internal reasoning steps, scores the agent's confidence in its current answer, and routes based on a calibrated threshold — not a prompt instruction.

### 1. Know-Act Quadrant Probe (KAPRO)

Before every tool call or answer commitment, run a lightweight self-assessment probe:

```
System prompt addendum:
Before answering, rate your confidence:
(1) I can answer from known facts — proceed
(2) I could answer but am uncertain — use tool to verify
(3) I don't know — reach for external tool or say so
```

Classify responses into internal/external/hybrid zones. Route accordingly. ACL 2026 (ACL Anthology, Chen et al.) found this separation cuts both redundant tool calls (when internal knowledge suffices) and insufficient calls (when external verification is needed).

### 2. Calibration-Aware Token Routing

Train or prompt the model to emit a calibrated confidence score alongside its primary output:

```python
class CalibrationGate:
    def __init__(self, threshold=0.7):
        self.threshold = threshold

    def should_verify(self, response: str, confidence_signal: float) -> bool:
        if confidence_signal >= self.threshold:
            return False  # proceed
        # Below threshold: route to verification tool
        return True

    def route_tool_call(
        self, task: str, confidence_signal: float, tool_results: list
    ) -> str:
        if confidence_signal >= self.threshold and tool_results:
            # Overconfidence + conflicting tool data = reject answer
            self.alert("calibration_gate: confidence_tool_conflict")
            return tool_results[0]  # trust tool over model
        return response
```

### 3. Confidence-Weighted Tool Selection

When multiple tools could apply, weight the selection by calibrated confidence:

- High internal confidence → prefer weight knowledge, skip tool
- Low internal confidence → prefer tool verification, discount parametric answer
- Confidence below threshold + tool unavailable → escalate to human

### 4. Behavioral Calibration Training (ET-Agent)

For production agents built on fine-tuned models, apply behavior calibration training (ACL 2026, Chen et al., ET-Agent framework): specifically penalize redundant tool calls (calling calculator when answer is in context) and reward under-use corrections (retrieving when the model's internal answer was wrong). Standard accuracy-based training doesn't distinguish these failure modes — calibration training does.

### 5. Per-Step Confidence Monitoring in Long Chains

In multi-step reasoning, inject a confidence probe at every intermediate step. Track confidence trajectories:

```python
def score_step_confidence(messages: list[dict]) -> float:
    """Estimate confidence of last assistant message via self-consistency."""
    # Ask the same question again with temperature > 0
    # If answers diverge, confidence is low
    pass  # implementation: self-consistency sampling
```

Flag confidence drops across steps as a cascade signal — not just final answer confidence.

### 6. Dunning-Kruger Mitigation

Accept that the model will be most overconfident where it's most ignorant. Mitigate with:

- **External-grounding mandate**: for factual claims above a threshold length, require a cited source
- **Inverse confidence penalty**: if the model's answer sounds hedged ("it seems likely"), suppress the hedging and force a binary decision, then compare the result
- **Tool-as-verification default**: when task involves facts that can be verified, default to tool call and use model output as fallback

## Receipt

> Receipt pending — 2026-07-28. Sources: ACL 2026 (Chen et al., ET-Agent, ACL Anthology 2026.acl-long.333), arXiv:2603.09985 (Ghosh & Panday, Feb 2026), Zylos Research (Apr 2026), ACL Anthology KAware dataset framing. Code examples are structural; specific threshold calibration requires per-model ECE measurement against a held-out calibration set.

## See also

[S-1789 · The Capability Boundary Stack](s1789-the-capability-boundary-stack-when-your-agent-reaches-for-a-tool-it-doesnt-need.md) · [S-1790 · The Trajectory Evaluation Stack](s1790-the-trajectory-evaluation-stack-when-your-agent-looks-right-but-gets-there-for-the-wrong-reasons.md) · [S-1786 · The Trajectory vs. Outcome Stack](s1786-the-trajectory-vs-outcome-stack-when-you-dont-know-if-your-agent-is-reasoning-well-or-just-getting-lucky.md) · [S-1791 · The Agent Harness Stack](s1791-the-agent-harness-stack-when-your-model-generates-text-but-your-system-decides-what-it-touches.md)
