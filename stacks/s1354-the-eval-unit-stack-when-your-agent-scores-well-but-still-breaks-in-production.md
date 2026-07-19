# S-1354 · The Eval Unit Stack

When you reach for this: Your agent passes your eval suite but users still complain. Your benchmark says 90% — but your incident log says something else. You don't know which layer is failing: the model, the scaffold, or the environment.

## Forces

- **Most agent failures look like software bugs, not model bugs** — broken URLs in tool calls, localhost calls in cloud, missing API keys, external services blocking requests. Benchmark-style eval catches none of these.
- **Single-turn accuracy metrics (BLEU, ROUGE) don't capture trajectory quality** — an agent that answers correctly but takes 20 wrong steps before getting there isn't good, even if the final answer is right.
- **LLM-as-judge needs human calibration** — an agent grading itself will be overgenerous unless the rubric is specific and the judge is isolated from the agent's context.
- **Harness changes that help one model can hurt another** — SWE-CI benchmark results show prompt or harness improvements on Claude can degrade GPT-5 performance. Eval must isolate scaffold quality from model quality.
- **The eval loop is the product, not the score** — a passing eval that doesn't feed back into improvement is theater.

## The move

Treat agent eval as a five-stage closed loop, not a one-time benchmark:

1. **Define the unit as the trajectory, not the answer.** Measure task completion end-to-end, then drill into step-level metrics: tool call correctness, argument correctness, plan adherence, step efficiency.

2. **Build a golden dataset from production traces.** Log real inputs, then have human raters label success/failure. This is your ground truth. Start simple — binary: did the agent meet the user's goal? One yes/no per trajectory.

3. **Gate every PR with a CI eval.** Per-dimension assertions (tool correctness, latency, cost per task, token efficiency) on the same rubric as offline eval. Non-zero exit on any failing axis.

4. **Attach the eval rubric to live traces in production.** Same scoring rubric applied as a label on OpenTelemetry spans. Catch regressions before users report them.

5. **Run error feed clustering on failing traces.** Cluster failures by root cause axis, write a 4-D score + immediate_fix, then optimize the agent against the expanded dataset.

**Measure these six dimensions at trajectory level:**

| Dimension | What it catches |
|-----------|----------------|
| Task completion | Did the agent finish the goal? |
| Tool correctness | Right tool, right call? |
| Argument correctness | Right parameters? |
| Step efficiency | No wasted loops? |
| Plan quality | Coherent reasoning chain? |
| Recovery quality | Graceful handling of failures? |

## Evidence

- **HN post:** Practitioner evaluating a production agent found most "eval failures" were system bugs — broken URLs in tool calls dropped score to 22, localhost calls in cloud got stuck at 46, missing API keys caused silent failures. Concluded eval loops for agents should look more like software testing than benchmarking — repeatable test suites, clear pass/fail, fast feedback. — [HN #47416033](https://news.ycombinator.com/item?id=47416033)

- **InfoQ article:** "Agents are systems, not models — evaluate them accordingly." Key lessons: hybrid evaluation (automated + human judgment) is non-negotiable; operational constraints (latency, cost, token efficiency, tool reliability) are first-class evaluation targets, not afterthoughts. — [InfoQ, March 2026](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

- **SWE-CI benchmark (arXiv):** 100 real-world tasks spanning 233 days and 71 commits of evolution history. Claude Opus 4.6 scored 0.71; GPT-5.2 scored 0.23. Critically: prompting changes that massively boosted one model degraded another — proving that harness quality and model quality must be evaluated independently. — [HN #47295537 / arXiv:2603.03823](https://news.ycombinator.com/item?id=47295537)

- **Confident AI (DeepEval):** Agent eval requires both end-to-end task completion scoring and component-level checks on tools, arguments, and handoffs. LLM-as-judge must be calibrated against human rubrics on sample traces; metric-green/user-red cases are common without this. — [Confident AI Blog, April 2026](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)

- **KDD 2025 Tutorial:** Two-dimensional eval taxonomy: objectives (behavior, capability, reliability, safety) × process (interaction modes, benchmarks, metric computation, tooling). Enterprise-specific challenges include role-based data access, reliability guarantees, dynamic long-horizon interactions, and compliance. — [SAP-samples/llm-agents-eval-tutorial](https://sap-samples.github.io/llm-agents-eval-tutorial)

## Gotchas

- **Eval-green / production-red** — LLM-as-judge is overgenerous without human calibration on sample traces. Always validate your judge against a human-labeled subset before running at scale.
- **Benchmark score ≠ system reliability** — public benchmarks (GAIA, WebArena, OSWorld) measure model capability, not your harness quality. Use them for model selection; use your own golden dataset for regression prevention.
- **Measuring once is not measurement** — stochastic models mean a single run is unreliable. Run each eval scenario 3–5 times and report variance, or gate on median with a budget.
- **Tool failures are eval failures** — if your eval doesn't capture tool call outcomes, environment errors, and API response codes, you're measuring the happy path, not production reality.
- **Harness changes need independent eval** — any change to prompts, retry logic, or execution policy should be eval'd against all major models, not just the one you shipped.
