# S-1864 · The Eval-First Stack — When You Don't Know if Your Agent Is Lying to You

Your agent has been running for 3 weeks. Task completion rate looks fine. No exceptions, no timeouts, no alerts. On Thursday a domain expert flags that your routing decisions have been subtly wrong since last Tuesday. The agent was never failing — it was producing wrong outputs that sounded right. The issue: you had no way to measure whether the agent was doing the right thing, only whether it was doing *something*. This is the eval gap.

## Forces

- **Agents produce plausible failures, not errors.** A bad LLM output sounds confident and coherent. Traditional APM (error rates, latency) is blind to this failure mode — you need behavioral assertions against actual outcomes.
- **Output variance requires multiple trials.** Because LLM outputs vary, a single run of a task is not a reliable measurement. You need N trials to establish a pass rate, not a single boolean.
- **Grading is harder than it looks.** The final output is easy to check. Whether the agent's *reasoning path* was correct — whether it used the right tools, in the right order, with the right inputs — requires tracing the full trajectory.
- **Eval quality compounds.** A good eval suite run on every commit means regressions surface before users hit them. A missing eval suite means you're discovering failure modes through production incidents.

## The Move

Structure eval as a first-class concern from day one, not an afterthought.

- **Trace the trajectory, not just the output.** Instrument the full agent run — every tool call, every intermediate result, every decision branch. A task transcript gives you the causal chain; final output alone is insufficient for multi-step agents.
- **Separate the grader from the agent.** The grader is its own logic — programmatic assertions, deterministic checks, or a separate LLM call. It should not share the agent's context or trust its self-reported success. Anthropic calls this the "grader" as a distinct concept from the agent being evaluated.
- **Run multiple trials per task.** A single run gives you one data point. Run N trials (5–20 depending on variance) and track the pass rate — 80% pass rate across 10 trials means something very different than 100% on one run.
- **Check exit conditions with external validation.** If the agent says "schema validated," query the schema. If it says "all records processed," count the records. Ground the final assertion in environment state, not natural-language confidence.
- **Build a minimal eval harness early.** You don't need a full benchmarking suite on day one. You need: a way to replay a task, a way to score the output, and a way to record the result. LangChain's checkpointing primitives and Anthropic's harness concept are both good starting points — even a Python script that runs `n` trials and asserts on outcomes beats nothing.
- **Track what you can't check.** If a task is impossible to verify automatically (e.g., "did this email sound appropriate?"), log it as unverifiable rather than assume it passed. This creates a queue of human-reviewable cases.

## Evidence

- **Anthropic Engineering Blog:** Demystifying Evals for AI Agents (Jan 2026) — Introduces the eval anatomy: Task (defined input + success criteria), Trial (one run), Grader (scoring logic), Transcript (full trajectory record), Outcome (end state). Key insight: output variance means a single trial is not a reliable measurement — you need multiple trials per task to establish consistent pass rates. The grader can be programmatic or LLM-based, but it must be *separate* from the agent. https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- **LangChain Blog:** Fault Tolerance in LangGraph (Jun 2026) — Treats error handling as a first-class graph node concern, not boilerplate. Three primitives: `RetryPolicy` (exponential backoff + jitter for transient errors), `TimeoutPolicy` (hard deadline per node), `ErrorHandler` (catch and redirect on specific exception types). `NodeInterrupt` enables human-in-the-loop checkpoints mid-graph. Fault tolerance configuration lives next to the node it protects, not in a separate layer. https://www.langchain.com/blog/fault-tolerance-in-langgraph
- **Hacker News:** Ask HN — Multi-Agent AI Workflows in Production (Apr 2026) — Practitioners distinguish between "agent" scope (persists across runs) and "run" scope (one execution). Common patterns: shared MongoDB layer for agent-to-agent state passing via JSON documents, SQLite for lightweight per-run state, message queues (Kafka, SQS) for async agent communication. Multiple practitioners report "rolling their own" orchestration rather than relying on a single framework — "there's absolute 0 framework out there that's good enough for serious work." Observability wins mentioned: full transcript logging, per-step state snapshots, structured output schemas for machine-readable inspection. https://news.ycombinator.com/item?id=47660705

## Gotchas

- **Evals go stale.** If your eval suite doesn't update when your agent changes, you get false passes. Treat eval cases as first-class artifacts — version them, review them, retire ones that no longer reflect real success criteria.
- **LLM-as-judge is useful but noisy.** Using a separate LLM to grade agent outputs works for open-ended tasks but introduces its own variance and potential for systematic bias. Calibrate against human ground truth on a sample before trusting it at scale.
- **The happy-path eval is useless.** If your eval suite only tests cases you expect to succeed, it tells you nothing. Include failure-mode cases, edge cases, and adversarial inputs — the eval harness is only as good as its test coverage of failure.
- **Trajectory length creates eval cost.** Longer agent runs generate more tokens, more API calls, and more storage. Budget for eval infrastructure costs, not just inference costs. Shorter eval runs with structured intermediate checks are cheaper than full-transcript storage at scale.
