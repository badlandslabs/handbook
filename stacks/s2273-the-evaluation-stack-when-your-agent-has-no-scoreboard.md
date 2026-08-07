# S-2273 · The Evaluation Stack — When Your Agent Has No Scoreboard

You shipped the agent. You shipped it again after the first bug. And again after the second. Every iteration improves something — but you have no way to know if the overall system is getting better or worse, because there is no systematic evaluation. Tasks complete without errors and silently produce wrong results. This is the evaluation gap: the most expensive blind spot in production AI.

## Forces

- **Agents fail silently.** Traditional monitoring tracks completion (did it finish?) not correctness (did it do it right?). An agent that retrieves the wrong document, calls the wrong tool, and arrives at a plausible-but-wrong answer will report success the same way a correct one does. Over 40% of agentic AI projects will be canceled by 2027 — inadequate evaluation is cited as the primary cause.
- **Multi-step compounding accuracy destroys reliability.** At 99% per-step accuracy, a 10-step task succeeds ~90% of the time. At 95% per-step, it drops below 60%. At 90%, it is below 35%. Agents that seem to work in demos — which are short — fail in production because real tasks have more steps. This arithmetic is not theoretical; it is why demos work and production doesn't.
- **Existing benchmarks are unreliable.** A NeurIPS 2025 analysis of 17 widely-used agentic benchmarks found that 7 of 10 exhibit "outcome validity" flaws — the evaluation check doesn't actually measure task success. A trivial "do nothing" agent achieves 38% success rate on τ-bench-Airline, exceeding GPT-4o performance, because empty responses count as success on intentionally-impossible tasks. SWE-bench-Verified fails outcome validity because incorrect patches can still pass the test suite.
- **LLM-as-judge needs calibration.** The dominant approach — using an LLM to score agent outputs — is fast and scalable but drifts. Teams targeting 0.80+ Spearman correlation with human judgment as a calibration threshold find this is not achieved out of the box and requires iterative rubric refinement.
- **Evaluation without CI integration is useless.** Evals run once are a snapshot, not a system. Without evaluation triggered on every commit, model change, or prompt update, regressions accumulate undetected until a data quality audit surfaces them weeks later.

## The Move

Separate trajectory evaluation (how the agent reasons) from outcome evaluation (did the task complete), and wire both into CI/CD with automated judgment.

### Core Pattern

1. **Define task-level success criteria first.** Before building the eval, decide: is this a trajectory task (reasoning quality matters even if the answer is wrong) or an outcome task (only the final result counts)? Mixing them produces metrics that measure nothing precisely. For code agents: check test suite pass, file correctness, no regression. For research agents: check answer completeness against a ground-truth knowledge base. For tool-using agents: check both the tool calls made and the state they produced.

2. **Use LLM-as-judge for trajectory, deterministic checks for outcomes.** LLM-as-judge excels at scoring open-ended reasoning quality, instruction adherence, and safety. It fails on factual correctness — a confident hallucination scores high on coherence. Pair it with execution-based checks wherever possible. DeepEval (10M+ G-Eval metrics processed monthly in production) is the dominant open-source framework for this hybrid approach.

3. **Calibrate judges against human ground truth before trusting scores.** Build a small human-annotated golden dataset (20-50 examples is enough for calibration). Run your LLM-as-judge on it. Measure Spearman correlation to human scores. Iterate the rubric until you hit 0.80+. This is not optional — an uncalibrated judge will tell you confidently wrong things about your agent.

4. **Evaluate on real distribution, not curated happy paths.** Cua-Bench (Show HN, ~21K stars on GitHub) demonstrates the OS-version problem: an agent with 90% success on Windows 11 drops to 9% on Windows XP for the same task. Evaluating only on your current environment, current model version, and current tool state produces a number that does not generalize. Sample from production traces to build representative eval sets.

