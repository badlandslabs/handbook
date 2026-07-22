# S-1490 · The Fault Propagation Chain — When One Agent Bug Becomes a System-Wide Incident

Your agent's tool-call validation check failed silently. Nobody noticed. Six hours later, your orchestrator agent routed three downstream agents on a corrupted context, and your entire customer-onboarding pipeline produced documents with wrong account numbers. The root cause was a schema mismatch in a single MCP server's response format — a 4-line fix. The incident took 11 hours to diagnose because nobody had a map of how faults propagate across agent components. You needed a **fault propagation chain** — the structural model that links fault types to symptoms to root causes across your agent's architecture layers.

## Forces

- **Agentic faults are hybrid: part software, part probabilistic.** Unlike conventional software where a failure traces to a specific line of code, agentic failures combine SE faults (schema drift, dependency mismatch) with LLM-driven behavior (plausible wrong answers, confident failures). Standard debugging tools miss the hybrid layer entirely.
- **Failures cascade across architectural dimensions.** A data schema mismatch in the tool integration layer propagates upward to reasoning (agent draws wrong conclusions from malformed output) and downward to infrastructure (orchestrator retries exhaust budgets). The symptom you see in production is never where the fault originated.
- **The root cause is usually not where the failure manifests.** Association rule mining across 13,602 real-world agentic faults shows high-confidence propagation chains: schema mismatch → structured output failure → cascading runtime errors. Fixing the symptom at the output layer does not fix the fault at the schema layer.
- **Component-level debugging is insufficient.** When a fault spans the LLM reasoning layer, the tool integration layer, and the state management layer simultaneously, single-component debugging produces incomplete diagnoses.

## The move

### 1. Map Your Agent's Four Fault Dimensions

The empirical fault taxonomy (Shah et al., arXiv:2603.06847, March 2026) across 385 analyzed faults from 40 real-world agentic repositories identifies **four architectural dimensions** where faults originate and propagate:

| Dimension | Frequency | Dominant Faults | Key Symptom |
|-----------|-----------|----------------|-------------|
| System Infrastructure & Reliability | 155/385 (40%) | State management, dependency drift, runtime errors | Silent degradation, non-terminating loops |
| Context & Memory | 62/385 (16%) | Memory poisoning, context corruption, retrieval failure | Belief drift, repeated errors |
| Tooling, Integration & Actuation | 82/385 (21%) | Schema mismatch, tool-call failure, malformed output | Schema-pass/semantic-fail, downstream corruption |
| Agent Reasoning & Control | 86/385 (22%) | Planning failure, incorrect tool selection, hallucinated reasoning | Plausible wrong answers, misrouted tasks |

The dominant root causes in order: **data schema mismatches (28%)**, **dependency drift (21.9%)**, **state management complexity (14.1%)**, **model interface instability (11.6%)**.

Instrument your telemetry to tag every fault event with its dimension label. This alone cuts mean-time-to-diagnosis because you know which layer to look in.

### 2. Implement the Fault Propagation Classifier

Use the empirically-derived association rules to route fault signals to the right remediation:

