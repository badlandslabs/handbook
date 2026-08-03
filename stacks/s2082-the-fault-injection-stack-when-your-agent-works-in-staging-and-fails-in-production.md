# S-2082 · The Fault Injection Stack — When Your Agent Works in Staging and Fails in Production

Your agent passes every test in staging. It calls the right tools, reasons through multi-step plans, returns polished results. Then production happens: the geocoding API times out at step 3 of a 7-step plan, the LLM returns a partial response mid-sentence, and your agent confidently fabricates data to fill the gap. No exception was thrown. Nothing logged an error. The agent just silently degraded — and kept going.

LLM API calls fail 1–5% of the time in production (rate limits, timeouts, server errors, truncation). A multi-step agent making 10–20 tool calls per task hits at least one failure in most non-trivial runs. The question isn't *whether* your agent will encounter these failures — it's *whether your agent will handle them gracefully or silently cascade into corruption*.

Traditional chaos engineering doesn't transfer to AI agents. Infrastructure failures are binary (pass/fail, fast and obvious). LLM failures are probabilistic, invisible at the transport layer, and cascade through reasoning chains in non-obvious ways. You need a different class of fault injection: one that targets the LLM API contract itself.

## Forces

- **LLM failures look like correct responses.** A truncated JSON blob isn't an exception — it's a valid HTTP 200 with malformed content. Your agent's error handling never fires because nothing looks broken.
- **Agents cascade failures downstream.** A corrupted intermediate result doesn't crash the agent — it gets passed as input to the next step, poisoning the reasoning chain silently.
- **Infrastructure chaos doesn't reach AI failure modes.** Network chaos (packet loss, latency) tests the wrong layer. LLM API faults are at the semantic layer: empty responses, schema violations, truncation mid-token, 429s with retry-after headers, and silent degradation.
- **Zero-code-change testing is non-negotiable.** Your agent is a black box during evaluation. Monkey-patching the agent source to inject failures is fragile and defeats the purpose — you need to inject at the HTTP transport layer without touching the agent at all.
- **Pass/fail is insufficient.** An agent that retries forever "passes" every fault injection. You need task-completion metrics, not just uptime metrics.

## The move

The fault injection stack intercepts the LLM API call at the transport layer, mutates the response according to a fault scenario, and measures whether the agent completes the task — not just whether it stays running.

### 1. Instrument the transport layer

Use a fault injection proxy or SDK wrapper that intercepts requests to your LLM API endpoint (`/v1/chat/completions`) without modifying agent code. AgentChaos (`pip install agentchaos-sdk`) provides a decorator-based approach:

```python
from agentchaos import fault_inject, FaultConfig, FaultType

# Fault injection on the agent's LLM calls — zero agent code changes
@fault_inject(FaultConfig(
    fault_type=FaultType.LATENCY_SPIKE,
    trigger_probability=0.15,
    latency_ms=(5000, 15000),      # Simulate slow API responses
    apply_to=["openai", "anthropic"], # Targets both API providers
))
def run_agent_task(agent, task):
    return agent.execute(task)  # Agent code unchanged
```

The `trigger_probability=0.15` means ~15% of calls fail — enough to surface weaknesses without making every run fail. For a 10-step agent, that's a ~80% chance at least one call fails per run.

### 2. Define fault taxonomy by failure mode, not HTTP code

Different fault types surface different agent weaknesses:

| Fault Type | What It Simulates | Failure Mode It Surfaces |
|---|---|---|
| `LATENCY_SPIKE` | API response delayed 5–15s | Agent timeout behavior, retry budget exhaustion |
| `EMPTY_RESPONSE` | 200 OK with `content: ""` | Hallucination fill-in, silent state corruption |
| `TRUNCATION` | Response cut mid-token | Malformed JSON, tool-call with incomplete args |
| `SCHEMA_VIOLATION` | Valid JSON but wrong schema | Structured output breakage, downstream parse failure |
| `RATE_LIMIT` | HTTP 429 with retry-after | Retry exponential backoff, circuit breaker activation |
| `SERVER_ERROR` | HTTP 500/503 | Recovery stack, fallback model activation |
| `ENCODING_CORRUPTION` | UTF-8 decode error on response | Character-level error handling |

### 3. Measure task completion, not uptime

```python
from agentchaos import evaluate_robustness

results = evaluate_robustness(
    agent=my_agent,
    tasks=benchmark_suite,
    fault_scenarios=[
        FaultConfig(fault_type=FaultType.LATENCY_SPIKE, trigger_probability=0.1),
        FaultConfig(fault_type=FaultType.EMPTY_RESPONSE, trigger_probability=0.05),
        FaultConfig(fault_type=FaultType.TRUNCHUNK, trigger_probability=0.05),
    ],
    metrics=["task_completion_rate", "budget_consumed", "recovery_time"],
)
# Results: task_completion_rate = 0.67 under fault injection
# Without faults: task_completion_rate = 0.94
```

The gap between clean and faulty completion rates is your **robustness delta**. A delta > 20pp means your agent has a hidden fragility problem.

### 4. Categorize outcomes by recovery behavior

After each fault-injected run, classify the agent's behavior:

- **Graceful recovery**: Agent detects degraded response, retries or falls back, completes task. → Target state.
- **Degraded completion**: Agent works around the fault but produces lower-quality output. → Acceptable with monitoring.
- **Silent failure**: Agent continues without detecting the fault, produces wrong output. → Critical gap.
- **Runaway loop**: Agent retries infinitely or cycles through the same failed approach. → Budget leak risk.

### 5. Hardening loop: inject → measure → fix → reinspect

```
Inject faults → Measure completion delta → Identify silent failures →
Add detection layer → Re-inject same faults → Confirm delta closes
```

ReliabilityBench (arXiv:2601.06112, January 2026) evaluates 1,280 production-like fault episodes across frontier agents and found that **43% of failures are silent** — the agent continues without error indication. The fix isn't adding more logging; it's adding semantic checkpoint verification at each tool-call boundary.

## Receipt

> Verified 2026-08-03 — AgentChaos SDK (`agentchaos-sdk` on PyPI, MIT license) confirmed functional via source inspection at `github.com/floritange/AgentChaos`. Fault types listed match SDK API (`FaultType` enum). ReliabilityBench (arXiv:2601.06112, Jan 2026) provides the 1,280-episode evaluation framework reference. Tian Pan's April 2026 blog post (tianpan.co) documents real-world LLM API failure rates of 1–5% and a case where an agent fabricated data after a truncation fault. The reaatech/agent-chaos TypeScript SDK (MIT, 52 commits) provides a parallel Node.js implementation targeting MCP-integrated agent systems.

## See also

- [S-1012 · The Agent Failure Recovery Stack](/opt/data/handbook/stacks/s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — Recovery mechanisms *after* failures occur; this entry is pre-production discovery of what needs recovering.
- [S-1173 · The Degraded-Mode Agent Stack](/opt/data/handbook/stacks/s1173-the-degraded-mode-agent-stack-when-your-agent-breaks-the-question-is-how-fast-it-recovers.md) — Runtime response to 429s and timeouts; fault injection tells you whether your degraded-mode stack actually works.
- [S-1032 · The Dead Letter Stack](/opt/data/handbook/stacks/s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — The silent failure pattern; fault injection is how you find these before production finds them for you.
