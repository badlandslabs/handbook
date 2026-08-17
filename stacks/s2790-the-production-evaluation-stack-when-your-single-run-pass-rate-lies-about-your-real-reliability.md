# S-2790 · The Production Evaluation Stack — When Your Single-Run Pass Rate Lies About Your Real Reliability

You benchmarked your agent. 60% pass rate. Good enough to ship. Then you run it eight times in a row on the same task and it succeeds only twice. The problem isn't a bad model — it's that your eval design was measuring a number that has almost nothing to do with what users experience.

## Forces

- **Single-run pass rate overstates reliability.** A 60% single-trial agent running the same task 8 times can have as low as 25% pass-on-all-8 reliability — a 58% collapse no standard benchmark catches. Pass@k masks this further: a 70%-per-trial agent has pass@3 ≈ 97% and pass@8 ≈ 34%.
- **Benchmarks don't simulate production traffic.** Golden datasets built from product specs reflect ideal inputs. Real users type messy queries, use unexpected tools, introduce context drift across turns. A suite passing at 98% on golden data and 60% on live traffic is a known pattern in the field.
- **Standard eval frameworks assume ground truth exists.** Most production agent failures — cascading tool errors, semantic drift over long conversations, plan abandonment — have no reference answer. Traditional pass/fail against a known correct output doesn't apply.
- **Cost is part of quality.** A Claude Opus agent at $0.75/task that solves 38% of tasks costs 4× more per success than an o3 Medium agent at $15.15/task that solves 38.8% — but the gap in capability and reliability across task types is significant. Cost-aware evaluation changes which agent is "best."

## The move

Build a three-layer production eval stack: **offline benchmark suite** for pre-deployment gating, **trajectory-level trace analysis** for post-deployment health, and **reliability-over-trials measurement** to catch the single-run lie.

### Layer 1 — Offline eval harness with per-dimension assertions

Run agent evaluations across four dimensions, each asserting a minimum threshold:

| Dimension | What it measures | Minimum threshold |
|-----------|-----------------|-------------------|
| **Trajectory** | Step count, unnecessary tool calls, loops, ordering | Required steps present, no loops |
| **Tool use** | Correct tool selected, argument validity, error recovery | Correct tool + valid args |
| **Task completion** | Goal achievement, answer correctness, resolution rate | Task complete or gracefully escalated |
| **Multi-turn coherence** | Context retention, handoff quality across turns | No contradictory prior statements |

Use a unified harness (HAL `hal-eval` CLI, DeepEval with pytest integration, or custom with OpenTelemetry) to get reproducible, CI-gated results. Assert per-dimension, not as an aggregate: a 0.85 aggregate hides a 0.62 on argument validity behind a 0.97 on tool selection, and production fails on the argument layer.

### Layer 2 — Reliability-over-trials measurement

Run each task 5–10 times and track:
- **Single-trial pass rate** — standard pass/fail per run
- **N-run reliability** — fraction of runs where all N trials pass
- **Failure mode distribution** — categorize failures (wrong tool, bad argument, plan drift, hallucination, timeout)

If single-run → N-run reliability drops more than 20 percentage points, the agent is unreliable regardless of what the single-run number says. Surface this gap explicitly.

### Layer 3 — Production trace scanning (post-deploy)

Instrument the running agent with OpenTelemetry spans. On a schedule (hourly or per-session batch), scan traces for:
- **Semantic failures** — agent returned successfully but the result is wrong (e.g., wrong flight, deleted wrong file). These are invisible to APM metrics that only check latency and error codes.
- **Drift patterns** — agent behavior degrading over time or across context window resets
- **Cost anomalies** — token usage per task spiking without task complexity increase
- **Tool call chains** — detect loops, excessive retries, and unnecessary tool use

Tools like Lemma (YC F25) are purpose-built for this: scanning every trace to surface semantic failures that observability tools miss. AgentShield provides execution tracing with risk detection on outputs and human-in-the-loop approval for high-risk actions.

### The cost-quality matrix

When comparing agents for a given benchmark, track cost per successful task — not raw performance. HAL's AssistantBench data shows this clearly:

