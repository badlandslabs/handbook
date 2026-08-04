# S-2118 · The Agent Eval Stack

When you have agents running in production but no way to know if Tuesday's deployment made them better or silently broke them — and the gap between benchmark success and real-world reliability is your actual risk.

## Forces

- **Human review doesn't scale but teams still lean on it.** The largest study of agents in production (306 practitioners, 20 case studies) found 74% rely primarily on human-in-the-loop evaluation. This works for demos. It collapses at volume.
- **Agents are systems, not models — so single-output evals miss the point.** Agents orchestrate planning, tool calls, retrieval, and memory. Evaluating only the final output says nothing about whether the agent took the right path or just stumbled into the right answer.
- **The three-layer problem nobody talks about.** System efficiency (latency, tokens), session-level outcomes (did it complete the task), and node-level precision (was this specific tool call correct) — each requires different measurement and none can substitute for the others.
- **Agents change between deployments.** The oracle problem: you can't use the agent to evaluate itself, and the behaviors that matter today may not be the ones your eval captured last month.
- **The field is still building custom.** 85% of production agent teams build their own evaluation framework rather than using third-party tools. The tooling market is fragmented and early.

## The move

Separate evaluation into distinct layers and match each to the right measurement technique.

**Layer 1 — System Efficiency (operational)**

- Track latency per step, total tokens per session, tool call counts, and cost per task
- Catch regressions like "we switched models and it now calls twice as many tools"
- These are easy to measure with standard instrumentation (OpenTelemetry, Langfuse, existing APM)

**Layer 2 — Session-Level Outcomes (task completion)**

- Did the agent complete the task? Was the output correct?
- Build a **golden dataset**: curated inputs paired with expected outputs or pass/fail criteria
- Golden datasets require continuous curation — stale test cases are a common failure mode
- Supplement with programmatic **assertions**: check that outputs match a schema, contain required fields, don't contain prohibited content, or produce correct computed values
- Assertions catch regressions fast and deterministically; combine with LLM-judge for qualitative properties neither can handle alone

**Layer 3 — Node-Level Precision (reasoning quality)**

- Did the agent take the right tool at the right step? Was the reasoning coherent?
- Use **trajectory evaluation**: the judge model reviews the agent's full execution path against a rubric
- Include a **reference trajectory** so the judge can compare paths, not just score in isolation
- Key calibration: LLM-as-judge needs to be validated against human judgment — target 0.80+ Spearman correlation before trusting scores
- Agent-as-a-judge (using a secondary agent to evaluate the primary agent's trajectory) handles dynamic behavior that static output grading misses

**The evaluation pipeline:**

- **Offline**: Run eval suites against every code change in CI. Use synthetic task generation to scale coverage when golden datasets are sparse. Monitor drift in your eval distribution over time.
- **Online**: Deploy production monitoring with step-level tracing. Catch silent semantic failures — cases where the agent completes the task but produces subtly wrong output. Standard observability misses these.
- **Closed loop**: Alert on session-level regressions, drill into node-level traces to find the root cause, update the golden dataset and rubric, push back to CI.

**Measurement targets:**

- Task completion rate (how often the agent finishes the full session successfully)
- Step efficiency (fewer tool calls to the same outcome is better)
- Trajectory quality score (LLM-judge rubric on a 1-5 scale for reasoning coherence)
- Silent failure rate (completed session but output was wrong — this is the most dangerous metric)

## Evidence

- **Anthropic Engineering Blog:** "Demystifying evals for AI agents" — defines four evaluation patterns (golden datasets, programmatic assertions, LLM-as-judge, synthetic task generation), describes trajectory vs. outcome evaluation, and recommends calibrating LLM-judge with human reference — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **arXiv 2512.04123 — "Measuring Agents in Production" (MAP Study):** First large-scale study of AI agents in production. Surveyed 306 practitioners, 20 case studies, 26 domains. Found 74% rely on human-in-the-loop evaluation, 85% build custom frameworks, 68% of agents execute ≤10 steps before human intervention, and reliability is the #1 concern across all deployments — [arxiv.org/html/2512.04123v1](https://arxiv.org/html/2512.04123v1)
- **Maxim AI — "Evaluating Agentic AI Systems: Frameworks, Metrics, and Best Practices":** Three-layer evaluation framework: System Efficiency, Session-Level Outcomes, Node-Level Precision. Recommends combining LLM-as-Judge with human review and building observability pipelines from offline simulation to online production monitoring — [getmaxim.ai/articles/evaluating-agentic-ai-systems-frameworks-metrics-and-best-practices](https://www.getmaxim.ai/articles/evaluating-agentic-ai-systems-frameworks-metrics-and-best-practices)
- **Galileo Labs — "How to Build an Agent Evaluation Framework With Metrics, Rubrics, and Benchmarks":** Three-tier rubric taxonomy (7 dimensions → 25 sub-dimensions → 130 fine-grained rubric items), LLM-as-judge calibration targeting 0.80+ Spearman correlation, benchmark selection (WebArena, SWE-bench Verified, GAIA) — [galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- **HN Discussion — "Ask HN: How are you monitoring AI agents in production?":** Practitioners report no step-level visibility, surprise token bills, risky outputs going undetected, and no audit trail. Products like AgentShield, Lucidic, and Moda address execution tracing, cost tracking, risk detection, and human-in-the-loop approval — [news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)
- **arXiv 2508.02994 — "When AIs Judge AIs: The Rise of Agent-as-a-Judge":** Documents Agent-as-a-Judge framework for evaluating dynamic agent behavior (reasoning + tools), not just static outputs. Explains why pure outcome metrics miss how agents approached a task — [arxiv.org/html/2508.02994v1](https://arxiv.org/html/2508.02994v1)

## Gotchas

- **Golden datasets go stale.** Test cases that don't evolve with your agent's capabilities produce false confidence. Curation is continuous work, not a one-time setup.
- **Outcome metrics hide reasoning quality.** An agent can reach the right answer via a terrible path, then fail on a slightly different input. You need trajectory evaluation to catch this.
- **LLM-as-judge has bias that compounds at scale.** Calibration against human judgment is not optional — uncalibrated judges produce correlated errors that look like signal.
- **Benchmarks ≠ production behavior.** SWE-bench and WebArena are useful for regression testing but don't reflect your specific tool set, domain, or user behavior. Build domain-specific evals for the cases that actually matter.
- **Silent semantic failures are the worst kind.** The agent completes the task, logs show success, but the output is subtly wrong. Standard observability doesn't catch this — you need output validation (factual accuracy checks, schema assertions) at the session level.
