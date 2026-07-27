# S-1700 · The Conformance Convergence Stack — When Your Agent Is Right on the Outcome But Wrong in the Method

On July 9, 2026, the Correctover Research Group published a finding that rewires how production teams should think about agent correctness. Analysis of 50,000 production traces across 13 LLM providers revealed a hard number: single-fault self-healing works 97.4% of the time, but compound fault chains — where two or more things go wrong simultaneously — succeed only ~72% of the time. More critically, **19,251 failure paths (38.5%) remain uncovered by existing agent frameworks entirely.** The gap between what your agent did and what it was supposed to do — not whether the output was right, but whether the agent operated within its prescribed constraints — has become the central production problem of the agentic era. This is the **Conformance Convergence Stack**.

## Forces

- **Outcome correctness and constraint conformance are not the same thing.** An agent can deliver a numerically correct answer while violating memory boundaries, ignoring rate limits, executing unauthorized tools, or diverging from its declared behavioral contract. Traditional eval suites measure the former. Production failures come from the latter.
- **Compound fault chains are the actual production problem.** Single-step failures are handled by retry logic, fallback models, and guardrails. The failure mode that burns production systems is two or more things going wrong simultaneously — a tool returns malformed output while the agent is mid-context-overflow, while a third-party API is rate-limiting. Existing frameworks have no vocabulary for this.
- **Static testing cannot bound stochastic execution.** Prompt engineering, eval harnesses, and pre-deployment red-teaming all operate on controlled distributions. Production agent execution is open-ended: the agent decides its own action sequence at runtime, often diverging from anything tested. You cannot enumerate all failure paths in advance.
- **The governance vacuum is a regulatory liability.** The EU AI Act Article 14 mandates documented halt capability for high-risk autonomous agents. The CCS paper identifies this as part of a broader runtime conformance requirement — not just "can we stop it" but "can we prove it operated within its constraints at every step."

## The move

The core insight: **runtime conformance is a set-theoretic invariant, not an eval score.**

```
Required(τ) ⊆ Supported(τ)
```

The agent's required capabilities for a task must be a subset of what the runtime actually supports. When this invariant is violated — even if the output looks right — the agent is non-conformant.

### The Six-Dimension Verification Protocol

CCS defines six orthogonal dimensions of agent conformance. A conformant agent must pass all six simultaneously:

1. **Tool fidelity** — Did the agent call only authorized tools, with correct schemas, within declared rate limits? Includes idempotency: can the same call be safely retried?
2. **Context integrity** — Did the agent stay within its context budget, not overflow into adjacent sessions, and preserve memory isolation boundaries?
3. **Output structural conformance** — Does the output match the declared schema, type signature, and format contract — not just loosely, but exactly?
4. **Behavioral policy adherence** — Did the agent follow its declared behavioral policy (no disallowed content, no privilege escalation, no out-of-scope tool access)?
5. **Temporal constraints** — Did the agent complete within its declared time budget, respect rate limits, and not create unbounded loops?
6. **Semantic contract compliance** — Did the agent's actions achieve outcomes consistent with the declared intent contract, even when surface-level output looks correct?

### The Compound Fault Chain Pattern

The most important empirical finding: fault chains are not additive — they're multiplicative. When dimension A and dimension B both fail simultaneously, the combined failure is not 2x worse — it's a new class of failure. The CCS paper identifies this as the primary source of production incidents:

- **Chain type: Tool-call + context overflow** — Agent calls a tool with a large result that pushes context over the limit mid-call. Result: partial output + memory corruption + no rollback.
- **Chain type: Behavioral drift + temporal constraint** — Agent slowly drifts toward disallowed behavior while simultaneously approaching its time budget. Result: violation occurs just before the agent would have been killed by the timeout.
- **Chain type: Idempotency + rate limit** — Agent retries a non-idempotent call when rate-limited. Result: duplicate side effects (double charge, double write, double send).

### The Conformance Verification Architecture

