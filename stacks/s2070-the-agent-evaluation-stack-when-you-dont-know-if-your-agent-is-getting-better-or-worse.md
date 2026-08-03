# S-2070 · The Agent Evaluation Stack: When You Don't Know If Your Agent Is Getting Better or Worse

The moment your agent ships to production, you face a measurement problem. Traditional software has unit tests, integration tests, and CI gates. Agents have none of that infrastructure by default. You cannot assert `expect(agent.state).to.equal(expected)` because the agent's trajectory is non-deterministic, its success is context-dependent, and the thing that matters — whether the task was actually completed — often requires judgment a script cannot make. Teams ship agents, watch them run, and have no idea whether last Tuesday's update improved or degraded quality.

## Forces

- **Trajectory vs. outcome** — a model benchmark (MMLU, HumanEval) measures knowledge retrieval, not whether the agent completed the multi-step task. You need both, and they measure different things.
- **Non-determinism hides regression** — a single-run pass rate is meaningless. An agent that passes 95% of one-off tests but only 60% of 5-run consistency tests has a reliability problem that surfaces in the first week of deployment.
- **LLM-as-judge is powerful but self-referential** — a model evaluating its own family produces inflated scores. Cross-model evaluation is more honest but more expensive.
- **Eval quality vs. eval coverage** — you cannot test every input. Teams must decide what failure modes matter most and build rubrics around those.
- **Offline evals ≠ production behavior** — a test suite passing in CI says nothing about what happens under real traffic with real users stress-testing edge cases.

## The Move

Measure agent quality across three distinct layers, not one.

- **Tier 1 — Outcome metrics:** Did the task actually complete? Task success rate, measured across a representative test set, run N times (minimum N=5) to surface consistency. Target 80%+ N-run consistency before production.
- **Tier 2 — Trajectory metrics:** How did the agent get there? Track tool call accuracy (correct tool + correct parameters), plan adherence, step efficiency (avoiding redundant calls), and graceful recovery from tool failures. Comprehensive tracking across correctness, groundedness, safety, and performance per run.
- **Tier 3 — System efficiency:** What did it cost? Token usage per task, latency per step, cost per successful task, and cost-velocity (cost per minute of elapsed time). These determine whether the agent is economically viable, not just functionally correct.

Use LLM-as-judge for automated scoring at scale, but enforce cross-family evaluation: use a different model family to evaluate output quality, targeting 0.80+ Spearman correlation with human judgment. Combine with human spot-checks for tone, trust, and contextual appropriateness — dimensions LLMs consistently miss.

Build a domain-matched test set: SWE-bench Verified (~49-55% resolution for top agents as of early 2026) for coding agents, GAIA for generalist tool-use, WebArena for web interaction, AgentBench for multi-environment reasoning. Published benchmarks are directional signals, not replacements for internal evaluation.

Integrate evaluation into CI/CD with three trigger types: commit-triggered (regression gate on every change), scheduled (drift detection), and event-driven (production anomaly detection). Instrument full traces — plans, tool calls, intermediate reasoning, outcomes — so failures can be replayed and diagnosed.

Operationalize with observability: trace every session end-to-end, instrument cost and token velocity, and set alerts on metric degradation. Production monitoring reveals failure modes never represented in test datasets and provides the continuous feedback loop needed to improve.

## Evidence

- **HN thread (July 2025):** Practitioners debated LLM-as-judge reliability — one commenter noted internal experiments found "LLMs were not good critics" without evals to compare by. Counterpoint: same-family evaluation triggers false positives; cross-model evaluation is more accurate. — [Hacker News](https://news.ycombinator.com/item?id=44712315)
- **AWS Labs open-source framework:** AWS Agent Evaluation (v0.4.1, ~370 stars) provides CI/CD integration with commit, scheduled, and event-driven eval triggers, targeting agents on Amazon Bedrock and Amazon Q. Built around evaluators that score correctness, safety, and performance per session. — [GitHub / AWS Labs](https://github.com/awslabs/agent-evaluation)
- **Production engineering guide (Dec 2025):** Principal ML engineer documented that standard unit tests are "pretty much useless" for agents. Emphasizes defining success per agent type (coding agents need PR merge rates, research agents need citation accuracy), not one-size-fits-all metrics. — [Ashutosh Tripathi / Data Science Duniya](https://ashutoshtripathi.com/2025/12/01/ai-agent-performance-evaluation-a-production-engineers-guide/)
- **Three-layer eval framework:** Maxim AI's production guide establishes system efficiency (latency, tokens), session-level outcomes (task success, trajectory), and node-level precision (tool selection, step utility) as the three simultaneous measurement axes. Recommends moving eval from offline simulation to online production monitoring. — [Maxim AI](https://www.getmaxim.ai/articles/evaluating-agentic-ai-systems-frameworks-metrics-and-best-practices)
- **Benchmark analysis:** SWE-bench Verified with human-validated test cases shows top coding agents resolving 49-55% of real GitHub issues. GAIA tests generalist assistants on real-world multi-step tasks. WebArena tests long-horizon web navigation. Each benchmark has systematic blind spots — domain-match the benchmark to the agent type. — [Tech Jacks Solutions / Stanford HAI 2025 AI Index](https://techjacksolutions.com/ai/agentic-ai/build/agent-evaluation-benchmarks/)

## Gotchas

- **Single-run pass rate is a lie.** Always run N≥5 consistency checks. An agent that scores 95% on a single pass but 60% on a 5-run consistency test is not production-ready.
- **Same-family LLM-as-judge inflates scores.** Always use a different model family for evaluation. Bonus points if the judge model is intentionally less capable — it is less susceptible to false positive bias.
- **Published benchmarks are a floor, not a ceiling.** SWE-bench at 50% means your coding agent can fix half of real GitHub issues in controlled conditions. Production is messier. Internal test sets that reflect your actual domain will always outperform generic benchmarks for guiding decisions.
- **Offline passing ≠ production safety.** A regression suite passing in CI says nothing about behavior under real traffic. You need production observability with alerts, not just pre-deploy evaluation.
