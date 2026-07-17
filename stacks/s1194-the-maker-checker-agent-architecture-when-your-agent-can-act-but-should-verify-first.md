# S-1194 · The Maker-Checker Agent Architecture — When Your Agent Can Act But Should Verify First

Your agent drafts and sends a customer refund, approves a code merge, or transfers data to an external system — all within policy. Except the refund amount is wrong because the agent hallucinated the original charge, the merge introduces a regression the agent didn't see, and the data transfer went to the wrong endpoint because the agent misread a dropdown. The agent was working perfectly. The output was confidently wrong. Nothing in your infrastructure caught it because there was no failure to catch — only a wrong answer that looked right.

The maker-checker architecture addresses this: every high-stakes action goes through two independent agents — a maker that executes and a checker that independently verifies. The maker cannot claim "done" until the checker confirms. This is not a self-check. The checker is a separate identity with separate context, separate reasoning, and no access to the maker's internal state. When they disagree, a human escalates. When they agree, evidence exists for both.

## Forces

- **The maker is biased by its own output.** An agent that generates an answer evaluates that same answer differently than it would evaluate a stranger's answer. This is not a model flaw — it's a cognitive pattern LLMs inherit from their training. Intrinsic self-verification consistently degrades performance on reasoning tasks (BIG-Bench Hard, GSM8K, MMLU — prompting models to self-correct without external feedback makes them worse). A separate checker removes this bias entirely.
- **LLMs are calibrated wrong on confidence.** Frontier models are systematically overconfident on low-knowledge questions — the probability they assign to a wrong answer often exceeds 90% even when they're wrong. An agent that says "I'm confident this is correct" is not a reliability signal. The maker-checker pattern replaces the agent's self-reported confidence with independent verification.
- **Reversible vs. irreversible actions have fundamentally different risk profiles.** Reading data costs tokens. Writing data — sending emails, approving transactions, pushing code, modifying records — can cause real-world harm before anyone notices. Most agent architectures treat all tool calls uniformly. Maker-checker reserves the pattern for the irreversible subset.
- **Disagreements are the product.** When the maker and checker diverge, that gap is the most valuable signal in your system — it surfaces exactly the cases your evaluation suite didn't cover. Treating disagreements as errors to suppress is missing the point.

## The Move

### Layer 1 — Classify Actions by Reversibility

Not every action needs a checker. Classify your tool catalog into three tiers:

```python
REVERSIBILITY = {
    Tier.READ:     ["search", "lookup", "fetch", "get_balance", "get_record"],
    Tier.REVIEW:   ["draft", "summarize", "analyze", "generate_report"],
    Tier.EXECUTE:   ["send_email", "approve_refund", "transfer_funds", 
                    "merge_code", "delete_record", "push_to_prod",
                    "update_config", "create_user", "assign_role"],
}

def requires_checker(tool_name: str) -> bool:
    return tool_name in REVERSIBILITY[Tier.EXECUTE]
```

The execute tier triggers the maker-checker flow. Everything else runs normally.

### Layer 2 — The Parallel Execution Pattern

The maker and checker operate simultaneously on the same user request, not sequentially. Sequential checking doubles latency. Parallel checking halves it.

```python
import asyncio

async def maker_checker_execute(task: Task, maker: Agent, checker: Agent) -> Result:
    # Both agents work independently from the same original prompt
    maker_task = asyncio.create_task(maker.execute(task))
    checker_task = asyncio.create_task(
        checker.verify(task, maker_prompt=f"DO NOT SEE: {maker_task}")  # isolation
    )
    
    maker_result, checker_result = await asyncio.gather(maker_task, checker_task)
    
    if maker_result.action != checker_result.action:
        # Disagreement — escalate to human reviewer with full evidence
        return Result(
            status=Status.ESCALATED,
            maker_output=maker_result,
            checker_output=checker_result,
            disagreement_reason=checker_result.objection,
            evidence={"maker_trace": maker_result.trace, 
                      "checker_trace": checker_result.trace},
        )
    
    return Result(
        status=Status.CONFIRMED,
        action=maker_result.action,
        confidence=HIGH,
        evidence={"maker_trace": maker_result.trace,
                  "checker_trace": checker_result.trace,
                  "agreement": True},
    )
```

**Critical:** The checker is given the task goal and the maker's output — but never the maker's reasoning chain. A checker that can see the maker's intermediate steps will anchor on those steps and lose its independence. Pass only the final output, not the trajectory.

### Layer 3 — The Checker Prompt Is Not the Maker Prompt

