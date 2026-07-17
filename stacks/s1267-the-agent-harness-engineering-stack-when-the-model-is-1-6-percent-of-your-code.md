# S-1267 · The Agent Harness Engineering Stack

When your agent works in demos but fails in production — not because the model is wrong, but because nobody engineered the control layer around it.

## Forces

- **Frontier models converged** — swapping Claude for GPT or Gemini rarely changes production outcomes for most tasks. The layer that decides quality is the one nobody benchmarks.
- **The invisible 98%** — teams optimize prompts and model choice while the surrounding infrastructure (context management, tool scaffolding, permissions, sandboxing, recovery, eval) gets rebuilt from scratch every project.
- **Permission fatigue** — 93% of agent permission prompts get approved reflexively (BeConfident Labs, 2026), making routine prompts unreliable as safety controls.
- **Eval gap** — 20–40% of regressions are missed by output-only scoring. You need to evaluate what the agent *did*, not just what it said.

## The move

Treat the harness — the control, execution, safety, and evaluation infrastructure — as a first-class engineering concern, not an afterthought.

- **Map the eight subsystems.** BeConfident Labs' survey (June 2026) identifies eight harness subsystems: context management, tool definition, permission model, sandboxing/execution environment, state management, recovery/continuation, evaluation harness, and training/data feedback loop. Audit which ones you have, which are missing, and which are implicit.
- **Instrument before you optimize.** Use structured trace collection (LangFuse, Honeycomb, Phoenix) to capture full agent trajectories — not just final outputs. Spans and step-level metadata let you identify where in the trajectory failure occurred.
- **Build eval as code, not as judgment.** Frameworks like **DeepEval** (16.9k stars, Confident AI, Apache 2.0) treat agent evaluation as unit tests: pytest-native, parameterized test cases, span-level scoring. Run in CI on every commit. `deepeval test run` produces pass/fail with reasoning.
- **Track task-completeness, not accuracy.** The "north star" metric is end-to-end task success: did the agent achieve the user's goal? Pair with cost-per-task (two agents with similar accuracy can differ 50x in cost due to unnecessary tool calls) and trajectory efficiency (steps to completion).
- **Use LLM-as-judge for qualitative dimensions.** A second LLM (typically a stronger model) scores hallucinations, answer relevancy, and response quality against defined criteria. G-Eval (from Microsoft's 2024 paper) uses chain-of-thought prompting to produce more consistent scores than direct prompting.
- **Measure permission approval rate as a safety signal.** If 93%+ of prompts auto-approve, your safety controls are theater. Log and review: which actions triggered rejections? Are rejections being overridden?
- **Apply the operating system metaphor.** The model proposes; the harness disposes. The model is a process. The harness is the OS. You would not ship a server without an OS — do not ship an agent without a harness architecture.

## Evidence

- **Survey:** The 98.4% statistic comes from analyzing Claude Code's codebase directly: ~1.6% is model decision logic, the rest is harness. The survey generalizes this as a pattern — "Frontier models converged between 2023 and 2026. For most production tasks, swapping model families no longer changes outcomes significantly." — [BeConfident Labs, June 12, 2026](https://labs.beconfident.app/papers/harness-engineering-survey) — HN discussion: [news.ycombinator.com/item?id=48508618](https://news.ycombinator.com/item?id=48508618)
- **Framework:** DeepEval reports 100M+ daily evals, 150K+ developers, >50% Fortune 500 adoption. Their eval architecture captures full execution traces, scores at span level, and integrates with CI/CD. `TaskCompletenessMetric` + `assert_test()` is the unit-test pattern. — [docs.confident-ai.com](https://docs.confident-ai.com/docs/evaluation-agentic-llm-evals)
- **Industry data:** 37% lab-to-production performance gap; 50x cost variance for similar accuracy; 20–40% of regressions missed by output-only scoring. Sourced from industry surveys and engineering blog analysis. — [AI Agent Evaluation Guide 2026, Jobs by Culture](https://jobsbyculture.com/blog/ai-agent-evaluation-guide-2026)
- **Eval methodology:** Three evaluation strategies — black-box (treat agent as opaque, measure inputs/outputs), glass-box (instrument internal steps), white-box (use harness metadata: tool call counts, step durations, recovery rates). Most teams start black-box and migrate to glass-box. — [LangFuse Agent Evaluation Cookbook](https://langfuse.com/guides/cookbook/example_pydantic_ai_mcp_agent_evaluation)

## Gotchas

- **Eval contamination is real.** Test cases that overlap with training data produce inflated scores. Private test sets, procedural generation, or live-environment evaluation are the mitigations — each with trade-offs in cost, coverage, and realism.
- **Synthetic evals don't predict adversarial inputs.** Demos work on clean inputs; slightly off inputs cause hallucination and tool call invention. Build perturbation testing into your eval suite — inject null values, malformed responses, and rate-limit errors.
- **Cost-per-task is lagging.** By the time cost tracking flags a problem, you've already burned budget on the bad trajectory. Wire cost into the eval harness so it fails fast on inefficient paths.
- **The model is the cheapest part.** Inference costs are ~1–5% of total agent operating cost. The rest is API overhead, eval infrastructure, context management, and human review of edge cases. Optimize the harness first.
