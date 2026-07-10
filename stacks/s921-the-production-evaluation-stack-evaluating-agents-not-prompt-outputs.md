# S-921 · The Production Evaluation Stack: Evaluating Agents, Not Prompt Outputs

[Evaluating a single LLM call is solved — you check the response against a rubric. Evaluating an agent is different: a 20-step pipeline that completes successfully may have taken the worst possible path, and an agent that failed may have been unlucky rather than broken. The challenge is measuring trajectories, not just outputs.]

## Forces

- [Agents are probabilistic pipelines, not single calls — a 10-step pipeline with 85% reliability per step succeeds only ~20% of the time end-to-end, and failures distribute non-obviously across steps]
- [Standard NLP metrics (BLEU, ROUGE, F1) assume a single right answer — agents can complete the same task correctly via wildly different paths, or incorrectly via paths that look plausible]
- [Production traces reveal failure modes that never appear in curated eval sets — teams that only test against synthetic data are flying blind]
- [LLM-as-judge scales evaluation but inherits model bias — a judge's calibration matters as much as the agent's capability]
- [Agent eval data rots fast — a set that reflects the agent's behavior today may be misleading by next sprint as the model or tools change]

## The move

Track what actually happened, not just what the agent said. Build eval pipelines from four layers:

- **Trajectory capture.** Instrument every agent run end-to-end: each tool call, its arguments, the raw response, and the step's outcome. OpenTelemetry traces or Braintrust's trace format are common formats. This is the raw material for all downstream eval.
- **Outcome scoring.** Did the agent achieve the goal? Binary or rubric-based, applied to the final output. This is necessary but not sufficient — a correct answer arrived at via a broken path is a ticking bomb.
- **Trajectory scoring.** Evaluate the *path*: was the plan coherent? Were tools used correctly? Did the agent recover from bad intermediate results? LLM-as-judge (using a separate, often cheaper model) is the dominant approach for scaling this. Anthropic recommends evaluating with a model one tier below the agent's capability to avoid grade inflation.
- **Golden dataset from production.** Mine real failures from production traces — the agent hallucinated a tool name, passed malformed JSON, hit a rate limit, or dead-lettered. Turn each failure into a test case. Braintrust's Loop tool auto-generates eval cases from production traces using AI.

Specific eval harnesses in use (2025-2026):

| Tool | Focus | Source |
|------|-------|--------|
| **Braintrust** | Trajectory traces, LLM-as-judge scorers, CI integration | braintrust.dev |
| **AgentBench** (OSWorld, ToolBench) | Multi-domain agent benchmarks | OSWorld, WebArena |
| **Internal trace DBs** | Company-specific eval pipelines | Anthropic customers (anecdata) |
| **LangSmith** | LangChain-native eval, production traces | LangChain |

## Evidence

- **Engineering blog:** Anthropic's "Building Effective Agents" (Dec 2024) — recommends tracing every step, separating outcome from trajectory quality, and using production failures as the primary signal: "We recommend that developers start by using LLM APIs directly. Many patterns can be implemented in a few lines of code." — [URL](https://www.anthropic.com/engineering/building-effective-agents)
- **HN discussion:** "Ask HN: How are you orchestrating multi-agent AI workflows in production?" (3 months ago) — multiple practitioners describe using OpenTelemetry + custom dashboards for trace-level observability, and separate evaluation pipelines from production pipelines — [URL](https://news.ycombinator.com/item?id=47660705)
- **Article:** Braintrust "AI Agent Evaluation: A Practical Framework for Testing Multi-Step Agents" (Feb 2026) — defines trajectory vs outcome eval, documents LLM-as-judge calibration pitfalls, and recommends building eval from production traces: "An AI agent that performs well in demos could hallucinate instructions, call the wrong APIs, repeat the same actions in loops, and produce outputs that miss the original request entirely." — [URL](https://www.braintrust.dev/articles/ai-agent-evaluation-framework)
- **Article:** Towards Data Science "Agentic AI: On Evaluations" (Aug 2025) — documents the gap between traditional NLP metrics and agent-specific evaluation, recommends separate metrics for tool selection accuracy, plan quality, and execution efficiency — [URL](https://towardsdatascience.com/agentic-ai-evaluation-playbook/)

## Gotchas

- **Eval dataset staleness is invisible.** An eval set built today reflects the agent's behavior at that point. Model updates, tool schema changes, and prompt edits invalidate old tests silently. Treat eval sets as code: version them, run regression on every update, and expire cases that no longer represent production conditions.
- **LLM-as-judge has calibration drift.** Judges are themselves LLMs and can be too lenient, too harsh, or systematically biased toward certain response styles. Validate judge scores against human-rated samples quarterly — don't assume the judge's output is ground truth just because it came from a larger model.
- **Coverage is not the same as correctness.** High eval coverage (many test cases) masks low signal if the cases don't represent actual failure modes. A 500-case suite covering easy paths is weaker than a 30-case suite derived from real production failures.
- **Trajectory length skews evaluation.** Longer agent runs have more opportunities to diverge. Normalize eval scores by trajectory length or step count, or separately report early-exit failure rates vs late-step failure rates.
