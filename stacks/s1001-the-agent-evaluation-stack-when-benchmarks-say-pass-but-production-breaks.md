# S-1001 · The Agent Evaluation Stack — When Benchmarks Say Pass but Production Breaks

Your agent scores 87% on your test suite. In production it hallucinates tool calls, loops on rate limits, and costs 50x more per task than expected. Your benchmark was measuring the wrong thing — and you only find out after users do. You need an evaluation system that measures what actually matters: trajectories, not outputs; costs, not just correctness.

## Forces

- **Trajectories are invisible in output-only scoring.** A correct final answer achieved through three unnecessary tool calls, two retries, and a hallucinated intermediate step looks identical to a clean run in a pass/fail test. The failure modes only appear when you trace the path.
- **Cost and correctness are separable axes.** Two agents with identical accuracy can have 50x cost-per-task variance due to different model choices, retry behavior, and tool call counts. Optimizing only for correctness leaves the cost dimension unexamined.
- **Production behavior diverges from benchmarks by ~37%.** Benchmarks use curated inputs and controlled environments. Real production traffic includes ambiguous requests, flaky APIs, rate limits, adversarial inputs, and unexpected data formats — none of which appear in evaluation datasets.
- **Trajectory complexity defeats static assertions.** Traditional testing assumes deterministic outputs. Agent trajectories involve probabilistic reasoning, multi-step planning, tool selection, and error recovery — each step can compound or mask errors that only surface later.

## The move

Measure agents at three levels: end-to-end (did the task succeed?), trajectory-level (was the path efficient?), and component-level (which tool or reasoning step failed?). Build a regression pipeline that catches drift before it reaches users.

**Trajectory tracing as the backbone.** Instrument every run to record the full sequence: which tool was selected, what arguments were passed, what the tool returned, what the agent concluded from it. This is the primary artifact for debugging — it turns "the agent messed up" into "tool X received malformed input Y on step 3." Without trajectory tracing, failures stay invisible until they compound.

**Deterministic checks for tool correctness.** Use schema validation and unit-test-style assertions on tool call arguments and return values. These are compiler-style pass/fail signals: if the tool was called with the wrong parameters, the check catches it regardless of whether the final answer happened to be right. Save LLM-as-judge for context-dependent outputs (tone, relevance, reasoning quality) where deterministic checks can't apply.

**Three-level evaluation hierarchy:**
1. **End-to-end** — Did the agent complete the task correctly? Binary or rubric score.
2. **Trajectory-level** — Was the path efficient? Tool call count, retry loops, argument correctness, plan adherence.
3. **Component-level** — Which specific span caused failure? Enables targeted fixes without re-evaluating the whole run.

**Production regression pipeline.** Run offline eval against curated datasets in CI before every deploy — acts as unit tests for the agent. Supplement with online eval scoring real production traffic in real-time to detect quality drift. Re-evaluate periodically as your agent evolves: what passed six months ago may reflect outdated behavior assumptions.

**Human review as calibration signal.** Route edge cases and disagreements between automated evaluators to subject-matter experts. Use that feedback to improve your automated metrics over time. LLM-as-judge evaluators are not reliable without periodic human calibration.

**Budget for trajectory efficiency from the start.** Track cost-per-task and token-per-run alongside correctness. An agent that's right but slow and expensive still fails in production. Set per-task cost ceilings and alert when agents exceed them — this surfaces retry loops, unnecessary reasoning chains, and model misconfigurations early.

## Evidence

- **Blog post (Thinking Inc, 2026):** Production agent evaluation requires three distinct layers — pre-deployment benchmarks, real-time monitoring, and human feedback loops. Gartner projects 40% of enterprise AI failures by 2028 will trace to inadequate evaluation rather than model capability gaps. — [https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production)

- **HN thread / Anthropic guidance (June 2025):** Anthropic's "Building Effective AI Agents" HN discussion (543 points) surfaces the trajectory vs. output gap directly — practitioners confirm that pass/fail on final outputs misses retry loops, unnecessary tool calls, and hallucinated intermediate steps. LangChain practitioners recommend pairing trajectory evals with isolated runtimes (sandboxes) so tool calls can be safely replayed and checked. — [https://news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809) | [https://www.langchain.com/resources/how-to-evaluate-llms](https://www.langchain.com/resources/how-to-evaluate-llms)

- **Confident AI guide (2026):** Core metrics to track in agent evaluation: task completion, step efficiency, argument correctness, tool correctness, plan adherence, plan quality, reasoning quality, answer relevancy, faithfulness, safety, latency, and cost. Key insight on cost: teams measuring only correctness miss 50x cost-per-task variance between agents achieving similar accuracy. — [https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)

- **LangSmith vs Arize Phoenix comparison (Codeables, April 2026):** Phoenix leads on prebuilt evaluators (hallucination, correctness, relevance, toxicity) for high-throughput batch scoring and CI gates. LangSmith leads on managed eval workflows with hosted datasets and one-call `evaluate()` runners. Teams standardizing on either platform cite trajectory-level observability as the primary reason. — [https://codeables.dev/article/langchain-langsmith-vs-arize-phoenix-which-is-better-for-multi-turn](https://codeables.dev/article/langchain-langsmith-vs-arize-phoenix-which-is-better-for-multi-turn)

## Gotchas

- **Benchmarks measure the wrong thing.** Lab benchmarks predict production performance poorly — the 37% gap is well-documented. A high benchmark score is necessary but not sufficient. You need production-traffic evals, not just curated dataset scores.
- **LLM-as-judge needs calibration.** Automated judges don't always get it right, especially on nuanced cases. Route disagreements to humans periodically. An uncalibrated judge will confidently score incorrect trajectories as passing.
- **Tracing without acting on traces is theater.** Recording trajectories is valueless if nobody reviews them. Build alerting on trajectory anomalies (excessive tool calls, high retry counts, cost spikes) so traces translate into action, not just storage costs.
- **Offline eval alone misses production drift.** Your evaluation dataset goes stale. Production inputs change, user behavior shifts, upstream APIs evolve. Set up online evaluation on real traffic and re-run offline eval periodically — ideally on every agent version change.
- **Ignoring cost-per-task until it's a crisis.** By the time an agent has burned 50x the expected budget, you have a production incident. Track it from day one alongside correctness metrics.
