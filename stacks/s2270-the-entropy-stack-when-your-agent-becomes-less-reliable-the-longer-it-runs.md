# S-2270 · The Entropy Stack — When Your Agent Becomes Less Reliable the Longer It Runs

Your multi-agent pipeline ran perfectly for the first 200 tasks. By task 800, tasks were completing without errors but returning subtly wrong results — outputs that looked valid, passed basic checks, and accumulated quietly over two weeks until a data quality audit found 12% of records corrupted. No model change. No deployment. No anomaly in your monitoring dashboards. Your agents didn't break — they accumulated disorder. This is not a bug. It is physics.

## Forces

- **LLM outputs are intrinsically non-deterministic.** Two identical prompts can produce different answers. Over extended interaction, the distribution of outputs drifts even under identical conditions — not due to external perturbation, but due to the language model's probabilistic nature accumulating variance across rounds.
- **Agents lack intrinsic order-maintenance mechanisms.** Software systems maintain invariants through transactions, checksums, and ACID guarantees. LLM agents operate probabilistically across six lifecycle layers (foundation semantics, inter-agent transmission, memory persistence, task execution, feedback correction, systemic evolution) with no native invariant enforcement at any of them.
- **Existing failure detection assumes a failure event.** Monitoring dashboards look for errors, timeouts, and crashes. Entropy-driven degradation produces none of these — only a gradual, statistically detectable accumulation of output inconsistency, accuracy loss, and cross-session incoherence. By the time the symptom is obvious, the root cause has compounded across hundreds of turns.
- **The Entropy Principle formalizes this as unavoidable:** S(t) = S₀ × e^(αt), where entropy grows monotonically with interaction rounds. When a sufficient subset of the 22 identified intrinsic properties coexist in a system, entropy accumulation is mathematically guaranteed — not occasional, not contingent on bad luck.

## The move

### Measure entropy before it accumulates

Track three entropy proxies across agent sessions:

```python
# Entropy monitoring proxies — run on every N turns
from collections import Counter
import numpy as np

def semantic_entropy(outputs: list[str], n_bins: int = 20) -> float:
    """Cross-turn semantic drift: measure output distribution spread."""
    # Approximate via token-length distribution entropy
    lens = [len(o.split()) for o in outputs[-50:]]
    if len(set(lens)) <= 1:
        return 0.0
    counts = Counter(lens)
    probs = np.array([c / len(lens) for c in counts.values()])
    return -np.sum(probs * np.log(probs + 1e-10))

def response_distribution_drift(session_outputs: list[str]) -> float:
    """Detect when agent's response profile shifts from baseline."""
    baseline = session_outputs[:20]  # First 20 outputs as baseline
    recent = session_outputs[-20:]    # Last 20 as comparison window
    base_entropy = semantic_entropy(baseline)
    drift_entropy = semantic_entropy(recent)
    return abs(drift_entropy - base_entropy) / (base_entropy + 1e-10)

def cross_turn_coherence(trace: list[dict]) -> float:
    """Measure whether agent maintains consistent state across turns."""
    inconsistencies = 0
    for i in range(1, len(trace)):
        prev = set(trace[i-1].get('facts', []))
        curr = set(trace[i].get('facts', []))
        if prev and not prev.issubset(curr):
            inconsistencies += 1
    return 1.0 - (inconsistencies / max(len(trace) - 1, 1))

# Entropy budget enforcement
class EntropyBudget:
    def __init__(self, alpha: float = 0.05, max_rounds: int = 500):
        self.alpha = alpha
        self.max_rounds = max_rounds
        self.S0 = 0.1  # baseline entropy

    def current_entropy(self, rounds: int) -> float:
        return self.S0 * np.exp(self.alpha * rounds)

    def should_consolidate(self, rounds: int, threshold: float = 0.7) -> bool:
        return self.current_entropy(rounds) > threshold

    def trigger_checkpoint(self, rounds: int) -> str:
        """Forces state snapshot + restart when entropy threshold exceeded."""
        return f"ENTROPY_THRESHOLD_EXCEEDED_rounds={rounds}_S={self.current_entropy(rounds):.3f}"
```

### Deploy Physical Integrity Gates (PIG) at state-modifying boundaries

The PIG Engine (ADE-standard/ silent-failure, arXiv:2606.08162) places deterministic guard checks between LLM reasoning and side effects:

```python
from dataclasses import dataclass, field
from typing import Callable, Any
from enum import Enum

class PIGDecision(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    ESCALATE = "escalate"

@dataclass
class PhysicalIntegrityGate:
    """Sits between LLM output and any state-modifying operation."""
    tool_name: str
    idempotency_key: str | None = None
    range_checks: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    escalation_handler: Callable | None = None

    def evaluate(self, llm_output: dict, tool_args: dict) -> PIGDecision:
        # 1. Idempotency check — prevent duplicate side effects
        if self.idempotency_key and self._is_duplicate(self.idempotency_key):
            return PIGDecision.BLOCK

        # 2. Range checks — verify outputs fall within expected bounds
        for field, (lo, hi) in self.range_checks.items():
            val = tool_args.get(field)
            if val is not None and not (lo <= val <= hi):
                return PIGDecision.ESCALATE

        # 3. Structural integrity — verify output shape matches schema
        if not self._validate_structure(llm_output):
            return PIGDecision.ESCALATE

        return PIGDecision.ALLOW

    def _is_duplicate(self, key: str) -> bool:
        # Check against agent state store / idempotency registry
        return False  # stub

    def _validate_structure(self, output: dict) -> bool:
        return isinstance(output, dict) and "error" not in output

# Register gates for high-risk operations
TOOL_GATES: dict[str, PhysicalIntegrityGate] = {
    "write_file": PhysicalIntegrityGate(
        tool_name="write_file",
        range_checks={"content_length": (0, 100_000_000)},
        escalation_handler=lambda: notify_oncall(),
    ),
    "send_email": PhysicalIntegrityGate(
        tool_name="send_email",
        idempotency_key="email:{to}:{subject}:{timestamp_bucket}",
    ),
    "db_write": PhysicalIntegrityGate(
        tool_name="db_write",
        range_checks={"rows_affected": (1, 1000)},
    ),
}

def execute_with_pig(tool_name: str, llm_output: dict, args: dict) -> Any:
    gate = TOOL_GATES.get(tool_name)
    if not gate:
        return execute_tool(tool_name, args)

    decision = gate.evaluate(llm_output, args)
    if decision == PIGDecision.BLOCK:
        log.warning(f"PIG blocked {tool_name}: idempotency violation")
        return {"status": "blocked", "reason": "idempotency_check"}
    elif decision == PIGDecision.ESCALATE:
        log.warning(f"PIG escalated {tool_name}: range/structure violation")
        gate.escalation_handler()
        return {"status": "escalated", "reason": "integrity_check"}
    return execute_tool(tool_name, args)
```

### Use ADE protocol suite components

The Agent Delivery Engineering (ADE) protocol suite (BCP, CADVP, TLC, PIG) provides structured engineering countermeasures:

- **BCP (Baseline Configuration Protocol):** Lock system to a verified-good state snapshot at initialization. Any deviation from BCP baseline is an entropy event.
- **CADVP (Capability and Discovery Validation Protocol):** Periodically re-verify agent capabilities against a capability manifest — catch degradation before it propagates.
- **TLC (Trust Lifecycle Protocol):** Decay trust scores for memory records, tool responses, and inter-agent handoffs over time. Require periodic re-attestation.

```python
# ADE-TLC: Trust decay for memory records
from datetime import datetime, timedelta

class TrustLifecycle:
    def __init__(self, half_life_hours: int = 168):  # 1 week half-life
        self.half_life = timedelta(hours=half_life_hours)

    def trust_score(self, record_age: timedelta, initial_trust: float = 1.0) -> float:
        """Decay trust exponentially: T(t) = T₀ × 0.5^(t / half_life)"""
        decay_factor = 0.5 ** (record_age.total_seconds() / self.half_life.total_seconds())
        return initial_trust * decay_factor

    def is_verified(self, record_age: timedelta, threshold: float = 0.3) -> bool:
        return self.trust_score(record_age) >= threshold

    def needs_re_attestation(self, records: list[dict]) -> list[dict]:
        """Return records whose trust score has dropped below threshold."""
        now = datetime.now()
        stale = []
        for rec in records:
            age = now - rec.get("created_at", now)
            if self.trust_score(age) < 0.5:
                stale.append(rec)
        return stale
```

### Harden multi-agent handoffs with structured state snapshots

```python
# ADE-compliant handoff: snapshot state before any inter-agent transmission
import hashlib
import json

def agent_handoff_snapshot(agent_state: dict, prev_agent_id: str, next_agent_id: str) -> dict:
    """Create verifiable handoff package for inter-agent transmission."""
    snapshot = {
        "facts": agent_state.get("facts", []),
        "pending_tasks": agent_state.get("pending_tasks", []),
        "context_summary": agent_state.get("context_summary", ""),
        "entropy_score": agent_state.get("entropy_score", 0.0),
        "handoff_agent": prev_agent_id,
        "recipient_agent": next_agent_id,
        "timestamp": datetime.now().isoformat(),
    }
    snapshot["content_hash"] = hashlib.sha256(
        json.dumps(snapshot["facts"], sort_keys=True).encode()
    ).hexdigest()[:16]
    return snapshot

def verify_handoff_integrity(snapshot: dict) -> bool:
    """Verify the handoff package was not corrupted during transmission."""
    stored_hash = snapshot.pop("content_hash")
    computed = hashlib.sha256(
        json.dumps(snapshot["facts"], sort_keys=True).encode()
    ).hexdigest()[:16]
    snapshot["content_hash"] = stored_hash  # restore
    return stored_hash == computed
```

## Receipt

> Verified 2026-08-07 — arXiv:2606.08162 (Dexing Liu, June 2026) defines S(t) = S₀ × e^(αt) across 40,000+ controlled trials and 100,000+ production interactions. ADE-standard/silent-failure GitHub repo (github.com/ADE-standard/silent-failure) provides the PIG Engine reference implementation. Entropy growth rate α measured empirically across ReAct, Plan-and-Execute, and Tool-Parallel architectures. Countermeasures: entropy budgets (checkpoint + consolidate), PIG gates (deterministic pre-execution checks), ADE protocol suite (BCP/CADVP/TLC), state snapshots for multi-agent handoffs.

## See also

- [S-1032 · The Dead Letter Stack](/stacks/s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — the cost of silent failures (different angle: retry loops vs. entropy accumulation)
- [S-1000 · The Context Exhaustion Stack](/stacks/s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — degradation within a single context window
- [S-1022 · The Agent Drift Stack](/stacks/s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — behavioral drift in multi-agent systems (complementary to entropy framing)
- [S-983 · The Agent Recovery Stack](/stacks/s983-the-agent-recovery-stack-when-your-agent-looks-okay-but-isnt.md) — post-hoc recovery vs. entropy prevention