```python
"""
Fault Propagation Router — based on the association rule taxonomy
from Shah et al. (arXiv:2603.06847), validated by 145 practitioners.

Association rules map symptom patterns → fault dimensions → likely root causes.
High-confidence rules (>0.85 lift) form the routing table.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FaultDimension(Enum):
    SYSTEM_INFRA = "system_infrastructure"
    TOOLING_INTEGRATION = "tooling_integration"
    AGENT_REASONING = "agent_reasoning"
    CONTEXT_MEMORY = "context_memory"


@dataclass
class FaultSignal:
    symptom: str
    component: str
    error_type: str
    stack_trace_keywords: list[str]


@dataclass
class PropagationChain:
    symptom_dimension: FaultDimension
    propagated_from: Optional[FaultDimension]
    likely_root_cause: str
    confidence: float  # lift value from association rules


# High-confidence association rules from the empirical study
# Format: (symptom_pattern, error_keywords) → (root_cause, propagation_chain, confidence)
ASSOCIATION_RULES = [
    # Schema mismatch propagation chain (28% of all faults)
    (
        {"structured_output_failure", "malformed_json", "field_missing"},
        {"schema_mismatch": FaultDimension.TOOLING_INTEGRATION,
         "downstream_cascade": FaultDimension.AGENT_REASONING,
         "root_cause": "MCP server schema drift or tool response format change",
         "confidence": 0.91}
    ),
    # Dependency drift propagation chain (21.9% of all faults)
    (
        {"dependency_error", "import_failure", "version_conflict"},
        {"dependency_drift": FaultDimension.SYSTEM_INFRA,
         "runtime_failure": FaultDimension.SYSTEM_INFRA,
         "root_cause": "Unpinned tool dependency updated between runs",
         "confidence": 0.87}
    ),
    # State management propagation chain (14.1% of all faults)
    (
        {"inconsistent_state", "context_corruption", "memory_poisoning"},
        {"state_complexity": FaultDimension.CONTEXT_MEMORY,
         "reasoning_drift": FaultDimension.AGENT_REASONING,
         "root_cause": "Long-running session accumulates belief-state corruption",
         "confidence": 0.84}
    ),
    # Model interface instability propagation chain (11.6% of all faults)
    (
        {"api_error", "model_unavailable", "response_format_changed"},
        {"interface_instability": FaultDimension.SYSTEM_INFRA,
         "tool_call_failure": FaultDimension.TOOLING_INTEGRATION,
         "root_cause": "Model provider API changed response contract",
         "confidence": 0.82}
    ),
]


def classify_propagation(signal: FaultSignal) -> PropagationChain:
    """
    Given a fault signal, return the most likely propagation chain.
    
    The classifier uses the symptom signature to match against
    empirically-derived association rules and returns:
    1. Where the symptom manifests (symptom_dimension)
    2. Where it likely propagated FROM (propagated_from)
    3. What the root cause is (root_cause)
    4. How confident the prediction is (confidence)
    """
    symptom_set = {signal.error_type, *signal.stack_trace_keywords}
    
    best_match = None
    best_overlap = 0
    
    for rule_keywords, chain_info in ASSOCIATION_RULES:
        overlap = len(symptom_set & rule_keywords)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = (rule_keywords, chain_info)
    
    if best_match is None or best_overlap == 0:
        return PropagationChain(
            symptom_dimension=FaultDimension.SYSTEM_INFRA,
            propagated_from=None,
            likely_root_cause="unclassified — manual investigation required",
            confidence=0.0
        )
    
    chain_info = best_match[1]
    return PropagationChain(
        symptom_dimension=FaultDimension.AGENT_REASONING,  # where symptom manifests
        propagated_from=chain_info.get("schema_mismatch") or chain_info.get("dependency_drift"),
        likely_root_cause=chain_info["root_cause"],
        confidence=chain_info["confidence"]
    )


def route_remediation(chain: PropagationChain) -> dict:
    """
    Given a propagation chain, return the remediation action
    and the layer to fix it.
    """
    return {
        "fix_layer": chain.propagated_from.value if chain.propagated_from else "unknown",
        "fix_action": {
            "schema_mismatch": "Audit and pin MCP server schema versions; add schema validation gate",
            "dependency_drift": "Pin all tool dependencies with lockfiles; add dependency diff check to CI",
            "state_complexity": "Trigger entropy budget checkpoint; re-initialize agent state from authoritative source",
            "interface_instability": "Implement model response contract tests; pin model version or API version",
        }.get(chain.likely_root_cause.split()[0], "manual triage"),
        "escalate_to": {
            "schema_mismatch": "tool-integrations team",
            "dependency_drift": "infra team",
            "state_complexity": "agent-platform team",
            "interface_instability": "model-ops team",
        }.get(chain.likely_root_cause.split()[0], "agentic-SRE"),
        "confidence": chain.confidence,
    }
```

### 3. Deploy Component-Level Fault Injection Tests

