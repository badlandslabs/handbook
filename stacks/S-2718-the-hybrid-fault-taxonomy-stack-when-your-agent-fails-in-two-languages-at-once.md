# S-2718 · The Hybrid Fault Taxonomy Stack — When Your Agent Fails in Two Languages at Once

Your agent's schema validation check passed. Your retry loop ran. Your guardrails didn't trigger. Still, your pipeline produced wrong output for six hours before anyone noticed. You're treating it like a software bug or a hallucination — it's neither. It's a *hybrid failure*, and it requires a hybrid diagnosis.

## Forces

- **Agentic failures speak two languages.** Conventional software fails with stack traces. LLM systems fail with plausible nonsense. Agentic AI fails in both simultaneously — a schema drift in an MCP server cascades into a confident hallucination, and nobody's error handler catches it because it returned HTTP 200.
- **The dominant root causes surprise practitioners.** Dependency and integration failures (19.5%) and data/type handling failures (17.6%) account for 37.1% of all faults — not model weakness, not prompt quality. The problem is at the contract boundary between the probabilistic model and deterministic systems.
- **Silent degradation hides the failure.** 13 of 37 fault types manifest as quality degradation rather than crashes (Shah et al., arXiv:2603.06847). Your metrics look fine. Your users get wrong answers.
- **Fault propagation crosses architectural boundaries.** A fault in Runtime/Environment Grounding amplifies through Cognitive Control and Agency components. Fixing where it manifests doesn't fix where it originates.

## The move

The Shah et al. empirical study (2026) analyzed 13,602 closed issues and merged PRs across 40 agentic AI repositories, applying grounded theory to derive the first empirically grounded taxonomy of agentic faults. The result: **5 architectural dimensions, 13 symptom classes, 12 root cause categories, 37 fault types** — validated by 145 practitioners (Cronbach's α = 0.91).

### The five architectural dimensions

Each dimension is a fault container — a locus where failures originate or amplify:

| Dimension | What it covers | Relative frequency |
|-----------|---------------|-------------------|
| **Cognitive Control** | Reasoning, planning, decision-making failures | Moderate |
| **Agency** | Action selection, tool invocation, execution control | High |
| **Runtime/Environment** | API calls, tool integration, external dependencies | **Highest (87 instances)** |
| **Memory/State** | Context management, session state, memory poisoning | Moderate |
| **Orchestration** | Multi-agent coordination, handoff, message passing | Moderate |

### The two dominant root causes

These are not edge cases — they are the majority:

1. **Dependency and Integration Failures (19.5%)** — MCP server schema drift, API response format changes, tool version mismatches. The model generates correct arguments for a tool that no longer exists in the form it expects.

2. **Data and Type Handling Failures (17.6%)** — Schema mismatch between model output and tool input requirements. The model hallucinates a parameter type, or the orchestrator passes a string where an integer is expected.

These two alone account for more than a third of all failures. They are *contract violations* — the probabilistic output doesn't match the deterministic interface.

### The 13 symptom classes: know what failure looks like

```
Symptom class          | Example
-----------------------|--------------------------------------------------
Semantic deviation     | Agent produces correct JSON, wrong result
Loop/infinite trace    | Agent retries same failed approach N>20 times
Cascade propagation    | Module A failure → modules B, C, D degrade
Parameter mismatch     | String passed where integer expected
Timeout/stall          | Agent freezes mid-execution, no error
Silent degradation     | Quality drops gradually, metrics stay "green"
Irreversible action   | Agent takes destructive action before human notices
Context overflow       | Context window fills, quality degrades nonlinearly
Tool hallucination     | Agent calls tool that doesn't exist or has wrong args
Trust boundary breach  | Agent acts outside its authorized scope
Schema drift           | Tool/API response format changes, model unaware
Partial failure        | Agent completes subtask, skips remainder silently
Multi-agent deadlock   | Two agents wait for each other indefinitely
```

### The propagation pattern

Association rule mining over 385 faults revealed statistically significant cross-component propagation. The critical insight: **faults in Runtime/Environment Grounding components propagate upstream into Cognitive Control**. A tool timeout doesn't just fail the tool call — it corrupts the agent's reasoning state, leading to downstream decision errors on unrelated subtasks.

### The diagnostic protocol

When a failure occurs, map it across all three axes:

```
Fault type → Symptom class → Root cause category
     ↓              ↓                  ↓
"Schema drift"  "Parameter mismatch"  "Data/type handling"
```

If you only address the symptom (the visible bad output), you haven't fixed the fault. If you only address the root cause (the schema mismatch), you haven't caught the propagation damage.

### Production detection layer

The hybrid failure profile means you need three monitoring surfaces that conventional APM doesn't cover:

- **Semantic monitors** — not just "did the API return 200?" but "did the output match the expected schema and represent a semantically correct action?"
- **Propagation watchers** — trace how a fault in one component manifests in others; a tool failure in module A should alert if module B's output quality drops within 10 minutes
- **Type contract validators** — at every LLM-to-tool boundary, validate that output types match input requirements before the call fires (this is the pre-execution validation gate)

## Sources

- Shah, M.B., Morovati, M.M., Rahman, M.M., Khomh, F. "Characterizing Faults in Agentic AI: A Taxonomy of Types, Symptoms, and Root Causes." arXiv:2603.06847v1, JACM, March 2026.
- Zylos Research, "AI Agent Self-Healing and Failure Recovery." 2026-05-06. (ALAS framework, arXiv:2505.12501)
- Supergood Solutions, "When Your Agent Fails Silently — Retry Logic & Graceful Degradation in Production." 2026-04-09.
- Zylos Research, "Graceful Degradation Patterns for AI Agent Systems." 2026-05-30.

## Related

- [S-1490 · Fault Propagation Chain](s1490-the-fault-propagation-chain-when-one-agent-bug-becomes-a-system-wide-incident.md) — propagation mechanics and the association rule findings
- [S-1341 · Silent Failure](s1341-the-silent-failure-stack-when-your-agent-runs-all-night-and-produces-nothing.md) — the 13 silent degradation symptom class in depth
- [S-1082 · Error Taxonomy](s1082-the-error-taxonomy-and-the-five-layer-harness-stopping-agents-from-hurting-themselves-and-everything-else.md) — harness-layer countermeasures per fault type
- [S-746 · Memory Confabulation](s746-agentic-memory-confabulation-the-self-reinforcing-false-belief-problem.md) — the Memory/State dimension's cognitive failure mode
