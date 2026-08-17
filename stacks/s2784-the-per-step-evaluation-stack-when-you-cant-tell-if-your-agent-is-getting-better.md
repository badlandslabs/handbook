# S-2784 · The Per-Step Evaluation Stack — When You Can't Tell If Your Agent Is Getting Better

Your agent completes tasks. It returns 200. It passes your integration tests. But you have no idea if it's actually improving between releases, because you've been evaluating output quality by staring at the output. A 5% per-step error rate sounds acceptable until you realize it means your 10-step pipeline succeeds end-to-end only ~20% of the time. The per-step evaluation stack is the measurement architecture that makes agent quality visible, comparable, and improvable — not just guessable.

## Forces

- **Agents are trajectories, not functions.** Evaluating only the final output misses where in the chain things went wrong. The agent decided to call the wrong tool at step 3; by step 7 it's producing confident nonsense. Traditional unit tests against final outputs catch none of this.
- **Golden datasets go stale fast.** Agents hallucinate new failure modes every sprint. A static test set built in January is measuring last quarter's bugs, not this quarter's.
- **LLM-as-judge is powerful but gameable.** A model evaluating another model's output is fast and cheap, but it has a "politness bias" — it rates things higher than human evaluators would, and can be systematically fooled by output length or formatting.
- **Failure compounds.** A 10-step pipeline at 85% per-step reliability → ~20% end-to-end success. Without per-step diagnostics, you don't know which step is the bottleneck, so you can't fix it surgically.
- **Human labeling doesn't scale.** Having engineers read through agent traces to score them works for 50 test cases. It doesn't work for 50,000 production trajectories.

## The Move

Build a layered evaluation architecture that measures agent quality at every level: trajectory, step, tool call, and output.

### 1. Capture full trajectories, not just outputs

Log every turn — every LLM call, every tool invocation, every tool result, every decision point — as structured trace data. Tools like LangSmith, Maxim AI, and LangChain's `agentevals` package make this the entry point, not an afterthought.

```python
# LangChain agentevals — capture trajectory from LangGraph thread
from agentevals import TrajectoryMatchEvaluator
evaluator = TrajectoryMatchEvaluator(model="o3-mini")
results = evaluator.evaluate_batch(trajectories=langgraph_thread)
```

### 2. Evaluate per step, not per task

Measure success or failure at each individual step. A verifier agent — often a smaller, faster model — checks whether each tool call's output is semantically correct. If the verifier says "no," trigger a self-correction loop.

The compounding math makes this non-negotiable: fixing one weak step in a 10-step pipeline improves overall reliability more than optimizing the already-strong steps.

### 3. Use LLM-as-judge with guardrails

LLM judges are fast and scalable, but they need structure to avoid politeness bias. The proven approach:

- **In-context few-shot examples** with scored examples (both passing and failing) to anchor the judge
- **Structured output schemas** so the judge returns `{"score": 1, "reasoning": "..."}` rather than prose
- **Cross-reference against production telemetry** — if an eval score looks good but production error rates are rising, the eval is wrong, not the agent

### 4. Build a golden dataset from production, continuously

The most effective teams generate test cases from real production failures. When an agent fails in production, write the trajectory to a test case immediately. Over time, your eval suite becomes a living record of every failure mode your agent has encountered.

LangChain's agentevals package includes utilities for extracting trajectories from LangGraph threads, making it straightforward to capture and replay production traces as test cases.

### 5. Track cost-per-trajectory alongside quality

An agent that achieves 95% accuracy at $14 per session is not the same as one achieving 95% accuracy at $0.40 per session. Evaluation must include cost and latency alongside quality metrics. Budget caps (e.g., Tardigrade's `BudgetConfig`) prevent runaway spending during eval runs.

### 6. Alert on eval drift, not just production errors

Set a baseline eval score for each task type, then alert when the rolling average drops below threshold. This catches degradation before it becomes a production incident.

## Evidence

- **Framework benchmarks:** Weekly benchmarks across 40+ AI agent frameworks (agenticallysh/agent-framework-benchmarks, Oct 2025) show LangChain leading on production readiness (9.5/10), AutoGen on speed (180ms avg), Semantic Kernel on cost ($0.45/1k tokens). No single framework dominates all categories — the right choice depends on which quality dimension you need to optimize. — [GitHub Readme](https://github.com/agenticallysh/agent-framework-benchmarks)
- **Per-step eval math:** A 5% per-step error rate compounds to ~23% end-to-end failure across 5 steps. Conversely, identifying and hardening just the single weakest step delivers disproportionate overall improvement. — [Future AGI Evaluation Framework](https://futureagi.com/blog/agentic-ai-evaluation-2025/)
- **Klarna production eval:** Klarna used LangSmith's evaluation capabilities to move from 70% to 80% agent accuracy, identifying which design choices actually mattered by benchmarking against production data. — [LangSmith Case Study](https://info.langchain.com/agent-benchmarks)
- **7 failure modes that bypass traditional testing:** HN discussion identified hallucination under unexpected inputs, edge case collapse (Unicode, nulls), prompt injection, context limit surprises, silent degradation, tool call misordering, and confidence without accuracy as categories that unit tests systematically miss. — [Hacker News Ask HN](https://news.ycombinator.com/item?id=47325105)
- **Dapr CNCF agentic framework:** The Dapr project (CNCF) released an agentic AI framework (March 2025) with explicit reliability primitives — distributed tracing, state management, and actor model — built in rather than bolted on. — [Hacker News Show HN](https://news.ycombinator.com/item?id=43483255)

## Gotchas

- **Eval quality depends on eval design quality.** An LLM judge evaluating a task it wasn't specifically prompted to judge will give inflated scores. Invest in the few-shot examples and scoring rubric as much as the evaluation infrastructure.
- **Coverage ≠ correctness.** Running 1,000 eval cases doesn't mean you're testing the right things. Map eval cases to your actual failure modes from production, not to textbook categories.
- **Context window limits during eval.** Long trajectories exceed context windows for some models, making late-step evaluation impossible. Truncate or summarize earlier steps, but document that you're doing it.
- **Flakiness is real, not an eval problem.** A 15% flakiness rate on otherwise-correct agents is a feature, not a bug. Your eval harness needs to run each test case 3-5 times and report pass rates, not pass/fail on a single run.
- **Eval results lag behind production failures.** The fastest feedback loop is production telemetry (hours to days). Structured evals against golden datasets catch known patterns but miss novel failure modes. Use both.
