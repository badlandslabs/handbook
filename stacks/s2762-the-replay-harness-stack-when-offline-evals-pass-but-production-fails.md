# S-2762 · The Replay Harness

When your agent nails the benchmark but quietly degrades in production — same answer, different path, hidden policy violations.

## Forces

- Offline evals score the **output**, not the **route**. An agent can reach a correct answer through a reckless sequence: wrong tool first, lucky recovery, ignored constraint that didn't bite this time.
- Trajectory variance means a task that succeeds once in eight runs can drop to 25% reliability across runs — invisible to single-run evals.
- As agent capability grows, the gap between "passes eval" and "safe to ship" widens. Today's benchmark ceiling becomes tomorrow's floor, and your checks are designed for yesterday's capability.
- Teams that skip trajectory evaluation ship policy violations alongside correct outputs — and have no visibility into which.

## The move

### The three-layer eval stack

Every production agent needs evaluation at three distinct layers, not just the final answer:

- **Final-answer layer** — did the agent accomplish the task? Outcome check: state changed vs. message sent. The ceiling of this layer is "answer is right" with no visibility into cost, safety, or path quality.
- **Trajectory layer** — was the path correct? Scores the full run: tool calls, order, arguments, retries, loops, recovery attempts. Catches policy violations on the way to a correct answer.
- **Per-turn layer** — was each step warranted? Step-level rubrics that feed trajectory scoring and catch silent degradation (wrong tool selected, ignored guardrail, hallucinated intermediate state).

### Statistical eval, not point-in-time

- Run each task **10+ times** across trials — agent output variance means single-run evals hide reliability gaps.
- Track success rate distribution, not just pass/fail. Baseline for shipping: 65%+ task completion. Watch for the multi-run cliff where single-run success drops sharply.
- Use **replay harnesses** — capture a production trace and re-run it against a new model or policy without re-hitting live systems. Isolates behavioral regressions from environment changes.

### Offline-to-online pipeline

1. **Offline simulation** — curated dataset of 50–200 real examples (not synthetic), run through harness, scored on trajectory rubric.
2. **Shadow mode** — agent runs in parallel with production, outputs logged but not acted on, compared against live behavior.
3. **Online monitoring** — per-session metrics: task success, tool call count, step count, cost per session, recovery rate. Alert on trajectory drift.

### LLM-as-judge with guardrails

- Use a stronger model or a dedicated judge to score trajectory quality — not the same model being evaluated.
- LLM judges fail at fine-grained distinctions; pair with **deterministic assertions** (exact match, regex, JSON schema) for checkable behaviors.
- Layer in human review for the top 5–10% of stakes — not for every case, but for cases where trajectory violations have business consequences.

## Evidence

- **Engineering blog:** Anthropic's "Demystifying evals for AI agents" defines the three-layer model (task/trial/grader/transcript/outcome/harness vocabulary) and stresses that "agents operate over many turns: calling tools, modifying state, and adapting based on intermediate results" — requiring eval infrastructure that matches that complexity. — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- **Survey paper:** arXiv:2603.07670v1 (March 2026) surveys memory mechanisms in LLM agents and validates that persistent memory transforms stateless generators into adaptive agents — the same persistence that makes agents powerful makes them harder to eval, since behavior depends on accumulated state. — https://arxiv.org/html/2603.07670v1
- **Practitioner guide:** jamesm.blog (June 2026) recommends "50–200 real examples, per-step rubrics, 10+ runs per example, statistical regression tracking, and a held-out set you never tune against" as the minimum viable eval workload for production agents. — https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics
- **Framework post:** Maxim AI's three-layer framework (System Efficiency / Session-Level Outcomes / Node-Level Precision) operationalizes the same insight: operationalize evaluation from offline simulation to online production monitoring. — https://www.getmaxim.ai/articles/evaluating-agentic-ai-systems-frameworks-metrics-and-best-practices/

## Gotchas

- **Final-answer evals create a false ceiling.** The agent that scores 95% on your benchmark can still fail on 40% of production cases if you only check the last message. The 5% it "fails" in eval is often the easy 5%.
- **Synthetic datasets are a trap.** Agents learn to game held-out examples, especially if they can infer the eval distribution. Real production traffic — anonymized and curated — is the only durable source of representative test cases.
- **Trajectory eval without automated scoring is a one-time event.** Hand-labeling 200 traces is fine once. You need deterministic rubrics and regression tracking that fires on every PR, or evaluation becomes a checkpoint, not a continuous signal.
