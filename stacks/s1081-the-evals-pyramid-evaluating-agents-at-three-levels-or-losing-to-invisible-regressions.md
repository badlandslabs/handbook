# S-1081 · The Evals Pyramid — Evaluating Agents at Three Levels or Losing to Invisible Regressions

Your agent works. You shipped it. Three weeks later a model upgrade ships a "better" agent. It "feels" fine. A month later you notice the refund automation has been failing silently for two weeks. You had no eval framework, no regression gate, and no way to prove the upgrade hurt. Only 52% of teams running AI agents have evaluation frameworks, versus 89% with observability. The gap is where regressions go to hide.

## Forces

- **Agents break the determinism assumption.** Traditional tests expect identical output for identical input. Agents are stochastic across turns, adapt mid-trajectory, and mutate environment state. Standard unit tests don't apply.
- **A passing single-turn eval means nothing for a multi-turn agent.** The capability that makes agents useful — autonomy and flexibility — also makes it impossible to check correctness with a single assertion.
- **The 37-point gap between observability and evaluation.** Teams can see that the agent is "up" (traces exist) but not whether it is "right." Model upgrades feel like rolling dice because teams cannot distinguish quality drift from capability gain.
- **Regressions compound across steps.** A 95%-reliable step in a 20-step workflow delivers only 36% success rate end-to-end. Individual step metrics can be green while the overall task success rate collapses.

## The Move

Build a three-layer eval pyramid. Each layer catches different failure modes. Skip none.

**Layer 1 — Tool-call assertions (fast, deterministic):**
- Did the agent call the correct tool?
- Were arguments the right type and value?
- Did it handle the tool's error response correctly?
- Target: 5 test cases per tool (3 happy paths, 1 error case, 1 edge case)
- This layer runs in CI on every commit and should complete in seconds

**Layer 2 — Trajectory-level checks (moderate, allows path diversity):**
- Did the agent take a reasonable path to the goal? Multiple paths can be correct.
- Did it look up the order before attempting a refund?
- Did it solve the task in a reasonable number of steps?
- Did it avoid calling irrelevant tools?
- When a step failed, did it recover gracefully?
- Use a different model family for the grader here to avoid self-preference bias

**Layer 3 — Outcome-level LLM-as-judge (slowest, highest signal):**
- Did the agent achieve the goal, semantically? Correct outputs can be worded many ways.
- Is the information factually accurate and complete?
- Did it avoid harmful or off-policy content?
- Grade with a separate, typically cheaper model to avoid circular reasoning
- Track this alongside cost and latency per trace — a "correct" agent that costs 10× more is a regression

**Also layer in chaos engineering for agents:**
- Intentionally inject failures into your eval environment — tool outages, bad responses, permission errors
- Test whether the agent detects failure and asks for human help, rather than looping or giving up silently

**Close the loop with a CI regression gate:**
- Run the full eval suite before every deploy
- Block the release if the pass rate drops below threshold
- Use golden datasets for critical scenarios and re-run them when models are swapped
- Calibrate LLM-as-judge against human labels using Cohen's κ (inter-rater reliability), not just accuracy

## Evidence

- **Engineering Blog (Anthropic, Jan 2026):** "Demystifying Evals for AI Agents" — defines the core taxonomy: task (test case), trial (run), grader (scorer), transcript (full record). States the capabilities that make agents useful — autonomy, intelligence, flexibility — are the same properties that make them harder to evaluate. Emphasizes that evaluations compound in value over time, making problems visible before they reach users. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Engineering Blog (Shopify, Aug 2025):** "Building Production-Ready Agentic Systems: Lessons from Shopify Sidekick" — presented at ICML 2025. Describes the three-level evaluation stack used for Sidekick: tool-call assertions, trajectory-level workflow testing, and outcome-level LLM-as-judge. Includes chaos engineering for agents: intentionally injecting failures to test graceful degradation. — [shopify.engineering/building-production-ready-agentic-systems](https://shopify.engineering/building-production-ready-agentic-systems)
- **Industry Article (Maxim AI, Nov 2025):** Documents that the best current AI agents achieve goal completion rates below 55% on CRM tasks, and that a 20-step workflow with 95% step reliability yields only 36% end-to-end success. Quantifies the compounding reliability problem — every step is a failure surface. — [getmaxim.ai/articles/ensuring-ai-agent-reliability-in-production](https://www.getmaxim.ai/articles/ensuring-ai-agent-reliability-in-production/)
- **GitHub Repo (agent-eval-harness, 2026):** Open-source eval harness implementing traced RAG agent + eval suite + Cohen's κ calibrated LLM-as-judge + CI regression gate. Runs offline via deterministic mock LLM. Demonstrates the "eval is the product" philosophy — the agent is the easy part, the differentiated work is the metric suite and regression gate. — [github.com/ashishlandiwal/agent-eval-harness](https://github.com/ashishlandiwal/agent-eval-harness)
- **Industry Guide (Confident AI, 2026):** Tracks eight core agent metrics: task completion, step efficiency, argument correctness, tool correctness, plan adherence, plan quality, reasoning quality, and answer relevance. Emphasizes tracing as the connective tissue — every metric must trace back to the exact span that caused it. — [confident-ai.com/blog/definitive-ai-agent-evaluation-guide](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide)

## Gotchas

- **LLM-as-judge has its own reliability problem.** Judges are also LLMs and can be biased toward the model they are evaluating. Always calibrate against a sample of human-labeled ground truth and use Cohen's κ to measure agreement — not just raw accuracy.
- **Single-sample eval runs are meaningless.** Output variance is real. Run each task 3–5 times and aggregate. A single pass/fail on a stochastic agent tells you nothing about whether the behavior is stable.
- **Observability ≠ evaluation.** You can have beautiful trace dashboards and still not know if your agent is right. Traces show what happened; evals show whether it was correct. The 37-point adoption gap between them is where silent regressions live.
- **Benchmark contamination is an operational risk.** If your team uses a benchmark to drive development, the benchmark may no longer reflect real-world performance. Use offline benchmarks for coverage, pre-release regression suites for sanity, and canary gates in production for the actual safety net.
- **You cannot evaluate what you cannot observe.** Every eval run requires a complete transcript: all tool calls, all arguments, all responses, all reasoning steps. If your agent stack doesn't emit structured traces, you are flying blind before you even start the eval design.
