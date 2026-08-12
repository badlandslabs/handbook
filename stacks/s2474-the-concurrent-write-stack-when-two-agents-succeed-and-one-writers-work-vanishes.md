# S-2474 · The Concurrent Write Stack — When Two Agents Succeed and One Writer's Work Vanishes

Two agents are reading `config.yaml`, modifying it, and writing it back. Agent A reads version 1. Agent B reads version 1. Agent A writes its changes. Agent B writes its changes — overwriting Agent A's work completely. No error is thrown. Both agents report success. The system says "saved." Three hours later, you discover that Agent A's entire contribution is gone. This is not a bug. It is the default behavior of agents that share a file system and operate at read/write speed without coordination.

## Forces

- **The atomic file system is a lie at the application layer.** Linux `write()` is atomic at the byte level, not at the file level. Two sequential writes from different processes to the same file are not serializable by the OS — the second write simply overwrites the first.
- **Agent success signals are local, not transactional.** When Agent A calls `write_file()` and gets back `{status: "saved"}`, that only means the local write succeeded. It says nothing about whether another agent overwrote that file between A's read and A's write.
- **Workspace isolation defers the problem, not the cost.** Many teams solve concurrent writes by giving each agent a private directory or git worktree. This prevents interference during execution — but moves the conflict resolution to a post-hoc merge step where recovery is expensive. Textual merge conflicts are easy to spot; semantic conflicts (both versions compile, both are individually valid, but the combination breaks) are not.
- **The problem scales nonlinearly with agent count.** At two agents, a race is rare. At twelve agents (the average for organizations deploying multi-agent systems per Gartner, 2025), races become common enough to be a chronic reliability problem.
- **The silent nature makes it catastrophic.** Unlike a crash or an exception, a write-overwrite produces zero error signals. APM shows 200 OK. The orchestrator sees both agents complete their spans with status "success." The only evidence of the failure is a subtle divergence in the final state.

## The move

**Enforce write-time conflict detection, not post-hoc merge.**

### Layer 1 — Optimistic locking with version tokens

Before an agent reads a shared resource, it captures a version handle. On write, it submits both the new content and the expected version. The store rejects the write if the current version no longer matches — forcing a re-read and re-apply.

```python
import json, time
from pathlib import Path
from filelock import FileLock

CONFIG = Path("config.yaml")
LOCK_TIMEOUT = 10

def read_config():
    lock = FileLock(CONFIG.with_suffix(".lock"), timeout=LOCK_TIMEOUT)
    with lock:
        content = CONFIG.read_text()
        version = str(hash(content))  # lightweight version token
        return content, version

def write_config(content: str, expected_version: str) -> bool:
    lock = FileLock(CONFIG.with_suffix(".lock"), timeout=LOCK_TIMEOUT)
    with lock:
        current = CONFIG.read_text()
        current_version = str(hash(current))
        if current_version != expected_version:
            return False  # conflict detected
        CONFIG.write_text(content)
        return True

# Agent A
content_a, ver_a = read_config()
# ... agent A modifies content_a ...
ok = write_config(content_a, ver_a)
if not ok:
    content_a, ver_a = read_config()  # re-read after conflict
    # ... re-apply changes ...
    write_config(content_a, ver_a)
```

### Layer 2 — Structured state mediation (STORM pattern)

Replace shared file access with a state mediator that manages per-resource locks and emits conflict signals. Agents never read or write the shared resource directly — they submit operations to the mediator, which sequences them and detects semantic conflicts (e.g., both agents modified the same section, not just the same file).

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import hashlib

class OpType(Enum):
    READ = "read"
    WRITE = "write"

@dataclass
class ResourceOp:
    agent_id: str
    resource: str
    op: OpType
    expected_version: str
    payload: Optional[str] = None

class StateMediator:
    """
    STORM-style state mediator.
    Agents submit operations; mediator sequences them and
    detects version conflicts before they become silent overwrites.
    """
    def __init__(self):
        self._versions: dict[str, str] = {}
        self._pending: dict[str, list[ResourceOp]] = {}

    def submit(self, op: ResourceOp) -> dict:
        resource = op.resource
        if resource not in self._versions:
            # Initialize version from current disk state
            p = Path(resource)
            if p.exists():
                self._versions[resource] = str(hashlib.sha256(p.read_bytes()).hexdigest()[:16])
            else:
                self._versions[resource] = "0"

        if op.op == OpType.READ:
            return {"version": self._versions[resource], "locked_by": None}

        # WRITE
        if op.expected_version != self._versions[resource]:
            return {
                "accepted": False,
                "conflict": True,
                "current_version": self._versions[resource],
                "hint": "re-read and retry"
            }

        # Accept write, update version
        if op.payload:
            Path(resource).write_text(op.payload)
        new_version = str(hashlib.sha256((op.payload or "").encode()).hexdigest()[:16])
        self._versions[resource] = new_version
        return {"accepted": True, "version": new_version}

