# S-1392 · The Agent Evaluation Stack — When You Ship Agents and Don't Know If They Work

You shipped the agent. It passes the test cases. It works in staging. Three weeks later, users are getting confident-sounding wrong answers, burning budget on retry loops, and calling support because the agent did something it wasn't permitted to do. Nobody caught it because your eval suite only checked whether the agent could succeed — not whether it would fail safely, whether it was allowed to do what it did, or whether your latest prompt change quietly broke 15% of cases.

## Forces

- **Agents are stochastic and trajectory-dependent.** A single eval run with one prompt variant tells you almost nothing. The agent's path to success matters as much as whether it arrived — wrong tool calls, excessive tokens, and lucky timing can all produce a passing result on a non-representative input.
- **What agents say and what they're permitted to do are different tests.** A test suite that validates output quality is silent on authorization, temporal policy compliance, and compositional constraint violations. Rippletide calls this the "authority gap" — the agent can do X but was never allowed to.
- **Regression from prompt changes is invisible without trajectory tracking.** Editing a system prompt and watching an aggregate success rate hold while step counts spike 40% is a common failure mode. Aggregate pass rate masks per-task-class regressions that are only visible in traces.
- **LLM-as-a-judge introduces its own biases.** Frontier models used as graders exhibit position bias (prefer the first answer), verbosity bias (prefer longer responses), self-preference bias, and familiarity bias. Without calibration, you may be optimizing against your grader's preferences, not your users' needs.
- **Offline evals are necessary but not sufficient.** 52% of organizations run offline evaluations on test sets, but only ~33% have continuous production monitoring (Rippletide, 2026). The gap between "passed the test suite" and "working in production" is where most agent failures live.

## The Move

Build a layered eval architecture that answers three questions at three different scopes: Did it complete the task? Did it get there efficiently and correctly? Did each component behave? Then gate deployment and monitor continuously in production.

**1. The three-layer metric model**

| Layer | What it measures | Example metrics |
|-------|-----------------|-----------------|
| Task-level | End-to-end goal attainment | Task success rate, completion rate, user satisfaction |
| Trajectory-level | Path quality and efficiency | Steps to completion, token cost per task, tool call count, retry loops |
| Component-level | Individual step correctness | Tool selection accuracy, argument correctness, retrieval precision |

Track all three. A stable task success rate hiding a 3x increase in tool call count is a cost regression, not a win.

**2. Task/Trial/Grader — the Anthropic base model**

Define each eval as a **Task** (input + success criteria), run multiple **Trials** per task to handle output variance, and use a **Grader** (rule-based, LLM-based, or human) to score each trial. Build the eval suite *before* the agent is fully built — it forces explicit agreement on what success looks like and what edge cases are acceptable.

**3. Code the criteria, not just the expected output**

Output-matching tests break on paraphrasing. Instead:
- **Unit tests** for tool call arguments and return type parsing
- **Compilation/syntax checks** for code generation agents
- **Regex validation** for structured output schema compliance
- **Golden datasets** (input → expected trajectory → expected output) for regression suites
- Run golden datasets multiple times (stochastic variance); flag flaky passes.

**4. Three structural gap tests (from Rippletide)**

Before shipping, verify the agent hasn't crossed three lines:
- **Authority gap:** Can the agent access or modify resources it shouldn't? Test with scoped permission boundaries.
- **Temporal gap:** Does the agent's behavior match current policies, not policies frozen at test-writing time? Auto-refresh eval criteria or flag stale test cases.
- **Composition gap:** Do two individually correct steps compose into a wrong or dangerous outcome? Test agent chains end-to-end, not just individual turns.

**5. LLM-as-a-judge with bias mitigation**

Use a frontier LLM as grader, but account for its known failure modes:
- Present candidates in random order to neutralize position bias
- Calibrate verbosity bias by scoring conciseness separately from correctness
- Include a "model reference" trap (a clearly wrong answer) to detect self-preference
- Periodically audit LLM-judge decisions against human judgment (calibration loop)

For code agents: **Agent-as-a-judge** — an LLM agent evaluating intermediate states achieves parity with human evaluators on code tasks (Confident AI, 2026).

**6. The deployment pipeline: offline → shadow → canary → full**

1. **Offline eval suite** — curated golden dataset, run on every prompt/System prompt change and every PR
2. **Shadow mode** — route production traffic to new variant, evaluate without affecting users; catch silent regressions
3. **Canary release** — 5–10% traffic; monitor task success rate, cost/task, latency; increase if metrics hold
4. **Full rollout** with continuous monitoring — traces + dashboards; alert on metric deltas, not just absolute thresholds

**7. Continuous production monitoring**

Track operating envelopes alongside quality: cost per task, latency per step, token budgets, retry loop detection. Store traces with full context (model, temperature, tool calls, arguments, results) using OpenTelemetry semantic conventions for correlation. Alert on step count increases, cost spikes, and trajectory anomalies — not just final output quality.

## Evidence

- **Company engineering post (Anthropic):** The three-layer metric model (task/trial/grader), building evals before agents, and regression tracking as a compounding investment — [Anthropic Engineering: Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) (Jan 9, 2026)

- **Engineering blog (Rippletide):** 52% of organizations run offline evals but only ~33% have production monitoring; authority/temporal/composition gap taxonomy; factual claim verification against hypergraph of trusted data — [Rippletide: AI Agent Evaluation](https://www.rippletide.com/resources/blog/ai-agent-evaluation-why-your-current-testing-framework-will-not-survive-production) (Mar 19, 2026)

- **Engineering blog (Confident AI):** Single-turn vs multi-turn eval distinction, LLM-as-a-judge bias modes, DeepEval for in-repo CI tracing, golden dataset variance testing, three-tier human review pipeline (rule checks → LLM-judge → human) — [Confident AI: Definitive AI Agent Evaluation Guide](https://www.confident-ai.com/blog/definitive-ai-agent-evaluation-guide) (Apr 13, 2026)

- **HN thread (jxmorris12):** "Why eval startups fail" — community discussion on the gap between eval tooling and actual production agent reliability needs, May 2026 — [HN: Why eval startups fail (2025)](https://news.ycombinator.com/item?id=48637868)

- **Engineering blog (Udit.co):** CI/CD pipelines for agent systems, BFCL for function-calling evals, OSWorld for OS operations, Tau-bench for tool use, per-turn lightweight classifiers at <90ms for regression monitoring — [Udit.co: AI Agent Testing Beyond POC](https://udit.co/blog/raw/ai-agent-testing-evaluation) (2025–2026)

## Gotchas

- **Aggregate pass rate is a lie.** A 95% pass rate across 1,000 test cases hides the fact that your coding agent regressed 40% on JSON parsing tasks — visible only in traces. Diff the score distribution, not just the aggregate.
- **Golden datasets rot.** Tests written against yesterday's policy or product behavior silently become false negatives. Automate eval criteria refresh or schedule regular test case audits.
- **You will over-index on what you measure.** If you only track task success rate, teams will optimize for completing tasks while burning 10x the budget on unnecessary tool calls. Measure cost and trajectory alongside quality from day one.
- **LLM-as-a-judge drift.** Frontier models change. Your grader's rubric calibration from March may not hold in June. Build a human-in-the-loop calibration checkpoint into your eval pipeline — periodic human review of grader decisions is not optional.
- **Multi-turn convergence is not the same as task completion.** An agent that loops 30 times before succeeding on a 3-turn task is not equivalent to one that succeeds in 3 turns. Step count budget, token budget, and convergence rate are first-class metrics.
