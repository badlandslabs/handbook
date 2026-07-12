# S-1004 · The Agent Eval Stack — When Your Benchmark Says Pass but Production Keeps Breaking

Most teams treat AI evaluation as a checkbox: run the benchmark, ship the agent. Then production surfaces a failure pattern the benchmark never caught — an agent that loops on edge cases, tool-calls that silently fail, or a trajectory that takes 10x the expected steps. You need an eval system that measures what agents actually do, not just what they answer.

## Forces

- **The three-layer gap.** Final-answer scoring misses trajectory quality, tool-call correctness, and per-turn recovery. Agents can produce correct answers via wrong or dangerous paths. Most teams only measure layer one.
- **Offline eval goes stale.** A fixed golden dataset degrades as models, prompts, and tools evolve. The eval that passed last month may reflect a world that no longer exists. Keeping it current is an open-ended maintenance burden.
- **LLM-as-judge needs its own calibration.** Grading outputs with a second LLM introduces variance and bias. An uncalibrated judge can greenlight failures and reject good outputs — and you won't know unless you check it against human ground truth.
- **Online monitoring is the gap nobody closes.** Offline regression suites gate shipping. Ongoing production sampling catches what static tests cannot. Most teams have the first. Almost nobody has the second.

## The Move

Build a layered eval architecture with three measurement layers, two temporal stages (offline + online), and a calibration loop on the judge.

**Layer 1 — Final-answer scoring (mandatory minimum):**
- Score the last agent output against expected result: exact match, regex, JSON schema, or LLM judge
- Fast, cheap, deterministic where possible; run on every commit via CI
- Required but not sufficient — a correct answer via a wrong path still hides risk

**Layer 2 — Trajectory scoring (where most agent quality lives):**
- Score the sequence of steps, tool calls, retries, and intermediate results
- Key metrics: tool-call accuracy, step count vs. expected, loop detection, recovery success
- Catch: agents that take 40 steps to do what 4 should, or call the wrong tool and recover by accident
- LangSmith traces, Phoenix spans, or custom transcript parsers make this inspectable

**Layer 3 — Per-turn classifiers (production-grade signal):**
- Score each reasoning/action turn independently in production at 1–5% sampling rate
- Binary or ternary: progressing / stuck / failing
- <90ms latency target to stay inline in the reasoning loop
- This is the layer that catches instruction drift and semantic tool-call errors in real traffic

**Offline gating:**
- Run layer-1 + layer-2 on a versioned golden dataset before every release
- Dataset: 50–200 cases tied to specific capabilities, not hundreds of generic ones
- Consolidate aggressively — fewer high-signal evals beat hundreds of low-signal ones

**Online monitoring:**
- Sample layer-3 production traffic (1–5% of sessions) with binary turn classifiers
- Alert on drift: if "stuck" turn rate rises above baseline, investigate before users report it
- Cluster related failures: 40 sessions failing for the same reason surface as 1 issue with a frequency count, not 40 log entries

**LLM-as-judge calibration:**
- Run judge outputs against a small human-calibrated anchor set (20–50 examples)
- Measure agreement rate; recalibrate when it drops below 80%
- Use code-based graders for verifiable assertions (format, schema, exact values); reserve model-based judges for subjective quality (helpfulness, tone, coherence)

## Evidence

- **Anthropic Engineering (Jan 2026):** Detailed guide on agent evaluation — defines the three-layer structure (task/trial/grader/transcript), covers code-based graders (fast, objective, brittle), model-based graders (flexible, non-deterministic), and human graders (expensive, gold standard). Recommends combining all three types based on what you're measuring. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- **Hacker News (11 months ago, 128 pts):** Thread on production AI agent principles — practitioners confirm "evaluations are vital for improving performance" and that teams "winging it without robust eval practices" are not trustworthy. One engineer who owned a coding agent eval suite describes consolidating from hundreds to fewer high-signal cases tied to specific capabilities. — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)
- **BigData Boutique (May 2026):** Layered eval architecture: offline regression suites + online/shadow evaluation + human-calibrated anchors. Key claim: "Most teams treat LLM evaluation as a tool-selection problem. It is not. Frameworks slot into that architecture; they do not replace it." Compares DeepEval, Ragas, Braintrust, Phoenix, LangSmith, Langfuse, and MLflow across 8 axes. — [bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices](https://bigdataboutique.com/blog/llm-evaluation-frameworks-metrics-best-practices)
- **Benchmarking Agents Review (Apr 2026, Vol. III):** Online vs. offline distinction: offline gates shipping (fixed dataset, deterministic), online monitors production (real traffic sampling, catches drift). Notes that most teams have some offline eval; systematic online monitoring is the rare exception. Covers cost-per-correct and regression detection via sampling. — [benchmarkingagents.com/for-production-monitoring](https://benchmarkingagents.com/for-production-monitoring)
- **MorphLLM (2026):** Three-layer agent eval (final-answer, trajectory, per-turn). Per-turn classifiers can run at <90ms latency. Production labels from per-turn eval feed back into training signal (fine-tune data, RL reward terms) — closing the loop so the agent improves from corrected behavior. — [morphllm.com/ai-agent-evaluation](https://www.morphllm.com/ai-agent-evaluation)

## Gotchas

- **A passing benchmark is not a safe agent.** An agent can score 95% on final-answer while looping on 20% of trajectories — and you won't see the loops unless you measure them.
- **Layer-3 per-turn eval requires an inspectable transcript architecture.** If your agent runtime doesn't expose step-by-step traces, you can't run per-turn classifiers. Invest in tracing before you invest in layer-3 evals.
- **Judge agreement degrades over time.** Model graders drift as base models update. Re-run calibration checks against human anchors monthly, not just at launch.
- **Sampling bias in online monitoring.** 1–5% sampling misses low-frequency failure modes. Supplement with targeted sampling on known risky inputs (edge cases, high-stakes actions).
- **Eval maintenance is a tax, not a one-time cost.** A stale golden dataset is worse than no dataset — it gives false confidence. Budget engineering time for ongoing eval maintenance as a first-class concern.
