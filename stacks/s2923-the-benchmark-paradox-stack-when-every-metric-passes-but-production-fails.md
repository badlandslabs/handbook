# S-2923 · The Benchmark Paradox Stack — When Every Metric Passes But Production Fails

Your agent scores 94% on AgentBench. Your unit tests pass. Your eval harness shows 97% task completion. Then you deploy it and watch it cascade into silent failure for six hours before anyone notices. The agent isn't broken — your measurement is. Standard agent evaluation frameworks measure capability in controlled single-session conditions, not reliability at scale. You have been optimizing for the wrong axis.

## Forces

- **Lab conditions vs. production reality** — Controlled eval settings eliminate the variability (tool failures, context drift, compounding errors) that dominates real deployments
- **Capability vs. reliability** — A model can complete a task once in a test environment and fail systematically in production where conditions differ
- **Delayed feedback loops** — Agent failures compound over time; lab evals measure immediate output quality, not downstream error accumulation
- **Ground truth absence** — Long-horizon tasks often have no verifiable correct answer, making automated eval inherently incomplete
- **Non-determinism** — The same agent on the same input can produce different tool-calling sequences across runs, making reproducibility-based eval unreliable

## The move

**Run evaluation against production failure modes, not benchmark leaderboards.** Replace or supplement static benchmarks with continuous, multi-dimensional eval that mirrors the actual failure surface.

### The 7 Production Failure Modes (billion-event scale)

Based on production observations at scale, agents exhibit distinct failure modes standard benchmarks miss entirely:

1. **Repetition loops** — Agent cycles through the same tool sequence without progress (detectable via tool-call sequence entropy)
2. **Context drift** — Agent loses task intent after repeated tool interactions, drifts toward tangential subtasks
3. **Tool call cascades** — Single tool failure triggers a cascade of downstream tool calls that all fail, burning budget silently
4. **Semantic success / protocol failure** — Tool returns HTTP 200 but wrong/incomplete data; agent proceeds on faulty info
5. **Confidence calibration collapse** — Agent becomes overconfident after early successes, stops checking work
6. **Output format drift** — Agent's structured output format slowly degrades across a session (JSON becomes malformed)
7. **Silent truncation** — Long conversations silently lose early context; agent operates with incomplete state without realizing it

### The PAEF 5-Dimension Evaluation Framework

Standard eval frameworks evaluate single-turn quality. Production eval needs continuous, multi-axis measurement:

| Dimension | What it measures | Why it matters |
|-----------|-------------------|----------------|
| **Task Completion** | Did the agent finish the full workflow? | Binary baseline for success |
| **Error Recovery Rate** | How often does the agent self-correct aftertool failures? | Measures resilience |
| **Output Drift Index** | Does output quality degrade over a session? | Catches silent degradation |
| **Tool Call Efficiency** | Are tool calls necessary and correctly sequenced? | Catches waste and loops |
| **Context Retention** | Does the agent maintain task state across turns? | Catches context truncation |

### Operational Practices

- **Run evals continuously, not just at release** — Deploy canary agents that shadow production and measure divergence against expected behavior
- **Instrument tool call boundaries** — Every tool invocation should emit a span; correlate tool failures with downstream agent behavior
- **Measure cost-per-task, not just accuracy** — A 95% accurate agent that uses 3x the tokens of a 92% accurate one is worse in production
- **Watch for confidence collapse** — If agent self-correction rate drops to zero mid-session, that's a failure signal, not a success signal
- **Re-evaluate after any model or prompt change** — Evals that passed before a system prompt tweak can regress silently

## Evidence

- **arXiv paper (2026):** Taxonomy of 7 production failure modes from billion-event scale observations. Standard benchmarks (AgentBench, MT-Bench, BIG-bench) miss 4 of 7 entirely and detect the other 3 only after multiple evaluation-cycle lag. PAEF detects all 7. — [arXiv:2605.01604](https://arxiv.org/abs/2605.01604)
- **HN discussion:** Practitioners report that in regulated or high-consequence domains, AI agents are blocked from production not due to capability but accountability — outputs must be deterministic, replayable, auditable, and human-vetoable. Until agent architectures treat controllability as first-class, autonomy remains a demo feature. — [Hacker News — "Why autonomous AI agents fail in production"](https://news.ycombinator.com/item?id=46450307)
- **arXiv system-level taxonomy (2025):** 15 hidden failure modes across reasoning, consistency, context, integration, and upstream/downstream categories. Key finding: "LLM reliability must be framed as a system-engineering problem rather than a model-centric one." — [arXiv:2511.19933](https://arxiv.org/abs/2511.19933)

## Gotchas

- **Passing a benchmark ≠ reliable in production.** The eval conditions in AgentBench, HELM, and MT-Bench are fundamentally different from continuous production operation. Treat benchmark scores as necessary-but-not-sufficient.
- **A single eval score hides everything.** Accuracy averaged across tasks hides the tasks where the agent catastrophically fails. Break eval down by task type, failure mode, and session length.
- **Self-reported confidence is unreliable.** Agents confidently produce wrong answers. Build behavioral checks (output validation, tool-call audits) that don't depend on the agent judging itself.
- **Context window is not the same as context retention.** The model can technically address more tokens than it actually maintains coherent task state across. Monitor actual task retention, not just token count.
- **Cost eval is often skipped.** Teams measure quality evals but skip cost-per-task. An agent that "works" but costs 10x a deterministic alternative is a deployment risk.
