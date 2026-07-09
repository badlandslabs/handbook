# S-845 · The Agent Evaluation Stack — When You Can't Tell If Your Agent Is Getting Better

A senior engineer shows you a dashboard of agent response times, token counts, and API error rates. Everything is green. The agent is clearly failing in production — wrong documents retrieved, tasks completed incorrectly, the same mistake repeated three times in one session. None of the metrics caught it. The model returned 200, the latency was fine, the cost was within budget. The quality crater was invisible because no one was measuring quality.

Agent evaluation is the discipline of knowing whether your agent is actually working — not just whether it's running, but whether it's working correctly, safely, and efficiently across the full distribution of tasks it will encounter.

## Forces

- **Agents are non-deterministic** — the same input can produce different tool calls, different trajectories, and different outputs across runs. Traditional ML test/eval paradigms (input → output → compare to ground truth) collapse when the agent's reasoning path matters as much as the final answer.
- **The regression cliff is invisible without coverage** — a prompt tweak, a model version bump, or a tool schema change can silently degrade an agent's behavior on 15% of task types. Without a regression eval suite, this surfaces only in production complaints.
- **LLM-as-judge has bias failure modes** — position bias (prefers first/last answer), self-preference bias (favors outputs similar to the judge's own style), length bias (longer responses score higher). These don't show up in small eval sets.
- **Trajectory length makes long-horizon eval hard** — coding agents, research agents, and customer support agents can generate traces spanning hundreds of tool calls and hundreds of thousands of tokens. An LLM judge asked to evaluate the entire trace loses coherence mid-way.
- **Context window growth hasn't solved eval quality** — SWE-bench benchmarks show 49% → 80% improvement (Claude, one year), but these are narrow coding tasks. Real agent deployments encounter distribution shifts, ambiguous goals, and edge cases no benchmark captures.
- **The compounding failure math** — 98% per-step reliability across 10 steps yields ~82% end-to-end reliability. Without step-level eval, you don't know which steps are the failure points.

## The Move

Build a layered evaluation harness with deterministic guards at the fast/cheap tier and LLM-judge verification at the quality tier.

**Establish a metric hierarchy before writing a single eval:**

- **Correctness** — Did the agent achieve the intended outcome? (pass/fail, state verification)
- **Safety** — Did the agent make inappropriate tool calls, hallucinate facts, or violate constraints? (rule-based + LLM-judge)
- **Efficiency** — How many tool calls, tokens, and dollars per task? (automatic, cheap)
- **Quality** — Is the output actually good, not just non-wrong? (LLM-judge, expensive)

**Run regression evals on every change.** Every prompt tweak, model version bump, or tool schema change runs the full eval suite before shipping. Treat the eval suite as CI — a red suite means no deploy. Budget 3–6 weeks to build the initial harness; teams consistently underestimate this.

**Verify steps against environment state, not just trajectory.** For long traces, break the eval into step-level checkpoints. At each checkpoint, assert that the environment state matches the expected state. A coding agent that ran `git commit` should have a verifiable commit in the git log. A customer support agent that "escalated" should have a ticket in the system. This converts the agent's self-reported actions into ground-truth facts.

**Use hybrid eval: deterministic + LLM-judge.** Deterministic checks (schema validation, regex extraction, API response codes, git state) run in milliseconds and catch obvious failures. LLM-judge runs on a sampled subset and on every failure, catching qualitative issues the deterministic layer misses. This cuts LLM-judge costs by 90%+ while maintaining coverage.

**Choose judge size by stakes, not preference.** Large proprietary judges (Claude 3.7 Sonnet, GPT-4o) for high-stakes final verification — customer-facing outputs, safety decisions, financial transactions. Small distilled judges (Luna-2 3B–8B, Prometheus 2 7B, Patronus Lynx 8B) for inline high-throughput checks — catching hallucinated tool arguments before execution, routing decisions, formatting checks. Small distilled judges deliver 97% cost reduction at 0.88–0.95 accuracy against human labels.

**Calibrate LLM judges with golden examples.** Take 20–50 known-good and known-bad outputs from your domain. Score them yourself (or with a human expert). Use these as calibration anchors for the judge. Without calibration, position bias and self-preference bias corrupt scores until they are worse than random.

**Track trajectory length as an early warning signal.** An agent that starts taking 3× longer than baseline is usually looping, hitting a dead-end tool, or encountering a context overflow. Set thresholds: alert at 2× median, rollback recommendation at 5× median.

**Build custom evals for your domain.** Generic benchmarks (MMLU, GPQA) do not predict agent performance in your specific task distribution. A customer support agent needs evals against your actual support ticket distribution. A coding agent needs evals against your codebase's actual patterns. SWE-bench is useful for directional signal only.

## Evidence

- **Anthropic engineering blog:** "Without evals, it's easy to get stuck in reactive loops — catching issues only in production, where fixing one failure creates others. Evals make problems and behavioral changes visible before they affect users, and their value compounds over the lifecycle of an agent." Covers the shift from single-turn prompts (2024) → workflows (mid-2024) → agentic architectures with tool loops (late 2024-2025). — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **HN discussion (Ask HN, 128 points):** A practitioner who owned a coding agent eval suite: "LLM as judge is fundamentally flawed without a calibration set. Position bias is real — GPT-4o consistently scores the first answer highest, regardless of quality. Calibrate against 20–50 known examples." — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)
- **TDS / Intuz (100+ enterprise deployments):** "Three months into a healthcare AI deployment, our client's compliance officer asked us: 'How do you know your agent isn't hallucinating patient symptoms?' We had unit tests and integration tests. We had a model that performed beautifully on the demo dataset. What we didn't have was an evaluation harness." — [towardsdatascience.com](https://towardsdatascience.com/building-an-evaluation-harness-for-production-ai-agents-a-12-metric-framework-from-100-deployments)
- **Zylos Research (Apr 2026):** "LLM-as-judge has crossed from evaluation harness territory into load-bearing production infrastructure. More than half of surveyed production agent teams now rely on judge LLMs at runtime for quality gating, hallucination defense, and tool-call verification." Documents six patterns and the small/large judge bifurcation with cost-accuracy data. — [zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026)
- **Judgment Labs (May 2026):** "LLM judges break down on long-horizon agents for three reasons: long trajectories (hundreds of tool calls, millions of tokens), stateful actions (judge sees trajectory but not environment), and mid-trajectory errors (judge attention degrades after 30+ steps). Agent Judge solves this by checking actions against environment state, not just the trajectory text." — [judgmentlabs.ai/blogs/agent-judge-solving-long-context-evaluations](https://www.judgmentlabs.ai/blogs/agent-judge-solving-long-context-evaluations)
- **RaftLabs (Nov 2025):** 57% of organizations have agents in production; 89% of teams have observability; only teams with evaluation harnesses report measurable productivity gains. — [raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## Gotchas

- **Generic benchmarks don't predict domain performance.** MMLU and GPQA scores have near-zero correlation with your agent's performance on your specific task distribution. Build domain-specific eval sets or accept that benchmark performance is theater.
- **LLM judges have systematic biases that require calibration.** Position bias, self-preference bias, and length bias are documented failure modes. Run a golden calibration set (20–50 labeled examples) before trusting judge scores on anything high-stakes.
- **Long-horizon eval requires state verification, not just trajectory review.** Judging the entire trace text fails after ~30 tool calls. Check the environment state (database records, file system, API calls) against expected outcomes at each step boundary.
- **Eval overfitting is a real risk.** An agent that scores 95% on your eval suite but fails in production is a signal that your eval suite doesn't cover the real distribution. Evals must be refreshed against production failure cases, not just curated for success.
- **Silent success is the worst failure mode.** The agent returns "completed" with no error, but completed the wrong task, the wrong customer's data, or with hallucinated facts. Every success-path output needs sampling, not just failure-path.
