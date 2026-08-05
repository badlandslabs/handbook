# S-2189 · The Invisible Eval Stack — When Your Agent Always Passes but Always Fails

Your agent ships. The tests pass. The final answer looks right. Then a user escalates because the agent called the wrong tool, took a needlessly expensive 23-step path, and silently corrupted a record that no test was watching. The agent never errored out. It never failed a check. It was wrong by every metric that matters to your users, and your eval suite caught none of it.

This is the invisible eval stack: the failure mode where an agent produces correct-looking outputs while taking paths that are wrong, wasteful, or dangerous — because the evaluation system was measuring the wrong things, at the wrong level, or not at all.

## Forces

- **Agents reason over trajectories, not just outputs.** A correct final answer produced through the wrong tool sequence is a failed agent by production standards. Most evals score only the endpoint.
- **The escalation ladder has a cost-order.** Deterministic checks (zero cost, fully deterministic) sit at the bottom; LLM-as-judge (high token cost, variable reliability) sits at the top. Most teams either skip the cheap checks and overspend on judges, or skip the expensive ones and miss the failures only a judge can catch.
- **Trajectory evaluation is systematically underdone.** Tracing every step of an agent's execution path — the tool calls, the intermediate reasoning, the branching decisions — is the hardest part of evaluation and the most frequently skipped. LangChain's June 2026 data: 89% of organizations have observability in place, but only 52% run offline evals on test sets, and only 37% run online evals on production traffic.
- **LLM-as-judge is powerful but has a known position-bias problem.** Research on 21 LLM judges showed position bias ranged from p=0.002 to p=0.5 — significant enough to flip pass/fail decisions depending on answer order.
- **Offline eval catches regressions; online eval catches drift.** Teams that only test before shipping and never monitor production consistently experience quality degradation within 30–60 days.

## The Move

Evaluate agents on four dimensions, at three levels, using two modes. Never stop at final-answer scoring.

**Four dimensions to measure (Langfuse, Confident AI):**

- **Trajectory** — Did the agent take a reasonable path? Score the quality of decisions, not the exact sequence. Rigid path-matching fails when valid routes diverge from the expected one.
- **Tool use** — Did it call the right tools with correct arguments? Tool-argument validation belongs on individual tool-call observations, not the final trace.
- **Task completion** — Was the user's goal met? Attach to the root of the trace, not intermediate steps. A task can be partially complete across many correct-seeming steps.
- **Multi-turn quality** — Did performance hold across the full conversation? A session can produce five individually reasonable turns that collectively fail to resolve the issue.

**Three evaluation levels (LangChain):**

- **Run-level** — individual LLM call: output correctness, latency, token cost
- **Trace-level** — full execution path: trajectory quality, tool-call accuracy, state changes (did the agent create the right artifacts or side effects?)
- **Thread-level** — multi-turn conversation: session-level goal resolution, escalation rate

**Two modes to run:**

- **Offline (pre-ship):** Run evals against curated test datasets before every significant change. Catches regressions. Use deterministic checks (exact match for structured outputs, regex for import resolution, syntax validation) as the cheapest and fastest gate.
- **Online (production):** Sample production traffic and run evals continuously. Catches drift from model updates, prompt changes, or data distribution shifts. Targets: task completion rate, escalation rate, cost per task.

**Build the escalation ladder from the bottom up (Vercel):**

| Check type | Cost | Determinism | Right for |
|---|---|---|---|
| Deterministic assertion | Zero | Fully deterministic | Syntax, import resolution, format enforcement |
| Exact match | Low | Deterministic | Structured outputs (JSON schemas) |
| Semantic similarity | Low–moderate | Mostly deterministic | Paraphrase-tolerant text comparison |
| LLM-as-judge | High (token cost) | Variable (position-sensitive) | Judgment calls the cheap checks cannot make |
| Custom domain metric | Highest | Deterministic once built | Domain-specific correctness only a specialist can validate |

**Metrics that matter in production (FuturOneAI framework, Confident AI):**

- Task completion rate — target >85% without human intervention
- First-pass accuracy — target >70% accepted without revision
- Escalation rate — target <15% returned to human
- Cost per task — must be below equivalent manual cost
- Latency P50/P95 — task-dependent, but an agent that answers correctly in 60 seconds when the user expects 10 has failed
- Hallucination rate on tool calls — did the agent fabricate API responses or claim to have called tools it didn't?

## Evidence

- **Langfuse engineering guide:** "Evaluate agents on four dimensions: trajectory, tool use, task completion, and multi-turn quality. Tool-argument checks belong on tool-call observations, and task completion belongs on the root of the trace. Many agents are conversational, so the session, not the trace, is the unit users experience." — https://langfuse.com/resources/engineering/ai-agent-evaluation

- **LangChain agent evaluation resource:** "An agent can pass every test and still be fragile in production. The answers look great at first. But when a user asks a question your test suite already covers, the agent can take a different route. Correct answers can mask unstable, inefficient, or risky execution paths." Industry data: 89% of organizations have observability, but only 52% run offline evals on test sets and 37% run online evals. — https://www.langchain.com/resources/agent-evals

- **Vercel eval framework:** "A wrong answer in step two doesn't stay contained to step two. It corrupts every step downstream that depended on it being right. Order matters more than method choice: start with the cheapest check that can catch a given failure." Position bias across 21 LLM judges ranged from p=0.002 to p=0.5. — https://vercel.com/i/ai-agent-evaluation-frameworks-production

- **OpenAI cookbook (Langfuse integration):** "Evaluating agents is important for debugging issues when tasks fail, monitoring costs and performance in real-time, and improving reliability and safety through continuous feedback." Documents the offline + online eval pattern used by teams shipping with the OpenAI Agents SDK. — https://developers.openai.com/cookbook/examples/agents_sdk/evaluate_agents

## Gotchas

- **Scoring only the final answer misses most failure modes.** Retrieval can return wrong documents, a tool can be called with malformed arguments, and a loop can repeat the same failing call — none visible if you only evaluate final text.
- **Trajectory evaluation is too often too rigid.** Asserting that an agent must follow a specific sequence of tool calls in a specific order fails when valid paths diverge from the expected one. Score what matters: outcome and decision quality.
- **LLM-as-judge without calibration produces noisy signals.** Position bias, temperature variance, and judge-model quality mean uncalibrated judges can flip pass/fail on the same trace. Run human annotation to calibrate judges before trusting them at scale.
- **Evaluating once before launch is not evaluation — it's a checkpoint.** Teams that stop monitoring post-launch consistently experience quality degradation within 30–60 days. Treat evaluation as an operational practice, not a pre-launch checklist.
