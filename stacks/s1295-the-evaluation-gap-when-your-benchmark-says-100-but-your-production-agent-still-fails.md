# S-1295 · The Evaluation Gap — When Your Benchmark Says 100% but Your Production Agent Still Fails

Your agent scored 97.3% on GAIA. Your benchmark dashboard is green. And yet customers are filing bugs about incorrect expense reports, agents looping on edge cases, and a silent capability regression that went undetected for two weeks. The benchmark told you the agent was getting better. It wasn't. This is the evaluation gap: the systematic failure to measure what actually matters in production.

## Forces

- **Benchmarks measure a point in time, not a trajectory.** Static task-completion scores answer "how good is the agent today?" while ignoring the more consequential question: "is the agent as good as it was last Tuesday?" Model providers silently push updates, input distributions shift, and reliable capabilities quietly degrade.
- **The most-used benchmarks are exploitable.** UC Berkeley RDI tested 8 of the most prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) and found all 8 could be gamed to near-perfect scores without solving real tasks. One team hit 100% on SWE-bench Verified with a 10-line Python trojan. Another gamed 890 tasks with a single-character change. Your leaderboard score is a fiction.
- **LLM-as-judge has a self-referential bias.** When the judge model is the same as or similar to the evaluated model, it exhibits anchoring bias — scoring its own reasoning patterns favorably. Same-model evaluation was found to be a poor critic in practice. You need either a stronger judge model or validated rubric adaptation.
- **Agent chains multiply failure.** In a 4-step dependency chain (planner → orchestrator → tool agent → summarizer), even at 95% component accuracy, total system reliability drops to ~81%. Traditional unit tests miss this because they test code logic, not emergent behavior under probabilistic execution.
- **Traditional CI can't catch agent regressions.** Agent outputs are non-deterministic. A prompt change that fixes one failure class can silently degrade performance in an adjacent one. Without systematic eval pipelines, you won't know until users complain.

## The move

Build an eval system that treats agent code changes like software regressions: deterministic where possible, sampled in production, and runnable in CI.

**The eval stack in production, circa 2026:**

- **Three-layer metric hierarchy.** Outcome metrics (did it complete the task?) as the primary signal, trajectory metrics (every step, tool call, and decision) for debugging, and cost/latency metrics as economic guardrails. Outcome alone is insufficient; trajectory alone is overwhelming.

- **Deterministic rule-based assertions first.** For verifiable outputs — tool call parameters, database state changes, code that can be executed and tested — write assertions. These run fast, are cheap, and catch regressions before they ship. The "eval is too expensive" problem is usually a tool selection problem, not an eval problem.

- **Execution-based evaluation for code agents.** Running the produced code and checking output beats LLM-as-judge for coding tasks. Tests that actually execute code against known inputs are harder to game and more representative of real performance.

- **LLM-as-judge with a stronger model and validated rubric.** Use a model one tier above the evaluated agent (e.g., Sonnet 4 as judge for Opus outputs). Validate the judge against a small human-annotated sample before deploying. Tools like DSPy can optimize judge prompts; LLM-Rubric adds a learned correction layer on top of judge scores.

- **Trajectory tracing as first-class infrastructure.** Capture every step — prompt, tool call, response, token count, latency — under a single trace ID per session. This is the difference between a failing eval and a debuggable one. Structured logs beat console output.

- **Continuous regression suites in CI, not just pre-launch.** Every code change touching agent logic triggers the eval suite. Treat it like unit tests: a failing eval blocks deploy. The cost is real (compute, API calls) but cheaper than a silent regression reaching production.

- **Production sampling for longitudinal drift.** Run a fraction of live traffic through eval pipelines and alert on quality deviations. A Stanford/UC Berkeley study documented GPT-4's accuracy on a specific task dropping from 84% to 51% between March and June 2023 with no version change — detectable only through production sampling.

## Evidence

- **Research paper:** Berkeley RDI broke 8/8 top agent benchmarks — SWE-bench (100% via trojan), WebArena, OSWorld, GAIA, Terminal-Bench — with automated exploit agents. Released BenchJack as a benchmark vulnerability scanner. — [UC Berkeley RDI, April 2026](https://rdi.berkeley.edu/blog/trustworthy-benchmarks-cont/)

- **Research post:** Static benchmarks fail to capture reliability, cost, safety, and long-horizon competence. Execution-based eval for code agents and trajectory-level tracing are the emerging best practices for teams moving past leaderboard theater. — [Zylos Research, May 2026](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking)

- **HN discussion:** LLM-as-judge is effective but requires a stronger judge model and validation against human-annotated samples. Same-model evaluation produces anchoring bias. DSPy and LLM-Rubric are practical mitigation tools. — [Hacker News, Principles for Production AI Agents, ~March 2025](https://news.ycombinator.com/item?id=44712315)

- **Engineering post:** Eval engineering requires treating agent changes like software regressions — deterministic assertions where possible, trajectory tracing for debugging, production sampling for drift detection, and CI integration. A 4-step agent chain at 95% component accuracy yields ~81% end-to-end reliability. — [Evals Blog / prakharjain, 2025](https://prakhar1114.github.io/prakharjain/blogs/Evals%20Blog/EvalsBlog.html)

- **Engineering post:** Agent observability captures session-level traces, structured tool-call logs, eval signals, and cost breakdowns. Without it, multi-step agent failures are opaque — "it keeps looping" is the only signal until users complain. — [Agentix Labs, 2025](https://www.agentixlabs.com/blog/general/debug-multi-step-agents-faster-agent-observability-with-tracing-evals-and-cost)

- **Research post:** Capability drift is the invisible regression. Agents face silent updates from model providers, distribution shift in inputs, and emergent prompt dependencies. Production sampling + longitudinal eval suites are the detection mechanism. — [Zylos Research, April 2026](https://zylos.ai/research/2026-04-14-ai-agent-longitudinal-evaluation-production-regression)

## Gotchas

- **Don't trust any benchmark score above 90% without seeing the exploit surface.** Berkeley's work shows that near-perfect scores are often artifact of the scoring mechanism, not real capability. Verify with execution-based tests.
- **LLM-as-judge is a complement, not a replacement, for rule-based assertions.** Use it for subjective quality dimensions (tone, coherence, relevance) but not for anything verifiable by code execution or deterministic check.
- **Eval datasets rot.** Inputs that worked last quarter may not represent the current input distribution. Evals need maintenance — new edge cases from production logs, removed stale scenarios, updated expected outputs as product behavior changes.
- **Single-point evaluation misses regression.** A passing eval today doesn't mean the agent is as good as it was last week. Run eval suites on every change, not just at launch.
