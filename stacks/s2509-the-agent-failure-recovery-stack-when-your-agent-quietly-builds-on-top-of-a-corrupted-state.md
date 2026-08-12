# S-2509 · The Agent Failure Recovery Stack — When Your Agent Quietly Builds on Top of a Corrupted State

Your agent ran 1,200 tasks last week without throwing a single exception. The traces look clean. The logs show no errors. But 18% of the outputs were quietly wrong — a tool returned malformed data, the agent treated it as valid, and three reasoning steps later the conclusion was structurally sound but factually hollow. This is the failure recovery problem: agents don't crash, they confabulate on top of bad state and look confident doing it.

## Forces

- **Agents don't fail loudly.** A REST API returns an error; the agent catches it and retries. A tool returns garbage JSON; the agent wraps it in apology language and proceeds. The only trace of failure is a quiet re-attempt that looks like a normal step.
- **Recovery patterns are not one-size-fits-all.** Transient network timeouts warrant a blind retry. A logic error — wrong tool, wrong assumption — requires backtracking to a checkpoint. Context poisoning requires aborting and starting over. Retrying blindly on a logic error compounds the damage.
- **The retry loop is the most expensive failure mode.** Without hard limits, an agent in a soft loop will burn credits indefinitely. Teams have reported runaway loops costing $47,000 over 11 days — not because the agent was broken, but because nobody set a max-attempts cap.
- **Error classification must happen before recovery strategy is chosen.** Teams that treat all errors the same end up with either too-aggressive retries (costly, potentially destructive) or too-conservative ones (agents give up too early on fixable problems).
- **Context poisoning is invisible without trace-level inspection.** The agent's state after step N is a function of every tool result from steps 1 through N. One bad read poisons every downstream reasoning step. The final output can still be grammatically correct and confident — which is worse than an outright crash.

## The Move

The failure-recovery stack operates in five layers: detection, classification, containment, recovery, and observability. Each layer has specific, implementable mechanisms — not vague principles.

### Layer 1 — Detection: Instrument Every Tool Boundary

```
PreToolUse hook  →  log intent (which tool, what args)
PostToolUse hook →  log outcome (response, latency, status)
SubagentStop     →  log final state + trajectory
```

- Capture the tool name, arguments, and raw response at every tool call boundary.
- Flag tool responses that return empty, null, or malformed data before the agent sees them.
- Use structured JSON logging with `trace_id`, `step_number`, `tool_name`, `duration_ms`, `status` — not plain text.
- **Evidence:** TribeAI's `claude-evals` framework hooks into `PreToolUse`, `PostToolUse`, and `SubagentStop` lifecycle events specifically to capture the full trajectory, not just the final output — because the failure is usually in the middle of the loop, not at the edges. ([GitHub — TribeAI/claude-evals](https://github.com/TribeAI/claude-evals))

### Layer 2 — Classification: Separate Error Taxonomies Before Retrying

Two distinct error categories require different responses:

| Error Type | Examples | Correct Response |
|---|---|---|
| **Transient / Technical** | Network timeout, API 5xx, JSON parse failure, rate limit | Blind retry with exponential backoff |
| **Logic / Semantic** | Wrong tool selected, bad argument, hallucinated assumption | Abort and backtrack — do not retry blindly |
| **Context Poisoning** | Tool returned corrupted data treated as valid | Invalidate state from that point, restart |
| **Hard Loop** | Same tool called 3+ times consecutively with same args | Hard stop — max-attempts exceeded |
| **Soft Loop** | Similar reasoning pattern with different surface tokens | Warn, but allow limited continuation |

