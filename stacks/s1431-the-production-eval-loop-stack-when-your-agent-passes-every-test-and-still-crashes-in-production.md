# S-1431 · The Production Eval Loop Stack · When Your Agent Passes Every Test and Still Crashes in Production

You've built a rigorous eval suite. Golden dataset passes. Rubric scores are green. The agent chose the right tools on the happy paths. The demo was solid. Then production happened — and you discover the agent is calling `localhost` in a cloud environment, hitting CVEs as hallucinations, and getting throttled by Reddit's rate limits. The eval set was a snapshot. Production is a river.

## Forces

- **The belief-execution gap is enormous.** 72% of AI teams say comprehensive testing drives reliability; only 15% achieve elite eval coverage (Galileo, 2025). Teams buy the platform and under-invest in the discipline.
- **Agent failures look like software bugs, not LLM mistakes.** When one team ran a benchmark-style eval, broken URLs dropped scores to 22, localhost calls stalled the agent at 46, and missing API keys caused silent failures. The agent's reasoning was fine — the plumbing was broken.
- **Eval sets age the day they ship.** Six drift modes erode eval signal over time: dataset drift, tool-API drift, prompt drift, retrieval-corpus drift, user-distribution drift, and agent-step compounding. A rubric written for v3 and frozen in git grades against a system now on v17.
- **Scaffold matters as much as the model.** AlphaEval (GAIR-NLP, April 2026) found the best agent product scores only 64.41/100 on production-grounded tasks — and that score varies more by scaffold choice than by model swap.
- **Offline evals can't catch production-specific failure modes.** Trajectory-aware evaluation (step-by-step reasoning chains, tool-call sequences, context management) is required — traditional accuracy metrics miss all of it.

## The Move

Build a closed production eval loop that treats traces as test cases and runs regression checks continuously, not just at deploy time.

**The four-dimensional trace score.** Rather than a single output quality score, measure four axes independently:
1. **Task completion** — did the agent finish the job?
2. **Step correctness** — was each tool call appropriate and correctly formed?
3. **Context fidelity** — did the agent use accurate, current information from retrieval?
4. **Output quality** — does the final deliverable meet the spec?

**Production traces → test cases automatically.** Instrument every production run to capture: full tool-call trajectory, intermediate outputs, error states, and final outcome. Flag low-confidence or error-heavy traces for human review, then promote the most instructive ones into the eval set (the "promote-back pattern").

**The Error Feed as loop closer.** Route agent errors — tool failures, rate limits, schema mismatches, unhandled edge cases — into a prioritized backlog reviewed on a weekly or bi-weekly cadence. Each error becomes a new eval case within 2 sprints.

**Dual scoring: code-based + LLM-as-judge.** Use deterministic code checks for things you can verify programmatically (tool called, argument shape correct, URL reachable, API response code). Use LLM-as-judge for qualities that require judgment: does the summary capture the key points, is the tone appropriate, did the agent reason soundly?

**Eval set refresh cadence.** Treat the eval set as a live artifact, not a git-frozen artifact. Recalibrate at minimum quarterly; continuously for high-stakes agents. The goal is eval-set half-life under 90 days.

**Regression budget per deploy.** Define a failure budget (e.g., "eval score must not drop more than 2 points on any axis") and gate deploys on it. This converts evaluation from a report into a gate.

## Evidence

- **HN thread:** "What broke when I tried to evaluate an AI agent in production" — Most failures from system-level issues (broken URLs → score 22, localhost in cloud → stalled at 46, missing API key → silent failure, Reddit blocking requests). Concluded eval loops for agents should look more like software testing: repeatable suites, clear pass/fail, CI integration. — [HN #47416033](https://news.ycombinator.com/item?id=47416033)

- **AlphaEval paper (GAIR-NLP, April 2026):** 94 production-sourced tasks across 6 O\*NET domains, evaluated against complete agent products (Claude Code, Codex, GitHub Copilot, Cursor). Best agent scores 64.41/100. Finding: scaffold choice matters as much as model choice. Contributes a requirement-to-benchmark construction framework for turning real production requirements into executable eval tasks. — [arXiv:2604.12162](https://arxiv.org/abs/2604.12162), [GitHub](https://github.com/GAIR-NLP/AlphaEval)

- **FutureAGI blog (2026):** "Your eval set is a snapshot. Production is a river." Documents six drift modes that age eval sets: dataset drift, tool-API drift, prompt drift, retrieval-corpus drift, user-distribution drift, and agent-step compounding. Proposes the promote-back pattern: production telemetry → eval set → regression gate. — [futureagi.com](https://futureagi.com/blog/agent-passes-evals-fails-production-2026)

## Gotchas

- **Don't evaluate outputs only — evaluate trajectories.** A correct final answer reached through a broken reasoning chain is a false positive. You need step-level visibility, not just end-state scoring.
- **LLM-as-judge introduces its own bias.** Judges have positional preferences (favoring first or last options), self-preference (scoring their own outputs higher), and are susceptible to prompt injection. Calibrate judges against human-labeled samples before trusting their scores.
- **Flaky tests are expected, not exceptional.** Agents are non-deterministic. Identical inputs produce different trajectories. Define statistical thresholds (e.g., pass if 4/5 runs succeed) rather than demanding 5/5.
- **Mocked tools give false confidence.** If your eval environment mocks tool responses, you're testing the agent's reasoning in a vacuum. Use real (or closely simulated) tool environments for production-critical evals — AlphaEval found tool-API drift is a top failure mode.
- **Eval coverage ≠ deployment readiness.** 72% of teams believe they have comprehensive eval coverage; only 15% actually do (Galileo, 2025). Buying an eval platform is not the same as building the evaluation discipline.
