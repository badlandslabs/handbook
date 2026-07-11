# S-946 · The Trajectory Eval Stack — When Final-Answer Evals Pass but Your Agent Still Fails in Production

You run your eval suite. Everything is green. Your agent "completes" the task every time. Then it ships and silently calls the wrong tool, loops 47 times burning $3 in tokens, ignores your policy guardrails, and nobody notices until the monthly bill arrives. The fix isn't more final-answer tests — it's trajectory-level evaluation.

## Forces

- **Final-answer evals lie.** An agent can reach the right answer via the wrong path — wrong tool selected, bad arguments passed, policy violated mid-trajectory. Outcome looks fine; behavior is broken. A 2025 analysis of lending-agent benchmarks found a 33–42 percentage point gap between "got the right answer" and "followed the correct process" across GPT-5.2 and Claude Opus 4.6.
- **Benchmarks are gamed.** UC Berkeley researchers examined eight major agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) and found all eight could be exploited to achieve near-perfect scores without solving a single underlying task. One team gamed 890 tasks with a single-character edit.
- **The eval stack is immature in production.** A Cleanlab survey of 1,837 enterprise respondents found fewer than 1 in 3 teams were satisfied with their observability and guardrail solutions. Only 5% cited accurate tool calling as a top challenge — a sign the field hasn't yet faced the hard measurement problems that come after basic demos work.
- **Context windows are expensive.** Tracing every agent turn for evaluation adds token overhead. Teams need per-turn signals that are cheap enough to run continuously, not just in batch.

## The Move

Layer your evals across three levels, not one. The final answer is the last thing you check, not the only thing.

### Three-layer eval architecture

- **Layer 1 — Outcome (end-to-end):** Did the agent complete the user's goal? Simple pass/fail or task-completion score. Necessary but insufficient. Check this last, not first.
- **Layer 2 — Trajectory (path-level):** Was the path efficient and compliant? Measure tool-call sequence correctness, plan adherence, loop detection, token burn rate. TAU-bench pioneered checking not just the final answer but the resulting database state — verifying that actions had the intended effect.
- **Layer 3 — Per-turn (component-level):** Did each individual step do the right thing with the right inputs? This surfaces failures that aggregate invisibly at the trajectory level. Agent-triage (converra/agent-triage, launched on HN July 2025) runs a per-turn policy classifier on production traces, labeling each turn as compliant or violating within 90ms — cheap enough to run on every turn continuously.

### Build golden datasets from real failures

Start with end-to-end evals — define one success criterion (did the agent meet the goal?) and output yes/no. Use this to identify edge cases from production. Add those real failures to your golden dataset. Do not start with synthetic test cases.

### Choose the right judge by what's being measured

- **Deterministic checks** for exact things: tool name, parameter values, API response shape, return codes. No LLM needed.
- **LLM-as-judge** for context-dependent things: whether the agent's reasoning was sound, whether a response was helpful, whether policy was followed in spirit vs. letter. Be aware of self-preference bias — judges favor their own outputs.
- **G-Eval** (Microsoft Research, 2024) — chain-of-thought prompted LLMs used as judges with detailed rubrics — is the most widely adopted LLM-judge method in open-source tooling. DeepEval implements it with 50+ ready-made metrics including task completion, faithfulness, and argument correctness.

### Run evals in CI, not just locally

Production eval stacks in 2026 run a four-stage pipeline: local iteration (DeepEval or Promptfoo against a golden dataset), offline batch evaluation on PRs, online scoring on a sample of live traffic, and automated quality gates that gate releases or alert humans.

## Evidence

- **Research paper:** "Are we evaluating AI agents all wrong?" — HN thread surfacing the process-vs-outcome gap, with evidence of 33–42pp outcome vs. process compliance gap in lending agent benchmarks — [https://news.ycombinator.com/item?id=46215574](https://news.ycombinator.com/item?id=46215574)
- **Benchmark analysis:** Zylos Research analysis of UC Berkeley's benchmark exploit study, finding all 8 major agent benchmarks gameable — [https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking](https://zylos.ai/zh/research/2026-05-13-ai-agent-evaluation-benchmarking)
- **Enterprise survey:** Cleanlab "AI Agents in Production 2025" — 1,837 respondents, <1/3 satisfied with observability, 70% of regulated enterprises rebuild their agent stack every 3 months — [https://cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **Benchmark:** TAU-bench (Anthropic) — multi-turn customer service agent benchmark that checks final answer AND database state, not just tool-call syntax — [https://github.com/Salesforce/TAU-bench](https://github.com/Salesforce/TAU-bench)
- **Open-source tool:** Agent-triage — per-turn policy compliance labeling on production traces, <90ms latency per turn — [https://github.com/converra/agent-triage](https://github.com/converra/agent-triage)
- **Open-source tool:** Agent trajectory evaluation (abhiai-git) — Python package evaluating tool-enabled LLM agent reasoning trajectories, supports ReAct, LangChain, and Google ADK traces — [https://github.com/abhiai-git/agent_trajectory_evaluation](https://github.com/abhiai-git/agent_trajectory_evaluation)
- **Framework:** DeepEval — pytest-style local evals with 50+ metrics including G-Eval, Apache 2.0, ~16k GitHub stars — [https://github.com/confident-ai/deepeval](https://github.com/confident-ai/deepeval)
- **Blog post:** "On evaluating agents" (AunHumano, Sep 2025) — pragmatic start: define one success criterion as yes/no, build golden datasets from production failures — [https://aunhumano.com/index.php/2025/09/03/on-evaluating-agents/](https://aunhumano.com/index.php/2025/09/03/on-evaluating-agents/)

## Gotchas

- **Final-answer evals can be green while the agent drifts off policy for 10 turns.** If you only check the last message, you miss everything that happened before it.
- **Synthetic test cases diverge from real traffic.** The benchmark crisis proves this. Build golden datasets from actual production failures, not from imagined scenarios.
- **LLM-as-judge has known biases** — it favors verbose outputs, outputs from the model it was trained on, and can be gamed by adversarial prompts. Treat judge scores as one signal among several.
- **Per-turn eval cost compounds.** Labeling every production turn adds token overhead. Use sampling strategies (random 5%, or triggered on low-confidence turns) rather than labeling everything always.
- **Eval coverage ≠ eval quality.** Running 500 test cases with the wrong success criteria produces false confidence. The metric that matters is whether your evals would have caught your last three production failures.
