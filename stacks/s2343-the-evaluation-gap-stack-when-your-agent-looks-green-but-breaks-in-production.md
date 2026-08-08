# S-2343 · The Evaluation Gap Stack — When Your Agent Looks Green But Breaks in Production

Your agent scores 92% on your test suite. You ship it. Three weeks later, your users are filing bug reports about agents that complete the wrong task, hallucinate tool parameters, and cost 4x more than expected. Your benchmark dashboard never flinched. You were measuring the model's ceiling, not the system's floor — and your agent lives at the floor.

This is the **evaluation gap**: the structural mismatch between how agents are tested and how they actually fail. Standard benchmarks measure whether the model *can* do the task. Production evaluation measures whether the *agent system* does the right one.

## Forces

- **Agents are systems, not models.** A single-turn accuracy score tells you nothing about tool-call sequences, error recovery paths, or multi-turn state drift. Most evals inherit the wrong abstraction.
- **The demo-to-production collapse is real.** Enterprise AI deployments show agents achieving ~60% success on single runs; that drops to ~25% across eight runs (Galileo AI, 2026). Test environments don't replicate the variability, rate limits, and partial states of production.
- **Trajectory failures are invisible to outcome metrics.** An agent that confidently completes a task by corrupting intermediate state looks identical to a clean completion — unless you're watching the trace.
- **Agent bugs compound across steps.** A bad tool argument at step 3 of 8 can produce a perfectly formatted but completely wrong final answer. A single score at the end misses the cascade.
- **Over 40% of agentic AI projects will be canceled by end of 2027** (Gartner, June 2025). Poor evaluation is a primary driver — teams ship what they can't measure and discover failure too late.

## The move

Decompose evaluation into four independent dimensions. Measure each one, gate on none, and watch trajectory as the leading indicator.

**1. Trajectory — did the reasoning path make sense?**
- Step count, unnecessary tool calls, loop detection, retry frequency
- Boolean tool-call assertions as regression signals: "given this input, agent must call `search`" (free to compute on every sampled trace, per Langfuse)
- Trajectory budget evaluator: hard cap on steps per task to catch infinite loops before they burn budget

**2. Tool use — did it call the right tools with real parameters?**
- Tool parameter hallucination is the most common agent failure mode in production (Harsh Rastogi, Modelia.ai, March 2026)
- Validate tool calls against a schema before execution — don't trust the agent's constructed arguments
- Track tool-call accuracy per tool, not aggregate: a single failure on the `send_email` tool is worse than five on `search`

**3. Task completion — did it achieve the user's actual goal?**
- Requires LLM-as-judge at the observation level: judge receives full input + final output, not intermediate steps
- LLM-as-judge should target 0.80+ Spearman correlation with human judgment (Galileo AI, 2026)
- Binary pass/fail is insufficient for open-ended tasks — use a 3-5 point rubric per dimension

**4. Operational metrics — does it run within constraints?**
- Latency per step and per task, cost per task, token efficiency
- Error rate by type: API failures (retryable), validation failures (fixable), reasoning failures (structural)
- Circuit breaker pattern: after N consecutive failures on a tool, stop calling it and alert

**Instrument both offline and online:**
- Offline: evaluation suite runs against a fixed dataset before every deploy (regression gate)
- Online: evaluate a sample of production traces continuously; alert on trajectory drift before users notice
- Run trials, not tasks: multiple attempts per task catch non-determinism; single-run success rates are misleading

**Layer in human judgment:**
- Expert review of sampled trajectories to calibrate LLM-as-judge accuracy
- Human annotation for the hardest cases: ambiguous success criteria, safety-sensitive outputs
- Use human judgment to build the rubric, not to score every run

## Evidence

- **Engineering post (Anthropic):** Agents achieve ~60% on single runs, ~25% across eight — the reliability collapse comes from trajectory-level failures that outcome metrics never surface. Defines core eval vocabulary: trials, graders, transcripts, evaluation harnesses. — [Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Engineering post (Langfuse):** Tool-call assertions make effective regression tests in experiments and free alerting signals in production. LLM-as-judge for task completion runs at the observation level (July 2026 recommendation). Trajectory budget evaluator prevents infinite loops. — [AI Agent Evaluation: Trajectory, Tool Calls, and Task Completion](https://langfuse.com/resources/engineering/ai-agent-evaluation)
- **Industry guide (Galileo AI):** Enterprise AI deployments show 60% single-run success, 25% multi-run. Gartner projects 40%+ project cancellation rate by 2027. LLM-as-judge requires 0.80+ Spearman correlation with human judgment. Domain-specific benchmarks (WebArena, SWE-bench, GAIA) predict production performance better than general benchmarks. — [Agent Evaluation Framework: Metrics, Rubrics, and Benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- **Industry post (AI Agents Blog):** Tool parameter hallucination — wrong tool, right name, fabricated arguments — is the most common production failure. Exponential backoff on retryable errors, circuit breakers on repeated tool failures, checkpoint-and-resume for partial progress. — [Agent Error Recovery: 5 Patterns for Production Reliability](https://aiagentsblog.com/blog/agent-error-recovery-patterns)
- **HN Ask thread:** Practitioners track cold facts (not accessed in 2+ weeks), use deterministic assertions for anything decidable, and combine automated scoring with expert review of sampled traces. — [Ask HN: How are you testing AI agents before shipping to production?](https://news.ycombinator.com/item?id=47325105)

## Gotchas

- **Don't evaluate the model, evaluate the system.** Changing the model without re-running the eval suite gives you false confidence. The agent system includes the prompt, tools, and orchestration — not just the foundation model.
- **Aggregate scores hide which dimension broke.** A composite score of 78% tells you nothing about whether the tool calls are correct or the task completion is wrong. Set per-dimension thresholds in CI, not a single gate.
- **Sampling production traces is not optional.** You cannot know your eval suite is representative if you never look at what the agent actually does in production. Langfuse, AgentOps, and Phoenix (Arize) are the common tooling choices.
- **LLM-as-judge has a calibration problem.** Without statistical validation against human judgment, judge scores can drift. Target 0.80+ Spearman correlation and revalidate after model updates.
- **Agent traces are large.** Tool responses account for ~68% of tokens in a typical agent trace (BuildMVPFast, March 2026). Your observability stack needs to handle 50KB+ spans, not the 900-byte spans of single-turn LLM calls.
