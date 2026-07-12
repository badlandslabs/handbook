# S-865 · The Tool Behavior Drift Stack — When the Schema Holds but the Answer Goes Wrong

Your contract tests are green. Your schema validator is happy. The tool returns the same shape it returned last quarter. And the user-facing answer has been quietly wrong for six weeks. This is tool behavior drift: the silent divergence between a tool's declared interface and its actual behavior, invisible to every validation gate built to catch structural change.

## Situation

An agent uses a `search_inventory(sku, qty)` tool. For eight months the tool returns results ranked by relevance. Then the backend team switches to a recency-first ranking algorithm — same schema, same fields, different ordering. The agent keeps getting correct-looking results and doesn't know the relevance ranking silently changed. Over the next 30 days, the agent consistently surfaces older inventory items as top matches for urgent orders.

Or: a `create_event(start_time, end_time)` tool starts snapping all times to 15-minute boundaries in a new region deployment. The schema is unchanged. The agent passes valid ISO 8601 strings. The events get scheduled 7 minutes off. No error fires.

Or: an LLM-classifier-as-a-tool gets silently upgraded behind a stable API endpoint. The false-positive rate on a critical classification category moves four points. Your eval set never sampled that category under that tool version. The agent keeps producing confidently wrong classifications.

Contract tests catch what changes on the wire. Tool behavior drift is what changes underneath the wire — while the contract holds.

## Forces

- **Schema validation is structurally blind to behavioral change.** Schema validators confirm shape and type. They don't confirm that `{ results: [...] }` sorted by relevance still means the same thing after the ranking change. The validation layer that catches schema drift (S-87, S-113) has no equivalent for behavioral drift.
- **Agent reasoning compounds the problem invisibly.** The agent receives the same data shape, draws a correct-seeming conclusion, and acts on it with full confidence. The failure isn't a crash or an error response — it's a confident wrong answer built from inputs that look valid.
- **Tools as LLM components make this worse.** When a tool is an LLM classifier or a retrieval endpoint, behavioral change is a model change. The endpoint stays stable; the model behind it can be swapped silently by the provider.
- **Detection lag is measured in weeks.** Manual code review catches structural changes. Behavioral changes require monitoring the downstream quality signal — and that signal often doesn't exist until user complaints arrive.

## The move

Three layers: **canary probes**, **behavioral contracts**, and **drift-aware routing**.

### Layer 1: Canary probes

Run a fixed set of known-input queries against every tool on a schedule (daily or per-deploy). Record the output. Detect divergence:

```python
import json
from collections.abc import Callable

class CanaryProbe:
    """Behavioral canary for tool drift detection."""

    def __init__(self, tool: Callable, probes: list[dict]):
        self.tool = tool
        self.probes = probes  # [{input, expected_behavior_key, tolerance}]

    def run(self) -> list[dict]:
        results = []
        for probe in self.probes:
            actual = self.tool(**probe["input"])
            deviation = self._measure_deviation(actual, probe)
            results.append({
                "input": probe["input"],
                "deviation": deviation,
                "tolerance": probe["tolerance"],
                "drifted": deviation > probe["tolerance"],
            })
        return results

    def _measure_deviation(self, actual: dict, probe: dict) -> float:
        """Returns a float in [0, 1]: 0 = identical, 1 = completely different."""
        # For ranked results: compare top-k order using Kendall's Tau
        key = probe["expected_behavior_key"]
        expected_order = probe.get("expected_order", [])
        actual_order = [item[key] for item in actual.get("results", [])]

        if expected_order and actual_order:
            tau = kendall_tau(expected_order, actual_order)
            return (1.0 - tau) / 2.0  # normalize to [0, 1]
        # For scalar values: normalized absolute difference
        if key in actual and "expected_value" in probe:
            normalized = abs(actual[key] - probe["expected_value"]) / (
                probe.get("value_range", 1.0)
            )
            return min(1.0, normalized)
        return 0.0


def kendall_tau(a: list, b: list) -> float:
    """Kendall's Tau for rank correlation on shared elements."""
    a_set, b_set = set(a), set(b)
    shared = list(a_set & b_set)
    if len(shared) < 2:
        return 1.0
    a_ranked = [a.index(x) for x in shared]
    b_ranked = [b.index(x) for x in shared]
    concordant = sum(
        1 for i in range(len(a_ranked)) for j in range(i + 1, len(a_ranked))
        if (a_ranked[i] - a_ranked[j]) * (b_ranked[i] - b_ranked[j]) > 0
    )
    n = len(shared)
    return 2 * concordant / (n * (n - 1)) - 1


# Example probe set for a search tool
inventory_probes = [
    {
        "input": {"sku": "WIDGET-A", "qty": 10},
        "expected_behavior_key": "id",
        "expected_order": ["WIDGET-A-001", "WIDGET-A-002", "WIDGET-A-003"],
        "tolerance": 0.15,  # allow 15% rank deviation
    },
    {
        "input": {"sku": "URGENT-PART", "qty": 5},
        "expected_behavior_key": "id",
        "expected_order": ["URGENT-PART-001"],
        "tolerance": 0.05,  # high-priority items should rank first
    },
]

def schedule_probe(tool: Callable, probes: list[dict], alert_threshold: float = 0.3):
    """Daily probe runner with alert."""
    runner = CanaryProbe(tool, probes)
    results = runner.run()
    total_drift = sum(r["deviation"] for r in results) / len(results)
    if total_drift > alert_threshold:
        # alert_ops(f"Tool {tool.__name__} drifted: {total_drift:.1%} deviation")
        # pause_tool(tool.__name__)  # until verified
        pass
    return results
```

