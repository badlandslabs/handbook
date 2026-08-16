# [S-2698] · The Memory Trace Stack

You spent three weeks debugging why your coding agent kept inserting the wrong database schema. The agent's memory had quietly absorbed a corrupted RAG chunk from a failed migration — and it trusted that memory absolutely. No stack trace. No error. Just a right answer that was wrong.

The trap: memory-augmented agents trust their stored knowledge more than their current context. When memory itself is the failure point, traditional debugging breaks.

## Forces

- Memory enables long-horizon agency but introduces a persistent attack/defect surface invisible in any single session
- Memory failures are **systematic** (they repeat, they compound, they propagate) — not random noise
- Existing agent debugging covers stateless failures; stateful memory failures require a fundamentally different trace model
- Agents cannot reliably self-diagnose their own memory corruption — the corrupted memory IS the reasoning substrate
- Memory systems (RAG, Mem0, EverMemOS, flat-file MEMORY.md) all fail differently; generic solutions don't hold
- The blast radius of a single bad memory insert grows over time as the agent builds on corrupted context

## The Move

The move is **memory evolution tracing** — building an operation-level provenance graph of every memory write, retrieval, compression, and synthesis event, then tracing failure attribution backwards through that graph.

### 1. Build the Memory Evolution Graph

Transform your memory pipeline into a directed acyclic graph where nodes are memory operations and edges carry information flow:

```python
from dataclasses import dataclass, field
from typing import Literal, Optional
from datetime import datetime
import uuid

@dataclass
class MemoryOp:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    op_type: Literal["write", "retrieve", "compress", "synthesize", "forget", "update"] = ""
    source: str = ""          # which document/tool/conversation produced this
    content_hash: str = ""    # content-addressed snapshot before the op
    parent_ids: list[str] = field(default_factory=list)  # provenance
    timestamp: datetime = field(default_factory=datetime.utcnow)
    session_id: str = ""
    confidence: float = 1.0   # trust signal at write time
    metadata: dict = field(default_factory=dict)

class MemoryTraceGraph:
    def __init__(self):
        self.ops: dict[str, MemoryOp] = {}
        self.edges: dict[str, list[str]] = {}  # op_id -> child op_ids

    def add_op(self, op: MemoryOp, parent_ids: list[str] | None = None) -> str:
        self.ops[op.id] = op
        op.parent_ids = parent_ids or []
        for pid in op.parent_ids:
            self.edges.setdefault(pid, []).append(op.id)
        return op.id

    def trace_failure(self, failed_mem_id: str) -> list[MemoryOp]:
        """Walk the graph backward from a failing memory node to root causes."""
        path = []
        visited = set()
        stack = [failed_mem_id]
        while stack:
            cur_id = stack.pop()
            if cur_id in visited:
                continue
            visited.add(cur_id)
            if cur_id in self.ops:
                path.append(self.ops[cur_id])
                stack.extend(self.ops[cur_id].parent_ids)
        return path

    def find_contamination_chain(self, suspect_content: str) -> list[MemoryOp]:
        """Find all ops reachable from memory containing suspect content."""
        contaminated = []
        for op in self.ops.values():
            if suspect_content.lower() in op.metadata.get("content", "").lower():
                contaminated.append(op)
                # Walk forward from this op to see downstream impact
                contaminated.extend(self._walk_forward(op.id))
        return contaminated

    def _walk_forward(self, op_id: str) -> list[MemoryOp]:
        """Propagate contamination forward through descendant ops."""
        affected = []
        stack = list(self.edges.get(op_id, []))
        visited = {op_id}
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            if cur in self.ops:
                affected.append(self.ops[cur])
                stack.extend(self.edges.get(cur, []))
        return affected

# Usage in your agent loop
trace = MemoryTraceGraph()

# Memory write with provenance
trace.add_op(MemoryOp(
    op_type="write",
    source="rag_retrieval",
    content_hash="sha256:abc123",
    parent_ids=["op_session_001"],  # the session that generated this
    metadata={"content": "SELECT user_id, email FROM users", "retrieval_score": 0.91}
))

# Compression operation — parent is the original write
trace.add_op(MemoryOp(
    op_type="compress",
    source="memory_consolidation",
    content_hash="sha256:def456",
    parent_ids=["op_abc123"],  # traces back to original
    metadata={"compression_ratio": 0.3, "extracted_entities": ["user_id", "schema_v2"]}
))

# Detect contamination: schema changed but memory wasn't invalidated
session_op = trace.add_op(MemoryOp(
    op_type="update",
    source="schema_migration_v3",
    content_hash="sha256:new789",
    parent_ids=["op_def456"],
    metadata={"schema_version": "v3", "breaking_change": True}
))

# The failure: agent retrieves compressed memory from v2-era op
path = trace.trace_failure(session_op)
print(f"Failure traced through {len(path)} operations:")
for op in reversed(path):
    print(f"  {op.op_type:12} | {op.source:20} | conf={op.confidence:.2f}")
```

