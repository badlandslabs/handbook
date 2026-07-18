# S-1298 · The Eval Gap — When Your Agent Passes Tests and Still Fails in Production

Your test suite passes. Your benchmark score is 91%. You ship to production and the agent spends $3,200 in a single afternoon retrying a failed API call, generating confident nonsense, and completing zero tasks. The benchmark lied. Not because it measures the wrong thing — because it only measures one thing. Agents are trajectories, not answers.

## Forces

- **Agent evaluation ≠ LLM evaluation.** Standard benchmarks assume one input, one output. Agents are loops: reason → act → observe → adapt. Evaluating only the final output is like grading a math test by checking the answer box while ignoring every intermediate step. The wrong path to a right answer is still a broken agent.
- **Error compounds forward.** A bad tool argument at step 2 produces a bad result at step 3, which the agent misinterprets at step 4. Output-only scoring catches none of this. The agentic pipeline arithmetic (each step ~90% reliable × 7 steps ≈ 48% end-to-end reliability) means step-level visibility is not optional — it's the entire problem.
- **Eval quality is dataset quality.** The most common failure mode teams describe: a folder of 20 examples someone wrote before a demo, mixed with pasted support tickets. Then they run GPT-4o as a judge over that dataset and call the score ground truth. A bad dataset produces confident wrong scores that feel more reliable than no score at all.
- **Trajectory correctness and output correctness diverge.** An agent can reach the right answer via the wrong tools, or the wrong answer via the right tools. Pass/fail on outputs masks both failure modes. Teams need to evaluate the *path*, not just the destination.
- **The observability-eval gap is where quality dies.** 89% of teams have production observability (traces, logs, token counts). Only 52% run offline evals. Only 37% run online production evals. Teams watch their agent misbehave in dashboards but have no automated way to catch regressions before deploy.

## The move

**Build a three-layer eval stack and treat it as infrastructure, not QA.**

### Layer 1 — Step-level (white-box) evals

Evaluate each decision point in the agent's trajectory, not just the final output:

- **Tool selection correctness** — did the agent call the right tool for this situation? (DeepEval calls this "工具选择准确性")
- **Argument extraction** — did it pass valid arguments matching the tool schema? A wrong tool name is obvious; a wrong argument shape is silent.
- **Reasoning quality per step** — did the agent's thinking at each step correctly interpret the prior observation?
- **Error recovery** — when a tool call fails, does the agent recognize the failure and adapt, or does it retry blindly?

The AgentEval paper (arxiv 2604.23581) formalizes this as a DAG: each node is a step, edges encode dependency, and eval scores propagate through the graph. Their approach achieves 2.17× higher failure detection recall than end-to-end evaluation alone, with κ=0.84 human agreement.

### Layer 2 — Golden dataset evals (black-box)

Run the full agent against a curated dataset of real inputs:

- **Composition**: weight toward edge cases and failure modes — "20 weird inputs beats 200 normal ones" (r/LLMDevs, Apr 2026). Include policy denials, approval gates, ambiguous inputs, and the cases that broke production last month.
- **Ground truth**: each row needs an expected outcome AND an acceptable trajectory. A code-writing agent that generates correct code via a malicious tool call should fail.
- **Dataset properties** (ContextOS framework): must be sliceable (by intent, risk, difficulty), replayable (pin snapshots and transcripts), held-out (release examples not used during development), learnable (corrections and incidents become rows), and aging-aware (stale rows get reviewed).
- **LLM-as-judge**: use a separate model (GPT-4o or Claude as judge) to score trajectories. Chain-of-thought prompting on the judge improves agreement. Pair with human spot-checks — don't calibrate the judge against itself.

### Layer 3 — Production monitoring (online evals)

Sample production traces and score them against the same criteria:

- **Shadow mode**: run a secondary judge on a percentage of live traffic without affecting the primary agent. Flag trajectories that score below threshold for human review.
- **Regression gates**: every pull request triggers a golden dataset run. The merge is blocked if the pass rate drops more than 5% or cost-per-task increases more than 15%.
- **Drift detection**: track eval scores over time. A gradual 3% monthly decline in tool selection accuracy is harder to notice than a broken deploy but equally costly.

### The dataset-first discipline

Strong teams start with a spreadsheet, not a prompt. The dataset defines the agent's operating reality — what counts as success, what counts as a policy denial, what level of cost is acceptable. Without this, the agent's behavior is measured against the engineer's intuition rather than the actual task distribution.

## Evidence

- **O'Reilly AI Agents Stack Survey (Jun 2026):** 89% observability adoption vs. 52% offline evals vs. 37% online production evals. 32% of teams cite quality as the top production blocker. Human review remains the most common eval method (59.8%), with LLM-as-judge at 53.3% — but human-only evaluation doesn't scale with agent complexity.
- **Hacker News discussion (128 pts, ~11 months ago):** Multiple production engineers confirm "evals are vital for improving performance" and "a core part of any up-to-date LLM team." Consensus: teams without robust eval practices are shipping blind. Evaluations are where the gap between "works in demo" and "works in production" actually gets found and fixed.
- **Reddit r/LLMDevs (Apr 2026):** Practical workflow shared: annotate 30–40 traces per week → cluster bad cases into failure modes → create one eval per failure mode → repeat weekly. Golden dataset run on every prompt change. Weight datasets toward edge cases.
- **AgentEval paper (arxiv 2604.23581, 2026):** DAG-structured step-level evaluation achieves 2.17× higher failure detection recall than end-to-end evaluation. Tested on three production workflows (Claude 3.5 Sonnet + Llama 3 70B agents, GPT-4o as judge). κ=0.84 human agreement, 72% root cause accuracy.
- **ContextOS blog (May 2026):** "Most weak agent projects start with a prompt. Most strong agent projects start with a spreadsheet." The dataset is not paperwork around the agent — it is the agent's operating definition of reality.

## Gotchas

- **A high eval score with a bad dataset is more dangerous than no score.** The dataset's quality is the ceiling on everything you can know about your agent. Treat dataset curation as a first-class engineering task, not a data labeling afterthought.
- **LLM-as-judge can learn to game the judge.** Without human spot-checks and held-out examples, the judge can overfit to the format of a good answer rather than the substance. Calibrate: run the judge on human-annotated samples first and measure agreement.
- **Cost-per-task is an eval dimension most teams ignore.** Two agents with the same accuracy score can differ 50× in cost-per-task due to different tool call counts, context sizes, and retry behaviors. Track both quality and cost, not just quality.
- **Eval scores lag production reality.** Golden datasets capture yesterday's failure modes. Production incidents become tomorrow's golden rows. Without a continuous cycle of incident → annotation → eval addition, your eval coverage drifts from your actual risk surface.
- **Trajectory length matters.** Longer agentic loops have more compounding failure surface. An agent that takes 12 steps with 90% per-step reliability delivers ~28% end-to-end reliability. Shortening the critical path is often higher ROI than improving step reliability.
