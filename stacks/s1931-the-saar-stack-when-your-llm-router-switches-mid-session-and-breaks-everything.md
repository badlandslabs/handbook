# S-1931 · The SAAR Stack — When Your LLM Router Switches Mid-Session and Breaks Everything

Your routing layer looked perfect in testing. Every standalone request lands on the right model: simple queries go to Haiku, complex ones go to Opus. But now your agent is on step 47 of a multi-file refactor, the router sees "continue" and routes to Haiku, and the session state is now on a model that has no memory of what it's doing. The agent generates a blank file and reports success. Your routing layer just burned a session.

Traditional LLM routing was designed for single-turn requests. Long-horizon agents break it fundamentally.

## Forces

- Single-turn routers classify each request in isolation, ignoring what the session has already paid for
- Switching models mid-session isn't free: prefix cache state, tool-loop phase, and conversation history create asymmetric switching costs that static routing can't see
- A "smart" router that routes the *last* turn to Haiku because "continue" looks simple can destroy the value of every prior turn on Opus
- Model providers update API behavior silently; a session that started on a reliable version may be running a quietly-updated one by turn 12
- The router that doesn't know session phase will route a tool-call mid-loop to a model with different tool-call formatting, generating failures that look like agent errors
- Cost savings from routing evaporate when you re-run failed sessions from scratch

## The move

**Session-Aware Agentic Routing (SAAR)** extends routing logic with five components that treat the session — not the request — as the unit of routing.

### 1. Router Memory (session-scoped)

The router maintains per-session state: current physical model, routing decision, agent phase (planning / tool-loop / reasoning / idle), switch count, idle time since last turn, cache evidence, replay metadata.

```
class RouterMemory:
    current_model: str          # last physical model used
    session_phase: Phase         # planning | tool_loop | reasoning | idle
    switch_count: int           # switches in this session
    prefix_cache_evidence: bool  # does this session have cached prefix?
    replay_trace: list[Turn]    # replayable history
```

### 2. Hard Lock (irreversible switching boundary)

Certain phases are *unsafe to switch* regardless of request content. A tool-call mid-execution, a planning phase with active state, or a reasoning chain in progress must not switch models — the new model may have different tool-call formatting, function-calling schema support, or instruction-following behavior.

```
HARD_LOCK_PHASES = { "tool_loop", "planning", "reasoning" }

def should_route(request, memory: RouterMemory) -> RouteDecision:
    if memory.session_phase in HARD_LOCK_PHASES:
        return RouteDecision(
            model=memory.current_model,
            reason="hard_lock",
            fallback_available=False
        )
    return semantic_classify(request, memory)
```

### 3. Safe Reset Boundary (turn classification)

The router classifies turns by their *relationship to prior history*:

| Turn type | Meaning | Safe to switch? |
|-----------|---------|-----------------|
| Fresh task | New goal, new session | Yes — same as single-turn |
| Continuation | "continue", "keep going" | Yes if same phase |
| Correction | "undo that", "fix it" | No — depends on prior model |
| Replay | Resume from checkpoint | Yes — state is explicit |
| Escalation | Switch to reasoning model | Intentional — router triggers it |

### 4. Prefix-Cache-Aware Switch Pricing

When the router considers switching, it charges the *true cost*, not just the new model's price:

```
effective_cost = new_model_cost + cache_invalidation_cost

# If session has 80K tokens in prefix cache on current model,
# switching to a different provider invalidates the entire cache.
# New model's first token latency = full cold-start.
cache_invalidation_cost = session.cache_size * new_model.input_rate
```

### 5. Replayable Traces (switch recovery)

Every routing decision is recorded with a full trace. On switch failure, the session can replay from the checkpoint rather than re-executing from the start.

```python
# On routing failure or agent error
def replay_from_checkpoint(session: Session, trace: list[Turn]):
    # Find last successful turn
    last_good = find_last_successful_turn(trace)
    # Replay remaining on current (or fallback) model
    return session.resume(turns=trace[last_good+1:])
```

## The SAAR Evaluation Result

vLLM's SAAR paper (June 2026, Liu et al.) evaluated SAAR against three baselines across long-horizon agent tasks:

| Routing Strategy | Cost Reduction | Quality Retention |
|-----------------|---------------|-----------------|
| No routing (Opus-only) | 0% | 100% |
| Static single-turn | 35% | 82% |
| SAAR (full) | **52%** | **97%** |

The key insight: single-turn routing loses 18% quality because it treats each turn independently. SAAR recovers that gap by tracking session phase and protecting continuity-critical turns.

## The Contrarian Take

The obvious solution — "route harder, route smarter" — doesn't fix this. The problem isn't the routing *algorithm*. It's the routing *unit*: a turn is not a session. The moment you model routing around sessions, the solution changes from "better classifier" to "session lifecycle management." That's the reframe.

## Receipt

> Verified 2026-07-31 — Core research from vLLM Semantic Router blog "Session-Aware Agentic Routing" (June 2, 2026, Liu et al.); Zylos Research "AI Agent Model Routing and Dynamic Model Selection" (Mar 2, 2026). Code patterns synthesized from described SAAR components (no live run). Five-component architecture confirmed from paper summary. Cost/quality figures from vLLM evaluation table. The practical implementation example reflects the SAAR design described in the paper.

## See also

- [S-06 · Model Routing](s06-model-routing.md) — single-turn routing foundation; SAAR is its session-aware successor
- [S-1920 · The Intra-Agent Router Stack](s1920-the-intra-agent-router-stack-when-your-agent-pays-frontier-prices-for-a-job-haiku-could-do.md) — wrong model within a session; SAAR addresses the harder problem of *when* switching is safe
- [S-1047 · The Agentic Dead Letter Queue](s1047-the-agentic-dead-letter-queue-when-your-agent-fails-mid-task-and-the-task-just-disappears.md) — failed session recovery; replayable traces are the SAAR analogue
- [F-08 · Agent Cost Control](../forward-deployed/f08-agent-cost-control.md) — cost visibility for agent runs
