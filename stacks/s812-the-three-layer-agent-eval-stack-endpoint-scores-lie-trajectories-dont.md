# S-812 · The Three-Layer Agent Eval Stack: Endpoint Scores Lie, Trajectories Don't

You ship an agent. Your benchmark says 87%. Your users say it's broken. The agent is hallucinating tool calls, looping on errors, and ignoring constraints — then accidentally landing on the right answer. Endpoint scoring rewarded the luck; trajectory evaluation would have caught the recklessness.

## Forces

- **Single-turn thinking infects eval design** — standard LLM metrics (accuracy, ROUGE, BLEU) score the last message. Agents make dozens of decisions before producing one. Evaluating only the output misses the whole system.
- **Offline evals go stale; production signal is sparse** — golden datasets decay as the world changes. But sampling production traffic for labeling is expensive and slow. The data flywheel most teams dream about never spins up.
- **Trajectory scoring is expensive and unstructured** — LLM-as-judge over full traces burns tokens. Hard-coded trajectory matching works for deterministic workflows but breaks on anything with genuine branching. Neither scales cleanly across a team.
- **Cost-per-task is a first-class metric nobody talks about** — an agent that gets the right answer after 12 tool calls and 3 retries costs differently than one that gets there in 2. Budget variance of 50x per task has been reported in production.
- **Security and safety are trajectory problems, not output problems** — an agent that refuses a harmful request through correct reasoning vs. through a formatting error are not equivalent. You can't tell from the final output.

## The move

Layer your eval stack across three levels. Use offline evals for regression, trajectory evals for quality audits, and production per-turn sampling for signal that actually tracks reality.

**Layer 1 — Endpoint (final-answer) eval:**
- Pass/fail or score against expected output for a given input
- Fast, cheap, deterministic. Use for regression gating in CI.
- Misses: tool selection, path efficiency, error recovery, constraint adherence

**Layer 2 — Trajectory eval:**
- Score the full execution trace: which tools called, in what order, with what arguments, whether each step satisfied policy
- Two sub-patterns: **trajectory match** (hard-coded reference path, step-by-step comparison — deterministic, cheap, good for rigid workflows) and **LLM-as-judge** (model reviews decisions against a rubric — flexible, nuanced, burns tokens)
- Captures: wrong-tool-first, lucky recovery, ignored constraints, loop detection
- LangSmith's `agentevals` package supports both; Braintrust's Loop automates judge rubric creation from production traces

**Layer 3 — Per-turn production sampling:**
- Label individual turns on real production traffic at a sample rate
- Feeds the data flywheel: production failures → annotation queue → regression test
- Calibrate LLM judges against human-labeled examples to mitigate bias drift
- Only way to catch failures that don't appear in curated test sets

**Structural decisions:**
- Route eval types to the right gate: endpoint → CI pull requests; trajectory → pre-release review; per-turn → continuous monitoring with alerting
- Instrument every tool call with structured metadata: tool name, arguments (sanitized), latency, error type if any
- Track **cost-per-task** alongside quality — a quality improvement that 8x's token spend is a regression
- Self-aware failure rate (agent recognizes and reports its own failures) is a useful proxy metric — it surfaces where the agent can't recover, even when the final answer happens to be right

## Evidence

- **HN Ask HN:** Practitioner documented that most agent eval failures in a small test suite came from system-level problems (broken URLs in tool calls, agents calling localhost in cloud env, external dependency failures) not model quality — a score of 22 was caused by broken external links, not bad reasoning. The conclusion: "instead of model quality issues, most failures came from system-level problems." — [HN #47416033](https://news.ycombinator.com/item?id=47416033)

- **LangChain engineering post:** Documents the data flywheel pattern — production monitoring → annotation queues → regression tests — and why offline evals go stale while per-turn labels on real traffic stay relevant. Notes that only teams that "can tell you their agent's final answer was correct" exist; far fewer can trace the path that got there. — [LangChain: LLM Evaluation Framework](https://www.langchain.com/articles/llm-evaluation-framework), April 2026

- **MorphLLM practitioner guide:** Establishes the three-layer framework (final-answer / trajectory / per-turn), notes that 52% of AI agent teams have adopted eval tooling but quality is still the #1 production blocker (cited by 32%) — evidence that tooling adoption ≠ eval effectiveness. Also notes 37% lab-vs-production performance gap and 50x cost variance per task. — [MorphLLM: AI Agent Evaluation 2026](https://www.morphllm.com/ai-agent-evaluation), June 2026

- **LangSmith docs:** Documents trajectory match (deterministic, hard-coded reference path) vs. LLM-as-judge (flexible rubric scoring) as two complementary approaches with different cost/quality tradeoffs. Trajectory match recommended for deterministic workflows; judge recommended for nuanced efficiency assessment. — [LangSmith: Trajectory Evals](https://docs.langchain.com/langsmith/trajectory-evals)

## Gotchas

- **Conflating offline and online eval questions** — offline evals answer "how would this model perform on these inputs?" (pre-deploy gate). Online evals answer "how is it performing on real traffic?" (production monitoring). Running the wrong type for the wrong gate produces signal that looks real but doesn't generalize.
- **LLM-as-judge bias without calibration** — judges drift. Without periodic calibration against human-labeled examples, you measure the judge's prior, not the agent's quality. Run human-in-the-loop on a sample of judge decisions, not just the outputs.
- **Golden dataset decay** — the world changes; your test cases don't. Tool descriptions shift, APIs change, user intent drifts. Offline evals that aren't regenerated quarterly are measuring a frozen version of the problem.
- **Optimizing endpoint score can worsen trajectory quality** — if you only reward correct final answers, agents learn to take reckless paths with lucky recoveries. Require trajectory-level checks to pass alongside endpoint checks.
