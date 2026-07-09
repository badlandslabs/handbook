# S-875 · The Trajectory-Light Stack — When Your Agent Passes Every Benchmark and Fails Every Customer

Your agent scores 94% on your internal eval suite, ships on Monday, and by Wednesday you have three customer escalations for the same failure mode nobody caught. The benchmark suite was green. The agent was not ready. The disconnect is trajectory-light evaluation: checking that the agent's outputs are acceptable without checking the full sequence of decisions, tool calls, and state transitions that produced them.

## Forces

- **Benchmarks measure completion, not competence.** SWE-bench, GAIA, WebArena — even the canonical agent benchmarks — measure whether the right answer was produced, not whether the agent earned it correctly. UC Berkeley's RDI Center demonstrated in April 2026 that all eight major agent benchmarks (SWE-bench Verified, SWE-bench Pro, Terminal-Bench, WebArena, FieldWorkArena, CAR-bench, GAIA, OSWorld) could be gamed to near-100% scores with zero actual task-solving, mostly without even calling an LLM.
- **Trajectories expose what end-state evaluation hides.** An agent can reach a correct-looking output via wrong reasoning, a miscalled tool, or a hallucinated intermediate result. Checking only the final answer misses all three.
- **Operational metrics are not quality signals.** HTTP 200, p99 latency, and token counts are system health metrics, not quality metrics. A catastrophically degraded agent returns 200 on every request.
- **Golden datasets go stale fast.** Datasets built from original product specs don't reflect how real users actually phrase requests. Agents routinely pass 98% of golden tests and 60% of real traffic.
- **Eval engineering is as hard as prompt engineering, but teams skip it.** Writing eval prompts that specify failure modes unambiguously, define judge inputs, and produce actionable structured output is genuinely difficult — and often an afterthought.

## The move

Evaluate the trajectory, not just the outcome. Build a layered evaluation system that combines offline scenario testing with continuous production monitoring.

**Layer 1 — Trajectory-level offline evals:**
- Track every tool call: which tool was selected, with what arguments, in what order
- Score trajectory efficiency: did the agent take the minimum required steps, or did it loop?
- Score tool call accuracy: correct tool selection, correct arguments, correct sequencing
- Include adversarial cases (MALT-style behavioral integrity tests) alongside happy-path scenarios
- Run in CI against every commit; gate on session-level task success rate, not model benchmark scores

**Layer 2 — LLM-as-judge with human calibration:**
- Use an LLM judge to score traces against a rubric — faster and more scalable than human review
- Calibrate the judge periodically against human-labeled samples (targets: 70-90% precision)
- Use multi-judge consensus for high-stakes evaluations to catch individual judge drift
- Complement automated scoring with human rubrics on a sampled trace subset — automation and human judgment are not interchangeable

**Layer 3 — Shadow mode deployment before production:**
- Run candidate version in parallel against real production traffic, never exposing its output to users
- Compare candidate vs. live outputs on a fairness-balanced nightly sample
- Use production-quality deltas as the pre-deploy gate, not offline eval scores alone
- Promote incrementally (5% → 25% → 100%) rather than binary cutover

**Layer 4 — Continuous production monitoring:**
- Track session-level metrics: task success rate, trajectory quality, handoff success
- Track node-level metrics: tool selection accuracy, step utility, argument validity
- Track efficiency metrics: latency, tokens per task, step/token budgets
- Set alerts on per-cohort signals (refusal rates, tool call accuracy, billing agent metrics) with automatic rollback triggers
- Use AgentCompass-style post-deployment analysis: error identification → thematic clustering → quantitative scoring → strategic summarization

**Layer 5 — Red team and safety:**
- Red teaming for permission boundary violations, PII leakage, and adversarial prompt injection
- Test against reward hacking and reward model exploitation (the same vulnerabilities that broke the benchmarks)
- Evaluate policy compliance and refusal quality — not just accuracy

## Evidence

- **Research paper:** UC Berkeley RDI demonstrated automated exploit agents hitting 100% on SWE-bench Verified (500 tasks), SWE-bench Pro (731 tasks), Terminal-Bench (89 tasks), FieldWorkArena (890 tasks), CAR-bench, and ~98% on GAIA — zero tasks actually solved, most runs without calling an LLM. Released BenchJack tool for benchmark authors to test their own harnesses. — [ToKnow.ai summary](https://toknow.ai/posts/berkeley-rdi-ai-agent-benchmarks-gamed-100-percent/), [Lilting.tech analysis](https://lilting.ch/en/articles/berkeley-rdi-ai-agent-benchmark-exploitation), [arXiv:2509.14647](https://arxiv.org/abs/2509.14647)

- **Engineering guide:** InfoQ article summarizing lessons from evaluating agents in production: trajectory tracking over static benchmarks, hybrid automated + human evaluation, operational constraints (latency, cost, token efficiency) as first-class targets, and safety/red-teaming as non-optional. — [InfoQ: Evaluating AI Agents in Practice](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

- **Tooling blog:** Confident AI (DeepEval) on agent eval mechanics: single-turn vs multi-turn evaluation, goldens + CI for regression catching (with retry logic for stochastic models), operating envelope tracking alongside quality scores, human rubrics for LLM-as-judge calibration. — [Confident AI: AI Agent Evaluation Guide](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)

- **Deployment guide:** TuringPulse on why standard Kubernetes health probes fail for agents — an agent returning HTTP 200 can be subtly wrong, off-tone, or hallucinating. Shadow mode and per-cohort rollout metrics are the appropriate deployment controls. — [TuringPulse: Safe Agent Deployments](https://turingpulse.ai/blog/safe-agent-deployments)

- **Observability platform:** Langfuse blog on agent tracing: LangGraph, OpenAI Agents, Pydantic AI, CrewAI all instrumented through trace-level observability to capture planning steps, tool invocations, and memory state. — [Langfuse: AI Agent Observability](https://langfuse.com/blog/2024-07-ai-agent-observability-with-langfuse)

## Gotchas

- **Offline evals are necessary but insufficient.** A perfect offline score is not a quality guarantee — production traffic has a long tail no held-out set captures. You need all five layers.
- **LLM-as-judge has known failure modes.** Judges can be prompt-injected (the same vulnerability that broke CAR-bench), exhibit positional bias, and disagree on edge cases. Never deploy judge scoring without periodic human calibration.
- **Golden datasets require maintenance.** When evaluation criteria drift (human labelers change criteria, judge prompts get tweaked), golden sets produce false signals. Treat dataset curation as a continuous process, not a one-time setup.
- **Scaffold and model performance are coupled.** When evaluating an agent, you evaluate the model + scaffold combination. A less capable model often outperforms with a scaffold that accommodates its tendencies. Decouple evaluations to know which component to fix.
- **Metric green ≠ user green.** Automated metrics can pass while users experience the agent as confusing, off-tone, or untrustworthy. Human evaluation on sampled traces catches what automation misses.
