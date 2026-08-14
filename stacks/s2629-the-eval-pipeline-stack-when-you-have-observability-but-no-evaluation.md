# S-2629 · The Eval Pipeline Stack — When You Have Observability but No Evaluation

[When your tracing dashboard is full of agent traces, your latency is nominal, and you have zero idea whether the agent completed the task correctly — because you instrumented the *wrong* thing, and the eval suite your team built in Q1 is now a graveyard of skipped CI runs.]

## Forces

- **The observability-evaluation gap is a chasm, not a gap.** 89% of teams running agents have observability tooling; only 52% have evaluation frameworks. You can see everything that happened. You cannot tell if it was correct. — *[RaftLabs AI Agent Testing Guide, May 2026](https://www.raftlabs.com/blog/ai-agent-testing-evaluation-guide)*
- **The eval suite nobody runs is not a control — it's a liability.** An eval that costs too much, runs too slowly, or returns ambiguous float scores gets skipped on the changes that need it most. The failure mode that quietly ends most eval programs is not a bad grader — it's a suite nobody runs anymore. — *[Vercel AI Agent Evaluation Frameworks, 2026](https://vercel.com/i/ai-agent-evaluation-frameworks-production)*
- **Agents produce correct outputs via wrong processes, and traditional monitoring never catches this.** The agent reports the right inventory number but read last year's report. The result looks right. Execution failed silently. — *[Google Cloud: A Methodical Approach to Agent Evaluation, November 2025](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)*
- **The judge is a system, not a truth.** LLM-as-judge carries its own biases — position preference, self-preference for larger models, length bias — and degrades over time as production data shifts. Treating the judge as an oracle is the mistake that makes evals diverge from reality. — *[arxiv:2510.12462, February 2026](https://arxiv.org/html/2510.12462v3); [Medium/Vinod Krane, 2026](https://medium.com/@vinodkrane/chapter-8-agent-evaluation-for-llms-how-to-test-tools-trajectories-and-llm-as-judge-788f6f3e0d52)*
- **Golden datasets decay faster than you think.** At least 24% of time-sensitive samples in five factuality benchmarks were already outdated. Grading the product as it was when someone curated it — not as it runs now. — *[Tessary: Production Traces vs Golden Datasets, June 2026](https://tessary.ai/blog/production-traces-vs-golden-datasets-llm-evals)*

## The Move

The three-level eval architecture (unit tests → LLM-as-judge → production monitoring) is well-understood in theory. The hard parts are: **what each level must catch**, **how the judge stays honest**, and **how to maintain the golden dataset without it becoming a snapshot of last quarter's product**.

### Build from production failures, not thought experiments

- Start with **20–50 real production failures** as your seed dataset, not a synthetic benchmark. Riya Thambiraj at RaftLabs: *"Evaluation is the thing that separates research demos from production systems. You can vibe-check a demo. You cannot vibe-check a system handling 10,000 tasks a day."* — *[RaftLabs](https://www.raftlabs.com/blog/ai-agent-testing-evaluation-guide)*
- Mine production traces for failures: save failing sessions as permanent test cases via your tracing platform (LangSmith annotation queues, Langfuse datasets, or Phoenix). This is the highest-signal input to an eval suite because each case represents a real user who got hurt.

### Grade both individual steps and full traces — separately

- **Step-level grading:** Catch the early error that corrupts everything downstream. An early error that looks plausible in isolation produces a wrong final state. Grade each tool call, each state mutation, each branching decision on its own.
- **Trace-level grading:** A trace where every individual step looks fine can still end in the wrong state. Grade the full trajectory — was the *right* tool selected, was the *right* path taken, not just "did it return something sensible."
- Vercel's finding: *"Single-response grading gave way to step and trace grading" in production code agents — step grading catches the early error, trace grading catches the accumulated drift.* — *[Vercel](https://vercel.com/i/ai-agent-evaluation-frameworks-production)*

### Treat the judge as a system that needs its own testing

- **Lock judge model versions.** The judge's output changes when the underlying model changes. Pin to a specific model and version, and re-run calibration when you upgrade.
- **Test the judge before trusting it:** Use **repetition stability** (same verdict across multiple runs), **position consistency** (swap A/B order and check for flipped verdict), and **preference fairness** (chose-A vs chose-B distribution is roughly even). The standard technique from Shi et al., 2025: present the same pair twice with swapped order. Flip = position bias confirmed. — *[Medium/Vinod Krane](https://medium.com/@vinodkrane/chapter-8-agent-evaluation-for-llms-how-to-test-tools-trajectories-and-llm-as-judge-788f6f3e0d52)*
- **Watch for criteria drift.** Manually grading a sample of outputs before trusting the judge — then comparing judge verdicts to manual verdicts — reveals when the judge has drifted. The paper *"Who Validates the Validators?"* (Shankar et al., 2024) shows that manually grading outputs helps teams refine expectations based on actual LLM error patterns. — *[arxiv:2404.12272](https://arxiv.org/abs/2404.12272)*
- **Use binary pass/fail over numeric scales.** Binary criteria per dimension produces more reliable results across judges than subjective numeric scales. Chiang et al., 2025 found that teams consistently debated float scores but acted decisively on pass/fail. — *[AWS Startups LLM Evaluation Agent](https://startups.aws.com/prompt-library/llm-eval-agent)*

### Make the eval run — not just exist

- **Order of evaluation methods matters more than which methods you choose.** Start with the cheapest check that can catch a given failure. Expensive evals that sit in CI unused teach you nothing.
- **Speed gate:** Unit-level checks (schema validation, regex, JSON parse) run in CI on every PR — milliseconds, deterministic. LLM-as-judge runs on merge, nightly, or release candidate — acceptable latency. Production monitoring runs continuously.
- **The CI gate is the control.** If evals don't block or warn on pull requests, they are not engineering controls — they are post-hoc reporting. GuardLoop (GitHub awesome-pro/guardloop) integrates budget caps, circuit breakers, and trace emission at the CI level for exactly this reason.

### Close the loop from production to eval

- **Continuous sampling from production:** Set a rate — 1% of traces, or all traces above a cost/latency threshold — for human review. Label them, add the failures to the golden dataset. This is the mechanism that keeps the eval suite from decaying.
- **Distinguish traces from golden datasets.** Traces grade the product as it runs now and carry the full span graph (messages, tool calls, state). Golden datasets carry expected answers that were correct when labeled but decay. Use traces for detecting regressions; use labeled golden datasets for calibrating the judge. — *[Tessary](https://tessary.ai/blog/production-traces-vs-golden-datasets-llm-evals)*

## Evidence

- **Company engineering post:** Google Cloud — *A Methodical Approach to Agent Evaluation* (Hugo Selbie, November 2025) — Defines "silent failure" taxonomy and the trajectory/interaction model for debugging agents. Introduces golden dataset building from anonymized production traces. — [cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)

- **Engineering blog / guide:** Vercel — *AI Agent Evaluation Frameworks for Production* (2026) — Documents the 70% manual evaluation statistic, step + trace grading requirement, and the eval-suite-usage failure mode. — [vercel.com/i/ai-agent-evaluation-frameworks-production](https://vercel.com/i/ai-agent-evaluation-frameworks-production)

- **Practitioner survey:** RaftLabs — *AI Agent Testing Guide: Evals for Production* (Riya Thambiraj, May 2026) — 52% of teams running agents lack evals despite 89% having observability; 91% of ML models degrade over time. 20–50 real production failures as seed dataset. — [raftlabs.com/blog/ai-agent-testing-evaluation-guide](https://www.raftlabs.com/blog/ai-agent-testing-evaluation-guide)

- **Academic:** Shankar et al. — *"Who Validates the Validators?"* (arxiv:2404.12272, 2024) — Documents criteria drift in LLM-as-judge; shows that manually grading outputs before trusting the judge is essential for calibration. Still canonical in 2026 practitioner discussions. — [arxiv.org/abs/2404.12272](https://arxiv.org/abs/2404.12272)

- **Academic:** Chiang et al. — Binary scoring study (referenced in AWS LLM Evaluation Agent docs, 2025) — Adaptable binary scoring (pass/fail per criteria) produces more reliable judge results than numeric scales across judges and criteria. — [startups.aws.com/prompt-library/llm-eval-agent](https://startups.aws.com/prompt-library/llm-eval-agent)

- **OSS:** awesome-pro/guardloop (MIT, created 2026-05-03) — Production runtime guardrails: budget caps, circuit breakers, per-tool call limits, verify-fix-retry loops, CI integration. — [github.com/awesome-pro/guardloop](https://github.com/awesome-pro/guardloop)

## Gotchas

- **Shipping an eval that never runs is not evaluation — it's decoration.** If your suite runs on a schedule nobody watches and doesn't gate CI, it provides false confidence. It will not catch the regression that matters.
- **The judge's biases are your biases.** If you use the same model family for agent and judge, the judge will prefer outputs that favor its own training distribution. Use a different model family for the judge, or at minimum a different version.
- **Golden datasets are a snapshot, not a stream.** If your eval suite uses only a static dataset, it will pass your agent on queries that have shifted in meaning since the dataset was labeled. Merge production trace sampling into the eval pipeline to catch distribution drift.
- **Catching a wrong output is not the same as catching a wrong process.** If you only grade final outputs, you miss the agent that took the long way, the one that read stale data and happened to output the right answer, and the one that corrupted state but recovered before responding. You need step-level instrumentation to catch these.
- **Human review at scale is a workflow problem, not a grading problem.** Labeling 1,000 traces for judge calibration requires an annotation queue, clear criteria, and a relabeling cadence — not just good intentions. LangSmith, Langfuse, and Phoenix each provide annotation queue features for this.
