# S-2246 · The Agent Eval Stack — When Your Agent Looks Good But Fails in Production

When an agent scores 92% on your test set but crashes in production, or when you can't tell if a new model version is actually better or just got luckier on your benchmarks.

## Forces

- Traditional LLM evals treat agents as black boxes and score only the final output — they miss the reasoning chain, tool selections, and context decisions that determine real-world reliability
- The pass@1 / pass@k gap is catastrophic: an agent achieving 70% per-trial success has a 97% pass@3 rate but only ~34% pass^3 across 3 consecutive trials — teams routinely mistake pass@3 for pass^3 and overestimate reliability by 3×
- Silent failures are invisible to structural checks — an agent can return a factually incorrect but structurally valid response and pass every schema validation
- 72% of AI teams believe comprehensive testing drives reliability, yet only 15% achieve elite eval coverage; the gap is operational, not conceptual
- Agent failures propagate forward: a bad decision in step two corrupts step three, which corrupts step four, until the final output fails — making retrospective post-mortems nearly useless without execution traces
- Without a golden dataset, eval scores are not comparable across runs, versions, or models — teams ship "improvements" that are actually noise

## The Move

Build a three-pillar evaluation system that scores outcome, trajectory, and safety — not just the final answer.

**1. Separate outcome eval from trajectory eval.**
Outcome eval asks "did the agent accomplish the task?" Trajectory eval asks "did the agent accomplish the task the right way?" An agent that reaches the correct answer through a reckless path — wrong tool first, lucky recovery, ignored constraints — should fail trajectory eval even if outcome eval passes. Score both independently.

**2. Build the golden dataset from production failures, not synthetics.**
Mine real failures from production traces: ambiguous inputs, edge cases, injection attempts, and regression cases. Supplement with adversarially crafted test cases. Minimum viable set is 50–200 labeled examples; for LLM-as-judge calibration, aim for 100+ human-labeled examples. Keep 20% held out — never tune against the full set.

**3. Calibrate LLM-as-judge against human reviewers before trusting it.**
Run your judge on human-labeled examples first. Acceptable agreement: Cohen's kappa ≥ 0.6. Without calibration, the judge inherits the model's biases and certifies wrong paths. Re-calibrate quarterly or after any model change.

**4. Run a tiered CI eval pipeline — don't gate everything equally.**
Three tiers match cost to risk:
- *PR tier (minutes, cheap):* Fast structural checks, schema compliance, finish-rate regressions. Blocks obviously broken commits.
- *Nightly tier (hours, moderate cost):* Full golden dataset, trajectory scoring, LLM-as-judge runs. Catches regressions before morning.
- *Production tier (continuous, sampling):* Shadow evaluation on live traffic, statistical comparison of score distributions, deployment gate requiring no significant regression.

**5. Track reliability over single runs.**
Run each golden dataset example 5–10 times. Report pass@k rates, not pass@1. Set CI thresholds on pass@1 and monitor pass@3 and pass@5 as leading indicators — a declining pass@5 catches brittleness before it becomes a CI failure.

**6. Instrument traces, not just outputs.**
Capture the full execution graph: every LLM call with its full prompt, every tool invocation with arguments and results, every decision point. Traces make post-mortems diagnostic instead of speculative. Without traces, you cannot tell whether a failure was a bad model call or a bad tool choice or a bad context window.

## Evidence

- **HN Ask thread:** "No visibility into what the agent did step-by-step, surprise LLM bills from untracked token usage, risky outputs going undetected, and no audit trail for post-mortems" — responses highlighted AgentShield, OpenTelemetry tracing, and custom instrumentation as common approaches; one practitioner noted they run agents in read-only mode until trace logs prove the decision path is safe — [Hacker News, "Ask HN: How are you monitoring AI agents in production?" (2026)](https://news.ycombinator.com/item?id=47301395)
- **Google Cloud blog:** Silent failure case study — an inventory-reporting agent gave correct numbers but referenced last year's report; the result "looked" right but execution failed silently. Google's three-pillar framework (Agent success/quality, Process/trajectory analysis, Safety/resistance) directly addresses this: "To debug effectively, you must understand the trajectory — the sequence of reasoning and tool calls leading to the result" — [Google Cloud, "A methodical approach to agent evaluation" (Nov 2025)](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)
- **jamesm.blog:** The trajectory eval case — endpoint scoring certifies answers, not behaviour. A minimal viable trajectory eval setup: 50–200 real examples, per-step rubrics, 10+ runs per example, statistical regression tracking, held-out set never tuned against. Replay harnesses let teams re-run a captured trace against a new model to isolate whether failures are model-induced or tool-induced — [jamesm.blog, "Evaluating Agents in Production: Trajectory Metrics, Not Just Final Answers" (June 2026)](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics)
- **Galileo AI / State of Eval Engineering Report:** 72% of AI teams believe comprehensive testing drives reliability; only 15% achieve elite eval coverage. The 57-point gap is operational, not knowledge-based. Teams establishing evaluation practices during experimental stages experience 60% fewer delays when scaling — [Galileo AI, State of Eval Engineering Report (2025)]
- **Digital Applied / 2026 methodology guide:** pass@3 vs pass^3 reliability gap — a 70%-per-trial agent shows 97% pass@3 but only ~34% pass^3 (reliability across 3 consecutive runs). Practical targets: ≥100 golden examples for judge calibration, Cohen's kappa ≥ 0.6 for judge acceptance, 60–80% of dev time on evals for successful teams, CI threshold ≥ 0.85 average score — [Digital Applied, "Building an AI Agent Evaluation Pipeline: 2026 Methodology"](https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology)
- **Braintrust:** Golden datasets grade the product as it was when curated. Production traces grade it as it runs now, and carry the span graph around the failing call. Anthropic's own postmortem (three recent issues) noted that evaluations "didn't capture the degradation" because engineers couldn't access the user interactions evaluations were meant to represent — [Tessary/Braintrust, "Production Traces vs Golden Datasets for LLM Evals" (2026)](https://tessary.ai/blog/production-traces-vs-golden-datasets-llm-evals)

## Gotchas

- **Structurally valid ≠ semantically correct.** An agent that hallucinates a plausible fact and formats it correctly passes every schema check. Add semantic validators, not just structural ones.
- **Golden datasets rot.** Inputs that looked hard six months ago may be trivially solved now. Refresh your dataset from production failures quarterly — or your CI is measuring the wrong distribution.
- **Judging the judge is non-negotiable.** Deploying LLM-as-judge without calibrating it against human-labeled examples means your automated scoring is unvalidated. You are optimizing toward a number that means nothing.
- **Cost compounds fast.** Running full golden datasets with LLM-as-judge on every commit can cost 10–15% of your production LLM spend. Tier your pipeline so expensive evals run nightly, not on every PR.
- **Anthropic and OpenAI model updates silently break agents.** Shadow evaluation running continuously against production traffic catches model-shift regressions within hours. Without it, you learn about broken agents from users.