```python
# Minimal CCS Conformance Gateway
from dataclasses import dataclass, field
from enum import Enum
from typing import Set, Dict, Any, List
import time

class ConformanceDimension(Enum):
    TOOL_FIDELITY = "tool_fidelity"
    CONTEXT_INTEGRITY = "context_integrity"
    OUTPUT_STRUCTURAL = "output_structural"
    BEHAVIORAL_POLICY = "behavioral_policy"
    TEMPORAL_CONSTRAINTS = "temporal_constraints"
    SEMANTIC_CONTRACT = "semantic_contract"

@dataclass
class AgentCapability:
    authorized_tools: Set[str]
    max_context_tokens: int
    output_schema: Dict[str, type]
    behavioral_policy: str
    max_duration_seconds: float
    semantic_intent_contract: str

@dataclass
class RuntimeSnapshot:
    """Point-in-time snapshot of agent execution state."""
    timestamp: float
    active_tools: Set[str]
    context_tokens: int
    elapsed_seconds: float
    output_buffer: Any
    behavioral_flags: Set[str]

def check_conformance(
    snapshot: RuntimeSnapshot,
    required: AgentCapability,
) -> Dict[ConformanceDimension, bool]:
    """
    Returns per-dimension conformance status.
    The Required ⊆ Supported invariant is checked for each dimension.
    """
    results = {}

    # 1. Tool fidelity
    unauthorized = snapshot.active_tools - required.authorized_tools
    results[ConformanceDimension.TOOL_FIDELITY] = len(unauthorized) == 0

    # 2. Context integrity
    results[ConformanceDimension.CONTEXT_INTEGRITY] = (
        snapshot.context_tokens <= required.max_context_tokens
    )

    # 3. Output structural conformance
    # (Schema validation against required.output_schema)
    results[ConformanceDimension.OUTPUT_STRUCTURAL] = True  # stub

    # 4. Behavioral policy
    # Check against required.behavioral_policy
    results[ConformanceDimension.BEHAVIORAL_POLICY] = True  # stub

    # 5. Temporal constraints
    results[ConformanceDimension.TEMPORAL_CONSTRAINTS] = (
        snapshot.elapsed_seconds <= required.max_duration_seconds
    )

    # 6. Semantic contract (requires outcome verification)
    results[ConformanceDimension.SEMANTIC_CONTRACT] = True  # stub

    return results

def conformance_gateway(
    agent_id: str,
    task_capability: AgentCapability,
    get_snapshot_fn,  # callable -> RuntimeSnapshot
) -> bool:
    """
    Main enforcement loop: poll snapshot, check conformance, halt on violation.
    Returns True if agent remained conformant throughout execution.
    """
    violations: List[tuple[ConformanceDimension, RuntimeSnapshot]] = []

    while True:
        snapshot = get_snapshot_fn(agent_id)
        results = check_conformance(snapshot, task_capability)

        for dim, conformant in results.items():
            if not conformant:
                violations.append((dim, snapshot))
                # Option 1: Halt immediately (strict)
                # Option 2: Log and continue with circuit breaker (graceful)
                _halt_agent(agent_id, f"Conformance violation: {dim.value}")
                return False

        if _is_terminated(agent_id):
            break

    return len(violations) == 0

def _halt_agent(agent_id: str, reason: str):
    """Hard halt: terminates the agent execution context."""
    # Implementation: send SIGTERM to agent process,
    # close all tool connections, persist violation trace
    pass

def _is_terminated(agent_id: str) -> bool:
    """Check if agent has reached a natural termination state."""
    pass
```

### Deployment Pattern: Conformance as a Sidecar

The most practical deployment model is a **conformance sidecar** — a separate process that observes the agent's execution trace via shared telemetry, checks each step against the capability contract, and halts on conformance violation. This decouples the conformance logic from the agent runtime, enabling:

- **Zero-code integration** with any framework (CrewAI, LangGraph, AutoGen, Semantic Kernel)
- **Audit trail** as a first-class output: every step logged with its conformance status per dimension
- **Incremental adoption**: start with just tool fidelity + temporal constraints, expand to all six dimensions
- **Framework-specific integration kits** (CCS integration kit for CrewAI reports 5.24µs/conformance-check overhead — negligible latency impact)

## Receipt

> Verified 2026-07-27 — Research synthesis from Correctover Research Group, CCS v1.0 (DOI 10.5281/zenodo.21234580, July 2026), GitHub gist performance validation report (d79fe2d2ff05e181023cbdd1c673bcc6), Microsoft autogen issue #7951 "Runtime Verification Imperative." Key numbers: 50,000 traces across 13 providers, 97.4% single-fault self-healing, ~72% compound fault chain success, 19,251 uncovered failure paths (38.5%). CCS integration kit benchmark: 5.24µs per conformance check on CrewAI. This material is fresh (July 2026) and the CCS framework is not yet covered in the handbook.

## See also

- [S-385 · Agent Trajectory Evaluation](stacks/s385-agent-trajectory-evaluation-process-vs-outcome-scoring.md) — Six-dimension process scoring predates CCS but covers trajectory eval, not runtime enforcement
- [S-340 · Agent Hard Enforcement Plane](stacks/s340-agent-hard-enforcement-plane.md) — Hard enforcement patterns, without the formal conformance framework
- [S-1239 · The Runtime Verification Loop](stacks/s1239-the-runtime-verification-loop-inline-agent-step-verification-at-production-scale.md) — LLM-as-judge runtime verification, complementary to formal conformance checking
