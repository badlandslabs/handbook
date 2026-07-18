# S-1324 · The Agent Eval Stack — When Your Framework Has No Measure of Wrong

Your agent passes every integration test. It calls tools, reasons through steps, and completes multi-turn tasks. But you have no idea whether it completes the *right* tasks, whether it's calling the *right* tools, or whether a recent prompt change made it 40% worse on a failure mode that only surfaces in production. You're flying blind in production — and you won't know until a customer tells you.

This is the **Agent Eval Stack** — a layered evaluation system built around the insight that agents are fundamentally harder to evaluate than LLMs, because the "answer" is not a text output but an entire execution trajectory. You need to measure not just outcomes but paths, and you need to do it at three levels: end-to-end, trajectory-level, and component-level.

## Forces

- **The output is a trajectory, not a text.** Traditional LLM metrics (BLEU, ROUGE, perplexity) measure the quality of a single text output. An agent's output is a sequence of decisions, tool calls, reasoning steps, and final outcomes — none of which those metrics capture.
- **Non-determinism makes regression testing feel impossible.** The same input can produce different trajectories on different runs. You can't just assert "output == expected" — you need probabilistic metrics with statistical thresholds.
- **Trajectory vs. outcome tension.** A task can complete (outcome) via a wasteful or wrong path (trajectory), or fail (outcome) despite using the correct approach (trajectory). You need both types of metrics, and they often conflict.
- **Eval overhead vs. shipping pressure.** Building a robust eval harness takes real engineering time. Teams defer it until production failures force the issue — by which point they've accumulated months of untested prompt drift.

## The Move

Build a **two-layer eval architecture** combining a code-first framework for offline regression gating with an observability platform for production tracing. Evaluate agents at three levels — end-to-end, trajectory, and component — using a mix of deterministic checks and LLM-as-judge.

### The Two-Layer Architecture

**Layer 1 — Offline CI Gate (Code-first frameworks)**
- Run eval suites on every commit using pytest-style assertions on research-backed metrics
- Tools: **DeepEval** (most popular open-source, 6+ built-in agent metrics), **RAGAS** (RAG-focused but extending to agent metrics like tool call accuracy), or **promptfoo** (HTTP-based, model-agnostic)
- Gate merges if pass rate exceeds threshold; fail and surface the exact trace on regression

**Layer 2 — Production Tracing (Observability platforms)**
- Capture every production trace: full execution path, tool calls, reasoning steps, latency, cost
- Tools: **LangSmith** (lowest friction for LangChain users), **Langfuse** (open-source, self-hostable, ~31k stars), **Arize Phoenix** (open-source, strong for multimodal), **Braintrust** (eval-first design, good for custom scoring)
- Enable alerting on metric drift: if task success rate drops 10% week-over-week, wake the team

### The Three Evaluation Levels

1. **End-to-end (task completion):** Did the agent finish the right task? Binary or graded success. Primary signal. Source from production traces with human-labeled ground truth.
2. **Trajectory-level (efficiency):** Was the path correct and efficient? Number of steps, tool call count, whether the agent loops or backtracks. Explains *why* a task failed, not just that it did.
3. **Component-level (spot-check):** Does each piece (retriever, planner, tool executor) work in isolation? Deterministic checks: tool call schema validity, argument correctness, retrieval precision.

### The Metric Stack

| Metric | Level | Method | Threshold Signal |
|--------|-------|--------|-----------------|
| **Task Success Rate** | End-to-end | Human-labeled eval set | Primary KPI |
| **Step Efficiency** | Trajectory | Tool call count vs. expected | <1.5x expected steps |
| **Tool Call Correctness** | Component | Schema validation + determinism | 100% valid calls |
| **Plan Adherence** | Trajectory | LLM-as-judge: "Did it follow the plan?" | >80% adherence |
| **Reasoning Quality** | Trajectory | LLM-as-judge: structured rubric | >75% agreement with human |
| **Latency per Step** | All | Timing instrumentation | p95 <2s per step |
| **Cost per Task** | End-to-end | Token counting | Track drift over time |

