# S-2649 · The Evaluation Mirage

> When your agent passes every test, logs every step, and still silently breaks in production — because you were measuring what it said, not what changed.

## Situation

Your agent pipeline runs 200 regression tests. All green. You ship it. Three days later you discover it has been approving obviously wrong image outputs for a week, contradicting its own reasoning mid-pipeline, and billing 3x above budget. Every test passed because the tests checked what the agent logged — not whether the world actually changed.

This is the **Evaluation Mirage**: agents feel evaluable because they produce rich, legible traces, but those traces measure the agent's confidence, not its correctness.

## Forces

- **The log-complete gap**: Agents complete workflows without errors, returning plausible-but-wrong results with HTTP 200. The workflow is marked done; the world state never changed.
- **Reliability collapses over turns**: Workflows that succeed 60% of the time on single runs drop to ~25% over eight consecutive turns. Single-turn eval results are structurally misleading for production.
- **Partial success looks identical to failure**: A tool returning "404 customer not found" followed by the agent approving the loan logs cleanly. No exception, no crash, task marked complete.
- **Eval cost vs. eval depth**: Trajectory-level evaluation — checking world state at each step — costs 4–10x more than output-only evaluation. Teams compromise on rigor to stay within budget.
- **LLM-as-critic flatters**: Using one LLM to judge another creates systematic bias — smaller models appear worse than they are, and models tend to rate themselves generously on tasks they just completed.

## The move

**Evaluate trajectories and world-state changes, not agent outputs.**

### Define world-state checkpoints, not output assertions

For each agent task, define what the world looks like after the task succeeds. A refund agent should verify the `transactions` table changed — not just that the agent said "refund processed." Build step-level assertions that run after each tool call, independent of the agent's own logging.

### Treat trajectory quality as a first-class metric

Track not just success/failure but: path length vs. optimal, number of tool-call retries, self-correction events, and time-to-first-correct-step. An agent that reaches the right answer in 12 steps with 3 retries is not equivalent to one that gets there in 2.

### Inject failures in evaluation, not just in production

Simulate API timeouts, 404 errors, 401 auth failures, and rate-limit responses during eval runs. Test whether the agent detects the failure, retries appropriately, escalates when it can't recover, and surfaces errors rather than fabricating success. Happy-path evals are structurally useless for production reliability.

### Use production traffic as the eval corpus

Shadow-run production traffic through eval and compare results. Build regression suites from real failures, not synthetic test cases. Each production incident becomes a permanent eval case.

### Separate the verification layer from the agent layer

Use a dedicated verifier model (often smaller, faster) that has no stake in the task outcome to check: does this tool output actually answer the query? Does the final state match the goal? This breaks the self-confirmation loop.

### Track cost-per-task in evaluation

If you don't measure tokens-per-task in eval, you won't notice when an agent's retry logic causes 3x cost inflation. Set cost budgets per task type and fail evals that exceed them.

## Evidence

- **Engineering blog — Spiral Scout (Feb 2026):** "State Must Be External: Storing workflow state inside the prompt guarantees data loss and audit failures. Treat every tool call from an agent as untrusted user input that requires validation." — [spiralscout.com/blog/agentic-ai-architecture-production-patterns](https://spiralscout.com/blog/agentic-ai-architecture-production-patterns)
- **HN discussion (128 pts, July 2025):** Practitioners report starting with hundreds of evals but ultimately consolidating to fewer tightly tied to product outcomes. LLM-as-critic noted as unreliable for safety-critical decisions — the model that performed the task tends to over-rate itself. — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)
- **AI researcher — Harsh Rastogi (March 2026):** Real deployments at Asynq.ai and Modelia.ai showed agents approving obviously wrong outputs while optimizing for workflow completion. Key failure mode: the agent considers the task done when it reaches the end of its reasoning trace, regardless of whether the downstream state changed. — [harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Research — Label Studio (March 2026):** Multi-turn reliability drops from 60% (single run) to 25% (8 consecutive turns). Automated evaluation rubrics create 4.4x–10.8x cost variation across model families and suffer from cross-model flattery bias. — [labelstud.io/blog/agent-evaluation-framework](https://labelstud.io/blog/agent-evaluation-framework/)
- **Engineering blog — LangWatch (June 2025):** "An agent that fails doesn't just produce a weird sentence; it might book the wrong flight, delete the wrong file, or spend your money. Traditional ML metrics — BLEU scores, perplexity — are structurally wrong for agents. You need outcome-based evaluation." — [langwatch.ai/blog/framework-for-evaluating-agents](https://langwatch.ai/blog/framework-for-evaluating-agents)

## Gotchas

- **Logs are not state**: An agent logging "refund processed" is not evidence a refund was processed. Check the database, not the transcript.
- **Single-turn eval is a lie**: If your eval suite only tests individual calls, you are measuring the demo, not the product. Run full trajectories.
- **LLM-as-critic introduces bias, not objectivity**: The same model that took the action will over-rate its own success. Calibrate against human review for safety-critical paths.
- **Cost surprises are eval failures**: If you aren't measuring tokens-per-task in evaluation, you will be surprised in production when retry loops multiply costs.
- **"All green" means your tests were insufficient**: A passing eval suite with no failure injection tells you the agent handles the happy path — which it was trained on.
