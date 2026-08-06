# S-2228 · The Agent Evaluation Stack — When You Ship and Pray

You've shipped your agent. You have no idea if it's better than last week. No regression suite, no golden dataset, no way to distinguish a real regression from stochastic noise. You just watch the error logs and pray. Agent evaluation is the discipline that makes "shipping with confidence" more than luck — and it has distinct phases, each with different failure modes and tools.

## Forces

- **Accuracy is not the hard problem.** Accuracy benchmarks exist (SWE-bench, WebArena, AgentBench). The hard problem is that lab accuracy does not transfer to production — RealClawBench found a 37% gap between benchmark scores and real-world agent performance on the same task distribution.
- **Output variance hides regressions.** Because agents use LLMs, the same input can produce different outputs across runs. A single trial is unreliable. You need multiple trials and statistical framing — yet most teams test once and call it done.
- **What you measure shapes what you optimize.** Teams that only track task completion miss cost, latency, reliability under retry, and safety. The CLEAR framework (Cost, Latency, Efficacy, Assurance, Reliability) found 50x cost variation across agents with similar accuracy — so cost is not a second-order concern.
- **Synthetic data is systematically misleading.** Agents that ace clean test cases routinely fail on ambiguous real-user instructions. The MachineLearningMastery analysis calls this the #1 eval failure mode: "evaluating on synthetic data that doesn't reflect production complexity."

## The Move

Build a **three-phase evaluation pipeline** that matches the agent's maturity:

### Phase 1 — Development: Golden Dataset + Deterministic Graders

- Curate 20–100 representative tasks from real production failures and edge cases, not idealized scenarios. RealClawBench found real developer sessions score 6.37/8 on "real demand" vs 3.85/8 for SWE-bench — the gap comes from implicit intent, local state, and environment-dependent behavior that synthetic tasks miss.
- Use deterministic graders (regex, exact match, JSON schema validation) wherever possible. They are fast, reproducible, and immune to grader drift. Reserve LLM-as-judge for nuanced quality dimensions.
- If you must use LLM-as-judge, provide structured rubrics, run multiple passes, and calibrate against human-labeled examples. Anthropic notes that judge quality depends entirely on the rubric's specificity — vague rubrics produce inconsistent scores.
- For tool-level evaluation, run tool evaluation in isolation from task evaluation (Anthropic's Cookbook approach, Sept 2025). A tool that works in a simple test but fails in a multi-step trajectory is a different failure mode entirely.

### Phase 2 — Canary / Shadow: Real Traffic Under the Microscope

- Run the agent on a slice of real production traffic alongside the existing system. Compare outputs without acting on the agent's results. This catches distribution shift — RealClawBench's core insight is that benchmark environments don't capture the actual distribution of user requests.
- Measure trajectory-level behavior: which tools the agent calls, in what order, how many steps before completion. LangChain's AgentEvals package specifically evaluates trajectories, not just final outputs, because a correct answer via the wrong path signals a fragile agent.
- Track escalation rate: what percentage of tasks the agent returns to a human. Anthropic's internal benchmark targets <15% escalation as the threshold for meaningful autonomy.

### Phase 3 — Regression Gate: Every PR, Automatically

- Wire evaluations into CI/CD. OpenAI's harness engineering practice (Feb 2026) frames this as "build rippable harnesses — the best harness is the one you eventually don't need." Their team ran hundreds of regression tests on every PR during a 5-month agent-first experiment that produced ~1M lines of code at 10x speed.
- Production monitoring closes the loop: real failures feed into annotation queues, expert-reviewed cases become new regression tests. LangChain's documentation calls this a "data flywheel" where the eval set continuously improves from live traffic.
- Set budget-aware thresholds: CLEAR found reliability drops from 60% (pass@1) to 25% (pass@8) under repeated runs — meaning your eval policy (how many trials per task) materially affects what you measure.

## Evidence

- **Engineering blog — Anthropic "Demystifying evals for AI agents" (Jan 2026):** Three-phase eval pipeline (development → canary → production monitoring); three grader types (assertion-based, deterministic, LLM-as-judge); importance of grading outcomes over trajectories when outcome is observable; production data flywheel pattern — [URL](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Engineering blog — OpenAI "Harness engineering: leveraging Codex in an agent-first world" (Feb 2026):** 5-month experiment, ~1M lines of agent-generated code, 0 manual PRs to application logic, 3.5 PRs/eng/day; harness-as-CI pattern: hundreds of automated regression tests on every PR, rip-when-confident philosophy — [URL](https://openai.com/index/harness-engineering)
- **Academic paper — "RealClawBench: Live OpenClaw Benchmarks from Real Developer-Agent Sessions" (arXiv:2606.03889):** Real sessions score 6.37/8 on real-demand vs SWE-bench's 3.85/8; 38.4% of real sessions have local state requirements (SWE-bench: 16%), 96.8% have implicit intent (SWE-bench: 42.3%) — [URL](https://arxiv.org/abs/2606.03889)
- **Academic paper — "Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems" (arXiv:2511.14136):** CLEAR framework: 50x cost variation for equivalent accuracy, 37% lab-to-production gap, reliability drops 60%→25% from pass@1 to pass@8, only 10% of enterprises successfully deploy GenAI agents in production — [URL](https://arxiv.org/abs/2511.14136)

## Gotchas

- **Measuring accuracy only is cargo-culting.** Cost, latency, and escalation rate are leading indicators of production success. An agent that scores 95% on your golden dataset but costs $5/task and takes 3 minutes is not better than one at 88% for $0.10/-task at 30 seconds.
- **Single-trial eval is noise, not signal.** Output variance means one run per task gives you a coin flip, not a measurement. The CLEAR paper's pass@1→pass@8 data makes this quantitative: a 35-point reliability drop across retry counts means your eval policy directly determines what you think your agent can do.
- **LLM-as-judge grading is only as good as its rubric.** Anthropic's blog explicitly calls out that judges drift without structured rubrics. If you can't describe what "good" looks like in words a human would agree on, your LLM judge will give you numbers that look precise but aren't accurate.
- **Tool eval ≠ task eval.** A tool that passes a unit test fails silently in a multi-step trajectory where the agent passes wrong state between steps. Anthropic's Cookbook separates these so teams catch both failure modes independently.
