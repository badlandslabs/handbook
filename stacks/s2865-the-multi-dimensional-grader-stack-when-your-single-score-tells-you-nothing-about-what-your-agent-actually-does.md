# S-2865 · The Multi-Dimensional Grader Stack — When Your Single Score Tells You Nothing About What Your Agent Actually Does

Your agent scores 91% on your eval suite. Your team celebrates. Your on-call rotation starts Thursday. You have no idea why customers are complaining about the same failure mode that appeared last week — because your grader outputs a single number, and a single number cannot capture the three things that actually matter: whether the agent completed the task, whether it used the right tools, and whether it produced output that is factually grounded.

The multi-dimensional grader stack disaggregates "pass/fail" into orthogonal signal layers — task completion, trajectory correctness, and output quality — so that regressions are caught not just in aggregate, but by the specific failure mode that caused them.

## Forces

- **One number masks multiple failure modes.** An 87% pass rate could mean 13% of tasks are catastrophic failures or 13% have cosmetic tone issues. You can't prioritize fixes without knowing which.
- **Grading strategy must match agent type.** A coding agent's success looks nothing like a customer-service agent's. Graders built for one domain produce misleading signals in another.
- **Multi-turn evaluation is not a scaled-up single-turn.** The trajectory — the sequence of tool calls and state changes — is the unit of measurement for agents, not the final output. This requires fundamentally different grader logic.
- **LLM-as-judge introduces judge variance.** The grader itself is non-deterministic. Without stochastic evaluation (multiple trials, pass-rate thresholds instead of binary pass/fail), you measure noise as signal.

## The move

Design a layered eval architecture that grades each dimension independently, using the right grader type for each layer:

- **Task completion** — use deterministic assertions (state checks, output schema validation) wherever possible. When the agent must reach a measurable end state, hard criteria beat LLM judgment.
- **Trajectory correctness** — assert on the sequence and arguments of tool calls. Did it call the right tools in the right order? Were the arguments valid? This catches silent drift before output quality degrades.
- **Output quality** — use LLM-as-judge for natural language assessment (tone, relevance, coherence). Run multiple trials and report pass-rate, not binary pass/fail, to account for LLM judge variance.
- **Dimension-specific thresholds.** Each layer gets its own pass threshold and alerting budget. Task completion might require 95%+ (hard constraint); output quality might tolerate 80% (soft constraint). Conflating them into one score hides which constraint is binding.
- **Match grader to agent archetype.** Coding agents: trajectory + deterministic output checks. Conversational agents: turn-count constraints + multi-dimensional LLM rubric. Research agents: faithfulness metrics against source documents. One-size grading produces one-size misleading signals.

## Evidence

- **Anthropic Engineering (Jan 2026):** Their three-component eval design — Task, Trial, Grader — defines Grader as "logic that scores some aspect of the agent's performance." They explicitly recommend **different grader types for different dimensions**: code-based checkers for deterministic properties, LLM-as-judge for subjective quality, and state inspection for completion. They also stress multi-trial evaluation for stochastic agents: "assert on pass _rate_, not pass/fail." — [Anthropic · Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **AWS Strands Evals (2025):** Their framework implements three built-in evaluator categories: **deterministic** (exact match, schema validation), **model-based** (LLM rubric scoring), and **reference-based** (golden output comparison). Crucially, they layer an **ActorSimulator** for multi-turn conversations — an LLM-driven user that drives the agent through realistic interaction flows — because "real users don't follow scripts." — [AWS · Evaluating AI Agents for Production: Strands Evals](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-for-production-a-practical-guide-to-strands-evals/)
- **Thoughtworks (Aug 2025):** Their three-layer eval architecture — unit evals (component-level), snapshot evals (behavioral regression), and production observability (continuous monitoring) — shows how dimension separation maps to cadence. Unit evals run on every commit; snapshot evals gate releases; production evals run continuously. Each layer uses different grading rigor and tolerance. — [Thoughtworks · Evaluating AI Agents in Production](https://www.thoughtworks.com/en-au/insights/blog/machine-learning-and-ai/Evaluating-AI-agents-in-production)

## Gotchas

- **LLM-as-judge variance is real.** An agent that scores 84% today might score 79% tomorrow from judge non-determinism alone. Run at least 3–5 trials per task and use a pass-rate threshold (e.g., ≥ 80%) rather than a binary cutoff. AgentEval (Microsoft's .NET toolkit) explicitly flags this as a core challenge and solves it with stochastic evaluation assertions.
- **Trajectory checks catch failures that output checks miss.** An agent that reaches the correct answer via the wrong tool sequence is a reliability risk — it got lucky. Assert on tool-call sequences and arguments directly, not just on final output. This is the insight behind AgentEval's "tool chain assertions" and the Microsoft Foundry agent evaluation GitHub Action.
- **Golden output comparison saturates.** Fixed expected outputs work for deterministic tasks but fail for open-ended generation. Use reference-based grading only for the "known-correct-answer" subset of your eval set; use LLM rubric or deterministic checks for the rest. The golden set should be a small, high-confidence anchor, not the whole evaluation surface.
