# S-2760 · The Measurement Stack — When Your Agent Is in Production and Nobody Knows If It's Working

Your agent handles 300 support tickets a day. But nobody can tell you whether it does them well. Your dashboard shows uptime and token count. Nobody knows if it's actually solving problems or confidently rearranging failures. This is the agent evaluation problem: the thing that's hardest to measure is the thing that matters most — whether the agent actually accomplished what it was supposed to do.

## Forces

- **Agents are systems, not models — but teams measure them like models.** Agents plan, call tools, maintain state, and adapt across turns. Single-turn accuracy metrics (BLEU, ROUGE) and classical NLP benchmarks don't capture how agents fail in practice — they just measure output similarity, not task completion.
- **The most important qualities are the hardest to auto-measure.** Task success rate, graceful error recovery, and consistency under variability matter most. They also require evaluating multi-turn trajectories, not just final outputs. The metric you want (did the agent accomplish the goal?) is the hardest to grade automatically.
- **Eval quality compounds, but teams treat it as an afterthought.** Teams building agents without evals get stuck in reactive loops — catching failures only in production, where fixing one regression creates two others. Evals make problems visible before users see them, and their value grows over an agent's lifecycle.
- **The grader is as important as the agent.** An LLM-as-judge can be confidently wrong. If you don't calibrate it against known examples and spot-check with humans, your measurement system misleads you more than if you'd measured nothing at all.

## The Move

Build a layered evaluation stack that runs different checks at different stages. The layers are not sequential — they run in parallel and feed into each other.

**Layer 1 — Unit evals (fast, deterministic):**
- Pattern matching for exact outputs: JSON schema validation, error code matching, return type checks
- Deterministic logic for anything with a ground-truth answer: "does the extracted email match the known customer email?"
- Run these on every PR. Cost: cents. Latency: milliseconds. Purpose: catch regressions before merge.

**Layer 2 — End-to-end / conversation evals (moderate cost, richer signal):**
- Evaluate full agent trajectories: did the agent accomplish the goal? how did it behave along the way?
- Use LLM-as-judge to score behavioral dimensions: task completion, tool call appropriateness, recovery quality, response groundedness
- Collect assertions (individual checks) into a grader. One grader covers multiple dimensions.
- Run these on deployment candidate builds. Cost: dollars per eval run. Latency: seconds to minutes. Purpose: catch behavioral regressions that unit evals miss.

**Layer 3 — Corpus-level evals (batch, longitudinal):**
- Aggregate results across 50–100+ test tasks to detect trends
- Track pass rates, failure categories, and cost-per-task over time
- Use to build and maintain a regression dataset that grows as new failure modes appear
- Run on schedule (nightly or weekly). Purpose: understand trajectory, not individual correctness.

**Layer 4 — Production sampling (real behavior, no synthetic data):**
- Sample a percentage of live interactions and run evals against them
- Catch failure modes that only appear with real users and real data
- Combine with distributed tracing (OpenTelemetry) for full trajectory visibility
- Purpose: close the eval-production gap, which is where most real failures hide.

**On grader design:**
- A grader contains one or more assertions (checks). One grader can cover task success, groundedness, and safety — you don't need separate graders for each dimension.
- LLM-as-judge achieves over 80% agreement with human evaluators when well-designed (MLflow benchmarking, 2025). The remaining ~20% gap requires spot-check calibration.
- Calibrate your judge against known examples before scaling it: run it on 10–20 human-graded cases, measure agreement, then iterate the judge prompt.

## Evidence

- **Anthropic Engineering (Jan 2026):** Defines the four grader types used across their deployments — pattern matching (fast regex/string checks), deterministic (exact ground-truth), LLM-as-judge (model grades trajectory quality), and corpus-level (aggregate across runs). Key quote: "The capabilities that make agents useful — autonomy, intelligence, and flexibility — also make them harder to evaluate. Evals make problems visible before they affect users, and their value compounds over the lifecycle of an agent." — [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **InfoQ (Mar 2026):** Found that LLM-as-judge achieves over 80% agreement with human evaluators in production settings when the judge is well-designed. Identified four key evaluation dimensions for agents: task completion rate, behavioral quality (tool call appropriateness, recovery), operational metrics (latency, cost per task, token efficiency), and safety/policy compliance. Noted that classical NLP metrics (BLEU, ROUGE) "don't capture how agents fail in practice." — [Evaluating AI Agents in Practice: Benchmarks, Frameworks, and Lessons Learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

- **Microsoft Agent Framework (2025):** Built evaluation as a first-class primitive with three core types — `EvalItem` (single conversation to evaluate), `Evaluator` (provider that scores, supporting local checks or cloud Foundry), and `EvalResults` (aggregated pass/fail with per-item detail). Design principles: provider-agnostic (works with any model), zero-friction (minimal code from agent to eval results), progressive disclosure (simple scenarios need near-zero code, advanced scenarios build on same primitives). — [Evaluation | Microsoft Learn](https://learn.microsoft.com/en-us/agent-framework/agents/evaluation)

- **MLflow (2025):** LLM-as-judge evaluation framework with built-in judges for correctness, relevance, groundedness, safety, and helpfulness; custom judge creation; automatic tracking of every eval run across model versions, prompt variants, and system configurations. Tracks all runs in MLflow for regression comparison. — [LLM-as-a-Judge Evaluation | MLflow](https://mlflow.org/llm-as-a-judge)

- **arXiv survey (Jul 2025):** "Evaluation and Benchmarking of LLM Agents: A Survey" — proposes Evaluation-driven Development (EDD): making evaluation an integral part of the agent development cycle, with continuous offline evaluation during development and online evaluation after deployment. Proposes an AgentOps component that monitors production performance and feeds insights back to developers. — [arXiv:2507.21504](https://arxiv.org/abs/2507.21504)

## Gotchas

- **Measuring only the final output, not the trajectory.** If your agent makes 6 useless tool calls and then outputs something plausible, an outcome-only eval scores it a pass. A trace-based eval catches the waste. You need trajectory visibility — full transcript recording — to catch behavioral failures that are invisible in the final output.

- **Building evals once and never updating them.** As the agent improves or the environment changes, your eval dataset becomes stale. Stale evals measure past failures, not current behavior. The regression dataset needs to grow continuously: every production failure that wasn't caught is a candidate for a new eval case.

- **Treating production evaluation as optional.** The eval-production gap is where most real failures hide. Synthetic test cases can't cover the full distribution of real user inputs. Production sampling with LLM-as-judge on real trajectories is not optional for agents that matter — it's the only way to know what the agent is actually doing.

- **An uncalibrated grader is a false signal.** A poorly designed LLM-as-judge can be confidently wrong, and it will be consistently wrong in the same ways. Before scaling, run the judge against 10–20 human-graded examples, measure agreement, and iterate. Measure grader agreement periodically in production too — grader drift happens.
