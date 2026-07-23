# S-1551 · The Agent Evaluation Stack — When Your Agent Succeeds in Tests and Fails in Production

Your agent scores 94% on your internal benchmark. You ship it. Three days later it has corrupted a customer's data, spent $14,000 on API calls, and no one noticed for two days because the monitoring dashboard showed green. The benchmark tested the wrong thing. This is the evaluation gap — the systematic mismatch between how agents are tested and how they actually fail.

## Forces

- **Agents are systems, not models.** Traditional LLM metrics (BLEU, ROUGE, single-turn accuracy) evaluate text output. Agents plan, call tools, modify external state, and compound decisions across multiple turns. The same fundamental mismatch that makes agents powerful makes them impossible to evaluate with old tools.
- **Benchmarks measure potential, not reliability.** Enterprise agents achieve ~60% success on single runs, dropping to ~25% across eight runs (Galileo, 2026). Standard benchmarks report the single-run number. Production operators need the eight-run number.
- **Trajectory quality is invisible to outcome metrics.** An agent can reach the right answer through the wrong reasoning and pass an outcome eval — while being one prompt change away from reaching the wrong answer through the same wrong reasoning. Outcome metrics tell you if the agent works; trajectory metrics tell you why it might not.
- **Evaluation is a moving target.** Agents are non-deterministic. Identical inputs produce different outputs on different runs. This isn't noise — it's a fundamental property that requires statistical evaluation, not binary pass/fail.

## The move

Separate evaluation into three distinct layers, each answering a different question. Run them together in a continuous pipeline from offline development to live production monitoring.

**Layer 1 — Node-Level Precision (Micro)**
- Measure individual tool calls, retrieval steps, and single LLM decisions
- Track: correct tool selection, valid parameters, retrieval precision/recall, hallucination detection per step
- Use deterministic checks where possible (schema validation, ground-truth comparisons) before reaching for LLM-as-judge
- Run this on every test case, every commit

**Layer 2 — Session-Level Outcomes (Meso)**
- Measure complete agent sessions: task success rate, trajectory quality, recovery behavior
- Track: did the agent reach the goal, how many steps did it take, did it recover gracefully from tool failures, how consistent is it across multiple runs of the same task
- Use LLM-as-judge with a calibrated rubric: define explicit criteria (helpful, correct, complete) and use chain-of-thought prompting so the judge explains its reasoning
- Calibrate the judge against human judgment on a small sample first — LLM judges consistently show 0.8–0.9 correlation with human preferences at aggregate level but can be gamed on individual cases (Microsoft LLM-as-Judge research, 2025)
- Target 20–50 eval cases minimum for statistical significance on pass/fail decisions

**Layer 3 — System Efficiency (Macro)**
- Measure cost, latency, token usage, and error rates at the infrastructure level
- Track per-tool cost breakdown, average trajectory length, time-to-first-useful-step
- Set automated alerts on cost spikes, latency regressions, and error rate thresholds
- This layer is the early warning system that catches silent runaway spending

**The evaluation pipeline:**
- Offline: run Layer 1 + 2 against curated test datasets before every deployment
- Shadow mode: run Layer 2 against a sample of production traffic in parallel (no user impact)
- Online: run Layer 3 as production monitoring with Layer 2 scoring on sampled traces
- Human review loop: route 5–10% of flagged sessions to human evaluators; feed corrections back into the test dataset

**Frameworks that implement this pattern:**
- **DeepEval** (Confident AI, 17K+ GitHub stars): pytest-style agent evaluation with G-Eval, task completion, answer relevancy, hallucination metrics. Runs locally, integrates with CI/CD.
- **LangSmith** (LangChain): trace-based evaluation pipeline with LLM-as-judge, online evals, and production monitoring in a single platform.
- **Langfuse**: open-source alternative to LangSmith with evaluation, tracing, and production monitoring.
- **Microsoft Agent Framework** (Azure AI Foundry): built-in evaluation with local fast checks + cloud-based production-grade assessors.

## Evidence

- **Benchmark analysis:** SWE-bench introduced pass/fail as the standard for coding-agent evaluation, with the first agent-based system (SWE-agent) scoring 12.47%. SWE-bench Verified later fixed annotation bugs and became the canonical cleaned version. Modern coding agents (Claude Code, Devin, Cursor agents) are evaluated on pass rate across realistic software engineering tasks including PR-level work — [SWE-bench](https://www.swebench.com/original.html), [Presenc AI Coding Agent Benchmarks 2026](https://presenc.ai/research/coding-agent-benchmarks-2026)
- **Industry research:** Enterprise agents achieve 60% success on single runs, dropping to 25% across eight runs. Trajectory metrics expose reasoning failures invisible to outcome metrics alone. Gartner projects 40% of enterprise AI project cancellations by end of 2027 trace to inadequate evaluation rather than model capability gaps — [Galileo AI, "Agent Evaluation Framework," Feb 2026](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks), [Thinking Inc, "AI Agent Evaluation in Production," 2026](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/)
- **LLM-as-judge research:** GPT-4 judges show 0.8–0.9 Spearman correlation with aggregate human preferences (LMSYS Chatbot Arena data). However, single judges have known biases and can be gamed by adversarial outputs. Chain-of-thought prompting improves consistency. Calibration against human judgment is required for high-stakes decisions — [Microsoft LLM-as-Judge, GitHub](https://github.com/microsoft/llm-as-judge), [arXiv:2508.02994 "When AIs Judge AIs"](https://arxiv.org/pdf/2508.02994)

## Gotchas

- **Don't use single-run pass/fail as your primary metric.** Run the same test case 5–10 times and report the success rate distribution. If your agent works 1/5 times, it doesn't work — regardless of what one benchmark run says.
- **Benchmarks measure potential, not production reliability.** WebArena, GAIA, and SWE-bench tell you what a well-engineered agent can do in ideal conditions. They don't tell you what your agent will do on your specific users' inputs with your specific tool implementations.
- **LLM-as-judge needs calibration before trust.** Run your judge on 10–20 human-evaluated cases first. If the judge disagrees with humans more than 15% of the time, the rubric needs refinement. An uncalibrated judge gives you false confidence.
- **Evaluation data rots.** User inputs shift, expected behavior changes, edge cases accumulate. Re-evaluate your test dataset quarterly. A eval suite that hasn't been touched in six months is measuring yesterday's agent against yesterday's requirements.
