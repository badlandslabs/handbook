# S-2064 · The Trajectory Scoring Stack — When Your Agent Looks Correct but Decides Wrong

Your agent completes the task. The final answer is right. You ship it. Three weeks later a production incident reveals it was taking the wrong tool at step 3, compensating by over-correcting at step 7 — a pattern that held in demos because the demo inputs happened to be forgiving. You had no test catching this because your evaluation scored the answer, not the path. The failure was invisible.

## Forces

- **Final-answer scoring misses how agents fail.** Agents make multi-step decisions. A wrong tool at step 2 can be papered over by right-enough recovery at step 6 — and the final output looks fine. Trajectory-level failures are systematically invisible to output-only scoring. Teams report 20–40% of regressions are missed by answer-only evaluation.
- **Offline evals go stale against live traffic.** A supermajority of YC agent builders report that offline evaluation suites under-deliver because production traffic distribution shifts every day. The moment you ship, the test suite measures a world that no longer exists. The mechanism is structural, not a tooling flaw.
- **Benchmarks reward the wrong thing.** SWE-Bench grades verifiable artifacts. tau-bench grades against database state. They measure orthogonal capabilities — a high score on one predicts almost nothing on another. More critically, both reward correct answers, not correct *paths*. Agents that ace benchmarks routinely fail in production because production imposes structural constraints benchmarks don't measure.
- **Constraint decay is real and universal.** The "Constraint Decay" study (arXiv 2605.06445, Dente et al., May 2026) systematically tested LLM coding agents on multi-file backend generation with structural constraints. Assertion pass rate dropped an average of 30 percentage points from unconstrained to fully-specified tasks — a 40% relative capability loss. The benchmark score said the agent was capable. The structural requirement revealed it wasn't.

## The Move

Score trajectories, not answers. This means instrumenting the agent to emit per-step data, building a scoring rubric across the 6 evaluation dimensions, running offline regression suites in CI, and deploying a parallel per-turn classifier in production.

**The 6 evaluation dimensions (any agent):**
- **Tool selection** — Did the agent pick the right tool, or correctly call none? Wrong tool is the most common catastrophic failure.
- **Argument extraction** — Are the extracted arguments schema-valid and semantically correct? Right tool, wrong format is nearly as dangerous as wrong tool.
- **Result utilization** — Did the agent use the tool's payload, or substitute model knowledge? Hallucinated numbers often come from ignoring the retrieval result.
- **Error recovery** — Did the agent retry, fall back, or escalate on failure? Infinite retry loops and silent success-on-failure are the two dominant error-handling failure modes.
- **Plan coherence** — Does the agent's step sequence follow from the previous step's output? Breaks in coherence compound across steps.
- **Task completion** — Did the agent finish the task correctly? This is the only dimension traditional eval captures.

**Build a two-layer production stack:**

*Layer 1 — CI gate (offline, reproducible):*
- Run DeepEval with trajectory-scoring metrics on every PR. Test each of the 6 dimensions independently; gate on per-dimension thresholds, not an aggregate score. An aggregate that passes while tool selection scores 40% is a false negative.
- Use tau-bench (or tau2-bench for multi-agent) to benchmark against ground-truth database state on customer service and tool-use scenarios.
- Include adversarial test cases: null values, Unicode names (O'Brien, José), malformed inputs, rate-limited APIs, empty retrieval results.

*Layer 2 — Production monitoring (per-turn, live):*
- Deploy a lightweight per-turn classifier on a sample of live traffic. Score tool selection, argument extraction, and error recovery per turn — not per task.
- Compare production traffic scores to the offline CI baseline. A gap between offline and online scores on any dimension is an early warning that the offline suite has gone stale.
- Log every trajectory with trace IDs. Store inputs, tool calls, payloads, and final outputs. This is the corpus you use to build next quarter's offline test suite.

**CI gate: per-dimension thresholds beat aggregates.** A single aggregate score masks which dimension failed. Set minimum thresholds per dimension (e.g., tool selection ≥ 0.85, error recovery ≥ 0.70) and fail the gate if any dimension drops below threshold — even if the aggregate passes.

**Use LLM-as-judge carefully.** It's useful for trajectory coherence and final-answer scoring on a sample. It fails for: tool-call argument correctness (can't verify schema), error recovery quality (can't observe the alternative), and anything requiring ground-truth state. Calibrate against human labels before trusting it on production gates.

## Evidence

- **Research paper:** "Constraint Decay: The Fragility of LLM Agents in Backend Code Generation" — systematic study showing 30pp average drop in assertion pass rate from unconstrained to fully-constrained multi-file code generation tasks (arXiv 2605.06445, Dente et al., May 2026) — https://arxiv.org/abs/2605.06445
- **Practitioner guide:** The Definitive Guide to AI Agent Evaluation (2026) — six-dimension rubric, 4-D trajectory scoring, CI gate architecture, structural argument for per-dimension thresholds over aggregate scores — https://futureagi.com/blog/definitive-guide-ai-agent-evaluation-2026
- **Survey of evaluation frameworks (2026):** "AI Agent Evaluation (2026)" — compares LangSmith, Braintrust, DeepEval, Arize Phoenix, RAGAS, OpenAI Evals, and Galileo on trajectory scoring, offline vs online capability, and LLM-as-judge limitations. Notes a supermajority of YC agent builders report offline evals under-deliver due to structural staleness — https://www.morphllm.com/ai-agent-evaluation
- **Practitioner discussion:** "Ask HN: How are you testing AI agents before shipping to production?" — real incident: prompt injection in a customer support agent processed a $47,000 fraudulent refund (January 2026); Gartner projection that over 40% of AI agent projects will fail by 2027, with inadequate evaluation as the primary cause — https://news.ycombinator.com/item?id=47325105
- **Tooling:** DeepEval — open-source framework for offline CI testing of agents and RAG systems with trajectory-level metrics; pytest-compatible; GitHub: https://github.com/confident-ai/deepeval
- **Tooling:** Braintrust — agent evaluation platform with trajectory tracing, per-span scoring, and A/B experiment support; Notion, Dropbox, Zapier, Coursera use it in production; https://www.braintrust.dev

## Gotchas

- **Output-only scoring produces false confidence.** An agent that takes the wrong path and arrives at the right answer by accident will pass output-only evaluation every time. You will not know it is one意外input away from a wrong answer.
- **Offline evals drift from production silently.** The test suite you wrote last quarter measures the distribution you had last quarter. Monitor the gap between offline and production scores per dimension. When the gap widens, rebuild the offline suite from production traces.
- **Benchmarks are floors, not ceilings.** SWE-Bench, tau-bench, and GAIA measure specific, verifiable capabilities. High benchmark scores do not predict performance under structural constraints (the Constraint Decay finding), under distribution shift, or on domain-specific edge cases your production traffic contains.
- **LLM-as-judge is not ground truth.** It works acceptably for trajectory coherence and final-answer scoring. It systematically fails for verifying tool-call arguments, evaluating error recovery alternatives, and anything requiring ground-truth state. Treat it as a signal, not a verdict.
