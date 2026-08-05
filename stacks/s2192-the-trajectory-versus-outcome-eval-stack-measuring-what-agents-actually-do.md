# S-2192 · The Trajectory vs. Outcome Eval Stack — Measuring What Agents Actually Do

Your agent passes every unit test, ships clean traces, and hits 95% on your curated eval set. Then in production it corrupts data, loops infinitely on edge cases, and nobody notices until users complain. The gap: your tests measure whether the agent said the right thing, not whether it did the right thing.

## Forces

- **The trajectory/outcome split** — agents are multi-step systems; the path matters independently from the destination. A bad trajectory can still reach a good outcome by accident, and a good trajectory can be undermined by a bad final step.
- **Non-determinism hides regressions** — LLM outputs vary between runs. A test that passes once may fail the next ten times. Static test sets overestimate reliability.
- **Benchmarks measure the wrong thing** — MMLU, HumanEval, and standard NLP benchmarks evaluate models as stateless functions, not agents that plan, call tools, and adapt. Your agent can ace every benchmark and still fail at your specific workflow.
- **The verification gap** — 88% of enterprise AI agents fail to reach production because no one verified the agent actually performed the right actions and changed the correct state (not just said the right thing).
- **Teams confuse observability with evaluation** — trace logging tells you what happened; evals tell you whether what happened was correct. Most teams have the former and think they have the latter.

## The Move

Separate evaluation into two independent tracks — **trajectory metrics** (how the agent reasoned and acted step-by-step) and **outcome metrics** (did it accomplish the task) — then layer in a third operational track for production viability.

**Trajectory evaluation:**
- Log every tool call, reasoning step, and decision point as a trace
- Score the trace for tool-call correctness: did it invoke the right tool with valid parameters at each step?
- Detect loop patterns: has the agent repeated the same tool with the same arguments N times?
- Measure wasted steps: did it take 5 turns when 2 would have sufficed?
- Use LLM-as-judge to score intermediate reasoning quality (not just final output)

**Outcome evaluation:**
- Define binary or scalar success criteria per task type (task completion rate)
- Run each task across 3–5 trials (LLM variance means one run is never enough)
- Score final output against ground truth using structured rubric or judge model
- Include negative outcomes: did the agent corrupt data, make unauthorized calls, or leave the system in a bad state?

**Operational evaluation:**
- Latency per step and total task duration
- Cost per task (token count × model pricing)
- Tool reliability: what percentage of tool calls succeeded vs. errored?
- Escalation rate: what percentage of tasks required human intervention?

**Build it into CI:**
- Run trajectory + outcome evals on every commit using a pytest-style framework (DeepEval, Promptfoo)
- Gate deploys on pass rates (e.g., 90% task completion, <5% regression from baseline)
- Store eval results, test datasets, production logs, and model artifacts in a versioned store

**The grader hierarchy:**
- **Code-based assertions** (fastest, deterministic): regex match, JSON schema validation, tool-call parameter checks
- **LLM-as-judge** (flexible, probabilistic): rubric-scored grading of trajectory and output quality
- **Human review** (slowest, highest fidelity): spot-check final outputs, tone, and edge-case behavior

Start with code-based assertions for safety-critical paths, layer LLM judges for quality dimensions, reserve human review for launch gates and quarterly audits.

## Evidence

- **Anthropic Engineering Blog:** Distinguishes tasks (single test with inputs + success criteria), trials (individual runs — run 3–5x to account for variance), and graders (logic that scores outputs). Recommends hybrid evaluation combining code assertions, LLM judges, and human spot-checks. — [URL](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Cleanlab Enterprise Survey (Aug 2025, n=95 with agents in prod):** 70% of regulated enterprises rebuild their AI agent stack every 3 months or faster. Only 5% cite tool calling accuracy as a top concern. Less than 1 in 3 teams are satisfied with observability and guardrail solutions. 63% plan to improve evaluation and observability in the next year. — [URL](https://cleanlab.ai/ai-agents-in-production-2025)

- **InfoQ Analysis (Mar 2026):** "Agents are systems, not models — evaluate them accordingly. Single-turn accuracy metrics and NLP benchmarks (BLEU, ROUGE) don't capture how agents fail in practice." Key findings: trajectory metrics matter independently from outcome metrics; hybrid evaluation combining automated scoring with human judgment is non-negotiable; operational constraints (latency, cost per task, token efficiency, tool reliability) are first-class evaluation targets. — [URL](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

- **DeepEval (GitHub, 17k stars):** Most popular open-source eval framework for LLM applications. Treats evals as unit tests — `pytest`-style syntax with metrics including G-Eval, hallucination detection, task completion, answer relevancy, and RAGAS. All LLM-as-judge metrics run locally. Integrates with CI pipelines and supports LangChain, LlamaIndex, and any custom agent. — [URL](https://github.com/confident-ai/deepeval)

- **Databricks Blog (Sep 2025):** 73% of companies say GenAI is critical to strategic goals, yet the majority of GenAI projects stall after pilot. Recommends three-pillar eval approach: task-level benchmarking, grounded evaluation (does output match source data?), and change tracking. — [URL](https://www.databricks.com/blog/key-production-ai-agents-evaluations)

- **HN Show HN — agent-skills-eval (652 stars):** Developer experiment showing even explicit CLAUDE.md instructions get ignored by models in practice — agent defaulted to shell habits instead of following skill directives. Reveals that skills are assumed to work but untested; the eval framework compares with-skill vs. without-skill runs to empirically prove skills help. — [URL](https://news.ycombinator.com/item?id=48046023)

- **AgentV / ai-agent-eval-harness (GitHub, Apache-2.0):** Verification harness that checks agents actually performed correct actions and changed correct state — not just produced correct text output. Aligns with NIST AI-100-1. Supports industry-specific scenario libraries and multi-agent evaluation. — [URL](https://github.com/najeed/ai-agent-eval-harness)

## Gotchas

- **Eval once and declare victory** — a single eval run against a static dataset is a snapshot, not a monitoring system. Regressions emerge between runs; you need continuous evaluation on every commit or deploy gate.
- **Treating observability as evaluation** — trace logs, latency dashboards, and token counters tell you what happened; they don't tell you whether what happened was correct. Build explicit pass/fail criteria, not just visibility.
- **Running single-trial evals** — LLM outputs are probabilistic. A task that passes once may fail 3 of 5 subsequent runs. Always run 3–5 trials and report the distribution, not just the mean.
- **Evaluating output quality without trajectory review** — a correct final answer reached through a broken or inefficient reasoning path will pass outcome-only evals but fail in production when the edge case hits a different branch. Always inspect trajectories for systematic reasoning errors.
- **Ignoring cost and latency in eval criteria** — a task that costs $2 and takes 45 seconds to complete technically succeeds but may be operationally unacceptable. Make cost and latency first-class metrics, not afterthoughts.
- **The benchmark illusion** — passing WebArena, SWE-bench, or any general benchmark does not predict performance on your specific domain workflow. Build domain-specific eval sets that mirror your actual production inputs.