- **Evidence:** AgentPatterns.tech distinguishes hard loops (identical consecutive calls) from soft loops (similar patterns with different surface text) and semantic loops (the agent is solving the wrong problem consistently) — each requiring a different intervention. ([AgentPatterns.tech — Infinite Agent Loop](https://www.agentpatterns.tech/en/failures/infinite-loop))
- **Evidence:** Codemia's error taxonomy separates logic errors (agent solves the wrong problem without crashing) from technical errors — noting that logic errors are the ones that slip past naive retry-based recovery because nothing technically "failed." ([Codemia — Error Handling and Recovery](https://codemia.io/courses/introduction_to_agentic_ai/error_handling_and_recovery))

### Layer 3 — Containment: Circuit Breakers and Budget Limits

- **Max-step budget:** Cap the total number of agent loop iterations (e.g., 50). A hard stop beats a runaway loop.
- **Per-tool call limits:** If the same tool is called with the same or similar arguments 3+ times consecutively, interrupt and surface the pattern to a human.
- **Cost ceiling:** Set a maximum spend per task (e.g., $2.00). The $47,000, 11-day loop from the Coasty case study happened because there was no cost circuit breaker. ([Coasty Blog — AI Agent Error Handling](https://coasty.ai/blog/ai-agent-error-handling-and-recovery-computer-use-disaster-stories))
- **Validation gates between agents:** In multi-agent pipelines, a lightweight schema check on each agent's output before it feeds into the next agent catches corruption early. This is cheaper than letting bad state propagate through five downstream agents.
- **Evidence:** Cloudzy's six failure modes for agent loops include retry storm (cascading retries that amplify load), state loss (agent loses mid-task context), and circuit breaker patterns — recommending that production agents implement explicit OPEN / HALF-OPEN / CLOSED states for tool calls. ([Cloudzy Blog — 6 AI Agent Loop Failure Modes](https://cloudzy.com/blog/why-ai-agent-loops-fail-in-production/))

### Layer 4 — Recovery: Match Strategy to Error Type

- **For transient errors:** Exponential backoff retry (base=2, cap=5 attempts, jitter). Log each attempt so you can distinguish "failed once" from "failed five times."
- **For logic errors:** Implement checkpointing — save agent state at key decision points. On a logic error, roll back to the last known-good checkpoint rather than restarting from scratch.
- **For context poisoning:** Detect corrupted tool responses at the boundary (schema validation, null checks, type checks) and invalidate the context window from that step forward. The agent should not continue reasoning on bad data.
- **For soft loops:** Allow a bounded number of additional attempts with a forced strategy shift (e.g., "you've tried the search tool 5 times without result — switch to the browse tool or return an incomplete answer").
- **For dead ends:** Surface the failure explicitly to the user with what the agent tried, what it observed, and what it could not resolve. Do not fabricate a resolution.
- **Evidence:** BestAIWeb's five-layer recovery taxonomy recommends validation gates at each tool boundary to detect poisoning before it cascades, paired with targeted rollback strategies that vary by error type rather than applying a uniform retry. ([BestAIWeb — Agent Error Handling](https://www.bestaiweb.ai/what-is-agent-error-handling-and-how-resilient-agents-recover-from-tool-and-llm-failures))

### Layer 5 — Observability: Trace-Level Debugging, Not Log-Level

- **Full trajectory capture:** Store the complete sequence of user input → reasoning → tool calls → tool responses → final output for every task.
- **Error rate per tool:** Track which tools fail most often, which tool combinations cause loops, and which error patterns precede a soft loop.
- **Cost-per-task histogram:** Identify outliers (tasks that cost 10x the median) before they surprise you on the monthly bill.
- **Regression alerting:** If error rate on tool-X jumps from 2% to 15% week-over-week, alert the team — the tool may have changed its API contract.
- **Evidence:** MyEngineeringPath notes that production agents fail in ways RAG pipelines never do — "the agent can get stuck in a reasoning loop, misinterpret a tool error as valid data, exhaust its context window mid-task, or silently produce wrong results that look correct." Their recommendation: "debugging these failures requires trace-level observability, not log-level debugging." ([MyEngineeringPath — Agent Debugging & Error Handling](https://myengineeringpath.dev/genai-engineer/agent-debugging/))

## Evidence

- **Blog post:** Coasty documented a real $47,000, 11-day runaway loop caused by retry-without-limits, citing missing circuit breakers and cost ceilings as the root cause. Recommends max-attempts caps and explicit cost budgets per task. — [Coasty Blog — AI Agent Error Handling and Recovery: The $47K Infinite Loop](https://coasty.ai/blog/ai-agent-error-handling-and-recovery-computer-use-disaster-stories)
- **Engineering blog:** Cloudzy enumerated six distinct failure modes for agent loops in production (infinite loop, silent tool failure, reasoning drift, state loss, retry storm, circuit breaker gap), arguing that evaluation and observability must operate at the loop level, not the call level. — [Cloudzy Blog — 6 AI Agent Loop Failure Modes That Break Production Systems](https://cloudzy.com/blog/why-ai-agent-loops-fail-in-production/)
- **Technical guide:** BestAIWeb's five-layer recovery taxonomy (detect → contain → reverse) with per-layer mechanisms and specific failure-mode mapping — noting that "production agents fail in stranger ways than traditional services. They almost never crash — instead, they keep going confidently, sometimes for a dozen more steps, while quietly building a tower of conclusions on top of a corrupted tool response." — [BestAIWeb — Agent Error Handling: How Retries and Guardrails Work](https://www.bestaiweb.ai/what-is-agent-error-handling-and-how-resilient-agents-recover-from-tool-and-llm-failures)
- **Reference site:** AgentPatterns.tech provides the hard/soft/semantic loop taxonomy with detection heuristics and intervention strategies, with production architecture diagrams showing where loop guards fit into the agent execution loop. — [AgentPatterns.tech — Infinite Agent Loop](https://www.agentpatterns.tech/en/failures/infinite-loop)
- **Engineering guide:** MyEngineeringPath covers the three-layer non-determinism problem (LLM, tool, context), structured error logging with trace IDs, and trace-level debugging workflows for production agents. — [MyEngineeringPath — Agent Debugging & Error Handling (2026)](https://myengineeringpath.dev/genai-engineer/agent-debugging/)

## Gotchas

- **Treating logic errors like transient errors.** A retry will not fix a wrong tool choice — it will keep calling the wrong tool faster. Classify before you retry.
- **Logging errors without structured context.** Plain-text logs with no `trace_id`, no `step_number`, and no `tool_name` are useless when you need to reconstruct a trajectory. Structure your error logs at instrument time, not retrospectively.
- **No max-step budget.** The agent will eventually either succeed, fail, or cost more than the task is worth. Without a hard cap, the third option wins. Set the budget before deployment.
- **Assuming a clean final output means clean intermediate steps.** The agent's final answer can look coherent while being built on a corrupted tool result three steps back. Always inspect the trajectory, not just the output.
- **Human-in-the-loop added reactively, not designed in.** Recovery patterns that require human review (e.g., context poisoning detected, cost ceiling hit) need a designed-in escalation path — not a Slack message and a prayer.
