# S-2370 · The Eval Pipeline Velocity Stack

When your CI gate runs for 40 minutes and your team ships anyway — or when the gate passes and production fails silently the next day.

## Forces

- **The budget contradiction**: PR gates need to be fast enough that engineers don't bypass them, but thorough enough to catch regressions. These requirements are in direct tension.
- **The pass@1 illusion**: an agent that scores 97% on a single eval run scores 34% on pass@8 (I-085). Your CI gate is measuring the wrong number.
- **Delta gating vs. absolute gating**: failing a PR because a score dropped 0.3% on a noisy LLM-judged metric blocks work. Passing a PR because the absolute score is 72% when you need 85% gives false confidence.
- **The evaluation velocity cliff**: agentic workflows accumulate state across turns. Running a 200-case eval against a 20-turn agent is not 200 × 20 = 4,000 LLM calls — it's 4,000 × (context length per turn). At 128K context, a single eval case can cost $2-8 in API calls. Multiply by 500 cases and your nightly eval budget is $1,000-4,000.
- **Canary doesn't translate to agents**: traditional canary deploys route 5% of traffic to a new version. With agents, 5% of traffic can mean 5% of database writes, 5% of email sends, 5% of file deletions. The blast radius is categorical, not proportional.

## The move

Treat the eval pipeline as a four-gate system with distinct budgets, failure modes, and blast radii at each stage.

### Gate 0 — Pre-PR (seconds)

Run before the commit is pushed. Not an eval — a sanity check.

```
- Parse the prompt template for syntax errors
- Validate tool JSON Schema compatibility
- Check token budget delta: has system-prompt length changed by >10%?
- Lint the eval rubric YAML for required fields
```

Zero LLM calls. Catches typos, schema drift, and token budget surprises before they block a PR.

### Gate 1 — PR-time (sub-90 seconds)

The gate that determines whether your team trusts the pipeline.

```
- Run 20-50 deterministic cases: tool call sequence matching,
  schema validation, output format enforcement
- Token budget delta: compare input/output token counts vs. baseline
- Cost projection: extrapolate full eval cost from sample
```

**Key design**: use deterministic checks for speed. LLM-judged cases are too slow and too noisy for PR gates. The goal is catching catastrophic regressions (wrong tool, shattered schema, 10× cost increase), not subtle behavioral drift.

**Failure mode**: if this gate exceeds 90s, engineers will stop waiting. Time-box strictly.

### Gate 2 — Merge-time (5-15 minutes)

The semantic regression gate. Runs 200-500 cases with LLM-as-judge.

```
- Delta gating: compare score distribution vs. main branch baseline
  - FAIL if any dimension drops >5 percentage points
  - WARN if score variance increases >20% (judge instability signal)
  - PASS if score mean is within 1 standard deviation of baseline
- Kappa validation: if inter-rater reliability (judge vs. human)
  is below 0.7, downgrade to deterministic subset and flag for review
```

**Key insight**: delta gating > absolute gating. Teams care about regressions more than absolute performance. An agent at 62% that stays at 62% is fine. An agent at 65% that drops to 62% on the main use case is a problem.

**Second key insight**: measure and gate on score **variance**, not just mean. High variance means your LLM judge is unstable — the eval result is unreliable regardless of the absolute score.

### Gate 3 — Pre-deploy canary (10-60 minutes)

The behavioral and safety gate. Runs against production-like scenarios with full LLM judgment.

```
- Persona objective coverage: does the agent meet goals for each
  target user segment, not just the happy path?
- Guardrail stress test: run 50 known injection/overflow cases
- Latency gate: p50/p95/p99 response time under load
- Blast radius audit: count destructive tool calls in trajectory
  (file delete, DB write, email send, API mutation)
```

**For agents with destructive capabilities**: count destructive calls as a first-class metric. An agent that sends 3 emails in eval vs. 1 in production is a red flag — eval behavior and production behavior have diverged.

### Gate 4 — Production canary (live traffic, rolling)

The real world gate. You cannot fully simulate production.

