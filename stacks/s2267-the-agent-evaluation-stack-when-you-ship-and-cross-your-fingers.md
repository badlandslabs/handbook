# S-2267 · The Agent Evaluation Stack

[Your agent passes every test. Your users still get bad outcomes. The gap between passing a curated eval and shipping a reliable agent is where most agentic projects die — and most teams never measure it.]

## Forces

- Per-turn eval scores that look green can mask catastrophic end-to-end failure — compound error math means 95% per-step accuracy over 8 steps yields only ~66% overall success
- Traditional software testing breaks down: outputs are non-deterministic, failure modes are quality regressions, not exceptions
- Reference ground truth doesn't scale — hand-labeling thousands of production interactions is expensive and still can't capture the long tail of edge cases
- Teams wait for a human annotation team before building evals, leaving months of unmeasured shipping in the interim
- Agent trajectories are opaque — knowing the final answer is wrong tells you nothing about which tool call, argument, or reasoning step caused it

## The Move

Score trajectories, not responses. Build a layered eval stack that runs on every PR and catches regressions before users do.

**1. Separate trajectory eval from outcome eval.** A right answer from the wrong path is a ticking failure. Score tool selection (did it pick the right tool?), argument extraction (were the parameters correct?), result utilization (did it use the output?), error recovery (did it backtrack when it dead-ended?), and plan coherence (did the steps follow logically?) independently from task completion. Use end-state success only as the top-line number.

**2. Run LLM-as-judge with discipline.** Don't just "ask if it's good." Design explicit rubrics with 3-5 point scales, few-shot examples of each score band, and structured JSON outputs that require the judge to cite evidence before scoring. Calibrate the judge against human annotations on a 50-100 sample golden set before shipping. Apply pairwise comparison (A vs B on the same input) to reduce positional bias.

**3. Set per-dimension CI gates, not aggregate scores.** Block deployment if error recovery drops below 80%, tool selection falls below 85%, or any dimension regresses by more than 5 points from baseline. An agent that scores 72/100 overall is shippable; one that drops from 92→68 on tool selection is not.

**4. Build regression datasets from production failures.** Every production failure is a test case you couldn't have invented. Convert the failure trace into a structured test: real input, expected recovery behavior, and the dimension that failed. 20-50 high-signal production-failure cases are more valuable than 500 synthetic ones.

**5. Use public benchmarks as floor checks, not targets.** SWE-bench (87.6% top score on real GitHub issues), WebArena (68.7% on realistic browser tasks), and GAIA set the baseline that decent agents should clear. Your production distribution is not these benchmarks. Calibrate your eval against your actual user input distribution, not published leaderboards.

**6. Instrument traces end-to-end.** Log every tool call, argument, observation, and reasoning step. Metrics tell you something went wrong; traces tell you why. LangSmith, Phoenix (Arize), or Braintrust give you trajectory-level visibility with eval integration. Without trace data, your regression suite is flying blind.

## Evidence

- **HN Show: Agent Evaluation Platform (2025):** Open-source reference platform for multi-provider LLM-as-judge scoring, regression tests, A/B benchmarks, and safety checks — implements the CI-gate pattern with per-dimension thresholds across OpenAI, Anthropic, and Gemini evaluators — [GitHub](https://github.com/josephsenior/agent-evaluation-platform)
- **InfoQ: Evaluating AI Agents in Practice (2026):** "Agents are systems, not models — evaluate them accordingly. Single-turn accuracy metrics (BLEU, ROUGE) don't capture how agents fail in practice. Hybrid evaluation is non-negotiable: combine automated scoring with human judgment for tone, trust, and contextual appropriateness" — [InfoQ](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **Future AGI: Definitive Guide to Agent Evaluation (2026):** The compound error math — 95% per-step × 8 steps = ~66% end-to-end success — is why teams ship agents that pass per-turn eval and tank in production. Six dimensions: tool selection, argument extraction, result utilization, error recovery, plan coherence, task completion — [Future AGI](https://futureagi.com/blog/definitive-guide-ai-agent-evaluation-2026)
- **NVIDIA Technical Blog (2026):** Model eval (MMLU, GSM8K, HumanEval) answers "is the engine powerful enough?" Agent eval (GAIA, SWE-bench, WebArena) answers "can this system reliably execute workflows?" — these are different questions requiring different methodologies — [NVIDIA](https://developer.nvidia.com/blog/mastering-agentic-techniques-ai-agent-evaluation/)
- **Clawfficer Blog: Production Eval Framework (2026):** "Imperfect evals you run on every PR are more valuable than perfect evals you run once a quarter" — the case for starting eval infrastructure on day one even with rough rubrics — [Clawfficer](https://clawfficer.com/blog/llm-evaluation-evals-framework.html)
- **Zylos Research: LLM-as-Judge Patterns (2026):** The evolution from "ask GPT-4 if this is good" to disciplined methodology with calibration protocols, bias taxonomies, rubric engineering standards, and trajectory-specific scoring — [Zylos](https://zylos.ai/en/research/2026-05-26-llm-as-judge-agent-evaluation-patterns/)
- **Arthur.ai Column (2026):** The production-failure-to-regression-test pipeline: failure trace → test case → golden dataset → CI gate — 20-50 high-signal production cases outperform 500 synthetic ones — [Arthur](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)

## Gotchas

- **Aggregate scores hide dimension-level regressions.** An agent can score 78/100 overall and still have error recovery drop from 91→52 — aggregate noise cancels; per-dimension thresholds catch it
- **Judge bias is real and systematic.** Positional bias (A vs B preference), verbosity bias (longer answers score higher), and self-preference bias (GPT-4 scoring GPT-4 outputs more favorably) all distort LLM-as-judge scores. Pairwise comparison and judge calibration against human ground truth are not optional
- **Public benchmark saturation.** SWE-bench top scores are inflated by harness-specific scaffolding that doesn't transfer to production environments. Treat benchmark gains as necessary-but-not-sufficient evidence
- **Eval data drift.** Your eval dataset captures the input distribution of 3 months ago. User queries evolve. Rebaseline expected final answer fields periodically and monitor distribution shift between eval inputs and live traffic