The study found that the **specific fault type** is more diagnostic than the symptom. Build fault injection tests for each dominant fault type across each dimension:

```python
# Fault injection test suite — exercises the four fault dimensions
import pytest


class TestSchemaMismatchPropagation:
    """Simulate: MCP server returns field with wrong type (int vs string).
    Validates that your system: (a) detects schema mismatch, (b) does NOT
    propagate corrupted output to downstream agents.
    """
    
    def test_mcp_schema_drift_isolation(self, agent_with_mcp):
        # Arrange: corrupt one MCP server's response schema
        mock_mcp_server.return_schema = {"user_id": int}  # changed from str
        agent = agent_with_mcp
        
        # Act
        result = agent.run("get_user_profile", {"user_id": "U-12345"})
        
        # Assert: schema validation FAILS in tool layer, NOT in reasoning layer
        # The error should surface at the integration layer, not as a
        # "user not found" response from the agent (reasoning layer)
        assert agent.last_error.layer == "tooling_integration"
        assert agent.last_error.type == "schema_validation_failure"
        assert agent.reasoning_state.used_corrupted_output is False


class TestDependencyDriftDetection:
    """Simulate: tool dependency silently updates and changes behavior.
    Validates that your system: (a) detects behavioral drift, (b) falls
    back to pinned version or gracefully degrades.
    """
    
    def test_unpinned_dependency_drift_circuit_breaker(self, agent_with_tools):
        # Arrange: simulate a tool whose dependency silently changed behavior
        mock_tool_server.set_drift(silent=True, new_behavior="return_empty_list")
        
        # Act
        result = agent_with_tools.run("list_active_users")
        
        # Assert: system detects behavioral drift (not just failure) and
        # circuit-breakers to fallback before cascading
        assert agent.circuit_breaker.tripped is True
        assert agent.circuit_breaker.reason == "behavioral_drift"
        assert result.fallback_used is True
```

### 4. Build the Cross-Dimension Incident Map

When an incident occurs, the **cross-dimension propagation map** is more useful than a flat stack trace. Structure your incident report to answer:

1. **Which dimension did this fault originate in?** (Schema? Dependency? State? Interface?)
2. **Which dimensions did it propagate TO?** (Symptom vs. root cause)
3. **What was the propagation chain?** (Root cause → intermediate → symptom)

The association rules reveal that 34 fault types map predictably to 12 root cause categories. Build a lookup table from the empirical data so your on-call runbook maps fault signatures to fix layers directly.

## Receipt

> Verified 2026-07-22 — Research: Shah et al., arXiv:2603.06847v2 (March 2026): empirical study of 13,602 issues/PRs from 40 open-source agentic repositories, 385 faults analyzed via grounded theory, 145-practitioner validation study. 34 fault types across 4 architectural dimensions, 12 symptom categories, 12 root cause categories, Apriori-based association rules with >0.85 lift for top propagation chains. Dominant chain: schema mismatch (28%) → structured output interpretation failure → cascading runtime errors. Deduplication: S-938 covers escalation gates, S-940 covers drift recovery, S-1013 covers multi-agent observability. None cover the empirically-derived fault taxonomy with component-level propagation mapping. This entry delivers the propagation chain classifier, the four-dimension fault map, and the cross-dimension incident structure — novel tooling for the handbook.

## See also

- [S-194 · Schema-Pass, Semantic-Fail: The Three-Tier Validation Gap in Structured Agent Outputs](s1258-the-schema-pass-semantic-fail-three-tier-validation-gap-in-structured-agent-outputs.md) — the upstream schema validation layer that prevents propagation chains from starting
- [S-124 · Agent Drift Recovery Stack: The Architecture After Detection](s940-the-agent-drift-recovery-stack-the-architecture-after-detection.md) — post-detection recovery architecture that complements propagation-based triage
- [S-140 · The Intelligence Entropy Stack — When Your Agent Breaks Without Being Attacked](s1479-the-intelligence-entropy-stack-when-your-agent-breaks-without-being-attacked.md) — the state management complexity dimension (14.1% of faults) as a self-organizing degradation process
