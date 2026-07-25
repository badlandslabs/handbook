# S-1628 · The Multi-Agent Fault Injection Stack — When Your Agent System Looks Robust But Has 11 Silent Failure Modes

Your multi-agent pipeline passes every test. Each agent works alone. The integration tests pass. You ship to production. Then: agents misread each other's messages and build on wrong assumptions; the coordinator times out silently and the worker keeps going with stale context; one agent's hallucination propagates to three others with no error signal. The system never crashed. It just quietly produced garbage.

This is not a model capability problem. It is an **inter-agent communication failure** — and single-agent chaos engineering misses it entirely. MAS-FIRE (arXiv:2602.19843, Jia et al., 2026) provides the first systematic fault injection framework for LLM-based multi-agent systems, revealing 11 distinct fault categories that standard testing never surfaces.

## Forces

- **Agents communicate in unstructured natural language, not typed protocols.** Unlike gRPC or REST, inter-agent messages have no schema enforcement, no runtime type checking, no protocol-level retry. A misinterpreted instruction produces a confident wrong output, not an error.
- **Standard chaos engineering is single-agent.** S-370 (Agent Chaos Engineering) injects tool failures and API errors at the infrastructure layer. It never touches the *semantic* layer — agents sending each other wrong intent, stale context, or contradictory goals.
- **Multi-agent failures propagate silently without runtime exceptions.** An agent that "succeeds" on a misinterpreted subtask produces output that looks valid to the next agent. By the time the final artifact is obviously wrong, you cannot trace which handoff introduced the deviation.
- **79% of production multi-agent failures originate from coordination issues, not model capability.** Acharya (arXiv:2604.16339, March 2026): 41–86.7% production failure rate; 79% from specification and coordination failures. MAS-FIRE targets exactly this failure class.
- **The blast radius of a multi-agent fault grows exponentially.** A single corrupted memory write in agent A reaches agents B, C, and D through shared context. A message injection in one handoff compounds across every downstream consumer.

## The move

### The 11-Fault Taxonomy (MAS-FIRE)

MAS-FIRE categorizes multi-agent faults into three severity tiers:

**Tier 1 — Agent-Level Faults (faults originating within one agent)**

1. **LLM Hallucination** — agent produces a factually incorrect output and communicates it as ground truth
2. **Reasoning Drift** — agent's chain-of-thought wanders off-task; downstream agents receive misaligned context
3. **Context Confusion** — agent conflates instructions from different sessions or user requests

**Tier 2 — Communication-Level Faults (faults in inter-agent message passing)**

4. **Intent Misinterpretation** — receiving agent misreads the sender's goal or constraint
5. **Message Omission** — a critical handoff message is silently dropped (context overflow eviction, rate limiting)
6. **Message Corruption** — message content is altered en route (adversarial injection, encoding drift)
7. **Ordering Violation** — messages arrive out of sequence; worker acts before coordinator's final directive
8. **Timing/Timeout Fault** — coordinator gives up waiting and proceeds with stale partial results

**Tier 3 — System-Level Faults (faults affecting the multi-agent system as a whole)**

9. **Cascade Corruption** — Tier 1 or 2 fault propagates through shared memory or message bus
10. **Role Confusion** — agent takes on responsibilities of another role (no explicit role enforcement)
11. **Emergent Loop** — agents enter a mutually-dependent waiting state with no timeout

### The Injection Protocol

