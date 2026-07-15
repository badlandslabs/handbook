# S-1129 · The Black-Box Stack — How to Measure an Agent You Can't See Inside

Your agent just completed 200 tasks. You know what it said. You don't know if it opened the right files, called the right tools in the right order, left the database in a valid state, or spent $12 or $400 doing it. Traditional software testing has no answer — the agent is non-deterministic, tool-using, and state-changing. This is the measurement problem: you need to know if your agent is working, but the things that determine "working" are spread across a multi-step trajectory you can't inspect directly.

## Forces

- **The final-message fallacy.** The agent's last output is the least reliable indicator of correctness. The agent may arrive at a correct answer through the wrong process — and you'll never catch it if you only check the output.
- **Agents are stochastic; one pass proves nothing.** Unlike a deterministic function, an agent can succeed once and fail ten times on the same input. A single trial gives you a coin flip, not a measurement.
- **Lab scores lie by 37%.** Enterprise data shows a 37% performance gap between benchmark scores and production outcomes. Your eval suite is not the real world.
- **LLM judges are biased critics.** Same-family models (GPT evaluating GPT, Claude evaluating Claude) show systematic self-favoritism. But using a different model introduces its own inconsistency. Neither approach is neutral.
- **Cost per task is invisible by default.** Without per-task cost tracking, you can't tell if your 92% accurate agent is 10x more expensive than an 87% accurate one that costs $0.04 per task.

## The move

The core discipline: evaluate the trace, not just the output. Check what the agent changed, not just what it said. Measure cost and reliability together, not separately.

### Build the vocabulary first

Anthropic's eval taxonomy (Jan 2026) gives you the components you need before you write a single test:

| Concept | What it is | Why it matters |
|---|---|---|
| **Task** | Single test with inputs and success criteria | The unit of measurement |
| **Trial** | One attempt at a task | Multiple trials = real signal |
| **Transcript / trace** | Full record: outputs, tool calls, reasoning | The artifact you actually inspect |
| **Outcome** | Final environment state after the trial | Not what the agent said — what changed |
| **Grader** | Logic that scores the transcript | Contains the assertions |
| **Eval harness** | Infrastructure that runs evals end-to-end | The CI/CD equivalent |

### Ground truth in environment state, not model output

The highest-signal check is always the state of the world after the agent runs: did the database record get written correctly? Is the file created? Does the API call actually exist in the logs? Does the browser show the correct page state? This is outcome-based evaluation, and it is more reliable than any LLM judge.

When environment checks aren't feasible (the task is genuinely subjective), fall back to trajectory checks: did the agent call the right tools in the right sequence? Were the right parameters passed? Did it stop at the right point?

Reserve final-message grading for the last resort. An agent that says "ticket created" but didn't create a ticket has failed — even if you graded it based on what it said.

### Run multiple trials; report the distribution

Agents are stochastic. A task that "passed" on one run might fail on nine others. Run a minimum of 5 trials per task before claiming a pass rate. Report both the mean and the variance — a 90% pass rate with ±5% variance is a different system than 90% with ±40%.

Enterprise teams target **>85% task completion rate without human intervention** as the primary operational metric. Below that, the agent creates more review work than it saves.

### Combine grading channels; don't rely on one

No single grading method is reliable on its own:

- **Deterministic checks** (schema validation, regex, exact-match assertions) — fast, reproducible, cheap. Brittle: they fail to credit creative valid solutions.
- **LLM judges** — flexible, handles nuance. Problematic: same-family bias, non-determinism, calibration drift. If you use them, use a different model family from the agent's underlying model.
- **Human spot-checks** — ground truth, but expensive and slow. Reserve for high-stakes tasks or calibrating your other graders.

The right approach: deterministic checks as the floor, LLM judges for process quality (was the reasoning sound?), human review for ambiguous or high-value tasks.

### Separate capability evals from regression evals

These are different jobs:

- **Capability evals** measure whether the agent can do something new. They push the frontier. Use challenging tasks, measure ceiling performance.
- **Regression evals** measure whether the agent still does what it did last week. They protect existing behavior. Run on every commit. Use a stable suite.

Mixing them leads to either over-tuning to old behavior (stalling capability progress) or breaking production with every new feature (stalling reliability).

### Track cost per task from day one

Cost per task is not a second-order concern. Enterprise data shows **50x cost variation** for comparable accuracy across different agent configurations. A Pareto-efficient agent — one that achieves near-peak accuracy at a fraction of the cost of the highest-accuracy configuration — is usually the right production choice. Track tokens per task, tool calls per task, and estimated cost per task alongside accuracy. An agent that scores 94% accuracy but costs 10x more than an 89% alternative is a worse production system.

### Build the eval harness before you deploy

Eval infrastructure is not a post-launch concern. Without it, you ship blind. The minimum viable eval stack: a way to replay tasks, record traces, run graders automatically, and track pass rate over time. Without this, every production incident is a surprise.

## Evidence

- **Anthropic Engineering guide:** Breaks agent eval into task/trial/transcript/outcome/grader/harness concepts. Emphasizes outcome-based grading over final-message grading, multiple trials for stochastic systems, and multi-channel grading combining deterministic checks with model-based judges. — [Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) (Jan 2026)
- **Zylos Research survey (May 2026):** Found a 37% performance gap between lab benchmark scores and production outcomes across enterprise agents. Documents 50x cost variation for comparable accuracy across agent configurations. UC Berkeley benchmark analysis found multiple leading agent benchmarks (SWE-bench, WebArena, OSWorld, etc.) had significant contamination or methodology issues. — [AI Agent Evaluation and Benchmarking: Beyond Task Completion](https://zylos.ai/research/2026-05-13-ai-agent-evaluation-benchmarking)
- **HN thread on production agent principles (128 points):** Practitioners universally agreed evals are vital. Debate on LLM judges: same-family models produce false positives; different-family judges introduce inconsistency. One researcher reported in internal experiments that LLMs "were not good critics." — [Hacker News #44712315](https://news.ycombinator.com/item?id=44712315)
- **HN "What broke when I tried to evaluate an AI agent in production":** Documents the gap between benchmark-style evaluation and real production evaluation. Found that model updates — not agent behavior — changed benchmark scores, making it impossible to attribute regressions to the agent. Environment flakiness introduced noise that overwhelmed signal. — [Hacker News #47416033](https://news.ycombinator.com/item?id=47416033)
- **FuturOneAI evaluation framework:** Open-source framework with task completion rate, first-pass accuracy, cost per task, and reliability (pass@8) metrics for enterprise agents. — [GitHub](https://github.com/FuturOneAI/ai-agent-evaluation-framework)

## Gotchas

- **Aggregate scores hide broken infrastructure.** A 90% pass rate means nothing if your grader has bugs, your test environment is flaky, or half your tasks have ambiguous success criteria. Inspect individual failures, not just the summary.
- **Static benchmarks decay.** As frontier models improve, benchmark difficulty must be recalibrated. An eval suite that scored your agent at 85% six months ago may score it at 99% today — not because the agent improved, but because the benchmark got easier.
- **LLM judges drift with model updates.** When your judge model is updated by its provider, evaluation scores shift even if your agent hasn't changed. Cache judge outputs for regression comparisons.
- **Calibration drift in long-horizon tasks.** For tasks that take hours to complete, defining "correct" is often subjective. Human evaluation is expensive and inconsistent across reviewers. Set explicit rubrics before collecting human judgments.
- **You can't eval what you can't replay.** If your agent interactions aren't logged as full transcripts — every tool call, every reasoning step, every environment change — you cannot run meaningful regression tests. Invest in trace collection early.
