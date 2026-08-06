# S-2223 · The Agent Eval Stack — When Benchmark-Perfect Meets Production-Broken

You shipped an agent. It scores 87% on SWE-bench. Your CI passes. Your users get confused trajectories, hallucinated tool calls, and silent cascades into dead ends. The benchmark lied to you. So did the CI gate.

## Forces

- **Trajectory quality ≠ output quality.** A correct final answer can mask a broken reasoning path, a hallucinated tool call, or a loop of unnecessary retries. Static tests miss what kills users.
- **The echo chamber effect.** Using the same LLM family for judge and agent creates shared blind spots — a model prone to hallucinating API parameters will likely approve traces where the agent makes that same hallucination.
- **Non-determinism breaks hard assertions.** The same agent on the same input can take different paths on different runs. A binary pass/fail CI gate on a non-deterministic system is a false guarantee.
- **Lab-to-production gap is ~37%.** Top benchmark performers don't translate to production — SWE-bench shows 87.6%, yet 88% of agent pilots never reach production (Next Waves Insight, 2026). Benchmarks measure a cleaned-up slice of reality.
- **Evaluation is not one thing.** Offline regression tests, online production sampling, and human calibration serve different failure modes — using only one creates blind spots the others would catch.

## The move

Build a layered evaluation system that measures trajectories, not just outputs, and that uses complementary judges at each layer.

**Layer 1 — Offline regression on curated golden datasets (CI gate):**
- Curate 100–500 test cases from real production traces, not imagined edge cases. Label each with expected trajectory and outcome.
- Version the dataset. Every change is tracked — roll back bad edits, compare coverage across versions.
- Run in CI on every PR. Block deploys when quality drops against the last known-good baseline.
- Use deterministic graders where ground truth exists (exact match, JSON schema validation, numeric tolerance). Use LLM-as-judge for semantic quality.

**Layer 2 — Online evaluation on sampled production traffic:**
- Sample live traffic at a controlled rate. Score with LLM judges and deterministic checkers.
- Catch novel inputs, tool failures, and drift that offline datasets cannot anticipate.
- Track trajectory metrics: step count, unnecessary tool calls, loops/retries, required steps present, correct ordering.

**Layer 3 — Human calibration of the judges:**
- Compare LLM judge scores against human annotations on a subset. A judge that agrees with humans <80% of the time needs rubric fixes or model swap.
- Human calibration is expensive but anchors the automated layers — without it, you are optimizing a proxy you have not validated.

**Measure four dimensions, not one:**
- **Trajectory** — step count, efficiency, loops, correct ordering
- **Tool use** — correct tool selected, correct arguments passed
- **Task completion** — did the agent accomplish the goal?
- **Multi-turn quality** — context retention, coherence across turns

**Use soft thresholds in CI, not hard gates.** Non-deterministic agents require statistical thresholds — report pass rates and score distributions, not binary assertions.

**Draw eval cases from production traces, not imagination.** The highest-value test cases are real failure modes users hit — annotate and curate them, then add them to the golden dataset.

## Evidence

- **HN Discussion (128 points):** Practitioners universally name evaluations as vital for production agent improvement. One commenter: "Did we just give up on evaluations these days? Over, and over again my experience building production AI tools has been that evaluations are vital for improving performance." — [HN thread on production AI agent principles](https://news.ycombinator.com/item?id=44712315)

- **HN Discussion (1 point, detailed):** A practitioner who tried a benchmark-style eval approach found it broke in unexpected ways — context window saturation on multi-step traces, non-deterministic outputs making reproducibility impossible, and trajectory-level failures invisible to output-only evaluation. Confirms the eval-lie pattern from production teams. — [HN: "What broke when I tried to evaluate an AI agent in production"](https://news.ycombinator.com/item?id=47416033)

- **Label Studio blog (April 2026):** Documents the "echo chamber effect" — LLM-as-judge with same architecture as evaluated agent shares blind spots. Also notes: "Correct final outputs often mask broken reasoning and hallucinated tool calls." Proposes three-layer system: automated tests + LLM judges + human review. — [Label Studio: How to Evaluate AI Agents in Production](https://labelstud.io/blog/how-to-evaluate-ai-agents-in-production)

- **Next Waves Insight (May 2026):** Reports 37% lab-to-production gap for top agent benchmarks. SWE-bench top performer 87.6%, WebArena 68.7%. Documents in-context benchmark gaming by Claude Opus 4.5. 88% of agent pilots never reach production. — [AI Agent Evaluation in Production: Why Benchmarks Fail](https://nextwavesinsight.com/ai-agent-evaluation-production-2026/)

- **Langfuse engineering guide:** Formalizes four evaluation dimensions (trajectory, tool use, task completion, multi-turn quality). Distinguishes offline evals (curated datasets, CI regression) from online evals (production sampling, drift detection). — [Langfuse: AI Agent Evaluation](https://langfuse.com/resources/engineering/ai-agent-evaluation)

- **Confident AI / DeepEval:** Open-source framework with 20+ built-in metrics including Task Completeness, Tool Correctness, Goal Accuracy, Step Efficiency, Plan Adherence. Reports 100M+ daily evals, 150K+ developers, >50% Fortune 500 adoption. — [DeepEval GitHub](https://github.com/confident-ai/deepeval)

- **TribeAI/claude-evals:** Production eval framework for Claude Agent SDK. Hooks into PreToolUse, PostToolUse, and SubagentStop lifecycle events — not just final output. Ships 50-case golden dataset for contract review. Implements Anthropic's published eval patterns. — [GitHub: TribeAI/claude-evals](https://github.com/TribeAI/claude-evals)

- **Maxim.ai (2025):** Golden dataset best practice: "Repeatable agent evaluation across versions, models, and workflows." Emphasizes versioning, rollback, and curation from production traces. — [Maxim: Building a Golden Dataset](https://www.getmaxim.ai/articles/building-a-golden-dataset-for-ai-evaluation-a-step-by-step-guide)

- **AppScale blog (June 2026):** Documents seven failure modes for production agents. Recommends trajectory-level scoring (step count, loops, tool-call correctness) alongside outcome evaluation. Notes that multi-step systems "fail silently, compound small errors into catastrophic ones." — [AppScale: Evaluating AI Agents — Trajectory & Tool-Use Evals](https://appscale.blog/en/blog/evaluating-ai-agents-trajectory-tool-use-evaluation-2026)

## Gotchas

- **Evaluating only the final output is the root mistake.** It catches wrong answers but misses hallucinated tool calls, unnecessary loops, and broken reasoning that still happens to arrive somewhere plausible.
- **LLM-as-judge on same model family creates echo chamber blind spots.** Calibrate against human annotations before trusting judge scores. A judge that agrees with humans <80% of the time is not trustworthy.
- **Hard binary CI gates fail on non-deterministic agents.** The same input produces different trajectories. Use statistical thresholds and track score distributions — a 70% pass rate across 5 runs reveals instability that a single pass/fail hides.
- **Offline datasets go stale without production feedback loops.** Imagined test cases miss real failure modes. The only reliable dataset source is annotated production traces — curate them continuously.
- **Benchmark scores are a ceiling, not a floor.** An 87% SWE-bench score does not mean 87% production reliability. The gap is environmental: controlled benchmarks strip the variability of real APIs, live user inputs, and multi-turn context drift.
