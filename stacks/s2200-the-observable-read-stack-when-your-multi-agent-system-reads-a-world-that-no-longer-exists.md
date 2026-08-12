# S-2200 · The Observable Read Stack — When Your Multi-Agent System Reads a World That No Longer Exists

Two agents share a vector store of available liquidity pools. Agent A reads the pool list — Pool XYZ reports $2M TVL. Concurrently, Agent B closes out a large position in that pool, dropping TVL to near-zero. Agent A, still working from its cached read, allocates 40% of a portfolio to Pool XYZ. No exception is thrown. No error is logged. The model made a confident, coherent decision based on data that was stale before the thought finished forming.

This is not a reasoning failure. This is a concurrency anomaly.

Multi-agent AI is concurrent systems engineering. Alignment and capability are orthogonal to consistency. A perfectly aligned, perfectly capable model still reads the state it was handed — and if that state changed after the read, it acts on a world that no longer exists.

## Forces

- **LLM agents are stateless between calls but the world isn't.** Two agents in the same system have no shared ground truth unless you explicitly engineer it. The temporal gap between "read" and "act" is an inconsistency window where the world can change underneath the agent.
- **Naive shared workspaces amplify hallucinations, not just errors.** Research from Zhou (arXiv:2605.31354, May 2026) on resource-constrained visual agents finds a counter-intuitive result: naive shared boards don't reduce hallucination — they amplify it, because noise accumulates faster than signal under concurrent read/write pressure.
- **Traditional monitoring misses this entirely.** Stale reads produce confident, coherent, wrong outputs. No 500. No exception. Just silent corruption. Standard observability dashboards show green because the database returned successfully — not because the data was current.
- **The binding constraint is communication fidelity, not model intelligence.** At production scale with concurrent agents, the bottleneck is not how smart the model is — it is whether the state it read is still the state that matters.
- **37% of multi-agent failures are state failures, not reasoning failures** (TierZero MAST 2025). Of those, the three formal concurrency anomaly classes — stale-generation, phantom-tool, and causal-cascade — are provably unavoidable without explicit isolation primitives (Blokz.dev research, Jun 2026, validated across 884,110 multi-agent commits).

## The move

Treat multi-agent shared state as a distributed systems problem. Three anomaly classes, three mitigation layers:

### 1. Classify the anomaly

| Anomaly | What happens | Why it's invisible |
|---------|-------------|-------------------|
| **Stale-generation** | Agent reads state S, world transitions to S', agent acts on S | Read succeeded; action succeeded; result is wrong |
| **Phantom-tool** | Agent reads a resource/tool reference that was removed before use | Tool list returned; invocation fails with silent miss |
| **Causal-cascade** | Agent A's stale decision triggers writes; agent B acts on those writes; inconsistency compounds | Each step looks fine in isolation; the cascade is the failure |

### 2. Apply Observable-Read Isolation (ORI)

The fix is not better prompting — it is transactional semantics. ORI is the name for a family of isolation-level guarantees applied to the agent-state interface:

```python
import hashlib
from dataclasses import dataclass
from typing import Any

@dataclass
class StateVersion:
    """Attach a version vector to every shared-state read."""
    content_hash: str      # SHA-256 of the read payload
    vector_clock: dict[str, int]   # {agent_id: last_write_counter}
    read_id: str           # Unique ID for this read event
    timestamp_ns: int

class ObservableReadStore:
    """
    Wraps any shared state store (DB, vector DB, message bus)
    with version tracking and stale-read detection.
    """
    def __init__(self, backend):
        self.backend = backend
        self._versions: dict[str, StateVersion] = {}

    def read(self, key: str, agent_id: str) -> tuple[Any, StateVersion]:
        value = self.backend.get(key)
        version = StateVersion(
            content_hash=hashlib.sha256(str(value).encode()).hexdigest()[:16],
            vector_clock={agent_id: 0},  # caller should merge
            read_id=f"{agent_id}:{key}:{os.urandom(8).hex()}",
            timestamp_ns=time.time_ns(),
        )
        self._versions[version.read_id] = version
        return value, version

    def verify(self, version: StateVersion) -> bool:
        """
        Call after agent completes its reasoning over this read.
        Returns True if state is unchanged since read.
        """
        current_value = self.backend.get(version.read_id.split(":")[1])
        current_hash = hashlib.sha256(str(current_value).encode()).hexdigest()[:16]
        return current_hash == version.content_hash

    def read_with_retry(self, key: str, agent_id: str,
                        max_retries: int = 2) -> tuple[Any, StateVersion]:
        """
        Read state, detect staleness, re-read if stale.
        Returns (value, version) only when read is confirmed current.
        """
        for attempt in range(max_retries + 1):
            value, version = self.read(key, agent_id)
            if self.verify(version):
                return value, version
            if attempt == max_retries:
                # Surface the staleness to the agent, don't silently continue
                raise StaleReadError(
                    f"State for '{key}' changed during reasoning. "
                    f"Read version: {version.content_hash}, "
                    f"current: {self._current_hash(key)}. "
                    f"Retry with fresh read."
                )
```

### 3. Enforce isolation at the trust boundary

The orchestrator-worker topology with a trust boundary separating the orchestrator from isolated worker containers is now the dominant production pattern. Apply three rules at the boundary:

- **Read isolation**: each worker agent gets a point-in-time snapshot, not a live reference
- **Write ordering**: all writes go through the orchestrator's message bus, never direct to shared state
- **Causal verification**: after a multi-agent pipeline completes, verify the chain's causal consistency (did each step act on the state produced by the previous step?)

```python
# Example: causal chain verification
def verify_chain(trace: list[AgentStep]) -> bool:
    """
    Given a multi-agent execution trace, verify that each step's
    output was the input to the next step — no stale reads in between.
    """
    for i in range(len(trace) - 1):
        step = trace[i]
        next_step = trace[i + 1]
        if step.output_version != next_step.input_version:
            raise CausalViolationError(
                f"Step {i+1} acted on stale state: "
                f"expected version {step.output_version}, "
                f"got {next_step.input_version}"
            )
    return True
```

### 4. Instrument for detection

Since you cannot prevent every stale read in complex pipelines, instrument for detection:

```python
# Prometheus metrics for stale-read monitoring
STALE_READ_COUNTER = Counter(
    "agent_stale_read_total",
    "Number of detected stale reads in multi-agent pipelines",
    ["agent_id", "state_key", "detection_method"]
)
VERSION_DRIFT_GAUGE = Gauge(
    "agent_version_drift_seconds",
    "Time between read and stale detection in nanoseconds",
    ["agent_id"]
)
```

Track `agent_stale_read_total` as a production alert. A spike means your isolation boundaries are leaking or your state version clock is not propagating correctly.

## See also
- [S-986 · The Coordination Breakdown Pattern](/stacks/s986-the-coordination-breakdown-pattern-when-your-multi-agent-system-is-its-own-worst-enemy.md) — broader coordination failure taxonomy
- [S-986 · Shared-state failures and the orchestrator-worker topology](/stacks/s986-the-coordination-breakdown-pattern-when-your-multi-agent-system-is-its-own-worst-enemy.md) — the trust boundary pattern
- [F-179 · Multi-Agent Coordination Failures](/forward-deployed/f179-multi-agent-coordination-failures.md) — MAST taxonomy and per-step reliability compounding