### 2. The Systematic Failure Taxonomy (MemTraceBench findings)

MemTraceBench's analysis of 160 annotated failure cases across Long-Context, RAG, Mem0, and EverMemOS reveals three systematic failure clusters:

**Cluster A — Information Loss at Compression**
Memory consolidation compresses context. The agent loses critical details silently. Detection: compare `content_hash` of parent write against what compression actually retains.

**Cluster B — Retrieval Misalignment**
The retrieval query matches memory, but the matched memory is stale or contextually wrong. The agent acts on it confidently. Detection: track `retrieval_score` alongside `parent_ids` — low-score matches feeding high-confidence downstream decisions are red flags.

**Cluster C — Cross-Generation Corruption**
Memory written in session N is retrieved in session N+7 and synthesized with new content, producing something that neither session intended. Detection: the evolution graph reveals multi-hop provenance chains that end in contradictory destinations.

### 3. Operational Integrity Checks

Run these before any high-stakes memory retrieval:

```python
def integrity_check(graph: MemoryTraceGraph, mem_id: str, threshold: float = 0.75) -> dict:
    op = graph.ops.get(mem_id)
    if not op:
        return {"status": "unknown", "reason": "op not found"}

    # Rule 1: Confidence decay through compression chains
    path = graph.trace_failure(mem_id)
    compress_ops = [p for p in path if p.op_type == "compress"]
    if compress_ops:
        avg_confidence = sum(p.confidence for p in compress_ops) / len(compress_ops)
        if avg_confidence < threshold:
            return {
                "status": "degraded",
                "reason": f"Compression chain degraded confidence to {avg_confidence:.2f}",
                "ops_affected": len(compress_ops)
            }

    # Rule 2: Detect stale writes feeding recent decisions
    if op.op_type in ("retrieve", "synthesize"):
        parents = [graph.ops[p] for p in op.parent_ids if p in graph.ops]
        stale_parents = [p for p in parents if p.source.startswith("deprecated_")]
        if stale_parents:
            return {
                "status": "stale",
                "reason": f"{len(stale_parents)} parent ops are deprecated",
                "stale_ids": [p.id for p in stale_parents]
            }

    # Rule 3: Check for orphaned writes (no parent, no timestamp continuity)
    if not op.parent_ids and op.op_type == "write":
        age_hours = (datetime.utcnow() - op.timestamp).total_seconds() / 3600
        if age_hours > 1:
            return {
                "status": "unverified",
                "reason": f"Write has no provenance and is {age_hours:.1f}h old",
                "recommendation": "inject_verification"
            }

    return {"status": "healthy"}
```

### 4. Memory Sanitization Defense (from arxiv-2603.11768)

When poisoning is detected, sanitize rather than delete:

```python
def sanitize_memory(graph: MemoryTraceGraph, poison_mem_id: str) -> str:
    """Replace poisoned memory with a grounded placeholder, preserving graph structure."""
    op = graph.ops.get(poison_mem_id)
    if not op:
        return ""

    # Create sanitized replacement with the same provenance
    safe_op = MemoryOp(
        op_type="write",
        source="sanitized",
        content_hash="sha256:SANITIZED",
        parent_ids=op.parent_ids,  # preserve traceability
        confidence=0.0,           # explicit distrust flag
        metadata={
            "original_hash": op.content_hash,
            "sanitized_at": datetime.utcnow().isoformat(),
            "reason": "memory_poison_detected"
        }
    )

    # Walk forward and annotate downstream contamination
    affected = graph._walk_forward(poison_mem_id)
    for aff_op in affected:
        aff_op.metadata["contamination_flagged"] = True
        aff_op.metadata["contamination_source"] = op.id

    new_id = graph.add_op(safe_op, parent_ids=op.parent_ids)
    return new_id
```

## Receipt

> Verified 2026-08-15 — MemTraceBench (arxiv-2605.28732) study of 160 annotated failure cases across Long-Context, RAG, Mem0, EverMemOS confirms systematic memory failures with operation-level root causes. NevaMind memU 28-day production study (Issue #381) measured 7% memory divergence between self-reported records and externally-verified outcomes. Microsoft Zero Trust catalog documents memory poisoning as a persistent cross-session attack surface distinct from prompt injection.

## See also

- [S-2693 · The Agent Failure Recovery Stack](/stacks/s2693-the-agent-failure-recovery-stack-when-your-agent-crashes-spirals-or-lies-about-it.md) — crash recovery when memory corruption surfaces as a crash
- [S-2680 · The Agent Context Lifecycle Stack](/stacks/s2680-the-agent-context-lifecycle-stack-when-your-agent-remembers-wrong-things-for-the-wrong-reasons.md) — memory lifecycle management upstream of tracing
- [S-2694 · The Error-Becomes-Narrative Stack](/stacks/s2694-the-error-becomes-narrative-stack-when-your-llm-agent-transforms-a-system-fault-into-a-confident-lie.md) — when memory error propagates into confident false reasoning