5. **Gate production deploys with eval suites.** LangSmith, Braintrust, and Arize Phoenix have all converged on the same pattern: eval runs triggered by CI events (commit, PR, scheduled) with pass/fail thresholds as deployment gates. Braintrust's "CI/CD for AI" framing and DeepEval's pytest integration are the two dominant implementations of this pattern. Without this gate, you have no confidence that the agent you shipped this week is better than the one you shipped last month.

6. **Monitor production traces continuously, not just at deploy time.** Online evals score live user interactions in real-time, catching distribution drift that offline evals miss. LangChain's 2025 survey of 1,340 engineers found one in three teams cite output quality as the primary blocker to shipping agents — not cost, not latency. The gap between teams that monitor production and teams that don't is the gap between shipping and stalling.

## Evidence

- **Survey:** LangChain's State of Agent Engineering 2025 survey of 1,340 engineers found "output quality" cited as the top blocker to shipping agents to production — 33% of teams. — [https://www.langchain.com/langsmith/evaluation](https://www.langchain.com/langsmith/evaluation)
- **NeurIPS paper:** Zhu et al. (UIUC, Stanford, Berkeley et al.), "Establishing Best Practices for Building Rigorous Agentic Benchmarks" (2025 Datasets & Benchmarks Track) found up to 100% relative error in agentic benchmark results. 7 of 17 benchmarks failed outcome validity; a "do nothing" agent achieved 38% on τ-bench-Airline. — [https://github.com/uiuc-kang-lab/agentic-benchmarks](https://github.com/uiuc-kang-lab/agentic-benchmarks)
- **Market analysis:** AgentMarketCap (April 2026) reported 88% of AI agent projects never reach production; 89% of organizations implemented agent observability in 2025; 10M+ G-Eval metrics processed monthly by DeepEval in production. Compounding accuracy table: 95% per-step → <60% 10-step success. — [https://agentmarketcap.ai/blog/2026/04/07/agent-evals-cicd-braintrust-langsmith-arize-phoenix](https://agentmarketcap.ai/blog/2026/04/07/agent-evals-cicd-braintrust-langsmith-arize-phoenix)
- **Show HN:** Cua-Bench — unified cross-OS agent benchmark, finding "90% on Windows 11 drops to 9% on Windows XP." 20,996 stars, 1,429 forks as of August 2026. — [https://news.ycombinator.com/item?id=46768906](https://news.ycombinator.com/item?id=46768906)
- **HN community post:** "Why eval startups fail (2025)" by Thomas I. Liao — structural analysis of why eval tooling companies struggle: eval talent captures more value in post-training ($100M-$1B returns) than in eval tooling ($capped contract value). — [https://news.ycombinator.com/item?id=48637868](https://news.ycombinator.com/item?id=48637868)

## Gotchas

- **Green monitoring ≠ correct output.** An agent completing 100% of tasks with silently wrong results looks identical to an agent completing 100% of tasks correctly in any dashboard that tracks completion rate. You must separately measure correctness, not just completion.
- **Eval benchmarks are not production tests.** SWE-bench-Verified, GAIA, and WebArena are research benchmarks, not production quality gates. They measure general capability on curated tasks. Your agent's quality on a specific internal workflow is not predicted by any of them.
- **LLM-as-judge correlation drifts with model updates.** When you switch model versions, your calibrated judge may no longer correlate with human scores. Re-run calibration on every model change — this is a recurring cost most teams underestimate.
- **Trivial agents can beat strong agents on broken benchmarks.** The τ-bench finding — a do-nothing agent exceeding GPT-4o — is not an anomaly. It is a symptom of a benchmark design problem that is common. Always sanity-check your eval by running a deliberately-wrong agent through it.
- **Human validation is not replaceable, only deferrable.** Every eval framework recommends human validation alongside automated judges. For specialized domains (legal, medical, safety-critical), automated judgment is a floor, not a ceiling. Budget for it accordingly.