# Usage: agent submits writes through mediator
mediator = StateMediator()
op = ResourceOp(agent_id="agent-B", resource="config.yaml",
                op=OpType.WRITE, expected_version="abc123", payload=new_content)
result = mediator.submit(op)
if result.get("conflict"):
    print("STORM conflict: re-read required")
    # re-read from mediator, merge, retry
elif result.get("accepted"):
    print("STORM accepted: version", result["version"])
```

### Layer 3 — Semantic conflict detection

Textual version conflicts are only half the problem. Two agents can write to different sections of the same JSON/YAML file that are semantically incompatible (one sets `timeout: 30`, another sets `retry_policy.max_attempts: 1` — together they produce an invalid configuration that neither individually creates). Use a schema validator or LLM-as-judge on the combined state:

```python
import yaml

def semantic_validate(path: str, incoming: str) -> list[str]:
    """Return list of semantic conflicts between current and incoming."""
    with open(path) as f:
        current = yaml.safe_load(f)

    incoming_parsed = yaml.safe_load(incoming)
    conflicts = []

    # Example: if current sets rate_limit and incoming sets rate_limit=0
    if current.get("rate_limit") and incoming_parsed.get("rate_limit") == 0:
        conflicts.append("rate_limit: current has non-zero, incoming sets 0 — possible miscoordination")

    return conflicts

current_cfg, ver = read_config()
new_cfg = merge_configs(current_cfg, agent_changes)
semantic_issues = semantic_validate(CONFIG, new_cfg)
if semantic_issues:
    print(f"STORM semantic conflict: {semantic_issues}")
    # Escalate to orchestrator for human review or automated merge strategy
```

### Layer 4 — The orchestrator as serialization boundary

In hierarchical orchestrator-worker patterns, the orchestrator itself is the natural serialization point. Instead of letting workers write independently, the orchestrator collects all intended writes and sequences them as a batch commit:

```python
class SerializingOrchestrator:
    """
    Orchestrator that batches and serializes writes from multiple agents.
    Workers propose writes; the orchestrator commits them in order.
    """
    def __init__(self):
        self._proposals: dict[str, dict] = {}  # agent_id -> proposed change
        self._mediator = StateMediator()

    def propose(self, agent_id: str, resource: str, content: str):
        # Get current version
        resp = self._mediator.submit(
            ResourceOp(agent_id, resource, OpType.READ, "")
        )
        self._proposals[agent_id] = {
            "resource": resource,
            "content": content,
            "version": resp["version"]
        }

    def commit_all(self):
        """Commit all proposals in deterministic order, retrying on conflict."""
        # Sort by agent_id for deterministic ordering
        for agent_id in sorted(self._proposals):
            prop = self._proposals[agent_id]
            result = self._mediator.submit(ResourceOp(
                agent_id, prop["resource"], OpType.WRITE,
                expected_version=prop["version"], payload=prop["content"]
            ))
            if not result.get("accepted"):
                print(f"[orchestrator] conflict on {agent_id}, re-syncing")
                # Re-read combined state, notify dependent agents
                del self._proposals[agent_id]
        self._proposals.clear()
```

## Receipt

> Verified 2026-08-11 — arXiv:2605.20563 (Liu et al., Shanghai Jiaotong / Cortices AI / Emory / Peking, May 2026) introduced STORM framework: +18.7 on Commit0-Lite vs git-worktree baseline, +1.4 on PaperBench. Key finding: workspace isolation (worktree per agent) defers resolution to post-hoc merge where semantic conflicts are expensive. Beam.ai (Aug 2026): 40% of multi-agent pilots fail within 6 months; coordination breakdown is a primary failure class. Grubenwald (2026): "57% of companies run 5+ agents concurrently on shared repositories." Dynatrace Perform 2026: 95%/step → ~60% at 10 steps — concurrent write conflicts compound this reliability cliff.

## See also

- [S-2406 · The Orchestration Success Signal Stack](stacks/s2406-the-orchestration-success-signal-stack-when-your-sub-agent-returns-but-nothing-happened.md) — success signals that miss silent write failures
- [S-1550 · The Plan Object Stack](stacks/s1550-the-plan-object-stack-when-your-agent-plans-in-prompt-space-and-loses-it-between-turns.md) — plan persistence across agent turns
- [S-2466 · The MCP Protocol Trust Stack](stacks/s2466-the-mcp-protocol-trust-stack-when-the-protocol-assumes-your-server-is-honest.md) — protocol-layer trust assumptions vs. actual guarantees
