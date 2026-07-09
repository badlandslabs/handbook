# S839 · The Agent Eval Stack — When Everything Runs but Nothing Is Measured

You have an agent that calls tools, browses the web, writes code, and completes tasks. It works. Then someone pushes a prompt edit, the model provider ships an update, or a tool changes its output schema — and quietly, it starts failing one in five cases. Nobody notices until a user reports it. The agent's output looks fine. The trajectory is broken.

## Forces

- Agents produce **trajectories**, not outputs — you cannot `assertEqual` a sequence of tool calls, memory reads, and decisions.
- **Aggregate scores hide broken graders** — a 90% pass rate masks the fact that your safety checks have silently degraded.
- **Non-determinism is structural** — the same input can produce different reasoning paths, so exact-string matching is useless.
- Eval is still an afterthought for most teams — the space has no gold standard, and every framework does it differently.
- The thing that makes agents powerful (autonomy, tool use, long-horizon reasoning) also makes them uniquely hard to test.

## The Move

Build a **production-to-evaluation flywheel** — every failure becomes a permanent test case, and every test case gates a release.

### 1. Capture from production first

The highest-value test cases are not handcrafted. They come from production failures. Every agent malfunction in front of a real user is an edge case you could not have invented — real ambiguous phrasings, malformed inputs, unanticipated tool sequences.

The loop: **Production failure → trace → test case → golden dataset → CI gate**. Run the golden dataset on every prompt change, model swap, retrieval tweak, or tool update.

> *"The agent doesn't magically get better. The system gets better because traces expose behavior, evals turn behavior into measurable signals, and humans refine the policy behind the loop."* — Arize AI, "How to Build a Better Agent Harness with Traces and Evals"

### 2. Grade two things: trajectory and outcome

Anthropic's "Demystifying Evals for AI Agents" (2026) establishes the critical distinction:

- **Outcome grading** — did the final result achieve the task? (binary or rubric)
- **Trajectory grading** — was the path correct? Did the agent use the right tools, in the right order, with the right context?

Outcome-only grading misses silent failures where the answer sounds right but the agent took a shortcut, used the wrong tool, or made an unsafe call. Trajectory grading catches this but is harder to automate.

### 3. Three grader types, used together

Anthropic's published eval patterns (implemented in [TribeAI/claude-evals](https://github.com/TribeAI/claude-evals)) cover three approaches:

- **Deterministic graders** — exact match, regex, JSON schema validation. Fast, cheap, reliable for code execution, math, and structured outputs. Use these wherever you can.
- **LLM-as-judge** — a second LLM scores outputs against a rubric. Handles subjectivity (tone, clarity, instruction following) but introduces variance and cost. Calibrate with golden examples; use a separate model from the one being evaluated.
- **Human review queue** — flag uncertain cases for human labeling. Use for safety-critical outputs, ambiguous scoring, or to bootstrap initial golden datasets.

### 4. Instrument the full agent lifecycle — not just the final call

LangSmith, Helicone, and Arize trace every tool call, sub-agent delegation, and memory operation. These traces are the raw material for evaluation. The practical loop: **trace → evaluate spans → inspect failures → decide if agent or evaluator is wrong → improve prompt/tools/context/rubric → run again**.

Microsoft's [ai-agent-evals](https://github.com/microsoft/ai-agent-evals) GitHub Action evaluates Foundry agents within CI/CD, with results including confidence intervals and statistical significance testing to distinguish real regressions from noise.

### 5. Handle non-determinism with ensemble scoring

Run each test case 3-5 times and score on a rubric, not exact match. This handles the variance inherent in probabilistic reasoning paths while still producing a meaningful pass/fail signal. Set a pass bar (e.g., 80% of runs must score above threshold), not a single-run gate.

### 6. Benchmark against task-specific suites

General benchmarks (MMLU, etc.) don't measure agent capability. Use domain-specific suites:

