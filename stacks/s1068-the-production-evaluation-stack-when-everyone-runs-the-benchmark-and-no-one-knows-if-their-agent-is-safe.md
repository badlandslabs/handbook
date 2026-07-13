# S-1068 · The Production Evaluation Stack — When Everyone Runs the Benchmark and No One Knows If Their Agent Is Safe

You run your agent through a benchmark. The numbers look great. You ship it. Six weeks later a user flags that the agent has been consistently mishandling a specific input class, generating confident wrong answers that no one caught because the benchmark didn't test for that scenario. The benchmark proved the agent could do tasks A, B, and C — it said nothing about task D, which is what all your users actually do. This is the evaluation gap: teams have no shortage of benchmarks, but they lack a systematic way to know whether their specific agent is safe, correct, and improving in the wild.

S-1064 covers trajectory eval (grading the path, not just the output). This entry covers the structural problem — why most teams don't evaluate their production agents at all, and the layered approach that separates teams who measure from teams who actually improve.

## Forces

- **Benchmarks prove capability on standardized tasks, not on your users' tasks.** SWE-bench, GAIA, and WebArena are designed to rank models on public tasks. Your agent's actual failure modes are specific to your prompts, tools, users, and domain. A 92% SWE-bench score tells you nothing about whether your customer-service agent refuses to escalate appropriately.
- **Most teams don't evaluate in production at all.** Only 52.4% of teams run offline evaluations on test sets; just 37.3% run online evaluations — meaning the majority of deployed agents operate without any systematic quality signal (Mastra.ai, 2025).
- **Non-determinism makes regression invisible.** An agent that passes today can fail tomorrow on the same input. Without trajectory capture and regression tests, degradation is silent until a user notices.
- **Trajectory and outcome are separate quality dimensions.** An agent can reach a correct final answer via a broken reasoning path that will fail under slightly different inputs. Grading only the outcome misses this entirely.
- **Benchmark scores are inflated by scaffolding and data contamination.** The same model can swing 30–50 points depending on the scaffolding around it. Training-data contamination has inflated SWE-bench scores by an estimated 5–15 points on post-2023 models (AnhTu.dev, 2026). Verified subsets reduce but don't eliminate this.
- **Evaluation cost vs. label quality tradeoff.** LLM-as-judge achieves ~80% agreement with human evaluators at 500x–5000x lower cost — but drops to 60–70% in expert domains (legal, medical, specialized code). Synthetic data scales cheaply but lacks the edge-case coverage that production failures provide.

## The Move

The production evaluation stack has four layers that must run continuously, not just at deployment:

### 1. Capture every production failure as a regression test

The highest-value test cases are not handcrafted — they come from failures. Every time an agent does something wrong in front of a real user, it hands you an authentic edge case, a real input distribution, and a concrete definition of "broken." The pattern is a closed loop: production failure → trace capture → test case → golden dataset → CI/CD release gate. Run the golden dataset on every prompt change, model swap, retrieval tweak, or tool update (Arthur.ai, 2026).

### 2. Grade trajectories, not just outcomes

Evaluate three separate dimensions on every test run:
- **Outcome correctness** — did the agent reach the right final state?
- **Trajectory soundness** — did it get there via reasonable steps, or did it stumble into the right answer for the wrong reasons?
- **Efficiency** — did it take a reasonable number of steps and tool calls, or did it loop?

Trajectory scoring catches regressions that outcome-only scoring misses: an agent can succeed at the final step while taking a path that fails under slightly different inputs (RockB/baeseokjae, 2026).

### 3. Calibrate LLM-as-judge with domain-specific rubrics

Don't ask the judge "is this a good answer?" — provide a 5-point rubric with concrete behavioral anchors for each score level. Without rubrics, judge agreement on subjective quality scores varies by as much as 30% across different prompts for the same content. In expert domains, supplement with human calibration: run a random sample of 10–20 evals through a human reviewer to measure and correct judge drift (RockB, 2026; Mastra.ai, 2025).

### 4. Instrument with distributed tracing from day one

Use OpenTelemetry-compatible instrumentation to capture spans for every prompt, tool call, retrieval, and LLM response. Structure the trace to distinguish: what the user asked → what the agent planned → what tools it called → what state it read/wrote → what it returned. This data feeds both real-time monitoring dashboards and offline evaluation datasets (Databricks Blog, 2025; Gheware, 2026).

## Evidence

- **Survey (Cleanlab, 2025):** Out of 1,837 engineering and AI leaders surveyed, only 95 (5%) had AI agents live in production. Of those, fewer than 1 in 3 were satisfied with their observability and guardrail solutions. 70% of regulated enterprises rebuild their AI stack every 3 months or faster. — [Cleanlab AI Agents in Production 2025](https://cleanlab.ai/ai-agents-in-production-2025)

- **Framework documentation (Mastra.ai, 2025):** Only 52.4% of teams run offline evaluations on test sets; 37.3% run online evals. LLM-as-judge achieves ~80% human agreement at 500x–5000x lower cost. pass@k measures capability (at least one success in k attempts); pass@1 measures reliability. — [Mastra.ai — AI Agent Evaluation](https://mastra.ai/articles/ai-agent-evaluation)

- **Engineering post (Arthur.ai, 2026):** Production failures are the highest-value regression test source. The loop (failure → trace → test case → golden dataset → release gate) prevents silent recurrence. Multi-step agent failures hide in tool calls, retrieval, and planning — not just final output. — [Arthur.ai — Regression Test Datasets From Production Failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

## Gotchas

- **Running a benchmark is not the same as evaluating your agent.** Benchmarks rank models on standardized tasks. Your agent's actual failure modes are domain-specific. The benchmark score is a floor, not a ceiling — and often not even that.
- **Golden datasets go stale.** If you only add tests when you remember to, the dataset drifts from production reality. Automated capture from production traces (step 1) is the only sustainable source.
- **Gating releases on LLM-as-judge scores without rubric calibration** creates perverse incentives: the agent learns to optimize for the judge's blind spots rather than for real task quality.
- **The 80% human-agreement number for LLM-as-judge is a domain average.** In specialized code review, legal reasoning, or medical domains, drop to 60–70%. Don't use the average to justify skipping human spot-checks in high-stakes domains.