The checker is given different instructions — it is optimizing for correctness, not for task completion:

```python
CHECKER_SYSTEM_PROMPT = """You are a quality assurance agent. Your job is to find flaws 
in the maker's output. You are not trying to complete the task — you are trying to break it.

Specifically, check for:
1. Factual accuracy — verify claims against known data sources
2. Tool call validity — did the agent call the right tools with valid arguments?
3. Constraint compliance — does the output violate any stated policies?
4. Completeness — did the agent miss any part of the request?
5. Hallucination signals — invented IDs, names, dates, or figures?

Be skeptical. The maker is trying to finish. You are trying to find what's wrong.
When you find something, state it precisely: what is wrong, why, and what evidence 
supports your objection.
"""
```

### Layer 4 — Escalation Handling

When maker and checker disagree, the escalation payload must include everything a human needs to adjudicate without re-running the agents:

```python
ESCALATION_PAYLOAD = {
    "task_id": task.id,
    "original_request": task.description,
    "maker_output": maker_result.output,
    "maker_trace": maker_result.trace,
    "checker_objection": checker_result.objection,
    "checker_trace": checker_result.trace,
    "disagreement_type": classify_disagreement(checker_result, maker_result),
    "created_at": timestamp,
    "severity": assess_severity(maker_result.action),
}
```

The `disagreement_type` classifier maps patterns to response protocols:
- `FACTUAL_CONFLICT` → human reviews source data, decides which is accurate
- `CONSTRAINT_VIOLATION` → human reviews policy, maker is wrong, no action
- `PARTIAL_CONFLICT` → maker proceeds on non-disputed parts, escalates only disputed part
- `FALSE_POSITIVE` → checker flagged something harmless, log for checker tuning

### Layer 5 — Tune the Checker to Match Your Recall Rate

The checker will occasionally disagree when the maker is actually correct. Track this and tune:

```python
# Track checker accuracy over time
checker_metrics = {
    "disagreements_total": 0,
    "checker_was_right": 0,   # maker was wrong, checker caught it
    "checker_was_wrong": 0,    # maker was correct, checker flagged in error
}

# If checker is too aggressive (high false positive rate):
# → add specificity instructions to checker prompt
# If checker is too lenient (misses real errors):
# → add red-team examples to checker training set
```

### Layer 6 — Apply to Tool Call Sequences, Not Just Final Outputs

Single tool calls are easy to verify. Multi-step sequences are where errors compound. For long sequences, insert checkpoint verifications at each tool call boundary:

```python
async def sequential_maker_checker(task: Task, maker: Agent, checker: Agent):
    steps = await maker.plan_sequence(task)  # maker generates the plan
    for step in steps:
        # Execute one step
        step_result = await maker.execute_step(step)
        # Check one step before proceeding
        check_result = await checker.verify_step(step, step_result)
        if check_result.has_objection:
            return escalate(step, step_result, check_result)
    return confirm_all_steps(steps)
```

## When to Use It

Use maker-checker when:
- Actions are irreversible (sending, approving, deleting, modifying)
- Errors are expensive (financial transactions, security changes, customer-facing communications)
- The task has a verifiable ground truth (does the refund match the original charge? does the code pass tests?)
- Latency is acceptable (parallel execution adds ~1 LLM round-trip; sequential adds ~2)

Do not use maker-checker when:
- The task is exploratory or creative (no ground truth to verify against)
- Latency is critical (< 1 second SLA)
- The action is read-only

## Receipt

> Verified 2026-07-16 — Pattern constructed from dual-agent verification research (Self-Correction in LLMs — BIG-Bench Hard, 2023; Cascade Watchdog — Codex Security Team, 2026; Maker-Checker — OWASP MAS categories; Redis Iris anomaly detection). No live execution run against production system. Components are validated from documented implementations in Redis multi-agent coordination (redis.io/blog/multi-agent-systems-coordinated-ai), Datafi multi-agent patterns, and agent observability tooling (Braintrust, Arize Phoenix, Langfuse). Checker prompt structure derived from agent evaluation best practices (ai-evaluation SDK, LayerLens).

## See also

- [S-1023 · The Recovery Ladder](/opt/data/handbook/stacks/s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — catching semantic failures that return HTTP 200
- [S-1016 · The Agent Failure Intervention Stack](/opt/data/handbook/stacks/s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — intervention points for wrong-but-successful actions
- [S-648 · Agent Contract Invariants](/opt/data/handbook/stacks/s648-agent-contract-invariants-multi-turn-behavioral-constraints.md) — behavioral constraints over conversation state
