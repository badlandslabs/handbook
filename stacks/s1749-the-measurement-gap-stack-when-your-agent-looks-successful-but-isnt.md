# S-1749 · The Measurement Gap Stack — When Your Agent "Looks" Successful But Isn't

Your agent completes every task. Pass rate is green. Users aren't complaining. You ship it to production and three weeks later someone finds it was generating incorrect downstream data the whole time — because you were measuring whether it finished, not whether it was right. This is the measurement gap: agents that appear to work because you never checked what they were actually doing.

## Forces

- **Trajectory and outcome are different questions** — an agent can reach a correct answer via a dangerously wrong path, or reach a wrong answer via a reasonable path, and most teams only measure one
- **Agents are non-deterministic** — running the same task twice can produce different tool sequences and different outcomes; a single test pass means nothing
- **Standard benchmarks are contaminated** — SWE-bench Verified inflates scores by 30+ percentage points due to training data leakage, making them useless for honest capability assessment
- **LLM-as-Judge has systematic biases** — position bias, verbosity bias, and self-preference can make judges systematically wrong; teams trust them without calibration
- **Traditional APM doesn't map** — tools built for stateless request/response can't capture multi-step agent trajectories, tool call sequences, or state mutations

## The move

Measure both dimensions with a layered evaluation system:

1. **Outcome evaluation first** — executable post-condition checks (run the tests, query the DB, verify the file exists). These are ground truth, not approximation.

2. **Trajectory evaluation second** — trace the full execution path. Did it call the right tools? In the right order? With the right arguments? Did it loop unnecessarily or get stuck?

3. **Golden dataset regression suite** — build a curated set of inputs with known-good outputs. Version-control it. Run it on every code change that touches agent behavior (prompt updates, model swaps, tool changes). This is your regression firewall.

4. **LLM-as-Judge with calibration** — use it for the things rules can't capture (subjective quality, tone, relevance), but calibrate against human judgments first. Target ≥0.80 Spearman correlation before trusting scores. Pairwise comparison outperforms single-score grading on noisy tasks.

5. **pass@k vs pass^k for reliability** — report both. pass@k measures whether an agent succeeds at least once in k attempts (capability). pass^k measures whether it succeeds every time (reliability). An agent with 75% per-trial reliability has only a 42% chance of succeeding four times in a row.

6. **CI/CD integration as a merge gate** — evaluation without enforcement is a suggestion box. Set pass-rate thresholds and block merges that regress quality.

## Evidence

- **Gartner forecast (June 2025):** Over 40% of agentic AI projects will be canceled by end of 2027, citing inadequate evaluation as a root cause alongside cost and unclear ROI. Only 1 in 10 agentic use cases reached production at all. — [Gartner Press Release, June 25, 2025](https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027)

- **Amazon Bedrock AgentCore (2025):** Amazon's evaluation workflow runs four-step automated assessment: dataset construction, execution, metrics computation, and analysis. Their AI Agent Evaluation Library provides systematic trajectory vs. outcome measurements. — [AWS Machine Learning Blog](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/)

- **SWE-bench contamination study:** OpenAI demonstrated SWE-bench Verified scores are inflated — Claude Opus 4.5 scores 80.9% on Verified but only 45.9% on SWE-bench Pro (a 35-point gap from training contamination). More reliable alternatives: SWE-bench Live, WebArena, AgentBench, GAIA. — [Paperclipped, March 2026](https://www.paperclipped.de/en/blog/ai-agent-benchmarks-swe-bench-webarena)

- **Trainly observability startup (HN, July 2026):** "The hardest part of selling observability for AI agents has been getting people to believe they have a problem. 'My agent works fine' is the universal answer, right up until you actually look at the traces." Their 72-hour trace audit consistently surfaces: silent tool failures, retry loops, latency outliers, and behavioral weirdness that outcome-only metrics miss. — [Hacker News Show HN](https://news.ycombinator.com/item?id=47867157)

- **Open-source evaluation stack:** A GitHub repo (2026) using LangGraph + LangSmith + pytest + golden dataset evaluation in CI demonstrates the production pattern: input guardrails → agent execution → output guardrails → golden dataset comparison → observability. Pass rate is a CI merge gate. — [GitHub: codeninja2022-create/production-grade-ai-agent](https://github.com/codeninja2022-create/production-grade-ai-agent)

## Gotchas

- **Outcome-only evaluation is a false安全感** — green pass rates mean the agent reached some end state, not that the end state was correct
- **Golden datasets require maintenance** — stale golden datasets are worse than none because they create false confidence; treat them like tests and update them when requirements change
- **LLM judges need grounding** — an uncalibrated LLM-as-Judge will favor longer answers (verbosity bias) and prefer its own output style (self-preference bias); always run human calibration checks first
- **Trajectory logging is not free** — storing full execution traces for every agent run is expensive; sample strategically (all failures, stratified sample of successes) rather than trying to log everything
- **Model updates invalidate evals** — swapping a model or changing a system prompt requires re-running the full golden dataset; this catches regressions but also means every model change has a non-trivial verification cost
