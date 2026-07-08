# S-796 · The Evaluation Gap: What Pass/Fail Misses About Agent Quality

You run your agent through 200 test cases and get 94% pass. Then you watch a live session: the agent loops for 35 minutes, takes an irreversible action, and ends up at the right answer by accident. Your benchmark is green. Your agent is not trustworthy. This is the evaluation gap — the blind spot between terminal accuracy and behavioral reliability. It bites when agents start taking real actions in production.

## Forces

- **Final-answer metrics lie.** Pass/fail on the end state tells you nothing about how the agent got there. A trajectory full of wasted tool calls, wrong turns, and recovery retries can still arrive at a correct answer and score well.
- **Trajectories are expensive to evaluate.** Watching an agent's full execution trace is time-consuming and non-scalable. Automated trajectory evaluation requires instrumentation most teams skip in the prototype phase.
- **Agent failures are non-deterministic.** A prompt that passes 98% of the time can silently degrade to 60% as model versions change, inputs drift, or downstream APIs change behavior. Static benchmarks go stale the moment you ship.
- **LLM-as-judge is circular.** Using the same model family to evaluate its own output introduces correlated errors. But the alternatives — human raters, small reference models — each have their own failure modes at scale.

## The move

Build a three-layer evaluation harness that treats final-answer, trajectory, and per-turn signals as independent concerns. Treat each layer as a separate release gate.

- **Layer 1 — Final answer (baseline, always on):** Does the agent reach the correct end state? This is necessary but insufficient. Use a golden test set with known answers, and treat this as the floor, not the ceiling.
- **Layer 2 — Trajectory quality (moderate cost):** Did the agent call the right tools in the right order? Did it recover from failures or loop? Track tool-call sequences, step counts, and cost-per-task. A trajectory assertion framework (e.g., Promptfoo's trajectory assertions) lets you specify acceptable execution paths and fail on deviations. A 10-step pipeline where each step has 85% reliability succeeds end-to-end only ~20% of the time — so trajectory analysis catches this compounding failure.
- **Layer 3 — Per-turn signals (highest fidelity):** Was there a jailbreak attempt, a policy violation, a leaked system prompt, or a user frustration signal at any step? This requires per-turn annotation or a fine-tuned classifier. Most teams skip this and pay for it in production incidents.
- **Run two frameworks in parallel:** one for development-time evaluation (DeepEval or Promptfoo for CI regression), one for production monitoring (Arize Phoenix, W&B Weave, or Braintrust for live drift detection). No single tool covers both needs well in 2026.
- **Use tolerance bands, not exact thresholds.** Pin the judge model and sample a stable golden set. Pure threshold equality breaks on non-deterministic LLM output — tolerance bands let the pipeline tolerate natural variance while catching real regressions.
- **Track cost and latency as first-class metrics.** Agent runs are expensive. TRAJECT-Bench (Amazon/Michigan State, Oct 2025) specifically evaluates whether tools are selected, parameterized, and ordered correctly — not just whether the final answer is right.

## Evidence

- **HN Discussion — "Principles for production AI agents":** Practitioners debate LLM-as-judge reliability; consensus emerges that you must validate judges against sample annotated data and adapt them per task (prompt optimization via DSPy, correction models like LLM-Rubric, or Prediction Powered Inference). "Evals somehow seem to be very very underrated, which is concerning in a world where we are moving towards systems with more autonomy." — abhgh on HN
- **TRAJECT-Bench (arXiv, Oct 2025):** Academic benchmark from Amazon and Michigan State University that evaluates tool-use trajectories — not just final answers. Tests whether tools are selected, parameterized, and ordered correctly across practical domains. Demonstrates that final-answer benchmarks systematically miss trajectory quality.
- **DeepEval HN Launch (YC W25):** Open-source evaluation framework with G-Eval (research-backed LLM-as-judge with structured criteria) and DAG metric (decision-based, virtually deterministic despite LLM evaluation). Integrates with Pytest for CI/CD, includes metric caching and cost tracking. One of only three companies doing this well per the founders — the other two are closed-source.
- **MorphLLM analysis (Jun 2026):** Documents the three-layer model: final-answer (✅ covered everywhere) vs trajectory (⚠️ often missed) vs per-turn (❌ mostly ignored). Notes that a held-out pass/fail can be green while the trajectory was a mess and three turns drifted off policy.

## Gotchas

- **A green benchmark with a broken trajectory is the most dangerous state.** It gives you false confidence right before a production incident.
- **Offline evals miss production-specific failures.** The inputs you haven't seen, the multi-turn conversations that drift, and the tool failures that only appear when external systems change. Shadow mode (run new versions in parallel with live traffic) is the most reliable pre-deploy check.
- **Benchmark Shopping is a real failure mode.** Teams adopt Tau-Bench for customer service, SWE-Bench for coding agents, and never validate those benchmarks correlate with their actual task distribution. At minimum, build one internal benchmark for your specific application — no matter how small.
- **LLM-as-judge without validation is not evaluation.** It's just asking the model to rate itself. Use it for exploratory analysis and rapid iteration, not as a release gate without ground-truth anchoring.
