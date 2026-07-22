# S-1504 · The Bounded Recovery Ladder Stack — When Your Agent Gets Stuck and Costs You Money

Your agent ran for 11 days straight without producing useful output. Two agents exchanged thousands of messages, the dashboard looked healthy, and nobody noticed until the billing statement arrived: $47,000. The agent wasn't broken — it was following its instructions. It just had no exit condition, no recovery ladder, and no way to recognize it was stuck.

## Forces

- **Agents follow instructions precisely into self-sustaining non-productive cycles.** They don't crash loudly. They return `200 OK` while producing nothing. Activity metrics (API calls, file edits, log volume) all rise during stuck loops — making activity a poor signal for distinguishing stuck from slow-but-converging.
- **The cheap fix for one failure mode is the wrong fix for another.** A nudge breaks a repeater but fails for a wanderer. Human handoff as a first response is the most expensive move when a single pivot instruction would have sufficed.
- **Agents consume 24x more tokens than conventional LLM usage.** A 10-step agent run without retry contracts fails on roughly 1 in 20 calls under normal load. Without a kill switch or spend cap, one stuck loop can run until the invoice arrives.
- **Tool-call failures are structural, not behavioral.** The LLM isn't confused — it produced a parameter that doesn't exist in your schema. The tool executed anyway, and now your system is in an invalid state. Validation at the boundary catches this before any side effect.

## The Move

Build a layered defense: prevent bad tool calls at the boundary, detect non-convergence through progress metrics (not activity), then climb a bounded recovery ladder from cheapest to most expensive intervention.

### 1. Pre-execution tool validation gate

Validate every LLM-generated tool call against a JSON Schema before it executes. Reject malformed arguments (wrong type, out-of-range enum, missing required field, hallucinated parameter) and return a structured error with a repair hint — not a raw stack trace. This catches the most common failure class (tool parameter hallucination) before any side effect occurs.

```python
# Wrap every tool with a validation layer
from agentvet import vet, ToolArgError

@vet(schema=search_schema)  # validates args before tool runs
def search(args):
    return search_api(query=args["query"], limit=args["limit"])
```

Source: [agentvet README](https://github.com/MukundaKatta/agentvet) — "Zero dependencies, throws ToolArgError with LLM-friendly retry hint"

### 2. Progress metric over activity metric

Track a metric that only increases when real work is done (tests resolved, unique sources gathered, checklist items checked). Flat progress across N heartbeats means stuck — regardless of how many API calls or file edits occurred. Activity proxies are unreliable: they rise during stuck loops just as they do during productive work.

Source: [agentpatterns.ai — Stuck-Loop Recovery](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery) — "Flat progress across N heartbeats = stuck"

### 3. Bounded recovery ladder (separate from detection)

Once non-convergence is detected, climb interventions in order — cheapest first, most expensive last:

1. **Nudge** — inject a pivot instruction: *"You've tried this path 3x. Try a different tool."* Lightweight, preserves in-context state.
2. **Replan** — wipe the current plan, re-prompt with the original goal and accumulated state. Breaks path lock-in for wanderers.
3. **Reset** — roll back to last checkpointed safe state via `update_state` (LangGraph) or `MemorySaver` (LangChain). Use when state has become incoherent.
4. **Fallback model** — switch to a smaller, more conservative model with fewer tools. Good for when the reasoning model keeps failing.
5. **Human handoff** — escalate with full context (trajectory, error history, current state) so a human can decide in seconds. Last resort because it kills throughput.

Source: [ai-system-design-guide — Error Handling and Recovery](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)

### 4. Structured self-correction loop for code edits

After a failed edit, feed back the exact error location (line numbers, lint diagnostics, test output) rather than a generic failure message. The LLM corrects errors well when given the location; it struggles to find the location itself. Retry up to 3x with progressively stronger hints before escalating.

> Pattern: `edit → validate → reflect (with structured error) → retry`

Source: [Aider self-correction loop](https://github.com/Aider-AI/aider/blob/main/aider/coders/base_coder.py) — 2,485-line implementation, inspired [NousResearch/hermes-agent#536](https://github.com/NousResearch/hermes-agent/issues/536)

### 5. Hard guardrails: timeouts, spend caps, max iterations

- **Max iterations**: interrupt after N steps (LangGraph: `run_timeout`, LangChain: configurable node retry limits)
- **Per-agent spend cap**: terminate when cumulative cost exceeds threshold — prevents the $47K scenario
- **Circuit breaker**: after X consecutive failures of the same type, stop retrying that path and escalate

Source: [Kognita — $47K incident post-mortem](https://www.kognita.co/blog/ai-agent-runaway-cost-no-kill-switch) — "No per-agent budget caps, no mechanism to terminate before next API call"

## Evidence

- **Post-mortem:** A multi-agent LangChain system ran 11 days, $47,000, four agents exchanging messages with no exit condition — detected only through billing. No spend cap, no timeout, no progress metric. — [Kognita: A Runaway AI Agent Ran for 11 Days](https://www.kognita.co/blog/ai-agent-runaway-cost-no-kill-switch) / [earezki: The $47,000 AI Agent Loop](https://earezki.com/ai-news/2026-03-23-the-ai-agent-that-cost-47000-while-everyone-thought-it-was-working/)

- **Framework documentation:** LangGraph ships `run_timeout`, `error_handlers`, `NodeInterrupt` for checkpoint/resume, and Postgres/Cassandra checkpointers. Recovery ladder can be implemented as a supervisor node that catches errors and routes to the appropriate intervention. — [LangChain: Fault Tolerance in LangGraph](https://www.langchain.com/blog/fault-tolerance-in-langgraph) (June 2026)

- **Production tooling:** agentvet wraps tools with JSON Schema validation, returns `ToolArgError` with repair hints before any side effect. Zero runtime deps, MIT licensed. — [GitHub: MukundaKatta/agentvet](https://github.com/MukundaKatta/agentvet) (created April 2026)

- **HITL checkpoint architecture:** Approval-gate HITL (human approves before each action) is the slowest pattern and the most common early mistake. Sampling-based or exception-based HITL (human reviews on flagged cases only) preserves throughput while maintaining safety. — [Brightlume: Building Human-in-the-Loop Checkpoints](https://brightlume.ai/blog/building-human-in-the-loop-checkpoints-agentic-systems)

## Gotchas

- **Activity != progress.** API call counts, file edits, and log volume all increase during stuck loops. Without a progress metric that only rises on real work, detection will fire late or not at all.
- **Retry mixes up failure domains.** Transient errors (rate limits, timeouts) want exponential backoff. Validation failures want a new plan. Retrying a schema-mismatch error 5x just produces 5 invalid calls and 5x the cost.
- **Checkpoints must be saved after every successful tool call** — not after the whole step. If you checkpoint only on step completion and the step crashes mid-way, the last safe state is already invalid.
- **LLMs correct errors well but find them poorly.** Research (ACL 2024, Tyen et al.) confirms: given the location of a reasoning error, models correct it effectively. Given only a failure signal, they misidentify the cause. Feed the model the location, not the symptom.
- **Hard timeouts alone don't solve loops.** A timeout that fires after 30 minutes of unproductive work still burned 30 minutes of compute. Timeouts are a ceiling; progress metrics are the signal.
