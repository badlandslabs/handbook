# S-1661 · The Agent Evaluation Stack — When Your Agent Passes the Benchmark But Fails in Production

Your agent scores 85% on the benchmark. You ship it. Three weeks later, a client asks why it recommended a database schema that violates their own foreign key constraints. The benchmark never tested that. The gap between benchmark performance and production behavior is now the dominant failure mode for agentic systems — and most teams have no systematic way to close it.

## Forces

- **Benchmarks are retrospective; production is real-time.** Academic benchmarks (SWE-bench, WebArena, OSWorld) use already-resolved GitHub issues and archived sessions with well-specified requirements. Production agents face implicit constraints, heterogeneous multi-modal inputs, and success criteria that evolve as domain experts learn what they actually want. A systematic analysis of 43 benchmarks confirmed this divergence — [arxiv.org/abs/2604.12162](https://arxiv.org/abs/2604.12162).
- **Constraint decay makes benchmarks misleading.** LLM coding agents lose ~30 percentage points in assertion pass rates when moving from loosely specified tasks to fully specified production-grade tasks. Flask-style minimal scaffolding (agent-friendly) vs FastAPI convention-heavy setups (agent-hostile) produce dramatically different results under identical API contracts. Data-layer defects — incorrect query composition and ORM runtime violations — drive ~45% of all logic failures, but benchmarks rarely impose database constraints. — [arxiv.org/html/2605.06445v1](https://arxiv.org/html/2605.06445v1)
- **The "shipping on vibes" loop.** When you change a prompt, swap a model, or adjust retrieval logic, most teams cannot measure whether they improved or regressed anything. Changes ship hoping for improvement; regressions surface when users complain. The LangChain State of Agent Engineering survey found 52.4% run offline evals and 37.3% run online evals — but that means nearly half run zero structured evaluation. — [LangChain State of Agent Engineering](https://www.langchain.com/state-of-agent-engineering)
- **LLM-as-judge is contested.** The HN discussion on production agent principles surfaced empirical skepticism: well-respected researchers found in internal experiments that LLMs could not reliably distinguish good outputs from bad ones when the task required domain-specific judgment. Yet practitioners widely use judges for nuanced quality dimensions because human review cannot scale. The practical consensus: use judges for interpretation-requiring tasks, deterministic checks for everything else, and always calibrate judges against human labels before trusting them. — [HN #44712315](https://news.ycombinator.com/item?id=44712315)

## The move

Build a three-layer evaluation architecture and a production feedback loop that turns real traces into future quality protection.

**Three evaluation layers (not one):**
- **Outcome metrics** — Did the agent complete the task? Binary or threshold: task success, error rate, cost per task.
- **Trajectory metrics** — How did it get there? Tool call sequence, retry frequency, step count, loop detection. Catch the path even when the destination is correct.
- **Component metrics** — Did each part work? Individual tool accuracy, retrieval precision, prompt adherence per stage.

**The production feedback loop:**
`trace → label → cluster → dedupe → versioned dataset → CI gate → online monitoring`

Promote production traces into test cases. The discipline: treat traces as evidence first, then decide which ones deserve promotion into regression fixtures. Production teaches faster than curated test sets. — [agentengineering.org](https://agentengineering.org/articles/traces-as-test-data-using-production-runs-to-improve-agent-quality/)

**Eval tooling pairs practitioners actually use:**
- **LangSmith + DeepEval**: LangSmith for tracing and online evaluation; DeepEval for offline CI checks. Pain point: keeping the two in sync requires glue code.
- **Braintrust**: Unified data + task + scorer pattern. Two scorer types: code-based for deterministic checks, LLM-as-judge for nuanced qualities.
- **Maxim AI / Arize / Galileo**: Observability platforms with eval integrations for teams that want tracing and evaluation under one roof.

**Weekly regression monitoring:** Compare agent quality against the previous week. Flag any agent showing more than a 3% quality decline for investigation. Sample 10% of production outputs for human review; bump to 25% for client-facing workflows. Use an 8-dimension rubric scored 1–5. — [thinking.inc](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/)

**Calibrate before trusting:** Run LLM judges against a small set of human-labeled examples first. Measure agreement. If the judge disagrees with humans more than 20% of the time on any dimension, either retrain the judge prompt or replace with deterministic checks.

## Evidence

- **Academic research:** Constraint Decay (arxiv 2605.06445, May 2026) — 30-point average assertion rate drop from loose to production constraints across 8 frontier models; ~45% of failures from data-layer defects. AlphaEval (arxiv 2604.12162, April 2026) — 94 tasks from 7 real companies; demonstrates that model-level benchmarks miss product-level failures.
- **Practitioner community:** HN thread on production agent principles (128 points) — empirical evidence that LLM-as-judge fails domain-specific judgment tasks; structured rubric + human sampling as the practical alternative. r/LangChain discussion on production evals — most teams use LangSmith + DeepEval combo but struggle with keeping two tools in sync; integrated platforms gaining adoption.
- **Engineering practice:** AgentEngineering.org (April 2026) — production traces → test case promotion pipeline; the eval loop that closes the feedback gap between "works in demo" and "works in production."

## Gotchas

- **Benchmarks measure capability, not product quality.** Your agent scoring high on SWE-bench says nothing about whether it handles your specific database schema, your error recovery requirements, or your user's implicit expectations. AlphaEval's core finding: evaluating agents as commercial products surfaces failures invisible to model-level benchmarks.
- **Offline evals and production reality diverge.** Notebook success means nothing once real traffic hits. The only reliable signal is a closed loop: trace real failures, promote them to test cases, run CI gates, monitor for regression. Everything else is guessing.
- **The step-count trap.** Teams optimize for task completion rate but ignore trajectory quality. An agent that reaches the right answer by calling the wrong tool 12 times is not a good agent — it's a lucky one. Track tool call sequence, retry rates, and loop counts alongside outcome metrics.
- **"It works" is not a number.** Without a baseline measurement before your change, you cannot know if you made things better. Establish a measured baseline for every agent before iterating — even if it's just a small labeled dataset and a handful of deterministic checks.
