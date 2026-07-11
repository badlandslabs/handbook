# S-929 · The Agent Eval Stack — When Your Benchmark Passes But Production Fails

You ship an agent. It scores 91% on your test suite. Two weeks into production, it's routing data wrong, hallucinating tool calls, and burning 40x your budget estimate. Your logs look clean. Your users say it's broken. Your benchmark says it's fine.

This is the fundamental eval problem in 2026: inherited methods from LLM testing — single-turn accuracy, curated datasets, leaderboard scores — don't capture what agents actually do in the wild.

## Forces

- **Single-step benchmarks miss multi-step cascades.** Agents that score 90%+ on individual tasks drop to 30–50% accuracy on chained workflows — the dominant real-world use case. Fiddler AI (2026) documented this across enterprise deployments.
- **Eval relevance decays fast.** Pre-launch evals degrade 41% in relevance within one month of production deployment. The test cases you wrote no longer reflect what the agent actually encounters.
- **Three evaluator types, each a tradeoff.** Code-based graders are fast and objective but brittle. Model-based graders handle nuance but are non-deterministic. Human graders are the gold standard but cost and latency make them unsustainable at scale. Anthropic recommends using all three in combination, not isolation.
- **The trace is the unit of evaluation, not the output.** An agent that returns the right answer via wrong steps is a future incident waiting to happen. You must evaluate the full trajectory — every tool call, every state mutation, every decision branch.

## The Move

Build a layered evaluation pipeline that scores both outcomes and trajectories, runs continuously, and uses the right grader type for each layer.

**1. Define two eval layers — outcome and trajectory.**
Outcome evals check the final result against a known-good answer or functional specification. Trajectory evals inspect the full run: correct tool selection, correct argument construction, correct sequencing, correct state transitions. LangChain's Agent Development Lifecycle (ADLC) positions evals at both the pre-deployment and production-monitoring stages.

**2. Use code-based graders for structural checks.**
Verify that a tool was called with the right schema, that a field exists in the output, that a branch was taken instead of another. These are fast, deterministic, cheap, and catch the class of errors that are obvious in hindsight. Anthropic calls these "code-based graders" — they are assertions, not opinions.

**3. Use model-based graders for subjective and open-ended checks.**
Quality of a generated response, coherence of reasoning, whether a decision aligns with stated policy — these require judgment. Route these to an LLM grader (often a cheaper/smaller model) with a clear rubric. Accept non-determinism here; run multiple trials and track score distributions, not just pass/fail.

**4. Capture traces, not just results.**
Every eval run should produce a structured trace: input → LLM output → tool call → tool result → state delta → next decision → final output. Braintrust's agent eval docs explicitly frame this as evaluating "both the whole (did the plan make sense, is the final answer correct?) and each individual step (did it choose the right tool?)." AWS Labs' agent-evaluation library (368 stars, v0.4.1) automates trace capture as a first-class artifact.

**5. Treat eval suites as living datasets, not static tests.**
Build regression from production failures: every incident becomes a new test case. AgentEvalHQ's .NET toolkit frames this explicitly — stochastic evaluation plus failure-case-as-test. The best agent eval suites grow continuously from real failure observations, not from synthetic task construction.

**6. Gate deployments with a cost and trajectory budget.**
Track cost-per-task and step-count distributions, not just accuracy. A 94%-accurate agent that costs $4.50 per 5-minute loop is a production incident. Set hard limits: max steps, max cost, max retries — these are eval constraints as much as runtime ones.

## Evidence

- **Engineering blog:** Anthropic's "Demystifying Evals for AI Agents" (Jan 2026) defines the foundational anatomy — tasks, trials, graders, transcripts — and the three grader types with explicit guidance on when to use each. It is the canonical reference for why agent eval is not model eval. — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- **Industry data:** Fiddler AI (2026) found agents scoring 90%+ on single-task benchmarks drop to 30–50% accuracy on multi-step chained workflows. Patronus AI's analysis of 1,600+ production traces identified three root causes: ambiguous instructions (system design), sub-agent misalignment (inter-agent), and no completion-verification mechanism (task handoff). — https://www.beri.net/article/patronus-ai-50m-enterprise-agent-testing-production-failure-2026
- **Market analysis:** The eval tooling market reached $500M+ in 2026 with four platforms competing: Braintrust ($800M valuation, $80M Series B), LangSmith (LangChain), Arize, and Patronus AI ($50M Series B). AgentEvalHQ (.NET), AWS Labs agent-evaluation (Python), and DeepEval (Pytest-style) represent the open-source layer. — https://agentmarketcap.ai/blog/2026/04/06/agent-eval-infrastructure-braintrust-langsmith-arize-patronus-500m-market

## Gotchas

- **Eval inflation is real.** If you run enough trials and only report your best score, you will ship overfit agents. Freeze your eval set before you start optimizing against it.
- **Model-based graders need their own eval.** An LLM grader can be biased, inconsistent, or gamed by the agent being graded. Calibrate your grader against human judgments on a subset of cases before trusting its scores at scale.
- **The handoff gap kills agents.** The most common failure in multi-agent systems is not wrong individual decisions — it's a sub-agent completing its task without a reliable signal to the next agent. Evaluations that only score end-to-end outcomes miss this entirely. You need trajectory-level checks at each agent boundary.
- **Offline eval cannot fully substitute for production monitoring.** 41% eval relevance decay within one month means pre-deployment testing is a floor, not a ceiling. Continuous production monitoring with the same grading logic as your offline suite is the only way to catch drift in real time.