```python
# MAS-FIRE-inspired fault injection harness
# github.com/wxhhxn/MASFIRE

from masfire import AgentSystem, FaultInjector, FaultType, Severity

def run_fault_injection_eval(system: AgentSystem, fault_type: FaultType):
    """
    For each fault type, inject the fault at the identified layer,
    run the full multi-agent task, and measure:
      - Detection rate: did any agent detect the fault?
      - Recovery rate: did the system self-correct?
      - Output fidelity: is the final artifact affected?
    """
    injector = FaultInjector(system)

    # Tier 1: Agent-level faults
    injector.inject(FaultType.LLM_HALLUCINATION, target="researcher_agent")
    injector.inject(FaultType.REASONING_DRIFT, target="writer_agent")
    injector.inject(FaultType.CONTEXT_CONFUSION, target="coordinator_agent")

    # Tier 2: Communication-level faults
    injector.inject(FaultType.INTENT_MISINTERPRETATION,
                    source="coordinator", target="worker")
    injector.inject(FaultType.MESSAGE_OMISSION,
                    channel="worker→coordinator", probability=0.3)
    injector.inject(FaultType.ORDERING_VIOLATION,
                    source="planner", target="executor")
    injector.inject(FaultType.TIMEOUT_FAULT,
                    timeout_ms=50, proceed_with_stale=True)

    # Tier 3: System-level faults
    injector.inject(FaultType.CASCADE_CORRUPTION,
                    origin="researcher_agent",
                    propagation_targets=["writer_agent", "reviewer_agent"])
    injector.inject(FaultType.EMERGENT_LOOP,
                    mutual_dependencies=[("agent_a", "agent_b"), ("agent_b", "agent_c")])

    results = system.run(task="produce_quarterly_report")

    return {
        "detection_rate": results.detected_faults / len(fault_types),
        "recovery_rate": results.self_recovered / len(fault_types),
        "output_fidelity": results.artifact_correct,
        "fault_log": results.fault_timeline,
    }

# Key insight: detection rate is your coverage gap metric
# A well-designed system should detect ≥7/11 faults autonomously
```

### Detection and Recovery Patterns by Fault Type

| Fault Type | Detection Signal | Recovery Mechanism |
|---|---|---|
| LLM Hallucination | Cross-reference with external source; consensus check across 2 agents | Flag + pause; re-retrieve from ground truth |
| Reasoning Drift | Step-by-step goal alignment check at each turn | Re-inject task directive; truncate reasoning chain |
| Intent Misinterpretation | Semantic similarity between sent and received intent | Echo-back confirmation loop; typed intent schema |
| Message Omission | Sequence number gap; expected output missing | NACK + retry; timeout triggers escalation |
| Cascade Corruption | Hash mismatch on shared memory reads | Quarantine corrupted agent; replay from last checkpoint |
| Emergent Loop | Circular dependency graph detection; max-iteration gate | Deadlock breaker; human handoff with partial result |

### The Evaluation Protocol

MAS-FIRE uses three metrics to score a multi-agent system's fault resilience:

1. **Detection Rate (DR)** — fraction of injected faults detected by any agent or monitoring layer
2. **Recovery Rate (RR)** — fraction of detected faults that the system self-corrects without human intervention
3. **Artifact Fidelity (AF)** — whether the final output is correct despite fault injection (0 or 1)

A production-ready system should target DR ≥ 0.70, RR ≥ 0.60, AF = 1.0 on Tier 1 faults.

## Receipt

> Verified 2026-07-25 — arXiv:2602.19843 (Jia et al., Sun Yat-sen University, Feb 2026): 11-fault taxonomy validated across 6 multi-agent frameworks. GitHub: `wxhhxn/MASFIRE`. Fault injection protocol tested on Research-Writer-Reviewer and Planner-Executor architectures. Key finding: communication-level faults (Tier 2) have the lowest detection rates — agents "confidently proceed" on misinterpreted instructions 73% of the time. Semantic intent verification at handoff boundaries is the highest-leverage mitigation.

## See also

- [S-370 · Agent Chaos Engineering](stacks/s370-agent-chaos-engineering-fault-injection-testing.md) — single-agent fault injection; the predecessor to this pattern
- [S-1389 · The Reliability Compounding Stack](stacks/s1389-the-reliability-compounding-stack-when-your-multi-agent-pipeline-fails-65-percent-of-the-time.md) — the compounding math behind multi-agent reliability; S-1628 is the defensive mirror
- [S-1132 · The Semantic Intent Divergence Stack](stacks/s1132-the-semantic-intent-divergence-stack-when-your-agents-all-succeed-but-disagree-on-what-success-means.md) — Tier 2 fault category (intent misinterpretation) as a first-class failure mode; S-1628 provides the injection methodology
- [S-1038 · Failure Handling for AI Agents](stacks/s1038-failure-handling-for-ai-agents.md) — Zylos Research breakdown: 42% specification, 37% coordination, 21% verification failures; MAS-FIRE targets the 37% coordination class
