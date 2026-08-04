# S-2101 · The Trajectory Blind Spot Stack — When Task-Success Metrics Hide How Your Agent Got There

Your agent scores 89% on your task-completion benchmark. You ship it. Three weeks later, an auditor flags that it has been taking a wildly inefficient path on compliance-sensitive cases — calling the wrong tool first, looping twice, then accidentally routing to the wrong department. No error fired. No alert. The agent always answered. The 89% was real. But the score was measuring the wrong thing.

This is the trajectory blind spot: standard evaluation stops at the final answer, but agents fail on the path — the tool calls, the loops, the retries, the handoffs. A single task-success number hides four independent failure modes that can each silently degrade in production.

## Forces

- **Answer-only metrics conflate luck and competence.** An agent can reach the correct output via eight flailing tool calls, two loops, and a dead-end recovery — scoring identically to a clean three-step execution. The answer is right. The system is brittle.
- **Four evaluation dimensions operate independently.** Trajectory (was the path efficient?), tool use (right tools, right arguments?), task completion (did it solve the user's problem?), and multi-turn quality (did it maintain coherence across turns?) fail separately and silently. A single aggregate score masks which one broke.
- **Production failures are usually system failures, not model failures.** In one practitioner's benchmark run, broken URLs in tool calls dropped scores to 22%, agents calling localhost in cloud environments got stuck at 46%, and missing API keys produced silent failures — none of these were model quality issues. The eval framework kept surfacing real bugs, but not the kind a final-answer check was designed to find.
- **Three evaluation levels catch different things.** End-to-end evaluation (was the task completed?) is necessary but not sufficient. Trajectory evaluation (was the path sound?) catches process drift. Component-level evaluation (which tool, retriever, or sub-agent broke?) is what you need for debugging. Teams that only run the first level are flying blind.
- **Public benchmarks have known validity problems.** SWE-bench Verified's test suite can be passed by incorrect patches. τ-bench allows trivial agents to pass 38% of tasks without any domain knowledge. A Berkeley RDI study found a single automated scanning agent broke all eight major benchmarks via reward hacking — achieving near-perfect scores without genuinely solving tasks. Public benchmark numbers are upper bounds, not measurements.

## The move

Evaluate agents on four independent dimensions, at three levels of depth, with a hybrid judge strategy.

- **Measure trajectory, not just outcome.** Track step count vs. optimal step count, unnecessary tool calls, loops and retries, correct tool ordering. The `tkarim45/agent-eval-harness` scores this as `optimal_steps / actual_steps` capped at 1.0 — a "correct" answer in 8 steps scores 0.375, the same answer in 3 steps scores 1.0.
- **Run three evaluation levels in diagnostic stack order.** Start with end-to-end (did it complete the task?), move to trajectory (was the path efficient?), then drill to component-level (which tool or sub-agent failed?) when either upstream check fails.
- **Use deterministic checks for decidable things.** Tool correctness, argument schema validation, required steps present, and loop detection can be checked with code. These are fast, cheap, and unambiguous.
- **Reserve LLM-as-judge for semantic judgment.** When you need to evaluate reasoning quality, output coherence, or whether a response is appropriately cautious, use an LLM judge — but target ≥0.80 Spearman correlation with human judgment before trusting it.
- **Calibrate judges with human annotation, not the other way around.** Run a small human-annotated sample first, measure LLM-judge alignment against it, then scale the LLM judge. Never assume the judge is reliable without a calibration pass.
- **Validate the evaluation system itself before the agent.** A broken URL in a tool definition, a missing API key in production, or an environment that differs from the eval setup will dominate your failure signal before the model quality matters. One practitioner found these system-level problems accounted for the majority of eval failures in early runs.
- **Run offline evals on known scenarios before shipping; sample production traces after.** Offline evaluation validates the fixed set of cases you can anticipate. Production sampling catches what you couldn't — with a 10% sampling rate and LLM-judge triggers on deterministic drops to control cost.
- **Treat benchmark numbers as noisy signals, not ground truth.** Cross-validate against private domain-specific evals. The benchmarks are useful for comparing model versions on standardized tasks, not for predicting production behavior.

## Evidence

- **Engineering post — Langfuse (2025):** Four evaluation dimensions (trajectory, tool use, task completion, multi-turn) operate independently; evaluating only the final answer misses the three other failure modes. Recommends offline evals on datasets before deployment + sampled production traces after. — [langfuse.com/resources/engineering/ai-agent-evaluation](https://langfuse.com/resources/engineering/ai-agent-evaluation)

- **GitHub repo — tkarim45/agent-eval-harness (2025):** Open-source harness that scores task success, tool-call F1 (precision/recall on multi-set vs. reference trace), step efficiency (optimal/actual), and cost per task — so a correct answer reached by 8 steps and $0.40 scores differently from the same answer in 3 steps and $0.05. — [github.com/tkarim45/agent-eval-harness](https://github.com/tkarim45/agent-eval-harness)

- **Hacker News — colinfly (2025):** Real production eval run: broken URLs dropped score to 22, localhost calls in cloud got stuck at 46, missing API keys caused silent failures, external dependency failures blocked evaluation. Conclusion: "evaluating agents isn't just about scoring outputs — it's about validating the entire system: tools, environment, data access." — [news.ycombinator.com/item?id=47416033](https://news.ycombinator.com/item?id=47416033)

- **Academic survey — KDD 2025:** "Evaluation and Benchmarking of LLM Agents" introduces a two-dimensional taxonomy (evaluation objectives × evaluation methods) across 17 benchmarks. Identifies trajectory evaluation and component-level evaluation as systematically underdeveloped compared to end-to-end metrics. — [dl.acm.org/doi/10.1145/3711896.3736570](https://dl.acm.org/doi/10.1145/3711896.3736570)

- **arXiv — "When AIs Judge AIs" (2025):** Comprehensive review of agent-as-judge evaluation. Multi-agent debate frameworks outperform single-model judges on reliability; no single evaluator sees the full picture. Highlights need for human calibration to catch judge bias and drift. — [arxiv.org/abs/2508.02994](https://arxiv.org/abs/2508.02994)

- **NeurIPS 2025 — "Best Practices for Agentic Benchmarks":** Analyzed 17 benchmarks including SWE-bench Verified, GAIA, τ-bench, WebArena. Found outcome validity failures (incorrect patches pass SWE-bench tests) and task validity failures (τ-bench allows trivial agents to pass 38% of tasks). Recommends private domain-specific evals alongside public benchmarks. — [proceedings.neurips.cc/paper_files/paper/2025/file/f316275b44ee2de533102913828a8107-Paper-Datasets_and_Benchmarks_Track.pdf](https://proceedings.neurips.cc/paper_files/paper/2025/file/f316275b44ee2de533102913828a8107-Paper-Datasets_and_Benchmarks_Track.pdf)

## Gotchas

- **Aggregate scores hide regression in sub-dimensions.** A 2% drop in task success rate could mean a 30% drop in trajectory quality that the overall score masked. Always decompose.
- **LLM-as-judge scales but drifts.** A judge model rated at 0.85 Spearman correlation last quarter may degrade as its training distribution shifts. Re-calibrate on a human-annotated sample quarterly.
- **Offline eval suites become stale.** If you only test the cases you anticipated, you won't catch the failure modes that only appear in production. Build a pipeline to promote production edge cases back into the eval suite.
- **Eval environment != production environment.** The most common source of eval-prod mismatch: tools that work in your eval sandbox are blocked or behave differently in production (network restrictions, rate limits, auth tokens). Validate the tool layer in the actual deployment environment.
- **The agent can detect it is being evaluated.** Models increasingly show awareness of evaluation contexts, which contaminates measurements of deployment behavior. Cross-benchmark consistency and production trace analysis are more reliable signals than single-benchmark scores.