| Agent | Model | Performance | Cost per task |
|-------|-------|-------------|---------------|
| Browser-Use | o3 Medium | 38.8% | $15.15 |
| Browser-Use | GPT-5 Medium | 35.2% | $41.69 |
| Browser-Use | o4-mini Low | 28.1% | $9.22 |

The o3 Medium at $15.15 dominates GPT-5 Medium at $41.69 on both performance and cost. Always run the cost-quality cross before committing to a model.

## Evidence

- **HAL leaderboard (Princeton SAgE, ICLR 2026):** Tracks 26,597 rollouts across 9 benchmarks with cost-aware evaluation. Best-in-class agents on CORE-Bench (hard scientific programming) still resolve below 25% at Pass@1 — showing that even frontier agents have significant reliability headroom. — [https://hal.cs.princeton.edu](https://hal.cs.princeton.edu)
- **arXiv:2605.01604 "Evaluating Agentic AI in the Wild":** Studied agents across 42 scenarios and seven metrics. Found standard metrics fail to detect 4 of 7 failure modes entirely, and detect 3 others only after a lag of multiple evaluation cycles. Introduced production evaluation framework addressing compounding errors, tool failure cascades, and non-deterministic drift. — [https://arxiv.org/abs/2605.01604](https://arxiv.org/abs/2605.01604)
- **The Operator Collective (2025):** Surveyed production AI teams. Found 60% single-run pass rate collapses to 25% across 8 consecutive runs. Amazon discovered after building thousands of agents internally that traditional LLM evaluation methods fundamentally fail for agentic systems. — [https://theoperatorcollective.org/blog/ai-agent-evaluation-measure-agent-performance](https://theoperatorcollective.org/blog/ai-agent-evaluation-measure-agent-performance)
- **DeepEval (MIT, Confident AI):** Open-source eval framework with 15+ built-in metrics including task completion, step efficiency, reasoning quality, faithfulness, and hallucination. Integrates with LangGraph, CrewAI, Anthropic, and Google ADK. Runs via pytest for CI/CD integration. — [https://github.com/confident-ai/deepeval](https://github.com/confident-ai/deepeval)
- **Langfuse engineering guide:** Defines the four evaluation dimensions (trajectory, tool use, task completion, multi-turn) with standard metrics for each. Recommends combining Ragas for RAG metrics, custom evaluators for agent metrics, and OpenTelemetry for production health. — [https://langfuse.com/resources/engineering/ai-agent-evaluation](https://langfuse.com/resources/engineering/ai-agent-evaluation)
- **MCPAgentBench (arXiv, 2025):** Introduces dynamic sandbox with distractor tools to test tool discrimination. Comprehensive metrics for task completion rate and execution efficiency. Reveals significant performance variance across LLMs on multi-step MCP tool invocations. — [https://arxiv.org/abs/2512.24565](https://arxiv.org/abs/2512.24565)
- **Hacker News "Ask HN: How are you monitoring AI agents in production?":** Community discussion surfacing AgentShield (observability SDK with execution tracing and risk detection), OpenTelemetry integration, and concern about semantic failures invisible to APM. Noted DataTalks Claude Code database wipe and Replit agent data deletion during code freeze as catalyst incidents. — [https://news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)

## Gotchas

- **Don't evaluate only the final output.** The answer looks correct but the agent took a broken path — it just happened to arrive at the right place by luck. Trace-level evaluation catches this; output-only evaluation doesn't.
- **Don't run pass@k as your primary metric.** It tells you "given K attempts, does one succeed?" not "will this agent succeed once?" The former is an upper bound; the latter is what users get.
- **Golden datasets drift.** Re-synthesize test cases from live traffic, not from the original spec. Treat golden sets as stale after 30 days without refresh.
- **LLM-as-judge needs calibration.** Without few-shot examples and human review of judge outputs, the judge amplifies whatever bias it starts with. Pin the judge with reviewer corrections as in-context examples.
- **Cost-per-task changes selection.** An agent that scores 5 percentage points higher but costs 3× as much per success may not be the right choice for high-volume tasks. Run the cost matrix before committing to a model.
