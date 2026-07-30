# S-1858 · The Trajectory-Grounded Eval Stack

When your agent produces the correct answer but takes three wrong turns to get there — and your evaluation gives it a passing score because you only checked the endpoint.

## Forces

- **Right answers through wrong paths are still fragile.** An agent that calls the wrong tool, gets a lucky error message, recovers by accident, and lands on the correct answer has not solved the problem reliably. Re-run it tomorrow and it may fail.
- **Endpoint scoring is the eval equivalent of testing coverage by line count.** It measures what was easy to measure, not what actually matters. Tool selection, argument correctness, reasoning coherence, and recovery quality all live in the trajectory — not the output.
- **Agents are non-deterministic by design.** Single-trial evaluation systematically overestimates reliability. A single pass/fail on one run tells you nothing about the distribution of outcomes.
- **Trajectory data exists but teams don't use it.** Every agent run produces a full execution trace — tool calls, arguments, intermediate responses, error messages, recovery attempts. This is rich signal that endpoint-only grading discards entirely.

## The move

**Evaluate the full trajectory, not just the destination:**

- **Step-level rubrics over endpoint rubrics.** Grade each tool call, argument, and decision point independently. A rubric like "did the agent select the correct tool within 2 attempts" catches path-level failures that disappear in endpoint-only scoring.
- **Run 10+ trials per test case.** Single-trial eval on a non-deterministic system is a sample size of one. Elite teams (15% with "eval coverage") run enough trials to compute pass@k and surface variance — a pass@90 that degrades to pass@75 under slight context changes is a different picture than pass@99→pass@98.
- **Build the golden dataset from production failures, not thought experiments.** Every agent failure in front of a real user is a test case you could not have invented. Capture the trace, turn it into a test case, add it to the regression suite. Production failure → trace → test case → CI gate. The flywheel compounds.
- **Size the eval tiers proportionally.** 50–200 curated examples for offline experimentation; 20–50 regression cases as a CI gate on every PR; 5–10% production traffic sampling with statistical drift detection running continuously.
- **Distinguish trajectory quality from result quality.** An agent can have sound reasoning and still fail due to external factors (API outage, rate limit). An agent can succeed and have unsound reasoning. These require different interventions.
- **Use LLM-as-judge for nuanced assessment, code-based graders for invariants.** Step rubrics with deterministic checks (argument shapes, scope compliance, forbidden tool calls) are fast and unbiased. Trajectory-level quality assessment — "was the recovery sound or superstitious?" — benefits from an LLM judge with explicit bias mitigation in the prompt.

## Evidence

- **Engineering blog + practitioner guide (Anthropic):** "Agents operate over many turns: calling tools, modifying state, and adapting based on intermediate results. This makes them fundamentally harder to evaluate than single-turn responses... An agent can reach the right answer through a flawed path, and endpoint scoring would miss this entirely." Introduces the task/trial/grader/transcript taxonomy for structured agent evaluation. — [Anthropic Engineering: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Google ADK codelab:** Defines the two-axis eval framework explicitly: "Trajectory (The Process) = Did the agent use the right tool at the right time? [analogous to] Logic/Regression Testing" vs. "Final Response (The Output) = Is the answer correct? [analogous to] Unit Test." — [Google Codelabs: Evaluating Agents with ADK](https://codelabs.developers.google.com/adk-eval/instructions)
- **Practitioner blog (James McInnes, Jun 2026):** "An agent can reach the right answer through a reckless path: wrong tool first, lucky recovery, ignored constraints that did not bite this time... Aggregate run-level metrics: Pass@k — fraction of runs that satisfy all step rubrics. Mean steps to completion — drift upward often precedes quality collapse. Cost per successful task — ties eval to token economics." — [Evaluating Agents in Production: Trajectory Metrics](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics)
- **AI monitoring platform (Arthur, Jun 2026):** "The highest-value regression test dataset for an AI agent is not handcrafted. It comes from production failures. The pattern is a loop: Production failure → Execution trace → Test case → Golden dataset → CI/CD release gate." — [Arthur: AI Agent Regression Testing From Production Failures](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **LangChain resources + practitioner post (Replyant, Apr 2026):** LangChain's 2026 State of Agent Engineering: 57% of organizations have agents in production, but 32% cite quality as top barrier; 86% pilot failure rate attributed to inability to measure agent quality. CI/CD eval architecture: three-tier — offline (50–200 golden cases), CI gate (20–50 per PR), production sampling (5–10% with z-score drift detection). — [Replyant: Agent Evals in CI/CD](https://replyant.com/lab/agent-evals-cicd)
- **arXiv research (TRACE, Sep 2025):** TRACE framework — "Triage-Inspect-Judge" loop that monitors long-horizon agent trajectories by identifying high-signal regions, performing targeted inspection with accumulated evidence across steps, and synthesizing trajectory-level verdicts. — [arXiv: TRACE - Trajectory Reasoning through Adaptive Cross-Step Evidence Aggregation](https://openreview.net/forum?id=chLlLbI7de)

## Gotchas

- **Endpoint scoring overcounts lucky paths.** If you only grade the final answer, you are effectively scoring the best-trajectory-outcome, not the agent's actual reliability. A grader that scores both "correct tool, correct execution" and "wrong tool, lucky recovery" as PASS is not measuring what you think.
- **Sampling 100% of production traffic for eval is usually overkill and expensive.** 5–10% with stratified sampling for high-risk trajectories (authenticated actions, tool calls, cost-heavy paths) gives better signal at lower cost than blanket sampling.
- **LLM-as-judge at step-level is expensive.** Running a judge over every step of every trajectory burns tokens fast. The practical split: deterministic code checks for invariant violations (scope, forbidden tools, malformed arguments), LLM judge only for nuanced trajectory quality questions (was the reasoning sound? was recovery appropriate?).
