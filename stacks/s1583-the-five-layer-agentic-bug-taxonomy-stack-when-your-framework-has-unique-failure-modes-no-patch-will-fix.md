# S-1583 · The Five-Layer Agentic Bug Taxonomy Stack: When Your Framework Has Unique Failure Modes No Patch Will Fix

Your agent loop breaks in production. You blame the model. You switch to a better one. It still breaks — same symptom, same stack trace, same invisible crash between steps. The problem isn't the LLM. It's a class of bugs that lives in the agentic framework itself: in the orchestration layer, the communication protocol, the cognitive context manager. These bugs have no benchmark. They have no patch. They have a taxonomy now.

## Forces

- **Framework bugs ≠ LLM bugs.** Agentic frameworks (CrewAI, AutoGen, LangGraph, etc.) have introduced autonomous multi-agent orchestration — a new reliability surface that earlier empirical studies didn't cover. The 409-bug ASE 2026 study (arXiv:2604.08906) found that 38% of agentic framework failures are framework-specific, not model-specific.
- **The five-layer model is new.** The study proposes a five-layer abstraction (Application → Cognitive → Orchestration → Communication → Infrastructure) that captures failure modes invisible to any single-layer view.
- **Specialized symptoms exist nowhere else.** Unexpected execution sequences and user-configuration-ignored failures appear only in multi-agent orchestration — they have no equivalent in single-agent or pipeline-based systems.
- **Cognitive context mismanagement is the dominant failure class.** The most common root cause in agentic frameworks is the layer responsible for maintaining what each agent knows, remembers, and can act on. It's the same problem as "hallucination" but at the framework level, not the model level.

## The move

**Apply the five-layer bug taxonomy to triage any agentic framework failure.** When something breaks, map the symptom to the correct layer before you reach for a model switch or a prompt tweak.

### The Five Layers

| Layer | What it owns | Typical failure modes |
|-------|-------------|----------------------|
| **Application** | Task definition, goal, success criteria | Goal drift, reward hacking, task scope creep |
| **Cognitive** | What each agent knows, retrieves, and grounds decisions on | Context dropout, memory corruption, stale retrieval, hallucinated tool capabilities |
| **Orchestration** | Agent lifecycle, sequencing, delegation, handoffs | Unexpected execution order, agent starvation, premature termination, delegation loops |
| **Communication** | How agents share results, errors, and state (MCP, A2A, shared memory) | Message loss, schema mismatches, serialization errors, capability advertised-but-not-delivered |
| **Infrastructure** | Compute, network, rate limits, model serving, tool hosting | Timeout cascades, cold-start degradation, token budget exhaustion |

### The Key Distinction: Cognitive Context Mismanagement

The ASE 2026 study found cognitive context mismanagement — agents losing, overwriting, or misrouting the state they need to make correct decisions — as the single most common framework-level root cause. It's not a hallucination problem. The model is fine. The framework fed it the wrong or incomplete context.

Symptoms that indicate cognitive layer failure:
- Agent knows something in step 3, forgets it in step 7
- Tool appears available but agent can't find it ("I don't have access to that tool")
- Two agents produce contradictory outputs and neither corrects the other
- Memory read returns stale data that was updated by a parallel agent

### Framework-Specific Symptoms vs. Standard Software Bugs

The study identified two symptom classes unique to agentic orchestration that don't appear in traditional software:

1. **Unexpected execution sequences** — The framework runs steps in an order that violates the intended workflow. An agent completes a task another agent was supposed to handle first. Or a parallel agent gets scheduled before its dependency is ready.

2. **User configuration ignored** — The framework accepts a config parameter (timeout, retry count, max iterations) but silently overrides it or never reads it in the execution path. This is invisible until the system runs unsupervised.

### Root Cause Categories (from 409 bugs, 5 frameworks)

| Root cause | Frequency | Layer |
|-----------|-----------|-------|
| Cognitive context mismanagement | 31% | Cognitive |
| Planner misalignment (agent's plan doesn't match task requirements) | 22% | Orchestration |
| Schema violation (tool/MCP response doesn't match declared schema) | 18% | Communication |
| Brittle prompt dependency (upstream prompt change silently breaks downstream behavior) | 15% | Cognitive |
| Message serialization loss | 9% | Communication |
| Infrastructure timeout cascade | 5% | Infrastructure |

### The Diagnostic Sequence

When an agentic system fails, run this before touching the model or the prompt:

```
1. Is the failure reproducible with the same input? → If yes, it's likely Cognitive or Orchestration.
2. Does the failure appear only in multi-agent mode? → If yes, it's Orchestration or Communication.
3. Does the agent "know" the answer but act wrong? → Cognitive context mismanagement.
4. Does the trace show steps out of order? → Orchestration layer bug.
5. Does the error mention tool schema or message format? → Communication layer bug.
6. Does it only fail under load or timeout? → Infrastructure layer bug.
```

## Receipt

> Verified 2026-07-24 — arXiv:2604.08906 (Zhang, Zhang, Tan — ASE 2026) analyzed 409 fixed bugs across five modern agentic frameworks. Five-layer abstraction confirmed as the primary contribution. Cognitive context mismanagement at 31% of all bugs is the standout finding. IBM AgentFixer (arXiv:2603.29848, ICSE AGENT 2026) independently validates the failure taxonomy through 15 detection tools on AppWorld and WebArena, finding the same recurrent patterns: planner misalignment, schema violations, and brittle prompt dependencies. Both papers use production-grade empirical methodology, not synthetic benchmarks.

## See also

[S-983 · The Agent Recovery Stack](./s983-the-agent-recovery-stack-when-your-agent-looks-okay-but-isnt.md) · [S-976 · The Verification Layer Stack](./s976-the-verification-layer-when-your-agent-cant-distinguish-right-from-almost-right.md) · [S-1008 · The Orchestration Pattern Match Stack](./s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md) · [S-1005 · AI SRE](./s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md)
