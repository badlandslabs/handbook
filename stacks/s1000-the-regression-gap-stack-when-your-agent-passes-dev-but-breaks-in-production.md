# S-1000 · The Regression Gap Stack — When Your Agent Passes Dev but Breaks in Production

You changed one sentence in the system prompt. The eval suite showed green. Two days later, a ticket lands: the agent is returning wrong answers for a specific edge case. Nobody caught it because nobody was testing the edge case. You have no regression harness. This is the gap that bites every agentic team — and it is not a model problem, it is an infrastructure problem.

## Forces

- **Prompt changes are the most common regression source, and the hardest to catch.** Changing a single sentence in a system prompt can drop pass rate by 8% with no model change. Traditional unit tests don't catch this. The "eval suite" most teams run is a few ad-hoc prompts, not a reproducible test suite.

- **Production traces reveal failures the dev environment never showed.** Only 5% of engineering leaders have AI agents live in production (Cleanlab/MIT State of AI in Business 2025). Even among those who do, less than 1 in 3 teams are satisfied with their observability and guardrail solutions. The gap between dev eval and production reality is structural.

- **Models are stochastic — rerunning is not optional.** A prompt that passes once can fail the next time. Evaluating once is not a test; it's a sample. CI needs to re-run critical scenarios, not check a single outcome.

- **Human review is expensive but irreplaceable for calibration.** LLM-as-judge scales, but it needs human rubrics on a sample of traces to surface "metric green, user red" cases. Skipping calibration means the judge drifts from real quality.

## The Move

Build a deterministic evaluation harness with CI gates — translate agent behavior into testable assertions that can fail a build.

- **Golden datasets first.** Curate representative task scenarios with known expected outputs. Every test case needs: input, expected output, and pass/fail criteria. Include edge cases deliberately — null values, Unicode names (O'Brien, José), concurrent requests, empty fields. These are the cases that silently break in production.

- **Track six dimensions, not just accuracy.** Task completion (did the agent finish the job?), tool accuracy (right tool, right arguments?), hallucination rate (did it invent facts?), cost per task, latency, and step efficiency (did it take unnecessary steps?). A trajectory can score high on completion but waste tokens looping.

- **Run step-level traces.** Every LLM call, tool invocation, and agent handoff gets a structured trace with OpenTelemetry metadata. Traces make the difference between "the agent failed" and "the agent called the wrong tool with wrong arguments at step 4."

- **Use multiple scorer types in combination.** Text-match for classification and extraction (exactMatch, fuzzyMatch, tokenOverlap). Rubric-based LLM-as-judge for open-ended responses. Rule-based functional checks for business logic. No single scorer covers all failure modes.

- **Gate on regression, not just quality.** Compare current run against a baseline. A 5% drop against baseline is a regression even if absolute scores look fine. CI fails on regression, not just on low absolute scores.

- **Promote failing production traces into the golden dataset.** When a failure surfaces in production, the trace gets added to the test suite. This closes the eval-to-production loop automatically.

## Evidence

- **Engineering survey:** Only 5% of engineering leaders have AI agents live in production; 63% plan to improve observability and evaluation in the next year — [Cleanlab / MIT State of AI in Business 2025](https://cleanlab.ai/ai-agents-in-production-2025/)

- **Harness regression finding:** Changing one sentence in a system prompt can drop pass rate by 8% without any model change. This is a harness regression, not a model failure, and it is undetectable without a regression suite. — [Rahul Kashyap, "Evaluation Pipelines for Agent Harnesses"](https://rahulkashyap.dev/blog/evaluation-pipelines-for-agent-harnesses.html)

- **Production task success rates:** Web research agents: 78% success rate (key factor: tool reliability). Data extraction: 85% (structured output). Code review: 72% (context quality). Customer support: 68% (escalation design). — [Keith's Atheneum, HN Synthesis, March 2026](https://kohnnn.github.io/keith-digital-garden/HN/2026-03-31-hn-llm-agents-production)

- **Evaluation harness:** Agent Eval Arena — golden datasets, multi-scorer execution, regression detection across model versions, CI gates for model promotion. Node.js/TypeScript, 25 unit tests. — [GitHub: mizcausevic-dev/agent-eval-arena](https://github.com/mizcausevic-dev/agent-eval-arena)

- **Trajectory evaluation:** StepEfficiencyMetric scores the complete ordered trace for redundant or circuitous actions. Redundant tool calls, unnecessary re-retrievals, and looping are visible in the trace but invisible to end-state-only evals. — [DeepEval docs](https://deepeval.com/guides/guides-ai-agent-evaluation-metrics)

## Gotchas

- **Single-run evals are not tests.** A one-time pass is a data point, not a validation. Re-run critical scenarios across multiple model versions and temperatures. Stochastic failures are real failures — they just don't reproduce on command.

- **End-state evals miss step-level failures.** If an agent takes 10 correct steps then one wrong step and recovers, end-state evaluation may miss the error entirely. The agent got the right answer — but it got there expensively, by luck. Trajectory-level evaluation catches this.

- **LLM-as-judge needs calibration.** An uncalibrated judge drifts from real user preferences. Run human review on a sample of traces to calibrate. A judge that always scores 80% is not measuring anything.

- **Cost and latency belong in traces alongside quality.** Teams track pass/fail but ignore that their agent is 3× over budget. Operating envelope violations (cost, latency, step budgets) should be tracked in the same traces used for quality — not in a separate dashboard nobody checks.
