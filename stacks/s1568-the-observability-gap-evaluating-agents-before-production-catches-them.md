# S-1568 · The Observability Gap: Evaluating Agents Before Production Catches Them

You have dashboards full of agent traces. You can replay every tool call. You know exactly what the agent did. You have no idea if it was right.

## Forces

- **Watching ≠ grading.** 89% of teams with production agents have observability (LangChain State of Agent Engineering 2026, n=1,340). Only 52% run offline evaluations. Teams are watching their agents work without grading whether the work is correct.
- **Agents break the test harness.** Unlike single-turn LLM calls, agents are non-deterministic, multi-step, tool-dependent, and environment-sensitive. Standard unit tests don't apply. Integration tests are flaky. Human review is slow.
- **Eval quality compounds.** Every eval you write pays dividends across model swaps, prompt changes, and infrastructure upgrades. Without evals, you can't safely change anything without cross-your-fingers deploys.
- **Correctness vs. trajectory are different questions.** An agent can reach a correct answer via a broken process, or produce a wrong answer from a perfectly logical chain. Both need measurement, and they require different evaluation approaches.

## The move

Build an eval pipeline before you trust the agent. Start with outcome-only evals (did it solve the task?), then layer in trajectory evals (how did it get there?). Treat evals as code: version them in git, gate deploys on them, run them in CI.

### Core anatomy (Anthropic, Jan 2026)

- **Task** (test case): a single eval with defined inputs and pass/fail criteria
- **Trial**: one run of a task — run each task 3-5 times to account for non-determinism
- **Grader**: logic that judges whether a trial passed — can be code, rule-based, or LLM-as-judge

### What to measure (MLMastery, Feb 2026)

- **Correctness** — did the agent produce the right output?
- **Efficiency** — how many steps, tool calls, or tokens to get there?
- **Safety** — did it avoid harmful actions or outputs?
- **Reliability** — does it pass consistently across multiple trials?

### Tool-call evaluation requires its own metrics (Cameron Wolfe, 2026)

- **Invocation accuracy** — correct decision to call or skip a tool
- **Selection accuracy** — correct tool chosen from available options
- **Structural accuracy** — correct tool call structure and argument schema
- **Trajectory accuracy** — correct sequence of tool calls end-to-end

### Structural split: eval vs. tracing

Teams conflate observability ("what did the agent do?") with evaluation ("was it right?"). These require different tooling and serve different purposes. An agentmodeai.com analysis (May 2026) identifies this as the load-bearing split: **observability platforms** (Langfuse, Arize Phoenix) answer "what happened," while **evaluation platforms** (DeepEval, Braintrust, Patronus) answer "was it correct."

### The three eval layers in practice

1. **Offline (pre-deploy):** synthetic dataset generation + LLM-as-judge grading. Run in CI to gate merges. Anthropic recommends generating synthetic tasks from a "task seed" using an LLM to expand into test cases — fast, scalable, covers edge cases humans forget.
2. **Shadow mode (staging):** run production traffic through eval pipeline without acting on results. Catch regressions in real scenarios before they hit users.
3. **Online (production):** sample-based evaluation of live agent runs. Route failures to human review. Track pass rates over time.

### Platform patterns

- **Output.ai (GrowthX, Show HN Mar 2026):** Built from 500+ production agents. Core belief: "prompts are code — versioned in git, reviewed in PRs, tested before shipping." Filesystem-first design: evals live next to the workflow they test, not in a separate SaaS dashboard.
- **DeepEval:** pytest-compatible agent eval framework. Write evals as Python test cases, run them in CI, gate on pass rate.
- **Braintrust:** rapid prompt iteration with eval backing. Best for teams that need to compare multiple prompt/model combinations quickly.
- **LangSmith:** deep LangChain integration, full trace + eval pipeline. Best if already invested in LangChain.

## Evidence

- **LangChain State of Agent Engineering survey (n=1,340, Nov–Dec 2025):** 57.3% of teams have agents in production. 89% have observability. Only 52% run offline evaluations. Quality cited as top production blocker at 32%, ahead of security (24%) and latency (20%). — [https://www.langchain.com/state-of-agent-engineering](https://www.langchain.com/state-of-agent-engineering) + [https://www.paperclipped.de/en/blog/state-of-agent-engineering-2026](https://www.paperclipped.de/en/blog/state-of-agent-engineering-2026)
- **Anthropic Engineering blog (Jan 9, 2026):** "Demystifying evals for AI agents" — task/trial/grader taxonomy, synthetic data generation for evals, LLM-as-judge pattern, trajectory evaluation for multi-step agents. — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **MachineLearningMastery (Feb 6, 2026):** "Agent Evaluation: How to Test and Measure Agentic AI Performance" — four-pillar framework (correctness, efficiency, safety, reliability), distinction from LLM eval. — [https://machinelearningmastery.com/agent-evaluation-how-to-test-and-measure-agentic-ai-performance/](https://machinelearningmastery.com/agent-evaluation-how-to-test-and-measure-agentic-ai-performance/)
- **Output.ai Show HN (Mar 2026):** OSS framework from 500+ production agents. "Prompts are code" principle, filesystem-first eval design, durable execution. — [https://news.ycombinator.com/item?id=47676157](https://news.ycombinator.com/item?id=47676157)
- **Cameron Wolfe Substack (2026):** Agent evaluation taxonomy including tool-calling metrics (invocation, selection, structural, trajectory accuracy). — [https://cameronrwolfe.substack.com/p/agent-evals](https://cameronrwolfe.substack.com/p/agent-evals)
- **agentmodeai.com (May 2026):** Comparison of DeepEval, Braintrust, LangSmith, Patronus. Structural argument: observability vs. evaluation are separate procurement decisions. — [https://agentmodeai.com/agent-eval-frameworks-deepeval-braintrust-langsmith-patronus/](https://agentmodeai.com/agent-eval-frameworks-deepeval-braintrust-langsmith-patronus/)

## Gotchas

- **Running evals once is not enough.** Eval pass rates fluctuate with model versions, prompt changes, and upstream API changes. Track them over time, not just at deploy time.
- **LLM-as-judge has biases.** LLMs are generous graders and favor longer, more detailed answers. Calibrate your grader against human-labeled examples before trusting it.
- **Synthetic eval data overfits to the model.** If you generate eval tasks using the same model you're evaluating, the eval will be too easy. Mix synthetic with real production-failure cases.
- **Trajectory length ≠ correctness.** A 20-step agent that gets the right answer is worse than a 3-step agent that does the same thing if the 20-step one is fragile. Measure both separately.