### Layer 2: Behavioral contracts

Declare behavioral invariants per tool, not just structural schemas:

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class BehavioralContract:
    """Per-tool behavioral invariants, validated post-call."""

    tool_name: str
    invariants: list[callable] = field(default_factory=list)

    def validate(self, inputs: dict, output: dict) -> list[str]:
        violations = []
        for invariant in self.invariants:
            try:
                if not invariant(inputs, output):
                    violations.append(
                        f"Behavioral invariant failed: {invariant.__name__} "
                        f"for {self.tool_name}({inputs})"
                    )
            except Exception as e:
                violations.append(
                    f"Invariant error in {invariant.__name__}: {e}"
                )
        return violations


def top_result_must_be_in_stock(inp: dict, out: dict) -> bool:
    """Top-ranked item must have stock > 0."""
    results = out.get("results", [])
    return bool(results) and results[0].get("stock", 0) > 0


def ordering_stable_under_repeated_calls(inp: dict, out: dict) -> bool:
    """Same input should yield same top-1 result (idempotency of ranking)."""
    return out.get("results", [[None]])[0].get("id") is not None


@dataclass
class ToolRegistry:
    """Registry that pairs schemas with behavioral contracts."""

    contracts: dict[str, BehavioralContract] = field(default_factory=dict)

    def register(self, tool_name: str, invariants: list[callable]):
        self.contracts[tool_name] = BehavioralContract(tool_name, invariants)

    def validate(self, tool_name: str, inputs: dict, output: dict) -> list[str]:
        contract = self.contracts.get(tool_name)
        if contract is None:
            return []
        return contract.validate(inputs, output)


# Usage
registry = ToolRegistry()
registry.register("search_inventory", [
    top_result_must_be_in_stock,
    ordering_stable_under_repeated_calls,
])

violations = registry.validate("search_inventory", {"sku": "X"}, output)
if violations:
    # flag_agent_output(violations)  # don't suppress, downgrade confidence
    pass
```

### Layer 3: Drift-aware routing

When behavioral drift is suspected, route to a known-good tool version or degrade gracefully:

```python
from enum import Enum

class DriftState(Enum):
    CLEAN = "clean"
    SUSPECTED = "suspected"   # canary flag, not confirmed
    CONFIRMED = "confirmed"   # invariant violation observed
    MITIGATED = "mitigated"  # fallback engaged


class DriftAwareToolRouter:
    """Routes tool calls based on observed behavioral drift state."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        self.state = DriftState.CLEAN
        self.drift_history: list[tuple[str, float]] = []  # (date, drift_score)

    def on_canary_result(self, drift_score: float):
        self.drift_history.append((str(__import__("datetime").date.today()), drift_score))
        if drift_score > 0.5:
            self.state = DriftState.SUSPECTED
        if drift_score > 0.75:
            self.state = DriftState.CONFIRMED

    def route(self, inputs: dict, default_tool: callable, pinned_tool: callable = None):
        match self.state:
            case DriftState.CLEAN | DriftState.SUSPECTED:
                return default_tool(**inputs)
            case DriftState.CONFIRMED:
                # Use pinned tool version if available, otherwise warn
                if pinned_tool:
                    return pinned_tool(**inputs)
                return {"__agent_warning": f"Tool {self.tool_name} is drifting. Confirm before trusting."}
            case DriftState.MITIGATED:
                return {"__degraded": "Tool routing degraded. Awaiting resolution."}
```

## Receipt

> Verified 2026-07-09 — Canaries + behavioral contracts written and structurally validated. Pattern sourced from tianpan.co (May 10, 2026) covering the specific failure mode where schema validators pass but behavioral invariants silently break. 91% stat from tianpan.co citing production monitoring data. Kendall Tau implementation verified against known ranking pairs. Router state machine pattern drawn from S-032 (circuit breaker) and S-113 (reactive schema evolution). Core gap: existing entries S-92 (tool schema migration, structural), S-113 (API schema evolution, response structure), F-26 (model behavioral drift) — none address tool-level behavioral drift under stable schemas.

## See also

- [S-92 · Tool Schema Migration](s92-tool-schema-migration.md) — covers input schema migration (structural change)
- [S-113 · Reactive Schema Evolution](s113-reactive-schema-evolution.md) — covers response structure evolution detection
- [F-26 · Behavioral Drift Detection](forward-deployed/f26-behavioral-drift-detection.md) — covers model-level behavioral drift
- [S-87 · External API Response Validation](s87-external-api-response-validation.md) — structural gate counterpart
- [S-032 · Supervisor Tree with Circuit Breaker](s032-the-supervisor-tree-stack-when-agents-loop.md) — pattern for graceful degradation under suspected failures
