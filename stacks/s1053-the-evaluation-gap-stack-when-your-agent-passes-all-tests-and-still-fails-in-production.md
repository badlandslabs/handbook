# S-1053 · The Evaluation Gap Stack — When Your Agent Passes All Tests and Still Fails in Production

Your agent scores 94% on your held-out benchmark. You ship it. Three weeks in, a customer gets a confidently stated hallucination, a billing agent authorizes a refund it shouldn't, and a coding agent checks in a migration that works in tests but corrupts production state. Your benchmark never caught any of this. The failure isn't your agent — it's your evaluation layer, which was designed to measure something different from what production actually demands.

## Forces

- **Static benchmarks measure task completion, not reliability or safety.** SWE-bench, WebArena, and GAIA score whether the agent reaches the right answer — not whether it reached it the right way, at the right cost, without policy violations.
- **The trajectory is invisible to pass/fail.** An agent that reaches a correct answer via a risky action, a hallucinated tool call, or 40 unnecessary steps is indistinguishable from a clean execution in a final-answer eval.
- **Production reveals failure modes benchmarks cannot predict.** Compounding decision errors, tool failure cascades, non-deterministic output drift, and policy violations in real-world inputs — none of these appear in a held-out benchmark suite.
- **The per-turn signal is locked inside the agent's reasoning.** Logs, traces, and latency metrics tell you that a turn happened, not what it meant or whether it was on-policy.
- **Standard metrics detect only 3 of 7 production failure modes** — the other four (including systematic drift and compounding error) escape detection until real damage is done (arXiv:2605.01604).

## The Move

Measure agent quality in three layers, not one:

- **Layer 1 — Final-answer:** Does the last message match expected output? (necessary but not sufficient)
- **Layer 2 — Trajectory:** Was the path correct, efficient, and safe? Score the sequence of tool calls, retries, and decisions against policy.
- **Layer 3 — Per-turn semantic:** What actually happened in each production turn? Capture intent, drift, and off-policy behavior invisible to logs and traces.

Gate every deploy on trajectory-level scores, not just final-answer accuracy:

- Build a **golden trajectory dataset**: hand-curated examples of correct paths (tool call sequences, intermediate decisions, retry behavior) not just correct final answers.
- Score trajectories with **LLM-as-judge** for nuanced qualities (helpfulness, coherence, policy adherence) and **deterministic code evaluators** for measurable ones (tool selection correctness, argument validity, token efficiency).
- Run **continuous production monitoring** in parallel with offline evals. Key signals: drift in per-turn distributions, trajectory shape changes, cost-per-task creep.
- Implement **two-stage evals**: offline batch evals against the golden dataset before every deploy, shadow-mode production evals that run on real traffic without blocking responses.
- Fail CI pipelines on eval score regressions. Not warnings — failures.

## Evidence

- **Research paper:** UC Berkeley researchers found all eight major agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench) are exploitable for near-perfect scores without solving actual tasks — some via trivially simple exploits (sending `{}` to FieldWorkArena, trojanizing binary wrappers in Terminal-Bench). The paper: "How We Broke Top AI Agent Benchmarks" — [HN discussion](https://news.ycombinator.com/item?id=47733217)
- **Framework documentation:** Braintrust's eval pattern uses data + task + scorers with two scorer types (code-based deterministic checks, LLM-as-judge for nuanced qualities). Notion's AI team reported 10x improvement in daily issues resolved after adopting rigorous evaluation — from 3 to 30 per day — demonstrating that eval infrastructure accelerates shipping rather than slowing it. — [Braintrust: How to eval in production](https://www.braintrust.dev/articles/how-to-eval)
- **HN field report:** Ask HN thread on monitoring agents in production surfaced consensus failure modes: no step-by-step visibility into agent actions, surprise LLM bills from untracked token usage, risky outputs going undetected, no audit trail. Solutions mentioned included AgentShield (execution tracing + risk detection + human-in-the-loop) and Lava (gateway proxy with spend keys that physically enforce budget limits). — [Ask HN: monitoring AI agents in production](https://news.ycombinator.com/item?id=47301395)
- **arXiv research:** arXiv:2605.01604 (Pandey, 2026) documents that standard metrics fail to detect four of seven production failure modes, including compounding decision errors and systematic drift. Proposes production evaluation framework with trajectory-level scoring and continuous monitoring. — [arXiv:2605.01604](https://arxiv.org/abs/2605.01604)
- **Survey:** A comprehensive survey on agent evaluation taxonomy (arXiv:2507.21504) organizes evaluation along two dimensions: what to evaluate (behavior, capabilities, reliability, safety) and how to evaluate (interaction modes, benchmarks, metric computation, tooling). Highlights enterprise-specific challenges — role-based access, reliability guarantees, dynamic long-horizon interactions, compliance — often absent from academic benchmarks. — [arXiv:2507.21504v1](https://arxiv.org/html/2507.21504v1)

## Gotchas

- **LLM-as-judge has known failure modes:** Judges favor verbose outputs, exhibit position bias, and may reinforce their own reasoning errors. Calibrate with golden examples before relying on them for pass/fail decisions.
- **A green eval is necessary but not sufficient.** A correct final answer achieved through a wrong or unsafe trajectory should fail your eval, not pass it.
- **Offline evals miss distribution drift.** Your eval dataset is a snapshot. Production inputs evolve. Run shadow-mode production evals continuously — not just at deploy time.
- **Cost and latency are quality signals.** An agent that answers correctly but uses 10x the expected tokens or takes 5x longer is a degraded quality agent, not a passing one. Include resource metrics in your trajectory scoring.
- **Benchmarks are for comparing models, not validating deployments.** SWE-bench tells you which model to choose. It does not tell you whether your agent on that model will behave safely in your specific environment.
