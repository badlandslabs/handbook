# S-802 · The Agent Evaluation Stack: Measuring What Your Agent Actually Does in Production

You've shipped an AI agent. The benchmark score was 87%. Real users are getting 60% task completion, runaway loops that burn tokens, and mysterious failures that only surface on Mondays. This is the evaluation stack — how teams actually measure agent quality in production, not just at benchmark time.

## Forces

- **Trajectory matters more than output** — a wrong answer finished cleanly beats a right answer that deleted your database on the way
- **Model eval ≠ agent eval** — SWE-bench scores your base model; agent eval tests your scaffolding, tools, and error recovery together
- **Benchmarks lie in production** — same model swings 30–50 points with different scaffolding; contamination pushes vendors to stop reporting SWE-bench scores entirely
- **Pass@k vs. Pass^k** — allowing k attempts inflates scores; production costs you per attempt
- **Three state types to track** — conversation state (what was said), tool state (what was done), world state (what changed in the environment)

## The Move

The practitioner evaluation stack runs on three layers simultaneously:

1. **Benchmark suites** — use as directional signal, not purchase decisions. Run Pass@1 (single attempt) not Pass@k. Track Pass^k for reliability measurement.
   - **SWE-bench Verified** — software engineering tasks; prefer Verified over the original (contamination issues plagued the original). Use SWE-bench Pro for harder cases.
   - **GAIA** — real-world multi-step reasoning; human baseline already surpassed (March 2025)
   - **WebArena / OSWorld** — browser and OS interaction; Tau²-Bench for airline/HR ticket workflows
   - **AgentBench** — 8-environment multi-turn benchmark; gives you cross-domain signal, not deep signal in any one

2. **Custom golden datasets** — build your own eval set from real failure cases:
   - LLM-as-judge for fast scoring on objective criteria (format compliance, tool call correctness)
   - Human review for subjective quality (usefulness, coherence, safety)
   - Cost-benefit: automated eval covers 80% of cases, human review gates the last 20%

3. **Production observability layer** — independent from the agent framework, otherwise you can't catch the intent-execution gap:
   - **Token accounting** — track per-session token usage to catch runaway loops before billing surprises
   - **Trajectory logging** — every tool call, every decision point, every retry with timestamps
   - **Intent-execution gap detection** — monitor when the agent's stated plan diverges from what it actually did (the DataTalks/Replit failure pattern)
   - **Recovery rate** — what percentage of failures did the agent self-correct vs. fail silently?

## Evidence

- **Benchmarking Agents Review (Vol. III, Apr 2026):** SWE-bench Verified has a contamination problem; the "official leaderboard is JavaScript-rendered and lags the current frontier" — do not trust static score tables for purchase decisions — [benchmarkingagents.com](https://benchmarkingagents.com/agent-benchmarks/)
- **AnhTu.dev (May 2026):** Documents the 30–50 point swing from scaffolding alone, OpenAI's decision to stop reporting SWE-bench scores, and the Pass@1 vs Pass^k distinction — [anhtu.dev](https://anhtu.dev/ai-agent-benchmarks-2026-swe-bench-gaia-osworld-measure-true-capability-2249)
- **HN Ask "How are you monitoring AI agents in production" (4 months ago):** Practitioners report the pattern: "The deviation was visible in hindsight from the logs, but no system caught the intent-execution gap in real time." Consensus: observability must live in an independent execution layer, not inside the agent framework — [news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)
- **GetMaxim.ai:** Agent evaluation = output quality + tool usage + trajectory correctness + safety + operational performance across full sessions; distinguishes model eval (static, single-response) from agent eval (end-to-end, multi-turn, decision-making under error) — [getmaxim.ai](https://www.getmaxim.ai/articles/how-to-evaluate-ai-agents-a-practical-checklist-for-production/)

## Gotchas

- **Don't buy based on leaderboard scores.** The same model gets different scores with different scaffolding. Run the benchmark against your actual pipeline.
- **Three-state tracking is non-negotiable in production.** Conversation state (chat history), tool state (files read, APIs called), and world state (environment changes) must all be observable independently — losing any one creates invisible failure modes.
- **LLM-as-judge has a reflection problem.** Judges trained on similar data give inflated scores on structurally-similar outputs. Cross-validate with human spot-checks on ambiguous cases.
- **Pass^k is your reliability number.** Pass@1 is your cost number. Ship both metrics to stakeholders; don't let Pass@k obscure how often your agent actually succeeds on the first try.
