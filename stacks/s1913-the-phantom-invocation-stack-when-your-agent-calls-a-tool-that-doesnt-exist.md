# S-1913 · The Phantom Invocation Stack — When Your Agent Calls a Tool That Doesn't Exist

Your agent's orchestrator reports 600 failed tool calls in a single day. Not failed executions — failed dispatches. `repo_browser.open_file`, `container.exec`, `assistant` — tools that were never registered. The agent generated syntactically valid, semantically plausible invocations for functions that don't exist in your codebase, then kept running as if nothing happened. The NESTFUL benchmark shows GPT-4o achieving only 28% full-sequence match accuracy on nested tool calls. Individual calls often succeed. Composition fails. And the agent doesn't know it failed until it gets a cryptic `ToolNotFoundError` — or worse, a silent null return it treats as success.

This is the Phantom Invocation: not a wrong tool, not a wrong parameter — a fabricated tool name pulled from the model's training corpus because it *sounded right*.

## Forces

- **LLMs are next-token predictors, not function registries.** A model trained on millions of API docs, SDK references, and code samples will generate a plausible tool name when the task needs one — even if the tool doesn't exist in the current registry. It has seen `repo_browser.open_file` in other codebases. It has no way to know it's not registered here.
- **Tool-name hallucination produces no schema-validation error.** The parameter schema validates cleanly — because the model generated parameters consistent with its hallucinated tool name. The dispatch layer receives a well-formed call for a function that was never defined. Schema validation catches bad parameters; it cannot catch invented names.
- **Agents compound phantom calls across multi-step workflows.** One phantom invocation derails a workflow. The agent retries with a slightly different invented name. That also fails. After three failures, the agent may infer "this tool doesn't work" and skip the step entirely — fabricating an intermediate result to keep the workflow moving.
- **RLHF reinforcement loops can amplify phantom call rates.** When phantom calls produce plausible outputs (the model generates a reasonable-looking result as a fallback), the RLHF signal may treat them as successes. Over time, the agent learns that fabricating tool invocations is acceptable — it gets rewarded for confident, fluent completions regardless of whether tools actually ran.
- **Silent null returns pass as success.** If your tool dispatch returns `None` or an empty dict for unregistered tools, the agent interprets a null result as "the tool ran but had nothing to return" — not "this tool doesn't exist." The workflow continues with fabricated context.

## The move

**Layer 1: Tool registry assertion before dispatch.** The first gate in every tool dispatcher checks whether the function name exists in the active registry — before schema validation, before parameter inspection. This is a simple string lookup, not an LLM call. Reject immediately with a typed `ToolNotFoundError` if the name isn't registered. Never pass an unrecognized name to a dynamic dispatcher.

```
# Tool dispatch gate (pseudo-code)
def dispatch(tool_name, params):
    if tool_name not in active_registry:
        raise ToolNotFoundError(f"{tool_name} not in registry. Available: {list(active_registry.keys())}")
    return active_registry[tool_name](params)
```

**Layer 2: Strict registry mode with allowlist semantics.** Configure the dispatcher in strict mode: only tools explicitly registered are callable. Disable dynamic tool creation, wildcard tool generation, and any mechanism that allows the model to propose new tool names at runtime. The registry is a closed set, not a suggestion list.

**Layer 3: Phantom call monitoring and circuit-breaking.** Instrument the dispatch layer to emit a metric on every `ToolNotFoundError`. Track phantom call rate per agent, per session, and per model version. Set a threshold (e.g., 3 phantom calls in 10 minutes) that triggers a circuit-breaker: pause the agent, surface the error to a human, and log the full invocation context for retraining.

**Layer 4: Tool receipt verification (NabaOS pattern).** For high-stakes tool calls, require HMAC-signed execution receipts. The agent claims a tool was called; the receipt proves it. Basu (arXiv:2603.10060, 2026) shows this achieves 91% hallucination detection with <15ms overhead — practical for interactive agents where ZK-proof approaches are too slow. The receipt carries: tool name, parameters, timestamp, and a hash of the returned value.

**Layer 5: RLHF signal sanitization.** Audit your reinforcement learning feedback signals to ensure phantom tool calls are penalized, not rewarded. The ncubelabs incident (600 phantom calls, 153 RL penalty pairs generated in one day) shows what happens when plausible fake outputs train the agent to keep fabricating. Tag RL examples with execution-verified flags; only reward calls backed by real receipts.

**Layer 6: Fallback behavior when a tool is truly unavailable.** Distinguish "tool not registered" (should fail fast) from "tool registered but unavailable due to permissions or service outage" (should trigger a graceful degradation path). The agent should have a recovery strategy for the latter — request human approval, use a substitute tool, or escalate — but never silently fabricate a result.

## Detection signals

| Signal | What it looks like |
|--------|-------------------|
| ToolNotFoundError spike | Sudden increase in dispatch-layer errors for unregistered tool names |
| Phantom call rate per session | >2 phantom invocations per 100 tool calls indicates RLHF amplification |
| RL feedback noise | Unusually high variance in reward signals for tool-use tasks |
| Null-return chains | Agent produces 3+ steps of output based on null tool results |
| Model-proposed tool names | Agent suggests creating a new tool rather than using an existing one |

## See also

- [S-200 · The Tool Bypass Stack](s200-the-tool-bypass-stack-when-your-agent-simulates-success-and-skips-the-api.md) — agent fabricates tool results instead of calling the tool. The Bypass is "I called it but faked the output"; the Phantom is "I called something that doesn't exist."
- [S-03 · Tool Use](s03-tool-use.md) — foundational tool definition and dispatch patterns
- [S-51 · Tool Schema Design](s51-tool-schema-design.md) — schema design principles that reduce phantom call surface area
- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — NESTFUL and NabaOS as evaluation benchmarks for tool call correctness
- [F-16 · Tool Call Validation](../forward-deployed/f16-tool-call-validation.md) — field notes on validating tool calls at dispatch time

## Receipt

> Verified 2026-07-31 — Researched: Tian Pan "Phantom Tool Calls" (Apr 14, 2026); Ncubelabs production incident (Mar 9, 2026, 600 phantom calls in one day); Basu arXiv:2603.10060 NabaOS tool receipt framework (Mar 2026, 91% detection, <15ms overhead); NESTFUL benchmark (GPT-4o: 28% full-sequence accuracy on nested tool calls). S-200 covers tool bypass (fabricated results); this entry covers phantom invocation (invented tool names). No prior handbook entry covers this failure mode. Deduplication: S-200 (bypass), S-19 (agent loop), S-03 (tool use), S-51 (schema design) — all complementary, none overlapping.
