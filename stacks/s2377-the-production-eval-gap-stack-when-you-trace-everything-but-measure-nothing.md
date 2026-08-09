# S-2377 · The Production Eval Gap Stack — When You Trace Everything but Measure Nothing

Your agent traces every session. Your observability platform shows every tool call, every token, every step in the trace. Your dashboards are green. You have no idea whether the agent is getting better or worse.

## Forces

- **Observability ≠ quality signal.** Tracing tells you what the agent did on one run. It tells you nothing about whether the change you shipped yesterday improved or degraded the system across the distribution of inputs you care about.
- **Benchmarks lie in production.** Standard agent benchmarks (SWE-bench, WebArena, AgentBench) measure research tasks in controlled environments. Production agents face requirement ambiguity, real-world tool drift, domain-specific edge cases, and users who don't phrase things the way benchmark tasks do. The research-production gap is substantial — the best model-scaffold configuration (Claude Code + Opus 4.6) scores only 64.41/100 on production-grounded tasks (AlphaEval, 94 tasks from 7 companies).
- **Agent behavior is a distribution, not a point estimate.** Unlike traditional software where the same input always produces the same output, LLM-based agents produce different outputs across runs. A single evaluation pass is nearly meaningless; you need statistical coverage.
- **Traditional CI can't catch silent regressions.** A prompt change, a model version bump, a modified tool definition — none of these produces a stack trace. They produce degraded task completion rates that surface in user complaints days or weeks later.

## The move

**Build an eval system that gates prompt and config changes, not just code changes — and measure at the session, trace, and step levels.**

### The three-level measurement framework (from Galileo's eval engineering survey, 500+ practitioners)

| Level | Measures | Answer it gives |
|---|---|---|
| **Session** | Overall goal achievement | "Did the user get what they needed?" |
| **Trace** | Multi-step reasoning chains, tool call sequences | "Did the agent plan and execute correctly?" |
| **Step** | Individual tool calls, tool selection accuracy | "Did this specific action succeed?" |

### Eval gate in CI/CD

Every prompt change, model swap, or tool definition modification must pass an eval gate before merging. The gate runs against a golden dataset — ideally built from real production failures (bad outputs converted to test cases) rather than synthetic examples. Teams that build eval infrastructure before the first production task consistently reach stable operation faster.

### LLM-as-judge with human calibration

LLM-as-judge scales scoring when criteria are well-defined (single criterion, scoring anchors, strict output format, bias warnings). It works for accuracy and groundedness scoring. But automated judges must be calibrated against human judgments — technical metrics dominate 83% of current eval research; injecting human-in-the-loop evaluation corrects systematic biases.

### Production-grounded benchmarks over research benchmarks

For domain-specific agents, supplement leaderboard benchmarks with tasks drawn from actual production requirements. AlphaEval's framework for building production-grounded benchmarks (94 tasks across 6 O*NET occupational domains) shows that domain performance varies dramatically: scores of 62.0 in some domains versus much lower in others for the same agent configuration.

## Evidence

- **Industry survey:** 72% of AI teams strongly believe comprehensive testing drives reliability, yet only 15% achieve elite eval coverage (90–100% of behaviors tested). The gap is operational, not knowledge-based. — *Galileo, State of Eval Engineering Report, 2026* — https://galileo.ai/blog/ai-agent-metrics
- **Production performance gap:** The best model-scaffold configuration (Claude Code + Opus 4.6) achieves only 64.41/100 on production-grounded tasks, vs. much higher scores on research benchmarks. Scaffold choice produces an 11–15 point spread for the same underlying model. — *AlphaEval: Evaluating Agents in Production (arXiv:2604.12162), SII-GAIR / SJTU / MiraclePlus, April 2026* — https://arxiv.org/abs/2604.12162
- **Observability-to-eval gap:** 89% of production agent teams have tracing/observability; only 52% run evals; only 38% run an eval on every prompt change. — *LangChain State of Agent Engineering survey (~1,300 practitioners, late 2025), via r/AI_Agents discussion* — https://old.reddit.com/r/AI_Agents/comments/1upn21x/in_production_89_of_agent_teams_have/
- **Benchmark limitations:** SWE-bench Verified has known contamination. Benchmark tasks saturate quickly as models improve. Static pre-defined benchmarks increasingly fail to differentiate emerging models. — *Paperclipped, "AI Agent Benchmarks Explained," March 2026* — https://www.paperclipped.de/en/blog/ai-agent-benchmarks-swe-bench-webarena/

## Gotchas

- **Running an eval once is not eval.** A single pass against a golden dataset gives you a point estimate. You need repeated runs to capture variance, and regression testing across versions to catch drift.
- **Golden datasets rot.** Synthetic test cases created at design time don't reflect what the agent actually fails on in production. Continuously update your golden set from real failures.
- **LLM-as-judge has a self-preference bias.** Models tend to score their own outputs higher. Calibrate judges against human ratings, or use ensemble adjudication.
- **Agent-native CI != code CI.** Standard CI pipelines that check unit tests and linting won't catch prompt regressions, model downgrades, or tool schema drift. You need separate eval gates for non-deterministic components.
- **Task success rate alone is insufficient.** Two agents can both achieve the same task success rate with entirely different trajectories. One might fix the right file with the right patch; the other might never localize the bug and edit unrelated code. You need trajectory-level metrics to understand *how* the agent succeeded or failed, not just *whether*.
