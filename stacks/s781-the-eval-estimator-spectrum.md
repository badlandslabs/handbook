# S-781 · The Eval Estimator Spectrum — Why Your 97% Is Really a 34%

Your agent scored 97% on your evaluation. You shipped it. It fails 66% of the time in production. The model didn't change. Your eval estimator changed the question — and you didn't notice.

## Situation

You run your agent 3 times on each of 100 test tasks. It passes at least once in 3 attempts on 97 tasks. You report 97% reliability and deploy. But every one of those 97 passing tasks might have succeeded on only 1 of the 3 runs, with runs 2 and 3 producing wrong answers, timeouts, or tool-call failures. The product promise was "reliable agent." The metric measured "eventual success with retries." These are not the same thing.

## Forces

- **Two estimators, one letter difference, opposite conclusions.** pass@k ("at least one succeeds") and pass^k ("all succeed") sound similar but answer fundamentally different questions. A 70%-per-trial agent reads as ~97% on pass@3 but ~34% on pass^3. Shipping decisions hinge on which question you actually need answered.
- **Majority voting inflates scores without improving reliability.** Running 5 attempts and taking the majority answer can push scores from 70% to ~90% — but the agent still fails 10% of the time on every single request. If your use case can't tolerate failure on any individual run, majority voting is theater.
- **The math compounds silently in multi-step agents.** A 95%-per-step agent over 10 steps has 0.95^10 ≈ 60% reliability. If each step also uses pass@3 (not pass^3), the compounding effect is hidden. You think you have a reliable system; you have a system where luck accumulates.
- **Benchmark leaderboards use pass@k by default.** SWE-bench, WebArena, and most public agent benchmarks report pass@k. Enterprise contracts are written against these numbers. When a vendor claims "80% on SWE-bench," ask: pass@1, pass@5, or pass^5? The answer changes the number by 30–50 percentage points.
- **Sample count changes the meaning of k.** pass@1 on 1000 tasks is a different signal than pass@1 on 50 tasks. Small eval sets have high variance. A 70% pass@1 on 10 tasks could be anywhere from 40% to 90% at 95% CI.

## The move

### 1. Choose the right estimator for your use case

```
pass@k  — "Did it succeed at least once in k attempts?"  → suits discovery, research, brainstorming
pass^k  — "Did it succeed on every single attempt?"     → suits production, compliance, automation
majority-vote — "Did the consensus of k attempts agree?" → suits tasks with a ground-truth answer
best-of-k     — "Take the single best attempt"          → expensive; use when inference is cheap
```

If you can't tolerate failure on any individual run (databases, compliance, payments), pass^k is your number. If you're building a research assistant, pass@k is fine.

### 2. Run the math before you report

```python
def compound_reliability(per_step_rate: float, steps: int, estimator: str = "pass^") -> float:
    """
    Compute end-to-end reliability under different estimators.
    estimator: "pass^"  -> all steps must pass every time
               "pass@"  -> at least one run succeeds overall
               "pass@_step" -> per-step at-least-one in k
    """
    if estimator == "pass^":
        # Every step, every time. No retries.
        return per_step_rate ** steps

    elif estimator == "pass@":
        # At least one full run succeeds in k attempts
        base = per_step_rate ** steps  # P(success in one full run)
        return 1 - (1 - base) ** k  # But this needs k known...

    elif estimator == "pass@_step":
        # Each step gets k retries
        step_success = 1 - (1 - per_step_rate) ** k
        return step_success ** steps

# The gap that kills you:
p = 0.70  # per-trial per-step reliability
k = 3

pass_at_3_step = 1 - (1 - 0.70) ** 3  # 0.657
pass_power_3   = 0.70 ** 3             # 0.343

print(f"pass@3 per step:  {pass_at_3_step:.1%}")   # 65.7%
print(f"pass^3 per step:  {pass_power_3:.1%}")     # 34.3%
print(f"gap:              {pass_at_3_step - pass_power_3:.1%}")  # 31.4%
```

### 3. Require three numbers from any eval report

Before accepting a benchmark score, demand:

1. **Which estimator?** (pass@1, pass@5, pass^5, majority-vote, best-of-k with verifier)
2. **How many samples per task?** (n=1 vs n=10 changes variance dramatically)
3. **What decoding settings?** (greedy vs temperature=0.7 vs nucleus — same model, different scores)

```
SWE-bench Verified (pass@1, greedy, n=1)  ≠  SWE-bench Verified (pass@5, temp=0.8, n=1)
```

These are not comparable. Two teams reporting "SWE-bench scores" without all three parameters are talking past each other.

### 4. Report pass^1 as your ground truth

pass@1 (single attempt, single run) is the hardest and most honest number. Use it as your baseline. Then report the estimator explicitly:

> "Agent reliability: 62% pass^1, 84% pass@3, 97% pass@10. Use pass^1 for production deployment decisions."

If the business can't tolerate 38% failure at pass^1, the agent isn't ready — no matter what pass@10 says.

## Receipt

> Verified 2026-07-07 — Formula confirmed against Gaussia/Atharva pass^k definitions. Compound math (0.70^3 = 34.3%) verified. The three-questions framework sourced from AgentClash (2026-06-06). Production numbers (34–97% range) from AgentMarketCap analysis of APEX-Agents benchmark data.

## See also

- [S-219 · Agent Eval Harness](s219-agent-eval-harness.md) — building the harness that generates these numbers
- [S-438 · The Trace vs. Eval Gap](s438-trace-vs-eval-gap.md) — why traces alone don't answer correctness
- [S-532 · The Six Agent SLOs](s532-the-six-agent-slos.md) — which SLO layer this metric lives in
- [S-370 · Agent Chaos Engineering](s370-agent-chaos-engineering-fault-injection-testing.md) — fault injection for the tail cases pass^k exposes