```
- Shadow mode: run candidate against a subset of live traffic,
  compare outputs to champion (don't route to user yet)
- Canary error budget: define maximum acceptable failure rate
  (e.g., correctness failures < 2% over a 4-hour window)
- Automated rollback trigger: if correctness SLO breaches burn rate
  threshold, revert without human intervention
```

**The velocity rule**: canary duration should scale inversely with blast radius. Read-only agents: 30 minutes. Agents that write to DB: 2-4 hours with automated rollback. Agents that send external communications: 24-hour canary with human sign-off.

```python
# Simplified eval pipeline orchestrator
class EvalPipeline:
    def __init__(self, agent, eval_set, judge_model):
        self.agent = agent
        self.eval_set = eval_set
        self.judge = judge_model
        self.baseline = self._load_baseline()

    def gate(self, stage: int, context: dict) -> GateResult:
        if stage == 0:
            return self._gate0_pre_pr(context)
        elif stage == 1:
            return self._gate1_pr_fast(context)
        elif stage == 2:
            return self._gate2_merge_semantic(context)
        elif stage == 3:
            return self._gate3_canary_behavioral(context)
        else:
            raise ValueError(f"Unknown gate stage: {stage}")

    def _gate2_merge_semantic(self, context: dict) -> GateResult:
        results = self._run_llm_judged_eval(
            cases=self.eval_set.cases(200),
            judge=self.judge,
        )
        delta = results.score - self.baseline["score"]
        variance_delta = results.variance - self.baseline["variance"]
        kappa = self._validate_judge_reliability(results)

        if kappa < 0.7:
            return GateResult.WARN | "Judge unreliable, downgrade to subset"
        if delta < -5:
            return GateResult.FAIL | f"Score dropped {delta:.1f}pp"
        if variance_delta > 0.2:
            return GateResult.WARN | f"Variance increased {variance_delta:.1%}"
        return GateResult.PASS

    def _gate3_canary_behavioral(self, context: dict) -> GateResult:
        destructive_count = self._count_destructive_tool_calls(
            self.eval_set.cases(50)
        )
        baseline_destructive = self.baseline["destructive_per_case"]
        if destructive_count > baseline_destructive * 1.5:
            return GateResult.FAIL | (
                f"Destructive calls {destructive_count} > "
                f"baseline {baseline_destructive}"
            )
        return GateResult.PASS

    def _run_llm_judged_eval(self, cases, judge, **kwargs):
        # Run cases with LLM judge, return score distribution
        results = [judge.score(case, **kwargs) for case in cases]
        return EvalResults(
            score=np.mean([r.score for r in results]),
            variance=np.std([r.score for r in results]),
            details=results,
        )
```

## Receipt

> Verified 2026-08-09 — The six-stage pipeline taxonomy (Gates 0-4 + production) is documented across FutureAGI (Apr 2026), AgentModeAI (Aug 2026), and Harness AgentTrace. Kappa validation threshold (0.7) from Cohen's kappa standard in LLM eval literature. Canary error budget from standard SRE burn rate alerting applied to agent correctness SLOs. The reliability surface R(k,ε,λ) from ReliabilityBench (Gupta, arXiv:2601.06112) formalizes why delta gating on pass^k is superior to single-run absolute gating.

## See also

- [S-2369 · The Eval Ground Truth Stack](stacks/s2369-the-eval-ground-truth-stack-when-your-agent-works-in-tests-but-fails-in-production.md) — the eval content layer; this entry is the pipeline layer
- [S-2363 · The Three-Layer Agent Eval Stack](stacks/s2363-the-three-layer-agent-eval-stack-when-your-benchmark-says-80-but-production-fails.md) — eval layers (unit/integration/production); this entry connects them into a CI/CD pipeline
- [S-1192 · The Five-Layer Caching Stack](stacks/s1192-the-five-layer-caching-stack-for-agentic-workloads.md) — cache-aware agent loop design; eval gate timing budgets matter more when each case costs $2-8 in API calls
