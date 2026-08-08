# S-2352 · The Eval Stack — Why Your Agent Passes Tests and Fails Production

When your agent works in the dev environment but silently degrades in production — same model, same prompt, different behavior.

## Forces

- **Single-run pass/fail is a lie.** Agents are stochastic. A one-time pass on one query set tells you nothing about consistency. An agent that scores 6/10 every time looks identical to one that scores 0/10 or 10/10 depending on luck.
- **The benchmark gap is real and quantified.** Agents achieving 60% pass@1 on tau-bench show only ~25% consistency across multiple trials — a 35-point collapse that benchmark reports don't surface.
- **Trajectory quality is invisible to final-answer eval.** A correct answer reached in 20 steps with two policy-violating intermediate calls is a failing trajectory. Standard BLEU/ROUGE metrics miss this entirely.
- **The harness is part of the system.** Scaffold decisions — when to execute, how to format context, how long to let the agent run, whether to retry — swing scores 10–20 percentage points for the same model.
- **Human review doesn't scale but is irreplaceable for calibration.** Automated eval gives scale and repeatability; human judgment catches tone, trust, and contextual appropriateness.

## The move

Build a layered evaluation system before you build the agent. Three layers, run at different cadences, covering different failure modes.

### Layer 1 — Final-Answer Evaluation
Score the last message against an expected result. Use deterministic checks where possible (regex, exact match, JSON schema validation). Supplement with LLM-as-judge for open-ended quality. Run on every commit.

### Layer 2 — Trajectory Evaluation
Score the *sequence* of steps: which tools were called, in what order, with what arguments, how many steps total, were there loops or recovery attempts. This is where policy violations, excessive token usage, and routing errors surface. Trajectory eval requires trace capture infrastructure (LangSmith, Phoenix, or equivalent).

### Layer 3 — Per-Turn Classification
Label every turn individually: tool-call correctness, argument validity, hallucination signals, policy compliance. Per-turn labels feed RL reward models, fine-tuning data, and failure regression suites. This is the layer that closes the production-to-training signal loop.

### The Swiss Cheese Model — Don't Rely on One Eval Layer
Production-grade evaluation stacks uncorrelated failure modes:
1. **Automated eval** (deterministic + LLM judge) — every commit, fast
2. **Production monitoring** (real traffic, actual outcomes, user ratings) — continuous
3. **Periodic human review** (calibration sample, weekly) — catches judge drift

When the judge and humans disagree, the judge prompt needs revision, not the agent.

### Pass@k vs Pass^k — Measure Both
- **pass@k** (capability ceiling): at least one of k attempts succeeds. Rises with k — at large k, even unreliable agents look good. Use for benchmarking against other systems.
- **pass^k** (consistency): how often the agent succeeds *every time* across k trials. Dominated by reliability. Low pass^k with high pass@k signals an agent that "can but doesn't reliably." Fix with better instructions, lower temperature, or added verification steps — not retraining.

### Start Small — 20 Queries, Not 200
Early-stage development shows 30–80% improvements from single prompt tweaks. Twenty curated queries covering the golden path and known edge cases are sufficient to measure these large effect sizes. Two hundred queries slow iteration before the agent works.

### LLM-as-Judge Has 4 Known Failure Modes
From Zylos Research's survey of production teams (2026): position bias (judge favors first/last position), verbosity bias (judge rewards longer answers), self-preference bias (judge favors its own reasoning style), and calibration drift (judge standards shift over time). Mitigation: use a different model family as judge, run calibration samples against human judgment, and prefer small fast judges (3B–8B distilled) for inline checks and large proprietary judges (Claude 3.7, GPT-4o) for high-stakes gate decisions.

## Evidence

