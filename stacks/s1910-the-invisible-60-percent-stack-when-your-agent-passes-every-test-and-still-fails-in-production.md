# S-1910 · The Invisible 60 Percent Stack

When your agent passes its eval suite and still breaks in production — because traditional testing treats a non-deterministic, multi-step, tool-using system as a deterministic function.

## Forces

- **Agents are systems, not models.** Single-turn accuracy metrics and classical NLP benchmarks (BLEU, ROUGE) don't capture how agents fail in practice — through reasoning chains, tool call sequences, and emergent behaviors under production load.
- **Lab performance diverges from reality.** Enterprise data shows a 37% performance gap between benchmark scores and production outcomes, alongside 50x cost variation across different agent configurations for equivalent accuracy.
- **Reliability collapses under repetition.** An agent passing a single test run at 60% can drop to 25% pass rate across 8 consecutive runs — a 58% reliability collapse that single-run evaluation never surfaces.
- **Evaluation is treated as a launch checklist, not an operational practice.** Teams that stop monitoring post-launch consistently see quality degradation within 30–60 days.

## The move

Separate trajectory evaluation (the reasoning chain) from outcome evaluation (the final result), instrument both layers continuously, and use LLM-as-judge as a scalable grader — not a substitute for human judgment on trust-sensitive dimensions.

- **Define the transcript, not just the output.** Log the full message array: tool calls, reasoning traces, intermediate results, final state. "What the agent says it did" and "what actually changed in the environment" are different things.
- **Measure trajectory AND outcome.** Trajectory metrics catch reasoning failures (wrong tool selected, missing step, premature termination); outcome metrics catch end-state failures (wrong data written, corrupted output). One without the other leaves blind spots.
- **Use domain-matched benchmarks selectively.** SWE-bench Verified for coding agents (bash-tool-only harness, minimal confounders); GAIA for general web/research tasks (competitive: Level 1 ≥70%, Level 2 ≥45%, Level 3 ≥25%); WebArena for browser-based agents. Don't use generic benchmarks as proxy for domain-specific reliability.
- **Implement LLM-as-judge targeting 0.80+ Spearman correlation with human judgment.** Pair with a separate judge model to reduce self-grading bias. The judge scores assertions like "did the agent select the correct tool?" and "did it recover gracefully from the failure?" — not just "was the final answer correct?"
- **Build a custom eval suite from real production failures.** Every bug that reaches production should have a corresponding eval that would have caught it. This closes the feedback loop: evals are not a gate — they are a living record of failure modes.
- **Integrate into CI/CD with three trigger types:** commit-triggered (pre-merge), scheduled (nightly regression), and event-triggered (on production anomaly). A 60-day evaluation gap between deploy and regression is enough for a broken agent to become production default.

## Evidence

- **Anthropic Engineering (Jan 2026):** Defines the eval taxonomy — Task (test case with success criteria), Trial (attempt), Grader (assertion logic), Transcript (full message array), Outcome (environment state not agent output). Emphasizes that "outcome is what actually changed, not what the agent says changed." — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **The Operator Collective / AWS ML Blog (2026):** Reports 60% single-run pass rate collapsing to 25% across 8 consecutive runs (58% reliability gap). States Gartner predicts over 40% of agentic AI projects will be canceled by end of 2027 due to evaluation failures. Notes traditional LLM eval methods treat agents as black boxes — evaluating only final output, ignoring reasoning chain and tool selection. — [https://theoperatorcollective.org/blog/ai-agent-evaluation-measure-agent-performance](https://theoperatorcollective.org/blog/ai-agent-evaluation-measure-agent-performance)
- **InfoQ / Amit Kumar Padhy (Mar 2026):** Documents the hybrid eval approach used at Sevdesk — combining reference-free scoring (helpfulness via LLM judge) with reference-aware scoring (correctness against known-good outputs). Recommends using a separate judge model to reduce self-grading bias. Emphasizes operational constraints (latency, cost per task, token efficiency, tool reliability) as first-class evaluation targets. — [https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned)
- **Zylos Research / Galileo Labs (2026):** UC Berkeley research found eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) all exploitable for near-perfect scores without solving the underlying task. GAIA SOTA (2025): best open-source agents score 55% overall vs. 92% human baseline. — [https://zylos.ai/research/2026-05-13-ai-agent-evaluation-benchmarking](https://zylos.ai/research/2026-05-13-ai-agent-evaluation-benchmarking)
- **Galileo Labs — Pratik Bhavsar (Feb 2026):** Proposes 3-tier rubric framework: 7 evaluation dimensions → 25 sub-dimensions → 130 rubric items. Recommends SWE-bench Verified for coding agents, WebArena for web interaction, GAIA for general assistants. — [https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

## Gotchas

- **Benchmark scores ≠ production reliability.** A benchmark scores how an agent performs on a curated task distribution. Production surfaces the long tail of edge cases the benchmark never included. Build evals from your actual failure modes, not from leaderboard scores.
- **A green dashboard with no trajectory visibility is a false signal.** Monitoring that shows "agent completed every task" while returning corrupted data is worse than a visible failure — it delays detection. Instrument the trace, not just the outcome.
- **LLM-as-judge introduces judge-model bias.** If the judge model is the same family as the agent model, it will be systematically overgenerous. Use a distinct judge model and validate judge accuracy against human labels before deploying at scale.
- **One-time evaluation is not evaluation.** A pre-launch eval suite with no post-deployment monitoring will diverge from production behavior within 30–60 days as the model, tools, and data drift.
- **The 58% reliability collapse is invisible without multi-trial runs.** If you only test each task once, you will overestimate reliability by a large margin. Run each eval task 5–8 times and measure variance, not just mean score.
