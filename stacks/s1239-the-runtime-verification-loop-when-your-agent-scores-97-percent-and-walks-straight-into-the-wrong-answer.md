# S-1239 · The Runtime Verification Loop — When Your Agent Scores 97% and Walks Straight into the Wrong Answer

Your agent just finished a 24-step workflow, returned a well-formed JSON payload, and logged zero errors. It also sent a refund confirmation to the wrong customer, routed a support ticket to the competitor's escalation queue, and generated a compliance report that cited a policy that was superseded three months ago. Your eval harness passed it at 97%. Your production monitor shows green. The failure happened in the 90 seconds between step 18 and step 19 — and no gate caught it.

You need a runtime verification loop: an inline critic that inspects agent decisions at each step, not just at the final answer.

## Forces

- **Eval gates check the destination, not the path.** Final-answer scoring (whether human label, LLM judge, or unit test) is blind to the intermediate steps that produced it. An agent that reaches the correct answer through a hallucinated tool call, a corrupted memory fetch, and two context drifts has the same final score as a clean run — until production.
- **Runtime verification has crossed into production infrastructure.** As of mid-2026, more than 50% of surveyed production agent teams run judge LLMs at runtime for quality gating. The field has bifurcated: large proprietary judges (GPT-4o, Claude 3.7 Sonnet) for high-stakes steps, small distilled judges (Galileo Luna-3, open-source 7B–13B) for low-latency inline checks. This is no longer experimental — it is load-bearing infra.
- **Verification overhead must be budgeted.** A $0.003 verification call after every $0.015 agent step doubles cost-per-task. The naive approach (verify everything) is economically untenable. You must spend verification budget where it buys the most error reduction.
- **Judges fail differently than agents.** LLM judges are themselves probabilistic — they have flip rates (same input → different verdict across identical runs), kappa deflation (Cohen's κ ≈ 0.48 when agreement rate looks like 85%), and failure modes that are systematically different from the agents they judge. A verification loop built on an uncalibrated judge trades one failure mode for another.
- **The 5% tool-call hallucination plateau makes verification non-optional.** Even frontier models fumble roughly one in twenty tool invocations in production. At five tool calls per task, that is a 23% task-level failure rate before retries. At ten steps with retries, compounding is the norm. No eval harness, however comprehensive, closes this gap — only inline verification at the step level does.

## The move

The runtime verification loop has three architectural layers: **where to verify, what to verify with, and how to budget the spend.**

### Layer 1 — Where: select verification checkpoints

Not every step needs verification. Gate these positions:

- **Side-effect boundaries** — any step that writes data, sends a message, triggers an external API call, or changes agent state irreversibly
- **Memory fetch gates** — any step where the agent retrieves from external memory or retrieves documents from RAG
- **Tool-call outputs** — any step where the agent acts on the result of a tool invocation (the tool can fail, return unexpected schema, or return stale data)
- **Handoff points** — any step where a sub-agent completes and control returns to the orchestrator
- **Confidence collapse** — any step where the agent expresses uncertainty, asks for clarification, or revisits a prior decision

Key principle: **gates verify decisions, not outputs.** Verify that the agent's reasoning for choosing action X is sound, not just that action X produced a well-formed result.

### Layer 2 — What: verification patterns by risk level

```
HIGH STAKES  (write, payment, send, delete, escalation)
  → Large proprietary judge (Claude 3.7 Sonnet / GPT-4o)
  → Full chain-of-thought critique: "Did the agent reason correctly?"
  → Budget: 1-2x the agent step cost; latency-tolerant

MEDIUM STAKES  (tool call, memory fetch, document retrieval)
  → Small distilled judge (Llama-4-70B / Galileo Luna-3)
  → Structured rubric with 3-5 dimensions: tool selection, argument correctness,
    contextual fit, hallucination signal
  → Budget: 0.2-0.5x the agent step cost; <200ms threshold

LOW STAKES  (summary, reformulation, routing)
  → Heuristic / schema validator (Pydantic, regex, value-range check)
  → No LLM judge — structural validation only
  → Budget: negligible
```

### Layer 3 — How: compose the loop

```python
import anthropic
from pydantic import BaseModel, ValidationError
from enum import Enum

class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"

class StepVerdict(BaseModel):
    verdict: Verdict
    reason: str
    retry_recommended: bool
    escalation_recommended: bool

class RuntimeVerificationLoop:
    def __init__(self, agent_client, judges: dict):
        self.agent = agent_client
        # judge tiers: small (fast, low-cost), large (slow, high-fidelity)
        self.small_judge = judges["small"]   # e.g., Claude 3.5 Haiku / Llama-4
        self.large_judge = judges["large"]   # e.g., Claude 3.7 Sonnet / GPT-4o

    def step(self, task: str, step_output: str, step_context: dict) -> StepVerdict:
        risk = self._classify_risk(step_context)

        if risk == "low":
            return self._structural_check(step_output)
        elif risk == "medium":
            return self._small_judge_verify(task, step_output, step_context)
        else:
            return self._large_judge_verify(task, step_output, step_context)

    def _classify_risk(self, ctx: dict) -> str:
        """Map step metadata to risk tier."""
        if ctx.get("has_side_effect") or ctx.get("writes_data"):
            return "high"
        if ctx.get("tool_call") or ctx.get("memory_fetch") or ctx.get("doc_retrieval"):
            return "medium"
        return "low"

    def _structural_check(self, output: str) -> StepVerdict:
        try:
            # If the agent claims structured output, validate it
            parsed = __import__("json").loads(output)
            return StepVerdict(verdict=Verdict.PASS, reason="structure valid",
                               retry_recommended=False, escalation_recommended=False)
        except Exception:
            return StepVerdict(verdict=Verdict.UNCERTAIN,
                               reason="non-structured output, manual review suggested",
                               retry_recommended=False, escalation_recommended=True)

    def _small_judge_verify(self, task: str, step_output: str, ctx: dict) -> StepVerdict:
        rubric = ctx.get("rubric", "Is the step output correct, relevant, and non-hallucinated?")
        prompt = f"""Task: {task}
Step output: {step_output}
Rubric: {rubric}
Respond with JSON: {{"verdict": "pass|fail|uncertain", "reason": "...", "retry": true|false, "escalate": true|false}}"""
        raw = self.small_judge.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}]
        )
        try:
            return StepVerdict.model_validate_json(raw.content[0].text)
        except ValidationError:
            return StepVerdict(verdict=Verdict.UNCERTAIN,
                               reason="judge output unparseable, escalate",
                               retry_recommended=False, escalation_recommended=True)

    def _large_judge_verify(self, task: str, step_output: str, ctx: dict) -> StepVerdict:
        trace = ctx.get("trajectory_so_far", "")
        prompt = f"""You are auditing an agent's reasoning chain.
Task: {task}
Full trajectory so far: {trace}
Step output: {step_output}
Did the agent reason correctly to reach this output? Are there signs of:
- Hallucinated facts or tool names?
- Incorrect tool argument construction?
- Context drift from the original task?
- Logical inconsistency?
Respond with JSON: {{"verdict": "pass|fail|uncertain", "reason": "...", "retry": true|false, "escalate": true|false}}"""
        raw = self.large_judge.messages.create(
            model="claude-opus-4-7-20251120",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        try:
            return StepVerdict.model_validate_json(raw.content[0].text)
        except ValidationError:
            return StepVerdict(verdict=Verdict.UNCERTAIN,
                               reason="judge unparseable, escalating",
                               retry_recommended=False, escalation_recommended=True)

    def run(self, task: str, agent_steps_fn, max_retries: int = 2):
        """Run an agent task with inline verification at each step."""
        trajectory = []
        for step_output, step_ctx in agent_steps_fn(task):
            verdict = self.step(task, step_output, step_ctx)
            trajectory.append((step_output, verdict))

            if verdict.escalation_recommended:
                return {"status": "escalated", "trajectory": trajectory,
                        "failing_step": len(trajectory) - 1}

            if verdict.verdict == Verdict.FAIL and verdict.retry_recommended:
                if max_retries > 0:
                    max_retries -= 1
                    continue  # re-run this step
                else:
                    return {"status": "dead_end", "trajectory": trajectory,
                            "failing_step": len(trajectory) - 1}

        return {"status": "complete", "trajectory": trajectory}
```

### Budget calibration

```
Verification cost fraction of total task cost:
  - Low-stakes task ($0.01/task): verify only side-effect steps → +8-12%
  - Medium-stakes task ($0.05/task): verify tool calls + memory → +25-40%
  - High-stakes task ($0.50/task): full per-step verification → +60-100%

At 50+ verification calls/day: switch to distilled judge (3B-7B)
  → 0.5-1ms latency vs 800-2000ms for large judge
  → Calibrate flip-rate threshold: reject verdicts where judge votes
    differently across 3 seeds at identical input
```

## Receipt

> Verified 2026-07-17 — LLM-as-judge at runtime is confirmed production practice (Zylos Research, 2026-04-10: "more than half of surveyed production agent teams now rely on judge LLMs at runtime"). ACON paper (arXiv:2510.00615, last revised June 2026) demonstrates that verification-triggered context compression reduces error rates on long-horizon tasks by 23%. The 5% tool-call hallucination plateau (Berkeley Function-Calling Leaderboard, 2025-2026) is the empirical anchor: no eval harness closes this gap without inline verification. Judge flip rate (S-1031) and kappa deflation (S-1024) are known failure modes of the judge layer — mitigated by small-distilled-judge calibration, not eliminated.

## See also

- [S-1031 · The Flip Rate Problem](stacks/s1031-the-flip-rate-problem-when-your-llm-judge-sometimes-votes-a-and-sometimes-votes-b-on-identical-inputs.md) — judge reliability at the verdict level
- [S-1024 · The Kappa Deflation Problem](stacks/s1024-the-kappa-deflation-problem-when-your-llm-judge-reports-85-but-has-kappa-0.48.md) — why raw agreement rates deceive
- [S-1007 · The Tool-Call Hallucination Plateau](stacks/s767-the-tool-call-hallucination-plateau.md) — the empirical anchor: why verification is non-optional
- [S-1016 · The Agent Failure Intervention Stack](stacks/s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — what to do when verification fires
- [S-1023 · The Recovery Ladder](stacks/s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — retry and escalation patterns after a failed gate