- **ACM KDD Survey (2025):** Two-dimensional taxonomy organizing agent evaluation along evaluation objectives (behavior, capabilities, reliability, safety) and evaluation process (interaction modes, datasets, metrics computation, tooling, environments). Confirms evaluation is fundamentally different from standard LLM benchmarks. — [arXiv:2507.21504](https://arxiv.org/abs/2507.21504)

- **InfoQ Article (March 2026):** Documents the gap between agent evaluation in controlled environments vs. production. Key finding: "Agents are systems, not models — evaluate them accordingly." BLEU/ROUGE and single-turn accuracy metrics fail to capture how agents fail in production (e.g., silent error swallowing in tool-call chains). — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)

- **LangChain Blog / Harrison Chase + Sam Crowder (Feb 2026):** Agents accept unbounded natural language input and exhibit non-deterministic behavior. Traditional APM tools (Datadog, New Relic) fall short for agent-specific requirements. Agents need trace-level observability that captures every model call, tool invocation, and intermediate state — not just system metrics. — [langchain.com/blog/production-monitoring](https://www.langchain.com/blog/production-monitoring)

- **Zylos Research (April 2026):** 57%+ of surveyed production agent teams now use judge LLMs at runtime as load-bearing infrastructure. Six distinct patterns: offline eval, online runtime verifier, self-consistency loops, Reflexion, constitutional AI/RLAIF, and inference-time reward models. Four LLM-as-judge failure modes documented with mitigations. — [zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026)

- **MorphLLM (2026):** tau-bench demonstrates that 60% pass@1 agents exhibit ~25% consistency across trials — the benchmark reliability gap is 35 percentage points. Recommends three-layer eval (final-answer, trajectory, per-turn) and per-turn labels as the foundation for RL fine-tuning. — [morphllm.com/ai-agent-evaluation](https://www.morphllm.com/ai-agent-evaluation)

- **agentpatterns.ai:** pass@k and pass^k are distinct metrics measuring capability ceiling and reliability respectively. If pass@k is high but pass^k is low, fix with better instructions, lower temperature, or added verification steps — not retraining. — [agentpatterns.ai/verification/pass-at-k-metrics](https://www.agentpatterns.ai/verification/pass-at-k-metrics/)

- **The LLM Stack (open-source book):** SWE-bench, ToolBench single-run success rates systematically overestimate production reliability. "The harness is part of the system" — scaffold decisions swing scores 10–20 percentage points for the same model. — [prakashkagitha.github.io/llm-stack-book](https://prakashkagitha.github.io/llm-stack-book/08-agents-harness/08-agent-evaluation.html)

- **Braintrust:** CI/CD quality gates built natively into the platform — GitHub Action evaluates every PR and blocks merges when scores drop below threshold. DeepEval provides open-source CI/CD integration. — [braintrust.dev/articles/deepeval-alternatives-2026](https://www.braintrust.dev/articles/deepeval-alternatives-2026)

- **LangSmith CI/CD documentation:** Automated pipeline with trigger types (code change, prompt commit, online eval alert, PR opened), quality-gated staging and production promotions, and continuous evaluation alerting. — [docs.langchain.com/langsmith/cicd-pipeline-example](https://docs.langchain.com/langsmith/cicd-pipeline-example)

## Gotchas

- **Don't stop at final-answer eval.** The correct answer via a wrong, expensive, or policy-violating path is a failing agent. Trajectory-level and per-turn evaluation are not optional — they are where most production failures live.
- **LLM-as-judge is not ground truth.** It's a scalable approximation that drifts. Calibrate it against human judgment on a periodic sample, and treat it as one layer in a multi-layer stack, not the only signal.
- **pass@k overstates reliability.** At large k, almost any non-zero-capability agent eventually succeeds. Use pass^k (consistency) as your headline reliability metric for production-readiness decisions.
- **Offline benchmarks miss production distribution.** Your real queries differ from curated benchmarks. Automated eval on curated test sets catches regressions; production monitoring on real traffic catches what automated eval doesn't.
- **The harness gap is invisible.** When switching scaffolding or orchestration frameworks, expect 10–20 point swings even with the same model. Treat the harness as a first-class evaluation target, not a detail.
