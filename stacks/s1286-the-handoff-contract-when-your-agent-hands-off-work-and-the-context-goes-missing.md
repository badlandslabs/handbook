# S-1286 · The Handoff Contract — When Your Agent Hands Off Work and the Context Goes Missing

Your triage agent collected a detailed customer complaint. Your routing agent handles it next. It asks the customer to restate their issue from scratch — it has no idea what the previous agent learned. Your research agent surfaced 12 relevant documents. Your writer agent receives "here are some documents" with no citations, no ranking, no relevance scores. The pipeline produced mediocre output, and nobody can explain why — the models were fine, the tools were fine, the handoff was the failure point. This is the handoff contract problem, and it is the primary cause of multi-agent pipeline failures in production.

## Forces

- **Agents don't share memory by default.** Each agent instance has its own isolated context window. A free-text summary passed between them loses the granularity that made earlier work valuable — constraints, reasoning traces, partial conclusions, source rankings, and confidence levels all evaporate in prose summarization. (Corbits, May 2026 — https://www.corbits.dev/blog/context-loss-in-multi-agent-systems)
- **79% of production multi-agent failures trace to coordination problems** — specification ambiguity, unstructured context passing, and agents misinterpreting their role in the chain. The models performed correctly; the wiring between them failed. (Cemri, Pan, Yang et al., arXiv:2503.13657v1, 2025)
- **Multi-agent only wins above ~12 tool domains.** Below that threshold, a well-prompted single agent outperforms multi-agent pipelines on accuracy, cost, and mean time to detection — unless handoff quality is deliberately engineered. Above the threshold, the payoff requires a structured artifact system, not free-text prose. (AgentMode.ai, May 2026 — https://agentmodeai.com/single-agent-vs-multi-agent-decision-framework/)
- **Intent drifts through transfers.** After 3–4 sequential handoffs, the original user intent is often unrecognizable in the final output. Intent preservation is not a context management problem — it requires explicit encoding in the handoff artifact. (Pramod Chandrayan, Medium/Predict, May 2026)

## The move

### 1. Define a schema-bound artifact for every handoff

Pass structured data, not prose summaries. A handoff artifact is a typed object with a known schema that both the sending and receiving agent must conform to.

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"

@dataclass
class HandoffArtifact:
    artifact_id: str          # Stable UUID — receivers pin to this, not the text
    task_id: str             # Parent task this contributes to
    source_agent: str        # Who created this
    target_agent: str         # Who should consume this
    status: TaskStatus

    # Structured payload — replace with domain-specific fields
    findings: list[dict] = field(default_factory=list)   # e.g. [{"url": "...", "relevance": 0.92}]
    constraints: list[str] = field(default_factory=list) # What the next agent MUST respect
    confidence: float        # 0.0–1.0; next agent gates on threshold
    reasoning_trace: str     # Why this path was chosen (not just the conclusion)
    schema_version: str = "1.0"

    # Provenance
    created_at: str = ""
    provenance_refs: list[str] = field(default_factory=list)  # Source hashes, document IDs

    def to_context_prompt(self) -> str:
        """Render artifact into a context window instruction for the receiving agent."""
        lines = [
            f"## Handoff Artifact [{self.artifact_id}]",
            f"Task: {self.task_id} | Source: {self.source_agent} → {self.target_agent}",
            f"Status: {self.status.value} | Confidence: {self.confidence:.0%}",
            f"",
            f"### Findings ({len(self.findings)} items)",
        ]
        for f in self.findings:
            lines.append(f"  - {f}")
        if self.constraints:
            lines.append(f"### Constraints (MUST NOT violate)")
            for c in self.constraints:
                lines.append(f"  - {c}")
        if self.reasoning_trace:
            lines.append(f"### Reasoning Trace\n{self.reasoning_trace}")
        return "\n".join(lines)
```

### 2. Annotate intent and constraints, not just output

The most valuable thing to preserve across a handoff is *why* something was chosen — the decision rationale, not just the conclusion.

```python
@dataclass
class DecisionRecord:
    decision_id: str
    decision_type: str           # "selected", "rejected", "escalated", "abandoned"
    subject: str                 # What was decided about
    rationale: str               # One-paragraph why
    alternatives_considered: list[str]
    constraints_applied: list[str]
    confidence: float
    reversible: bool             # Can the next agent revisit this?
    blocker: Optional[str]       # If BLOCKED, what's preventing progress?

def record_decision(artifact: HandoffArtifact, record: DecisionRecord) -> None:
    """Append a decision record to the artifact before handoff."""
    artifact.reasoning_trace += (
        f"\n[D#{record.decision_id}] {record.decision_type.upper()}: {record.subject}\n"
        f"  Rationale: {record.rationale}\n"
        f"  Alternatives: {', '.join(record.alternatives_considered)}\n"
        f"  Confidence: {record.confidence:.0%} | Reversible: {record.reversible}\n"
    )
```

### 3. Add an acceptance gate on the receiving side

The receiving agent must validate the artifact before acting on it — check required fields, confidence threshold, schema version, and provenance.

```python
MIN_CONFIDENCE = 0.70
MIN_FINDINGS = 1
SCHEMA_VERSION = "1.0"

def accept_handoff(artifact: HandoffArtifact, receiving_agent: str) -> None:
    errors = []

    if artifact.schema_version != SCHEMA_VERSION:
        errors.append(f"Schema mismatch: expected {SCHEMA_VERSION}, got {artifact.schema_version}")

    if artifact.confidence < MIN_CONFIDENCE:
        errors.append(f"Confidence {artifact.confidence:.0%} below threshold {MIN_CONFIDENCE:.0%}")

    if len(artifact.findings) < MIN_FINDINGS:
        errors.append(f"Only {len(artifact.findings)} findings, expected ≥{MIN_FINDINGS}")

    if not artifact.provenance_refs:
        errors.append("No provenance refs — sources unverifiable")

    if errors:
        # Escalate to human or retry with the source agent
        raise HandoffValidationError(
            f"Handoff {artifact.artifact_id} rejected:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    # Tag the artifact with the receiver so the handoff is logged
    artifact.target_agent = receiving_agent
    log_handoff(artifact)
```

### 4. Use schema fingerprints for API-bound handoffs

When handoffs cross system boundaries (not just agent-to-agent), pin to immutable artifact URIs.

```python
import hashlib, json

def artifact_fingerprint(artifact: HandoffArtifact) -> str:
    """SHA-256 digest of the structured payload — receivers pin to this, not text."""
    payload = {
        "task_id": artifact.task_id,
        "findings": artifact.findings,
        "constraints": artifact.constraints,
        "schema_version": artifact.schema_version,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]

# On the receiving side:
# 1. Fetch artifact by URI
# 2. Verify fingerprint matches what was agreed at handoff time
# 3. Reject if fingerprint drifted — the source state changed mid-transfer
```

### 5. Handle the "forgot why" failure mode

When an agent completes a subtask but the next agent needs to build on it (not just read it), include the *continuation context* — what the next agent should do, not just what was done.

```python
def build_continuation_context(
    artifact: HandoffArtifact,
    next_action: str,
    failure_modes: list[str],
) -> str:
    return (
        f"{artifact.to_context_prompt()}\n"
        f"### Next Action\n{next_action}\n"
        f"### Known Failure Modes at This Stage\n" +
        "\n".join(f"  - {f}" for f in failure_modes) +
        f"\n### Questions to Resolve Before Proceeding\n  - [ ] "
    )
```

## Receipt

> Verified 2026-07-18 — Sources: Corbits (context loss taxonomy, May 2026), AgentMemo (handoff protocol requirements, Feb 2026), Qurtoo (79% failure stat, arXiv:2503.13657), AgentMode.ai (12-tool-domain threshold), Trendifai/agentstate (GitHub, schema fingerprint pattern), Pramod Chandrayan (intent drift, Medium/Predict, May 2026). Code reflects established structured-state-passing patterns from Corbits SDK and AgentMemo's published protocol spec. Receipt pending — live execution against a multi-agent pipeline would confirm the acceptance gate reduces downstream error rate.

## See also

- [S-05 · Multi-Agent Patterns](s05-multi-agent-patterns.md) — foundational pipeline/fan-out patterns; this entry adds the handoff quality layer those patterns omit
- [S-05 · Multi-Agent Patterns](s05-multi-agent-patterns.md) — foundational pipeline/fan-out patterns; this entry adds the handoff quality layer those patterns omit
- [S-244 · Reliability Multiplication](s1240-the-reliability-multiplication-law-when-95-percent-per-step-accuracy-means-36-percent-task-completion.md) — explains why compound reliability degrades across sequential agents; handoff contracts are a partial mitigation
- [S-1008 · The Orchestration Pattern Match Stack](s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md) — pipeline pattern includes handoffs but doesn't address artifact structure
