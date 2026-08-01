# S-1964 · The Trace-First Evaluation Stack — When You Deploy an Agent and Don't Know If It Worked

*When your agent produces a plausible final answer, passes a simple pass/fail check, and ships to production — only to reveal six weeks later that it was taking the wrong path on 30% of runs, burning budget on useless tool calls, and hallucinating justifications for steps it never took.*

## Forces

- **Agents fail mid-trace, not at the end.** An agent that picks the wrong tool, retrieves the wrong document, or loops on a failing step can still produce a plausible final answer. If you only check the answer, you miss the failure.
- **Agent evaluation breaks three assumptions of traditional testing.** Tests assume deterministic outputs (agents are probabilistic), single calls (agents take multi-step trajectories), and observable failures (agent failures are often silent and retroactive).
- **Trajectory quality is independent of answer quality.** A correct answer achieved in 200 tool calls reveals a different problem than one achieved in 2. An agent that reaches the right destination by looping through every wrong intermediate step is not working — it's lucky.
- **Evaluation cost compounds with complexity.** Running full end-to-end evals on every change is expensive and slow. Teams need to know which layer to evaluate at to catch failures at the right cost point.

## The Move

**Evaluate at three layers, in order of cost and coverage: end-to-end, trajectory, and per-turn.**

### Layer 1 — End-to-End (Output-Level)
Check the final result against ground truth or explicit success criteria. Use task-completion metrics and deterministic assertions. This is your cheapest, fastest gate — it catches obvious failures. But it cannot tell you *why* the agent failed or whether it succeeded for the wrong reasons.

```python
from deepeval import evaluate
from deepeval.metrics import TaskCompletionMetric

result = evaluate(
    experiment_name="customer-support-agent",
    metrics=[TaskCompletionMetric(threshold=0.8)],
    runs=50
)
```

### Layer 2 — Trajectory (Path-Level)
Inspect the full sequence of steps: which tools were called, in what order, with what arguments, and what observations came back. This is where the real signal lives. Trajectory eval catches looping, wrong tool selection, unnecessary steps, and silent hallucinations in intermediate reasoning. Set up tracing from day one.

```python
from deepeval.tracing import observe
from deepeval.metrics import TaskCompletionMetric

@observe(metrics=[TaskCompletionMetric()])
def trip_planner_agent(destination, start_date, end_date):
    # Every tool call, LLM call, and intermediate step
    # is captured in the trace automatically
    ...
```

### Layer 3 — Per-Turn (Step-Level)
For high-volume or latency-sensitive deployments, run lightweight classifiers at each step to catch wrong tool selection or bad arguments before they compound. Per-turn classifiers can run at <90ms latency, enabling inline quality gates without blocking the loop.

### Instrument for Observability From Day One
Capture traces even before you have evals. Without visibility into what the agent actually did, you cannot design evals, debug failures, or reason about quality. Use a tracing platform appropriate to your stack:

| Tool | Strength | Best For |
|------|----------|----------|
| LangSmith | LangChain/LangGraph first-party, online scoring | Teams already in LangChain ecosystem |
| Braintrust | Generous free tier, eval-first design, unlimited users | Teams needing fast eval iteration |
| Arize Phoenix | OpenTelemetry-native, open source | Teams wanting self-hosted or OTel-aligned |
| Langfuse | Open source, self-hostable | Organizations with data-sovereignty requirements |
| Microsoft Foundry GH Action | CI/CD integration | Enterprises with Azure/Foundry stack |

### CI/CD Gate for Agents
Treat agent evaluation like code: run offline eval in your CI pipeline before every deploy. The Microsoft Foundry GitHub Action pattern — invoke agents with test queries, collect performance data, run evaluators, generate a summary report — catches regressions that unit tests cannot. The agent is the runtime; evaluate the runtime, not just the code that starts it.

## Evidence

- **Anthropic engineering post:** After working with dozens of teams building LLM agents across industries, Anthropic found that the most successful implementations used simple, composable patterns — and explicitly recommended starting with direct LLM API calls rather than frameworks. They emphasized three architectural patterns: agents (dynamic multi-step), chains (predefined tool sequences), and supervised execution (human approval at key gates). — [Anthropic — Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)

- **Research firm analysis:** Gartner projects that by 2028, **40% of enterprise AI failures** will trace to inadequate evaluation and monitoring rather than model capability gaps. This means teams investing in better models but not better measurement are solving the wrong half of the problem. — [The Thinking Company — AI Agent Evaluation in Production, March 2026](https://thinking.inc/en/blue-ocean/agentic/ai-agent-evaluation-production/)

- **Production survey:** Over 57% of surveyed production agent teams use judge LLMs at runtime for quality gating, hallucination defense, and tool-call verification. Small distilled judges (Patronus Lynx 8B, Prometheus 2 7B) deliver **97% cost reduction** at **0.88–0.95 accuracy** compared to large proprietary judges — making LLM-as-judge economically viable at production scale. — [Zylos Research — LLM-as-Judge in Production, April 2026](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026)

## Gotchas

- **End-to-end only is theater.** Stopping at "did the task complete" without inspecting the trajectory means you have no idea whether the agent succeeded by reasoning or by luck. You will ship regressions you cannot see and call them features.

- **LLM-as-judge is expensive at scale.** An LLM judge evaluating every production trace is slow and costly. Reserve it for: nuanced quality judgments (tone, policy compliance, helpfulness), offline eval runs on your test dataset, and periodic sampling of production traffic. Use deterministic checks (exact match, JSON schema validation, tool-call argument validation) for everything else — they're fast, cheap, and unambiguous.

- **Observability is not optional infrastructure.** Without traces, you cannot debug failures, design evals, or reason about quality. The minimum viable observability is logging every tool call, LLM call, and observation to a file or trace store. Start before you need it — you need it before you know you need it.
