# S-2071 · The Model Is Not the Problem

Your agent started failing in production. You switched to a better model. Still failing. You rewrote the system prompt. Still failing. Two weeks later, someone checked the tool definitions and found a logging middleware was silently stripping arguments nobody knew existed. The model was fine the entire time.

This is not an edge case. A systematic analysis of 591 documented AI agent failures (Clyro, 2023–2026) found that **88% trace to infrastructure gaps** — not model quality, not prompt quality, not model updates. The industry spends 100% of debugging time on the 13% that isn't the problem.

## Forces

- **The debugging reflex is trained on the wrong system class.** Engineers spend years building instincts for "check the model" because most ML failures are model failures. Agentic systems invert this: the model generates fine outputs; the infrastructure that receives, validates, scopes, and executes those outputs is where things break.
- **Agents fail forward.** An LLM gives a wrong answer — one bad response. An agent takes a wrong action, then compounds it with the next action. Context gets more corrupted, state gets more drifted. The blast radius grows for hours or days before anyone notices.
- **Success signals mask infrastructure failure.** HTTP 200 on a tool call doesn't mean the agent received valid context. A completed trace doesn't mean the output was scoped correctly. You need instrumentation at the infrastructure layer, not the generation layer.
- **Teams optimize the wrong thing.** The instinct when an agent fails is to reach for a better model. The evidence says: reach for your tool definitions first, then your context pipeline, then your permission boundaries.

## The move

When an agent fails in production, follow this checklist **in order** before touching the model or the prompt:

### The Infrastructure-First Debugging Checklist

```
1. TOOL DEFINITIONS
   → Are tool schemas intact? (logging/serialization middleware silently strip args)
   → Are permission scopes correct? (agent can call tool but gets denied)
   → Are response schemas enforced? (agent receives malformed tool responses)

2. CONTEXT PIPELINE
   → Is the context window filling correctly? (stale data, truncated history, missing session state)
   → Is retrieval producing relevant results? (wrong namespace, embedding drift, index staleness)
   → Does the agent have what it needs to act? (context blindness: acts on wrong/stale/fabricated info)

3. EXECUTION BOUNDARIES
   → Are destructive actions gated? (rogue actions: acts outside intended scope)
   → Are output formats validated before downstream use? (schema drift, partial corruption)
   → Is there an action confirmation layer? (high-stakes operations need human-in-the-loop)

4. OBSERVABILITY LAYER
   → Can you see what the agent actually received vs. what you think it received?
   → Are there silent failures (200 OK but wrong data)?
   → Is there a quality regression signal, or just a crash signal?

5. MODEL / PROMPT
   → Only if 1–4 check out clean.
```

### The Three Infrastructure Failure Modes

Every infrastructure failure maps to one of three root causes:

| Mode | Frequency | Description | Signature |
|------|-----------|-------------|-----------|
| **Context Blindness** | 31.6% | Agent lacks information it needs but doesn't know it's missing. Acts on wrong, stale, or fabricated context. | Air Canada chatbot invents bereavement policy → $812 tribunal ruling |
| **Rogue Actions** | 30.3% | Agent takes actions outside intended scope. Permission boundaries too broad, no destructive-action gate, output not scoped to principal. | Agent deletes production DB; agent emails sensitive data to wrong recipient |
| **Silent Degradation** | 24.9% | Output quality drops incrementally with no error signal. Green dashboards, 200 OK, everything looks fine. | Agent has been producing wrong reconciliations for three weeks |

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import time

class FailureMode(Enum):
    CONTEXT_BLINDNESS = "context_blindness"
    ROGUE_ACTION = "rogue_action"
    SILENT_DEGRADATION = "silent_degradation"

@dataclass
class AgentIncident:
    tool_call_status: int
    context_freshness_seconds: float
    output_validated: bool
    permission_scope: list[str]
    action_stakes: str  # "low" | "medium" | "high"

def triage_incident(incident: AgentIncident) -> tuple[FailureMode, str]:
    """
    Infrastructure-first incident triage.
    Returns the failure mode and a recommended debugging path.
    """
    # 1. Context blindness check
    if incident.context_freshness_seconds > 300:
        return (
            FailureMode.CONTEXT_BLINDNESS,
            "Check retrieval pipeline: context older than 5 minutes. "
            "Validate: (a) session state injection, (b) retrieval namespace, "
            "(c) embedding freshness, (d) truncation point in context window."
        )

    # 2. Rogue action check
    high_stakes_actions = {"delete", "write", "send_email", "deploy", "transfer", "execute"}
    if incident.action_stakes == "high":
        if not incident.output_validated:
            return (
                FailureMode.ROGUE_ACTION,
                "High-stakes action with no output validation. "
                "Check: (a) destructive-action gate, (b) permission scope breadth, "
                "(c) principal-check before execution, (d) confirmation hook."
            )
        if not incident.permission_scope:
            return (
                FailureMode.ROGUE_ACTION,
                "No permission scope defined. Implement least-privilege tool scoping."
            )

    # 3. Silent degradation check
    if incident.tool_call_status == 200 and not incident.output_validated:
        return (
            FailureMode.SILENT_DEGRADATION,
            "200 OK with no output validation is a silent-degradation risk. "
            "Check: (a) output schema enforcement, (b) quality signal instrumentation, "
            "(c) rolling-baseline comparison, (d) human-review sampling rate."
        )

    return (FailureMode.CONTEXT_BLINDNESS, "Reached end of triage without match.")

# Example: a degraded retrieval case
incident = AgentIncident(
    tool_call_status=200,
    context_freshness_seconds=1800,   # 30 minutes stale
    output_validated=False,
    permission_scope=["read"],
    action_stakes="low"
)
mode, guidance = triage_incident(incident)
print(f"Failure mode: {mode.value}")
print(f"Debugging guidance: {guidance}")
# Output:
# Failure mode: context_blindness
# Debugging guidance: Check retrieval pipeline: context older than 5 minutes...
```

### The 88% Rule in Practice

When you encounter an agent failure in staging vs. production:

| Scenario | Model-First Action | Infrastructure-First Action |
|----------|-------------------|---------------------------|
| Works in staging, fails in prod | Try a better model | **Check: tool definitions, context pipeline, permission scopes** |
| Model upgrade didn't help | Try another model | **Check: context freshness, output validation, retrieval** |
| Prompt changes don't help | Rewrite the prompt | **Check: execution boundaries, destructive-action gates** |
| Works for user A, fails for user B | Blame the model | **Check: session isolation, namespace scoping, multi-tenant state** |

## Receipt

> Verified 2026-08-03 — Pattern distilled from Clyro (591-incident analysis, 2023–2026; "The 5 AI Agent Failure Modes" blog), Codexical (May 2026), GrowthEngineer (May 2026). Key finding: 88% of classifiable agent failures trace to infrastructure gaps — missing context validation, permission boundaries, and execution bounds. Context Blindness (31.6%), Rogue Actions (30.3%), Silent Degradation (24.9%) are the three dominant failure modes. The model was usually fine.

## See also

- [S-257 · The Five Failure Modes That Kill Production Agents](s257-the-five-failure-modes-that-kill-production-agents.md) — the broader failure taxonomy from which these three modes are drawn
- [S-1799 · The Bounded Agent Stack](s1799-the-bounded-agent-stack-when-your-agent-wont-stop-failing.md) — rogue action prevention via explicit execution bounds
- [S-804 · The Untrusted Executor Pattern](s804-the-untrusted-executor-pattern-when-your-llm-output-is-untrusted-input-to-a-deterministic-system.md) — permission boundary enforcement at the execution layer