| Benchmark | What it measures |
|-----------|-----------------|
| [SWE-bench Verified](https://www.swebench.com) | GitHub issue resolution |
| [GAIA](https://huggingface.co/GAIA) | Multi-step web + code + file tasks |
| [τ-bench](https://github.com/sup党中央/τ-bench) | Tool-agent-user interaction |
| [WebArena](https://webarena.dev) | Browser automation |
| [OSWorld](https://os-world.github.io) | OS-level computer use |
| [AgentBench](https://github.com/TRI-Leap-Inc/AgentBench) | Multi-domain agent capability |

## Evidence

- **Engineering blog:** Anthropic — "Demystifying Evals for AI Agents" (2026) — establishes trajectory vs outcome grading, three grader types, CI integration patterns — [URL](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **GitHub (Apache 2.0):** TribeAI/claude-evals — implements Anthropic's eval patterns natively in Claude Agent SDK with 50-case golden dataset and one-command model comparison — [URL](https://github.com/TribeAI/claude-evals)
- **GitHub (MIT):** Microsoft/ai-agent-evals — GitHub Action for CI/CD evaluation with statistical significance testing, confidence intervals — [URL](https://github.com/microsoft/ai-agent-evals)
- **GitHub (CC BY-NC-SA):** HuggingFace/evaluation-guidebook (2.1k stars) — practical LLM eval guidance from the Open LLM Leaderboard team — [URL](https://github.com/huggingface/evaluation-guidebook)
- **Company blog:** Arize AI — "How to Build a Better Agent Harness with Traces and Evals" — trace-driven eval loop, failure grouping, improvement cadence — [URL](https://arize.com/blog/improve-ai-agents-traces-evals-harness)
- **Company blog:** Arthur.ai — "How to Build Regression Test Datasets for AI Agents From Production Failures" (Jun 2026) — production failure → trace → test case → golden dataset → CI loop — [URL](https://www.arthur.ai/column/regression-test-datasets-ai-agents-production-failures)
- **Company blog:** Gravity AI — "AI Agent Regression Testing: A Practical Guide" (Jun 2026) — golden set construction, non-determinism handling, CI pass bar — [URL](https://gravity.fast/blog/ai-agent-regression-testing-guide)
- **GitHub (MIT):** chanl-ai/chanl-eval (19 stars) — "pytest for AI agents": multi-turn persona simulation, configurable customer archetypes, scorecards — [URL](https://github.com/chanl-ai/chanl-eval)
- **HN thread:** "Ask HN: How are people doing AI evals these days?" — 30 pts, 43 comments — community consensus: no gold standard, eval is afterthought for most teams, output quality assessment is unsolved — [URL](https://news.ycombinator.com/item?id=47319587)
- **Academic survey:** "Evaluation and Benchmarking of LLM Agents: A Survey" — arXiv:2507.21504 (Jul 2025, SAP Labs) — two-dimensional taxonomy: evaluation objectives (what) × evaluation process (how) — [URL](https://arxiv.org/abs/2507.21504)
- **Community blog:** GAIA benchmark lessons (HuggingFace, Oct 2025) — model selection for agents, tool definition impact, multi-turn evaluation setup — [URL](https://huggingface.co/blog/hetline/lessons-learned-on-gaia-agents)

## Gotchas

- **Outcome-only grading is a false negative factory.** An agent can reach the right answer via the wrong trajectory — wrong tool, shortcut, hallucinated intermediate step. Catch this with trajectory-level checks.
- **LLM-as-judge introduces its own failure modes** — judge model bias, rubric ambiguity, cost at scale. Calibrate judges against human-labeled examples and never use the same model for agent and judge.
- **Aggregate pass rates hide broken sub-dimensions.** Break your eval into capability dimensions (tool use accuracy, safety, instruction following, cost efficiency) and monitor each independently. A 90% overall score is meaningless if your safety checks score 40%.
- **Golden datasets decay.** Input distributions shift. Real user behavior changes. Review and expand your test set quarterly — stale tests create false confidence.
- **Statistical noise masquerades as regression.** Run enough trials to detect meaningful deltas. Microsoft ai-agent-evals includes confidence intervals for exactly this reason. Don't ship a "fix" that was just variance.
