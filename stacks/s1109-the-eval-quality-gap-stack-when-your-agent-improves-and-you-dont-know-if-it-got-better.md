# S-1109 · The Eval-Quality Gap Stack — When Your Agent Improves and You Don't Know If It Got Better

You shipped a new prompt. The demo worked. Users said it felt better. But you have no idea if it actually improved because you have no systematic evaluation. You are flying blind while your agent grows more complex. In 2025-2026, as agents move from demos to production, evaluation engineering has become as critical as prompt engineering — and most teams are still improvising.

## Forces

- **Agents are non-deterministic by design.** Traditional software testing assumes: same input → same output. Agents violate this at every level — tool calls vary, reasoning paths differ, and "correct" can mean multiple valid approaches. You cannot assert an exact string; you need metrics that capture semantic correctness, trajectory efficiency, and behavioral safety.
- **The benchmark crisis.** UC Berkeley researchers examined eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) and found that static task-completion scores fail to capture reliability, cost efficiency, safety, and long-horizon competence. High benchmark scores don't predict production quality.
- **The taste problem.** You can get an LLM to give praise easily, and criticism with scaffolding — but getting an LLM to have *taste* is the hard part. LLMs lack lived experience of what good looks like in a domain. This is why LLM-as-judge is powerful but unreliable without calibration.
- **Eval quality is a moving target.** New models drop every two weeks. A prompt that worked on Claude 3.5 Sonnet may degrade on Claude 4. Your eval suite is the only thing that tells you whether a model swap is a regression or an improvement.

## The move

Build a layered evaluation system that combines deterministic checks, trace-level instrumentation, and calibrated LLM-as-judge — run in CI on every change.

### 1. Evaluate at three levels, not just the output

- **End-to-end (task success):** Did the agent complete the user's request? Binary or multi-level pass/fail against a ground-truth answer or rubric. This is your primary signal.
- **Trajectory-level (path efficiency):** How many tool calls, reasoning steps, and token spent? An agent that gets the right answer in 47 tool calls is worse than one that gets it in 3 — even if both "succeed."
- **Component-level (failure isolation):** Which sub-agent, retriever, or tool caused the failure? Trace spans let you pinpoint the broken part without re-running the full task.

### 2. Use deterministic checks for exact things, LLM-as-judge for fuzzy things

Deterministic checks (regex, JSON schema validation, tool call argument matching) are fast, reproducible, and free from judge bias. Reserve LLM-as-judge for answer quality, tone, helpfulness, and plan coherence — dimensions where correctness isn't binary.

### 3. Instrument traces before you need them

Add tracing to every agent step (tool calls, reasoning loops, handoffs, memory reads). Tracing is the backbone that connects a low score back to the exact span that caused it. Without traces, you know the eval failed — you don't know why.

### 4. Calibrate LLM-as-judge against humans

- Set judge temperature to 0 (deterministic outputs required for reproducible scores).
- Use majority voting across 3+ runs for critical evaluations.
- Prefer binary evaluations (pass/fail) over multi-point scales when possible.
- Aim for Cohen's κ > 0.8 against human judgments before trusting a judge model.
- **Use a different model for judging than for generation** — same-model judging introduces self-preference bias where the agent's outputs score higher because they share style patterns with the judge.

### 5. Run evals in CI, not manually

Every prompt change, model swap, or tool addition should trigger the eval suite automatically. The eval suite is the safety net — it catches regressions that "vibe checks" miss. Teams report cases where a prompt tweak passed a demo but clearly degraded on the full eval suite.

### 6. Start with 20-30 test cases, not 2,000

Curate test cases around your highest-stakes agent behaviors — not generic benchmarks. Coverage of important edge cases matters more than volume. Add cases when failures surface in production.

## Evidence

- **Hacker News (Ask HN):** "How are people doing AI evals these days?" — HN discussion (43 comments) revealed a fragmented landscape: some teams run no evals at all, others duct-tape LangFuse + PromptFoo + custom scripts together, and only a minority run automated benchmarks in CI. One commenter described the state as "very, very heterogeneous and fast moving." — [HN Thread](https://news.ycombinator.com/item?id=47319587)
- **Hacker News (Principles for Production AI Agents):** Practitioners emphasized that evals are the only way to know if changes actually help: "If you don't have evals, you really don't know if you're moving the needle at all. There were multiple situations where a tweak to a prompt passed an initial vibe check, but when run against the full eval suite, clearly performed worse." — [HN Thread](https://news.ycombinator.com/item?id=44712315)
- **UC Berkeley Benchmark Analysis:** Researchers found that eight major agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) have significant reliability issues — high benchmark performance doesn't predict production reliability, cost efficiency, or safety. — [Zylos Research summary](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking), original analysis cited from Berkeley AI agent benchmarks study
- **DeepEval (Confident AI):** Open-source evaluation framework with pytest-style syntax, model-agnostic, supports LangChain/LlamaIndex/Pydantic AI. Provides structured metrics for tool-calling correctness, trajectory accuracy, answer relevance, and faithfulness. Used in production by teams replacing ad-hoc eval scripts. — [DeepEval](https://deepeval.com), [Medium tutorial on DeepEval + DeepSeek](https://medium.com/@manuedavakandam/systematic-ai-agent-evaluation-deepeval-framework-powered-by-deepseek-c81d39b13f8b), [Engineering Notes guide](https://notes.muthu.co/2025/12/a-practical-guide-to-evaluating-your-ai-agents-with-deepeval/)
- **Microsoft AgentAsJudge:** Open-source framework using multi-agent reasoning pipeline for evaluation — discussion, criticism, and ranking agents assess content quality on 1-5 scale with written feedback. Released June 2025. — [GitHub](https://github.com/microsoft/AgentAsJudge)
- **AWS Labs Agent Evaluation:** Framework for evaluating agents on Amazon Bedrock, with configurable evaluators, CI/CD integration, and trace-level assessment. v0.4.1 with 369 stars. — [GitHub](https://github.com/awslabs/agent-evaluation)
- **Gartner Projection:** By 2028, 40% of enterprise AI failures will trace to inadequate evaluation and monitoring rather than model capability gaps. — [Thinking Company / Gartner](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production)

## Gotchas

- **Self-preference bias in judge selection.** When you use the same model for generation and judgment, outputs get inflated scores because they share stylistic patterns. Always use a different model family for judging.
- **Eval benchmarks ≠ production quality.** Passing WebArena or SWE-bench doesn't mean your agent is reliable in your specific domain. Build domain-specific test cases; off-the-shelf benchmarks are a floor, not a ceiling.
- **Non-determinism hides regressions.** An agent can fail 20% of the time and still "work" in demos if you only show the successful runs. You need multiple eval runs (majority voting) to surface flaky behavior.
- **Evals go stale.** As your agent gains capabilities and your domain shifts, old test cases become either trivially passable or irrelevant. Treat your eval suite as a living artifact — prune and refresh test cases quarterly.
