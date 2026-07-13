# S-1058 · The Production Eval Stack — When Your Evaluation Is a Spike and Your Production Is a Mystery

You run a prompt off a few examples, it looks good, you ship it. Weeks later you discover the agent has drifted — subtly favoring one class of answers it shouldn't, burning 3x the expected cost on a cluster of edge cases, silently failing on trajectories you never tested. The problem isn't that your agent broke. It's that you built an evaluation for launch day and never instrumented the system to keep measuring it after.

The production eval stack is the combination of grading approaches, metrics, and continuous measurement patterns that turn agent quality from a one-time judgment into an observable, auditable, improving system.

## Forces

- **Model benchmarks test the model; production evals test the system.** MMLU and HumanEval tell you about model capability — not about your specific tool bindings, prompt variants, or error recovery paths. An agent that scores well on benchmarks can still silently fail on your API surface.
- **A single pass/fail hides the trajectory.** If your eval only scores the final answer, you miss whether the agent got there through a hallucinated tool call, a dangerous action it recovered from, or a 40-step loop that burned budget without improving output.
- **Cost and quality are coupled but tracked separately.** Teams optimize for task success and ignore cost-per-task until the monthly bill reveals the agent has been retrying its way through failures at premium pricing.
- **Agent behavior drifts without versioned changes.** Prompt drift from downstream system changes, subtle RLHF shifts, or upstream model updates can degrade behavior weeks after deployment — invisible unless you have longitudinal measurement.
- **The three-grader problem.** Code-based graders are fast and objective but brittle. Model-based graders are flexible but non-deterministic. Human graders are the gold standard but expensive and slow. Most teams pick one and live with its failure mode.

## The Move

Build a layered evaluation system that uses each grader type for what it does well, and instrument the full lifecycle — from development through production — with metrics that track quality, cost, and drift together.

**Grader selection by use case:**

- **Code-based graders** for verifiable, structured outputs: tool call schema validation, JSON schema compliance, regex-match on expected values, unit-test assertions on returned data. Fast (milliseconds), cheap, deterministic. Use for anything where you can write an assertion.
- **Model-based graders (LLM-as-judge)** for subjective, open-ended quality: does this response answer the user's intent, is this explanation coherent, does this tone match brand guidelines. Run against the same model or a different one. Must be calibrated against human labels — an uncalibrated judge is worse than no judge because it gives false confidence.
- **Human graders** for calibration and edge cases: sample the top 5% of uncertain cases, use human labels to recalibrate the model grader, and validate safety-sensitive outputs. Run human eval on a rolling sample (e.g., weekly 50-case spot check) rather than on every release.

**Metrics that matter in production:**

- **Task success rate** — did the agent complete the task without escalation or fatal error. Not the same as output quality. An agent can succeed technically and deliver a confidently wrong answer.
- **Cost per task** — total inference cost including retries, tool calls, and fallback model invocations, divided by completed tasks. A rising cost-per-task with flat success rate signals the agent is burning budget without improving outcomes.
- **Span-level latency** — latency broken down by agent span (reasoning, tool calls, synthesis). Identifies which part of the pipeline is slow: a 45-second task may be 40 seconds of waiting on a database query and 5 seconds of LLM work.
- **Drift score** — compare the distribution of outputs (via embedding similarity or grader scores) on a fixed reference set over time. A sudden drop in drift score between Tuesday and Wednesday means something changed — a prompt edit, a model update, or a upstream data shift.
- **Trajectory quality** — score the full execution path, not just the final answer. Did the agent make unnecessary tool calls? Did it recover from errors? Did it stop at the right point? Trajectory scoring catches the failure modes that correct answers hide.

**Continuous evaluation loop:**

