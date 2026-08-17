# S-1000 · The Agent Evaluation Stack — When the Agent Looks Okay But You've No Idea If It Works

The agent passes every test you wrote on day one. It routes tasks correctly, calls tools in order, and produces fluent output. Six months later it has silently drifted — a prompt was adjusted, a tool response format changed, and the agent now silently fails on 12% of cases. The dashboard shows green. The users noticed first.

Agent evaluation is the hardest unsolved problem in production AI. Unlike traditional software, agents can succeed by multiple paths, fail in ways that look correct, and change behavior without any code change. Building the eval layer is not optional — it is the difference between an agent you trust and one you hope.

## Forces

- **Agents are non-deterministic by design.** Traditional software testing assumes determinism: same input → same output. Agents can take different tool sequences for the same request, all producing valid results. You cannot assert a single correct path — you must assert outcomes and constraints.
- **Trajectory quality ≠ outcome quality.** An agent can reach a correct final answer via a terrible reasoning path (hallucinated intermediate facts, wrong tool calls corrected later). Optimizing for outcome alone misses dangerous behaviors that happen to self-correct.
- **Eval quality is hard to verify itself.** LLM-as-judge has become the default — but judges drift, correlate with the model being judged, and may agree for the wrong reasons. Without measuring judge correlation against human ground truth, your eval system has unknown accuracy.
- **Eval data rots.** Prompts drift, tool schemas evolve, model capabilities shift. An eval suite that passes today may be measuring yesterday's failure modes — giving you false confidence that the agent is improving when it is merely staying still.
- **Cost and latency make continuous eval expensive.** Full trajectory evaluation with multiple LLM calls per step compounds cost. Teams that skip continuous eval because it's too expensive ship agents that silently degrade.

## The Move

Build evaluation into the agent runtime itself — not as a post-hoc testing layer but as a first-class component of the harness. The Anthropic 2026 Agent Harness architecture (Session, Harness, Sandbox, Credentials, Tool Protocol, Context Builder, **Trace**, **Eval**) makes this explicit: Trace captures every tool call, decision, and token boundary; Eval scores the trajectory and outcome against defined rubrics. This separates evaluation from prompting, making eval results reproducible and comparable across model versions.

Specifically:

- **Separate trajectory metrics from outcome metrics.** Trajectory metrics score the reasoning path (did the agent use the right tools in the right order, avoid hallucinations, handle errors gracefully). Outcome metrics score the final result (is the answer correct, complete, and formatted correctly). Both are necessary. Over 40% of agentic AI projects face cancellation due to insufficient evaluation frameworks — teams measure completion, not correctness of the process that led to it.
- **Use LLM-as-judge with ground-truth calibration.** LLM-as-judge correlates with human judgment at 0.80+ Spearman correlation when properly calibrated, but this requires a golden dataset of human-scored examples. Run judge output against human ground truth before deploying. Do not trust an uncalibrated judge on safety-critical or high-stakes outputs.
- **Build a 3-tier rubric.** Top level: 5-7 dimensions (accuracy, completeness, safety, coherence, efficiency, etc.). Each dimension: 3-5 sub-dimensions. Each sub-dimension: concrete behavioral items. For a customer support agent this might be: dimension "safety" → sub-dimension "no PII exposure" → items: "email not in response," "phone not in response," "address not in response."
- **Integrate evals into CI/CD.** Trigger eval runs on: every commit (regression detection), scheduled batch (drift detection), and event-driven (new tool added, prompt changed, model version updated). Galileo Labs recommends all three trigger types — the scheduled batch catches silent drift that commits miss.
- **Use sandboxed eval environments.** Run agent evaluations against isolated environments with synthetic data — do not evaluate against production APIs or live user data. The eval harness should control what the agent can see and do so failures are contained.
- **Track cost-per-task alongside quality.** Agents that achieve the same outcome with fewer tool calls and fewer tokens are better. Track token efficiency as a first-class metric alongside accuracy. Anthropic's multi-agent research showed 15x token variation across equivalent task completions.

## Evidence

- **Anthropic engineering blog (Jun 2025):** Multi-agent research system uses subagents as "intelligent filters" — each iteration scores and filters the previous output, building evaluation into the execution loop itself. Token usage became a proxy for path quality; measuring it revealed that parallel subagents exploring fewer, more targeted queries outperformed single agents doing exhaustive breadth-first search. — [https://www.anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)

- **Galileo Labs blog (Feb 2026):** Over 40% of agentic AI projects will be canceled by end of 2027 due to insufficient evaluation frameworks. Proposes 3-tier rubric (7 dimensions → 25 sub-dimensions → 130 behavioral items) and LLM-as-judge targeting 0.80+ Spearman correlation. Recommends three eval trigger types: commit, scheduled, and event-driven. — [https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

- **Catio blog (Jun 2026):** Agentic architecture separates "agentic" from stateless LLM systems by the closed-loop property: the agent perceives, plans, acts, and re-evaluates. This re-evaluation step is the eval primitive — production systems need explicit trace + score loops at every tool boundary, not just a final output check. — [https://www.catio.tech/blog/agentic-ai-architecture](https://www.catio.tech/blog/agentic-ai-architecture)

- **Luhui Dev / Hashnode (May 2026):** Anthropic's Agent Harness framework evolved through four phases — long context, workflow vs. autonomous loop, multi-agent orchestration, and the current runtime-with-eval approach. The key insight: "no matter how long the context window is, it's still tokens the model sees in a single call. It gets expensive. It degrades. It gets compressed. It gets polluted by noise." Eval is the feedback mechanism that compensates for this fragility. — [https://luhuidev.com/en/essays/anthropic-2026-agent-harness-managed-agents](https://luhuidev.com/en/essays/anthropic-2026-agent-harness-managed-agents)

## Gotchas

- **Do not evaluate only final output.** Agents that reach correct answers via broken reasoning are dangerous — they will fail silently when the lucky self-correction doesn't happen. Instrument every tool boundary, not just the final response.
- **LLM judges agree with themselves too easily.** A judge of the same family as the model being judged will often give generous scores because it recognizes its own reasoning style. Calibrate against human-labeled examples before trusting judge scores for high-stakes decisions.
- **Eval data is a moving target.** The behaviors you test today may not be the behaviors that matter in six months. Build a process for retiring eval cases when tools change, and add new cases when new failure modes emerge. A static eval suite is a stale eval suite.
- **Silent drift is the most dangerous failure mode.** An agent that degrades 1% per week across six months will fail on 30% of tasks by month six — and if you're only measuring top-level task success rate, you won't catch it until users complain. Scheduled batch evals with trend tracking are the defense.
- **Cost eval is often forgotten.** Token efficiency and tool call count are real costs. An agent that achieves 95% outcome accuracy but uses 3x the tokens of a leaner alternative may not be worth the quality margin in cost-sensitive applications. Track cost-per-successful-task as a first-class metric.
