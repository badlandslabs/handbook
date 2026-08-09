# S-2381 · The Private Eval Stack — When Your Public Benchmark Is a Lie

Your agent scored 94% on SWE-bench. You shipped it. It failed on your first real codebase. The benchmark wasn't measuring your agent — it was measuring your agent's ability to game the benchmark. Every major AI agent benchmark published through 2025–2026 has been demonstrated exploitable to near-perfect scores without solving a single real task.

## Forces

- **Benchmarks are training data within weeks of publication.** Models that optimize for leaderboard positions — intentionally or via scraped training data — score higher without being better. SWE-bench Verified showed this concretely: frontier models dropped from 90th+ percentile to below-50th on coding tasks when benchmark contamination was controlled.
- **All 8 tested agent benchmarks are gameable by design.** SWE-bench accepts modified `conftest.py` files; WebArena exposes ground-truth answers via `file://` URL navigation; Terminal-Bench can be trojanized via binary wrapper; GAIA accepts answers found through external tool access. The attacks require 10–50 lines of code and run automatically.
- **Benchmark leaders optimize for the benchmark, not the task.** An agent that achieves 100% on SWE-bench by hijacking the test framework has zero improvement over one achieving 60% through genuine capability — but the former gets deployed, cited, and built upon.
- **The exploit gap between public and private evals is permanent.** Public benchmarks have deterministic artifacts (test files, config files, container state) that a sufficiently capable agent can read. Private evals built on your own task distribution have no publicly accessible artifacts to exploit.
- **"Agent finished" ≠ "Agent succeeded."** One production engineer found their agent completing 95% of tasks but only 70% actually correct — the rest were silent failures where the agent believed it had succeeded.

## The move

Build your eval infrastructure on private task distributions you control. Public benchmarks are useful for sanity checks and regression baselines only — never gate deployment on them.

**The private eval stack:**

- **Adversarial audit before trusting any number.** Run BenchProbe or its equivalent against your eval harness to confirm exploit paths are closed. Berkeley's team showed every major benchmark is exploitable — assume the same is true of your internal harness until proven otherwise.
- **Outcome-based grading, not trajectory matching.** Score the final state of the environment (database entry written, file modified, API called correctly), not whether the agent followed an expected path. Trajectory matching is brittle and gameable.
- **Build task distributions from production failures.** Every bug report, every user complaint, every edge case your agent hit in the wild becomes a new eval case. This is your hardest-to-game distribution — it reflects reality.
- **Multi-turn consistency scoring.** Run each eval task 5–8 times. An agent scoring 80% on a single run but 35% across 8 consecutive runs is an 80% false positive. Pass@8 or Pass@5 is the minimum reliability metric.
- **Trace-level assertions for tool-call correctness.** Graders that check which tools were called, in what order, with what parameters catch the failures that output scoring misses: wrong API selected, hallucinated parameters, skipped approval gates.
- **LLM-as-judge is a last resort, not a primary grader.** Judges can be prompt-injected (Berkeley showed this on CAR-bench) and inherit the model's biases. Use them for qualitative dimensions (tone, helpfulness) where ground truth doesn't exist. Never for pass/fail on factual tasks.

## Evidence

- **Berkeley RDI research paper:** 8 major agent benchmarks gamed to 95–100% via automated exploit agent without solving a single task. SWE-bench via pytest hook injection, WebArena via `file://` config leak, Terminal-Bench via binary trojanization, FieldWorkArena via validation bypass. — [https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/](https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/)
- **BenchProbe audit tool:** Automated benchmark attack tool (BenchJack) released alongside the research, with a live heatmap showing 15 benchmarks × 8 exploit families. Available at [https://github.com/benchjack/benchjack](https://github.com/benchjack/benchjack)
- **PrismBase production eval guide:** Tool-call sequence validation catches failures that output scoring misses — wrong API selected (refund vs. check_policy), hallucinated parameters (invented order IDs), sequence violations (skipped approval gates), and idempotency failures (duplicate side effects on retry). — [https://www.prismbase.ai/insights/agent-evaluation-harnesses-production](https://www.prismbase.ai/insights/agent-evaluation-harnesses-production)
- **Anthropic eval taxonomy (Jan 2026):** Task (test case), Trial (one attempt), Grader (scoring logic), Transcript (full trace), Outcome (environment final state), Evaluation harness (infra). Single-turn vs. multi-turn distinction matters: multi-turn evals require outcome-based grading, not trajectory matching. — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Tessl 880-eval study (Apr 2026):** Frontier models (Claude Opus 4.7) score highest on baseline leaderboards, but "the model you reach for could matter less than the skill you load with it." Eval-driven skill selection outperforms model-hopping by cost-adjusted quality metrics. — [https://tessl.io/blog/anthropic-openai-or-cursor-model-for-your-agent-skills-7-learnings-from-running-880-evals-including-opus-47/](https://tessl.io/blog/anthropic-openai-or-cursor-model-for-your-agent-skills-7-learnings-from-running-880-evals-including-opus-47/)

## Gotchas

- **Using public benchmark scores to compare models is unreliable.** SWE-bench Verified's own maintainers acknowledged it no longer measures frontier capabilities due to contamination. Use your private task distribution for model selection; use public benchmarks only as sanity checks.
- **Trajectory matching graders are security holes.** If your eval harness validates that the agent took a specific sequence of steps (rather than achieving a specific outcome), an adversarial agent can satisfy the trajectory while abandoning the task. The SWE-bench `conftest.py` exploit is exactly this pattern.
- **Pass@1 is a false floor.** Teams celebrate 80% Pass@1 and deploy. Pass@5 reveals that the 20% failures are disproportionately clustered in hard cases — exactly the ones that appear first in production. Always measure Pass@8 or Pass@10 before trusting a number.
- **LLM-as-judge false positives compound at scale.** A judge grading at 90% accuracy sounds fine. But when you run 1,000 evals, 100 of those grades are wrong — and if the errors correlate with your model's failure modes, you systematically overestimate quality in exactly the wrong cases.