- Run the eval suite on every code change (pre-commit or CI gate). A hard regression on critical tasks should block deploy.
- Run a nightly or weekly production shadow eval: replay a sample of real user queries against the current agent and score them, but don't affect live users. Compare against baseline to catch drift.
- Maintain a **golden eval set** — 50-200 representative test cases that cover core functionality, known edge cases, and recent regressions. This set should evolve: remove cases the agent reliably solves, add cases from production failures.
- Instrument traces at the span level. Every tool call, every model invocation, every decision point should produce a trace event. Traces turn "the agent failed" into "the agent called the wrong API at step 7 after receiving an unexpected format from the search tool."

**CI/CD integration pattern:**

- Use pytest or similar test runners with an agent eval plugin (e.g., DeepEval, LangSmith). Define test cases as fixtures, run them in CI, gate on a minimum score threshold.
- Keep eval results as structured data (JSON), not just a pass/fail. Store them with the commit hash and model version so you can trace a regression to its cause.
- Distinguish **launch-time evals** (blocking gates before deploy) from **continuous monitoring** (non-blocking production observability). Teams that only run evals at launch quickly stop maintaining them.

## Evidence

- **Anthropic engineering guide on agent evals (Jan 2026)** establishes the three-grader taxonomy (code, model, human) and the Task/Trial/Grader framework. Recommends combining all three grader types based on what's verifiable, what's subjective, and what needs human calibration. Emphasizes that evals compound in value over an agent's lifecycle. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Prefactor practitioner guide (Jul 2026)** reports 62% of enterprises have agents live in production, but 74% of those agents get rolled back or shut down after launch. Identifies four production metrics that catch failures benchmarks miss: task success rate, cost per task, span-level latency, and drift score. Emphasizes that benchmarks test the model; production evals test the system. — [prefactor.tech/blog/agent-evaluation-in-production](https://prefactor.tech/blog/agent-evaluation-in-production-what-to-measure-and-how-to-prove-it)
- **AWS Labs Agent Evaluation framework (v0.4.1, 2025)** provides an open-source CLI and SDK for running standardized agent evaluations against Amazon Bedrock, SageMaker, and Q Business targets. Supports configurable evaluators (accuracy, safety, latency) and CI/CD integration. — [github.com/awslabs/agent-evaluation](https://awslabs.github.io/agent-evaluation)
- **Hacker News discussion on agent evals (Mar 2025)** surfaces the practitioner consensus: generic benchmarks (MMLU, HumanEval) are useful for model comparison but insufficient for production deployment. Custom task-specific evals are the main mechanism for evolving an agent toward production readiness. — [news.ycombinator.com/item?id=43244778](https://news.ycombinator.com/item?id=43244778)
- **CivBench long-horizon agent benchmark (HN, 2025)** — a benchmark for multi-agent economic simulations — finds that static benchmarks fail to predict long-horizon performance, and that cost per task is as important as raw performance when running agents for extended multi-step tasks. — [news.ycombinator.com/item?id=47152571](https://news.ycombinator.com/item?id=47152571)

## Gotchas

- **An uncalibrated LLM-as-judge is dangerous.** If you haven't validated your judge model against human labels on at least 50 cases, the judge's scores are approximately random relative to actual quality. Calibrate before you trust.
- **Task success rate without quality scoring hides confident failures.** An agent that returns a wrong answer with high confidence scores a "success" if you only measure whether it completed the workflow. Pair success rate with a quality or hallucination score.
- **Eval sets go stale.** Cases that the agent reliably solves should be retired; new failure cases from production should be added. An eval set that's not maintained for 6 months is measuring last quarter's agent, not today's.
- **Trajectory scoring is harder than output scoring but catches failures output scoring misses.** A correct answer achieved via a risky tool call, a hallucinated intermediate step, or an unsafe action should score lower than a correct answer achieved via a clean, auditable path — even if both produce the same final output.
- **Cost-per-task is the metric that surprises teams most.** An agent that escalates to a larger model on uncertain cases, or retries indefinitely on failures, can have a 5x higher cost-per-task than expected. Track it from day one.