### LLM-as-Judge: Calibrate Before You Scale

LLM-as-judge is the only scalable way to evaluate subjective dimensions (reasoning quality, plan quality, answer helpfulness). But it is not a free pass:

- **Validate first.** Run judge outputs against 50-200 human-labeled examples. Calibrate to 75–90% agreement with human labels before trusting at scale.
- **Use deterministic checks for exact things.** Tool call correctness, schema validity, argument types — these don't need a judge and are faster and more reliable.
- **Feed the right inputs.** Garbage input → garbage judge output. The judge needs the full trajectory context, not just the final answer.
- **Don't chase 100%.** A 100% pass rate on LLM-as-judge is a sign the rubric is too lenient or the eval set is too easy. Real production systems have failure modes.

### Build the Eval Set from Production, Not Imagination

- **Collect from failures.** Every production incident where the agent did the wrong thing becomes an eval case. Start with 30-50 examples; grow organically.
- **Include edge cases deliberately.** Agents fail on ambiguous inputs, boundary conditions, and multi-step dependencies — none of which random sampling captures well.
- **Keep it honest.** Separate eval sets from training data. If you're using eval examples to tune prompts, hold out a test set you never touch.

### Integration Triggers

Evaluation is only valuable if it runs automatically. Implement three trigger types:
- **Commit-based:** Run full eval suite on every PR. Block merge if task success drops below threshold.
- **Schedule-based:** Run eval on production traffic sample weekly. Catch drift from model version changes or prompt drift.
- **Event-based:** Trigger on deployment events, model swaps, or schema changes.

## Evidence

- **DeepEval README & Confident AI blog:** Open-source pytest-style framework with 6+ built-in agent metrics (task completion, tool call accuracy, step efficiency, argument correctness, plan adherence, reasoning quality). DeepEval is the most-starred open-source LLM eval framework on GitHub. — [deepeval.com](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)
- **AgentsCamp tool comparison (2026):** Documents the two-layer architecture split — "code-first frameworks for CI gate + observability platforms for production tracing." Comparative table of DeepEval, RAGAS, LangSmith, Langfuse, Arize Phoenix, Braintrust, and promptfoo with specific strengths. — [agentscamp.com](https://agentscamp.com/guides/evaluation/best-llm-eval-tools-2026)
- **Galileo AI benchmarks (July 2026):** Reports single-run agent success at ~60%, multi-run (8 attempts) at ~25%. Notes that 74% of production agents still rely on human-in-the-loop evaluation rather than automated evaluation. — [galileo.ai](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)
- **Arize AI LLM-as-Judge guide:** Validates judge model against 75–90% human label agreement before scaling. Notes that feeding the judge the full trajectory context (not just final answer) is critical for accurate scoring. — [arize.com](https://arize.com/llm-as-a-judge/)

## Gotchas

- **Treating LLM-as-judge as ground truth.** The judge model has its own biases (length preference, verbosity skew, positional effects). Calibrate against human labels before deploying; re-calibrate quarterly as models change.
- **Eval set too easy or too small.** If your eval set only covers happy paths, you're not measuring robustness. Target 50-200 examples with deliberate edge cases, not random samples.
- **No trajectory-level visibility.** Outcome-only metrics (task success yes/no) don't tell you *why* a task failed. Always instrument traces — tool calls, reasoning steps, intermediate outputs — so a failure surfaces with enough context to diagnose.
- **Measuring latency but not cost.** An agent that achieves 99% task success but costs $4 per task is not production-viable. Track cost per task alongside latency; they often trade off.
- **Eval drift from production.** If your eval set doesn't match production traffic distribution, your metrics are measuring the wrong thing. Re-sample from production logs every 4-6 weeks.
