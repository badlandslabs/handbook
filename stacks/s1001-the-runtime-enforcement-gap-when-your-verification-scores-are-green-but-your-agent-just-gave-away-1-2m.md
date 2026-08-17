# S-1001 · The Runtime Enforcement Gap: When Your Verification Scores Are Green but Your Agent Just Gave Away $1.2M

Your agent's LLM-as-judge scores 94/100. It marks the output "grounded" and "safe." The refund tool executes anyway — $1.2M to a fraudster. The gap is not between wrong answers and right ones. The gap is between measuring output quality and actually preventing consequential actions based on it. In 2026, over 57% of production agent teams run judge LLMs — but most are running dashboards, not guardrails.

## Situation

A customer support agent processes a refund request. The LLM-as-judge evaluates the response: "Appropriate tone, correct format, no policy violation." Score: 91/100. The agent marks the ticket resolved. Three days later, the fraud team flags the interaction: the agent issued a $47,000 refund to an account flagged 14 times in the past year. The judge was right about format and tone. It was blind to business logic, account history, and cumulative risk signals.

This is the **Runtime Enforcement Gap**: the architectural separation between systems that *measure* output quality and systems that *prevent* consequential actions based on it. LLM-as-judge was designed for evaluation. Enforcement is a different architectural layer with different failure modes, latency budgets, and decision rights.

## Forces

- **Measurement ≠ enforcement.** A judge scores what already happened. Enforcement decides what happens next. Scoring green on a 91/100 does not mean the next action is safe to execute.
- **The circularity problem.** When the judge uses the same model family as the agent (GPT-4o judging GPT-4o outputs), systematic biases align. The judge replicates the agent's blind spots, not corrects them. Substring-based judging agrees with human annotation at κ=0.049 — chance level (AgentProp-Bench, arXiv:2604.16706v1).
- **Latency kills enforcement.** A runtime judge adds 800ms–4s per step on a capable model. For high-frequency agent loops (10–100 LLM calls per task), inline enforcement multiplies latency by 1.5–3×. Teams that enforce only on "slow" consequential actions create a blind spot for fast multi-step pipelines.
- **Coverage is a design choice, not a default.** Most teams enable enforcement only on "obviously dangerous" actions. But the highest-impact failures — confident hallucination, context drift, plan collapse — look benign at the action level and catastrophic at the outcome level.
- **Judges disagree with themselves.** Self-consistency (running the same prompt twice) produces conflicting verdicts 8–15% of the time on complex multi-step reasoning tasks. A single-judge verdict is not a deterministic gate — it is a probabilistic signal.

## The Move

Split verification into two independent layers with different latency budgets, different model families, and different decision semantics:

### Layer 1: Fast Deterministic Gates (inline, zero latency overhead)
Apply these before any LLM call:

```
schema_contract_check(tool_args)       # Does args match the JSON schema?
business_rule_check(tool_name, args)   # Is this action allowed given context?
rate_limit_check(agent_id, tool_name)  # Has this agent called this tool N times?
audit_log(tool_name, args, session_id) # Immutable log of what was attempted
```

These catch 60–70% of dangerous outputs with <1ms overhead. No LLM needed.

### Layer 2: Semantic Enforcement Layer (async or inline depending on consequence)
Route to a **smaller distilled judge** (Galileo Luna-2 3B, Prometheus 2 7B, Patronus Lynx 8B) for inline checking, or a **large proprietary judge** (Claude 3.7 Sonnet, GPT-4o) for post-hoc audit of consequential actions.

```
def enforce(output, context, consequence_level):
    if consequence_level == "high":
        # Block and wait for large judge verdict
        verdict = large_judge.evaluate(output, context)
        if verdict.score < threshold:
            escalate(verdict.reason)
            return BLOCKED
    elif consequence_level == "medium":
        # Inline check with small distilled judge
        verdict = small_judge.evaluate(output, context)
        if verdict.score < threshold:
            return {"status": "warned", "verdict": verdict}
    # Consequence level "low": log only, don't block
```

Distilled judges deliver **97% cost reduction** at 0.88–0.95 accuracy vs large judges — sufficient for inline gating on medium-risk actions.

### Layer 3: The Circularity Break
Use a **different model family** for enforcement than for generation. If the agent runs Claude, the judge runs GPT-4o (or vice versa). This is not perfect — alignment bias exists across families — but it eliminates the intra-family blind spot that makes same-family judges unreliable.

```python
AGENT_MODEL = "claude-sonnet-4-20250514"
JUDGE_MODEL = "gpt-4o-20250514"  # Different family breaks circularity
```

### Layer 4: Enforcement Actions (not just scoring)
Verification scores are useless without enforcement actions. Define the action map:

| Score Range | Action |
|-------------|--------|
| ≥ threshold | Execute, log verdict |
| < threshold, high confidence | Block, escalate, require human sign-off |
| < threshold, low confidence | Flag for async audit, allow execution with tracking |
| Timeout on judge call | Fail-closed for high-consequence; log-and-proceed for low |

Fail-closed means: if the enforcement layer cannot get a verdict (judge timeout, service down), the action is blocked by default. This is the only safe default for consequential actions.

## Receipt
> Verified 2026-08-16 — Research synthesis from: arXiv:2606.19242v1 (C-Trace, Kahani et al., June 2026 — runtime compliance enforcement on GDPR traces); arXiv:2604.16706v1 (AgentProp-Bench, κ=0.049 for substring judging); Zylos Research (2026 — 57% adoption, 97% cost reduction for distilled judges); Waxell AI Blog (2026 — 40.55% of live MCP servers have no auth, structural enforcement gap); RelayPlane Blog (2026 — single agent loop burns $15 in 10 minutes without enforcement).

## See also
- [S-976 · The Verification Layer](stacks/s976-the-verification-layer-when-your-agent-cant-distinguish-right-from-almost-right.md) — measures quality
- [S-983 · The Agent Recovery Stack](stacks/s983-the-agent-recovery-stack-when-your-agent-looks-okay-but-isnt.md) — catches failure after the fact
- [S-982 · The Supervisor Pattern](stacks/s982-the-supervisor-pattern-stack-when-your-multi-agent-system-has-no-idea-whos-in-charge.md) — orchestration-level governance
