# S-1991 · The Agent Evaluation Gap Stack — When Your Agent Completes 95% of Tasks But Only 70% Are Actually Correct

[Your agent completes 95% of sessions. Your users still churn. The agent hit every step — tool calls made, outputs generated, final message delivered. But 25% of those completions were wrong: a hallucinated API response was treated as ground truth, a tool timeout was silently swallowed, a multi-turn reasoning chain drifted off-topic in step 7 and nobody noticed until the customer complained. You had no eval. You had no idea. This is the agent evaluation gap: the space between what agents report and what they actually deliver.]

## Forces

- **The compound failure math is brutal.** Each step in a 10-step agent workflow succeeding 85% of the time produces an end-to-end success rate of ~20%. Add tool calls, retries, and retrieval steps and the probability of a clean trajectory drops fast. Traditional software testing (pass/fail per step) misses the interactions between steps. — [Apptitude, "Why AI Agents Fail in Production," May 2026](https://apptitude.io/blog/why-ai-agents-fail-production-failure-modes/)
- **The belief-execution gap is 57 percentage points.** 72% of enterprise AI teams believe comprehensive eval coverage drives reliability; only 15% achieve elite (90–100%) coverage. The gap is operational, not intellectual — teams know what to do, they don't do it consistently. — [Galileo AI, State of Eval Engineering Report, 500+ practitioners, 2025](https://galileo.ai/blog/ai-agent-metrics)
- **The detection lag is measured in churn.** 90%+ of surveyed YC founders said the only way they knew their agents were failing users in production was by hearing complaints. By the time the signal reaches the team, the damage is already done. — [Voker (YC S24), Launch HN, 2025](https://news.ycombinator.com/item?id=48109962)
- **Offline benchmarks miss what production owns.** Held-out benchmarks and final-answer pass/fail capture trajectory quality, tool-call correctness, looping behavior, and recovery patterns. A correct answer in 20 steps with two policy-violating tool calls is a failing trajectory. Standard benchmarks cannot see it. — [Morphllm, "AI Agent Evaluation (2026): Metrics, Frameworks, and Production Failures"](https://www.morphllm.com/ai-agent-evaluation)
- **Agents that achieve 60% single-run success drop to 25% across eight runs.** Standard benchmarks test one-shot capability; production tests sustained reliability. The difference is enormous and invisible without a longitudinal eval design. — [Galileo AI, Agent Evaluation Framework Guide, 2025](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

## The move

Build a three-layer measurement stack that maps to where failures actually hide.

### Layer 1 — Task Success (outcome, not trajectory)
- Define success as a **structured assertion**: a golden-answer test case with an expected output, not a vibes check. "Did the agent complete the stated objective?" in a format the CI pipeline can run.
- Use **domain-specific benchmarks** as a baseline: GAIA for general-purpose agents, SWE-bench for code agents, τ-bench (tau-bench) for customer service agents, WebArena for web navigation. These are not sufficient but they are necessary — they give you a reproducible number before you ship.
- Complement with **LLM-as-judge** scoring: run a stronger model (GPT-4o, Claude 3.7 Sonnet) as an automated grader over a golden eval set. Target ≥0.80 Spearman correlation with human judgment — below that threshold the judge is not reliable. — [Galileo AI, Agent Evaluation Framework Guide](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

### Layer 2 — Trajectory Quality (the step-by-step path)
- Instrument traces at the span level: capture every LLM call, tool invocation, retrieval step, retry, and recovery. This is where the real quality signal lives. — [Morphllm, AI Agent Evaluation 2026](https://www.morphllm.com/ai-agent-evaluation)
- Measure **tool-call correctness** (did it call the right tool with the right arguments?), **loop detection** (is it re-calling the same tool with the same inputs?), and **recovery quality** (did it handle errors gracefully or cascade into bad state?).
- Track **cost per task** and **token efficiency**: an agent that solves 95% of tasks at 3× the token budget of a competitor is not a better agent, it's a cost management problem.
- Three production failure modes that trajectory analysis catches that outcome metrics miss: **ghost actions** (agent takes no action or wrong action and produces a plausible output), **silent hallucination** (retrieved context is subtly wrong, agent generates a fluent answer from it), and **context bleed** (prior session state contaminates the current task). — [Diwesh Saxena, "AI Agent Failure Modes in Production Systems," Zenodo, Sep 2025](https://www.diweshsaxena.com/research/ai-agent-failure-modes)

### Layer 3 — Per-Turn Production Monitoring (continuous, sampled)
- **Sample 1–5% of production traffic** for automated eval. Running a judge LLM on 100% of queries is expensive — sampling is operationally realistic and statistically meaningful if the sample is stratified by task type and user segment. — [MyEngineeringPath, "LLM Evaluation Guide: RAGAS, LLM-as-Judge & Production Evals"](https://myengineeringpath.dev/genai-engineer/evaluation/)
- Use a **different, stronger model as judge** than the one being evaluated. A judge using the same model as the system it evaluates has intrinsic self-evaluation bias toward its own reasoning style. Use GPT-4o or Claude 3.7 Sonnet as judge even if the agent runs a smaller model. — [MyEngineeringPath, LLM Evaluation Guide](https://myengineeringpath.dev/genai-engineer/evaluation/)
- **Distilled judges for high-throughput inline checking**: small models (Galileo Luna-2 3B–8B, Prometheus 2 7B, Patronus Lynx 8B) deliver 97% cost reduction vs. GPT-4 at 0.88–0.95 accuracy for inline gate-checking. Use frontier models for high-stakes verification, distilled models for per-turn sampling. — [Zylos Research, "LLM-as-Judge in Production: Agent Reasoning Verification," Apr 2026](https://zylos.ai/research/2026-04-10-llm-as-judge-production-agent-verification-2026/)
- Catch **drift without detection**: log per-turn policy violations, jailbreak attempts, and prompt injection patterns. These are invisible to final-answer eval and catastrophic in aggregate. A three-layer model (guardrails, runtime checks, eval replay) reduced incidents 40% in a live ATS agent deployment. — [Diwesh Saxena, AI Agent Failure Modes, Sep 2025](https://www.diweshsaxena.com/research/ai-agent-failure-modes)

### Integrate evals into CI/CD, not just pre-deployment
- Trigger eval runs on: every commit (regression), daily/weekly scheduled (drift), and event-driven (new tool, model change, prompt update).
- **Eval harnesses belong in CI, not slide decks.** A test that only runs in a notebook before the demo is not an eval — it's a demo harness. — [Diwesh Saxena, AI Agent Failure Modes](https://www.diweshsaxena.com/research/ai-agent-failure-modes)
- Teams establishing eval practices early experience **60% fewer implementation delays** when scaling to production. — [Galileo AI, State of Eval Engineering Report](https://galileo.ai/blog/ai-agent-metrics)

## Evidence

- **YC Survey (Voker):** 90%+ of founders building AI agents said the only signal of agent failure in production was customer complaints — no automated detection. — [Launch HN: Voker (YC S24)](https://news.ycombinator.com/item?id=48109962)
- **Galileo AI Research (500+ enterprise practitioners, 2025):** 72% of teams believe comprehensive eval drives reliability; only 15% achieve elite coverage. Elite teams (top 15%) achieve 2.2× better reliability outcomes. Teams with early eval practices see 60% fewer delays when scaling. — [Galileo AI, State of Eval Engineering Report](https://galileo.ai/blog/ai-agent-metrics)
- **Production Deployment (Diwesh Saxena, HRTech/HealthTech, Sep 2025):** Six documented failure modes (tool timeout cascades, silent hallucination, context bleed, wrong-entity merges, prompt injection, drift without detection) across real deployments. A three-layer resilience model reduced incidents 40% in a live ATS agent. — [Zenodo White Paper](https://www.diweshsaxena.com/research/ai-agent-failure-modes)
- **Apptitude Engineering (2026):** Each step in a 10-step workflow at 85% success → 20% end-to-end success rate. The math is not a model problem — it is an architectural challenge requiring eval-first design. — [Apptitude](https://apptitude.io/blog/why-ai-agents-fail-production-failure-modes/)

## Gotchas

- **LLM-as-judge self-bias is real.** A judge model using the same weights as the agent introduces stylistic preference bias. Always use a categorically different, stronger model as judge, and validate the judge's correlation with human labels before trusting it.
- **Offline eval coverage ≠ production reliability.** A 95% offline benchmark score tells you the agent can solve the eval set — not that it will solve production tasks consistently, recover from tool failures gracefully, or avoid cascading bad state. Run longitudinal reliability tests (multiple runs of the same task) alongside benchmarks.
- **Golden datasets drift.** An eval set created from the same documents used in the retrieval index produces artificially high recall. Questions that are too similar test the same retrieval path repeatedly. Curate eval sets from real production traffic, not synthetic queries, and review them quarterly.
- **Cost of full-judge coverage is prohibitive.** Running a frontier model as judge over 100% of production traffic is expensive. Treat it as a sampling problem: stratified sampling at 1–5% of traffic, supplemented by distilled judges for inline gating and human spot-checks for high-stakes cases.
- **Per-turn signals are invisible to traces alone.** Standard trace analysis (span duration, token count, tool call count) tells you what happened — not whether a turn violated policy, drifted off-topic, or leaked sensitive context. You need per-turn labeling infrastructure, not just trace instrumentation.
