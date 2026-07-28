# S-1742 · The Intent Uncertainty Stack — When Your Agent Assumes and Wrongly Acts

A user asks your agent: "Archive all the old records." It archives records from 2019–2022. The user meant 2023–2024. The agent spent $12 and deleted data before anyone could stop it. The agent was confident, responsive, and wrong — because it acted on an underspecified instruction without detecting the ambiguity. This is the intent uncertainty problem: agents interpret and execute rather than surface uncertainty and clarify before irreversible action.

## Forces

- **Agents optimize for responsiveness, not accuracy.** A model trained on completion奖励 learns that acting is better than asking. "I'll just assume the likely meaning" is a rational inference strategy that fails catastrophically when the assumption is wrong.
- **Clarification feels like failure.** Users say agents that ask questions are "annoying" or "slow." Agents internalize this pressure and resolve ambiguity through inference rather than dialogue — high confidence in low-clarity situations.
- **Intent uncertainty is invisible.** The agent has no native signal for "I am uncertain about this instruction." It has only token probabilities, which express linguistic confidence, not epistemic calibration. A 0.95 probability on a wrong assumption looks identical to 0.95 probability on the right one.
- **The cost of wrong action >> cost of clarification.** A clarifying question costs <500 tokens. A wrong archive deletion costs data, compliance risk, and recovery time. Agents systematically optimize for the wrong cost function.
- **Multi-step actions amplify intent errors.** A single ambiguous step cascades across a 7-step pipeline. The error at step 1 propagates through steps 2–7, each looking locally correct. By step 7, the output is confidently wrong and internally consistent.

## The Move

Build an intent uncertainty gate: a lightweight clarification layer that runs before any irreversible action, quantifying the expected information gain of asking versus acting.

**Step 1 — Detect uncertainty signals.** Flag requests that contain:
- Vague quantifiers: "all," "old," "recent," "relevant"
- Implicit scope: implied date ranges, user groups, or object types
- Underdetermined success criteria: "good enough," "substantially better," "clean up"
- Missing preconditions: "send the report" without specifying recipient, format, or channel

**Step 2 — Score information gain of clarification.** Before asking, compute expected value:

```
EV(clarify) = P(wrong|act) × Cost(wrong) − Cost(clarify)
EV(act)     = P(wrong|act) × Cost(wrong)
Clarify if: Cost(clarify) < P(wrong|act) × Cost(wrong) × (1 − P(recoverable))
```

Practical proxy: use token entropy of the top-K tool candidates. High entropy → multiple plausible interpretations → clarify. Low entropy → one dominant interpretation → act with logging.

**Step 3 — Ask with information gain ranking.** When clarification is warranted, present ranked options or binary questions ordered by expected information gain. A good clarification question eliminates the most uncertainty per token asked.

```python
# Uncertainty detection proxy using tool call entropy
def intent_uncertainty_score(agent_response, available_tools):
    tool_probs = [t["probability"] for t in agent_response.tool_calls]
    entropy = -sum(p * math.log(p) for p in tool_probs if p > 0)
    max_entropy = math.log(len(tool_probs))
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0
    
    # High entropy = ambiguous intent
    # Threshold 0.7 means top 2 tools are near-tied
    return normalized_entropy

# Threshold-based gating
THRESHOLD = 0.7
uncertainty = intent_uncertainty_score(response, tools)
if uncertainty > THRESHOLD:
    return {"action": "CLARIFY", "question": generate_clarifying_question(response)}
```

**Step 4 — Distinguish recoverable vs. irreversible actions.** Not everything needs pre-clarification. Classify actions by recoverability:

| Action Type | Requires Clarification |
|---|---|
| Read / Query / Search | No — low cost, high recoverability |
| Draft / Draft-Email / Draft-Report | Optional — can preview before send |
| Write / Update / Modify | Conditional — depends on scope |
| Delete / Archive / Send / Payment | Yes — requires explicit confirmation |
| Multi-step pipeline | Yes — uncertainty compounds across steps |

**Step 5 — Log and learn from clarifications.** Track every clarification: what was asked, what the user answered, how wrong the initial assumption was. Use this to improve the uncertainty detector over time. Patterns like "archive" → clarify date range appear repeatedly; once learned, surface the question proactively on recurrence.

## See Also

- [S-1331 · The Epistemic Memory Stack](s1331-the-epistemic-memory-stack-when-your-agent-stores-facts-beliefs-and-opinions-in-the-same-drawer.md) — stores beliefs vs. facts; intent clarification surfaces belief boundaries
- [S-1261 · The Confidence Calibration Stack](s1261-the-confidence-calibration-stack-when-your-agent-sounds-sure-and-is-wrong.md) — confidence ≠ calibration; intent uncertainty is a domain where this distinction matters operationally
- [S-1066 · The Invisible Failure Stack](s1066-the-invisible-failure-stack-when-your-agent-succeeds-and-burns-47k-instead.md) — wrong action is an invisible failure; clarification gates prevent the cost
- [F-192 · Cost Velocity Circuit Breaker](forward-deployed/f192-cost-velocity-circuit-breaker.md) — velocity-based intervention; intent clarification prevents the velocity event from happening
- [arXiv 2606.03135](https://arxiv.org/abs/2606.03135) — "Uncertainty-Aware Clarification in LLM Agents with Information Gain" (ICML 2026)

## Tags

intent-uncertainty, clarification-before-action, information-gain, underspecified-instructions, ambiguity-detection, intent-gate, irreversible-action, epistemic-uncertainty, bayesian-clarification, action-recoverability, intent-scoring, uncertainty-threshold, arxiv-2606.03135, icml-2026
