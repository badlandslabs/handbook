# S-2000 · The Agent Eval Gap — When 60% Pass Rate Really Means 25%

You shipped your agent. The eval suite passes. The demo works. In production it silently fails 75% of the time, and your dashboard still shows green because it only measures whether the agent ran — not whether it succeeded. The gap between agent eval and agent reality is where most projects die, and it is not obvious until you instrument the trace.

## Forces

- **Per-step compounding:** 95% per-step reliability over 20 steps = 36% end-to-end. Your agent looks great in benchmarks because benchmarks measure single-run pass@k, not multi-run consistency. A 95% reliable 20-step agent completes the full task only 36% of the time.
- **Outcome vs. trajectory blindness:** Standard monitoring checks "did the agent finish?" not "did it reason correctly?" Agents that return corrupted data still log as successful runs. A green dashboard is not a quality signal.
- **The self-correction trap:** Research through 2024–2025 consistently shows that prompting an LLM to "check your work" without external grounding degrades reasoning performance. Self-correction only works when grounded — unit test results, retrieval verification, tool-output comparison. Ungrounded self-correction is a false guarantee.
- **Eval is an afterthought:** 44% of agent evaluations happen pre-deployment only. 40.74% are continuous. Only 14.81% have post-deployment evaluation loops. Most teams ship evals that measure nothing that matters in production.
- **Gartner's reckoning:** 40%+ of enterprise agentic AI projects will be canceled by 2027. The cited causes are governance failures, ROI ambiguity, and inadequate risk controls — not model capability. Measurement failure is a business failure.

## The move

Measure agent reliability across three dimensions, not one. Track them in production, not just pre-deploy.

**1. Track pass^k (consistency), not just pass@k (peak performance).**
Pass@k measures "at least one of k attempts succeeds." Pass^k measures "all k attempts succeed." For production agents, pass^k is the real number: if your flight rebooking agent has a 70% single-run success rate, it succeeds on 8 consecutive runs only 6% of the time. Report both. A drop in pass^k across releases is a release gate, not a footnote.

**2. Instrument trajectory metrics alongside outcome metrics.**
Outcome metrics: Did the agent complete the task? Was the output accurate? Trajectory metrics: Did it call the right tools in the right order? Did it follow the reasoning path? Did it hit a dead end and recover or give up? Outcome tells you *if* it works. Trajectory tells you *why* it fails. Both are required.

**3. Place LLM-as-judge checks at three production boundaries — not everywhere.**
Three gates earn the cost: (a) before user-facing output, (b) before irreversible tool execution (writes, deletes, API mutations), (c) on writes to persistent memory. Do not judge every intermediate reasoning step — cost compounds fast. Use small distilled judges (3B–8B parameters: Luna-2, Prometheus 2, Patronus Lynx) for inline checking, which achieve 97% cost reduction at 0.88–0.95 accuracy versus GPT-4. Use frontier models (GPT-4o, Claude 3.5 Sonnet) for high-stakes verification only.

**4. Convert production failures into test cases automatically.**
Every flagged production trace (tool failure, wrong path, hallucinated tool call) is a candidate test case. Langfuse and similar tools support one-click conversion of production traces into eval datasets. Run regression evals against new model versions before shipping. A gap between old and new model pass@k is a signal. A gap in pass^k is a blocker.

**5. Measure failure modes by clustering, not by scanning traces.**
Run agents N times (minimum N=8 for meaningful pass^k data). Group failures by reason: "correctly routed to billing (4 runs)" vs. "hallucinated a support number (1 run)" vs. "tool timeout (2 runs)." This tells you *how* the agent fails, not just that it fails. Fix the largest failure cluster first.

**6. Run LLM-as-judge on production traffic, not just eval sets.**
Sample 5–10% of live traffic for continuous judge scoring. Set thresholds: score drop >10% from baseline triggers alert. This catches degradation from model updates, data drift, and adversarial inputs before they compound.

## Evidence

- **arXiv (2511.14136), Mehta 2025 — "Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems":** Found agent performance drops from 60% (single run) to 25% (8-run consistency). Analyzed 12 benchmarks across 6 leading agents. Identified three fundamental eval gaps: cost variation (50x cost differences for similar precision), reliability assessment, and missing multi-dimensional metrics. — https://arxiv.org/abs/2511.14136

- **Zylos Research, April 2026 — "LLM-as-Judge in Production: Agent Reasoning Verification, Self-Correction, and Hallucination Defense":** 57%+ of surveyed production agent teams now use judge LLMs. Small distilled judges (3B–8B) deliver 97% cost reduction at 0.88–0.95 accuracy vs GPT-4. Self-correction without external grounding degrades reasoning. Three production gate positions: before user output, before irreversible tool calls, before memory writes. — https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026/

- **Gartner Hype Cycle for Agentic AI, June 2025 — Beri 2026:** 40%+ of enterprise agentic AI projects will be canceled by end of 2027. Cited causes: escalating costs, unclear business value, inadequate risk controls, dirty data. No cited cause is a model failure — every failure mode is a governance and measurement failure. 95% of generative AI pilots do not deliver measurable financial returns (MIT Nanda Initiative). — https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027

- **Hacker News, Show HN — Trainly (kavin_key, 2025):** "The hardest part of selling observability for AI agents is getting people to believe they have a problem. 'My agent works fine' is the universal answer, right up until you actually look at the traces." — https://news.ycombinator.com/item?id=47867157

## Gotchas

- **Pass@k is not your reliability number.** It tells you whether retrying helps. Pass^k tells you whether your agent is trustworthy on a single attempt. Shipping with only pass@k data gives you false confidence.
- **Self-correction prompts backfire without grounding.** If you tell an LLM to "reconsider your answer" without feeding it unit test results, retrieval context, or tool output to verify against, it often confidently revises toward a worse answer. The correction must be grounded.
- **Eval sets go stale.** Production inputs drift from eval sets within weeks. Continuous sampling of live traffic for judge scoring is the only way to catch the gap before it becomes a failure spike.
- **Observability is not evaluation.** Tracing (LangSmith, Arize Phoenix, Langfuse) tells you what happened. Evaluation tells you whether what happened was correct. Teams buy observability and call it eval coverage — it is not.
