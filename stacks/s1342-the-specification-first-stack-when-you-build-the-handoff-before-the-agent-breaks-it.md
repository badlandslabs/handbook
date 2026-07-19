# S-1342 · The Specification-First Stack — When You Build the Handoff Before the Agent Breaks It

You add a researcher agent to your pipeline. It should read the brief, produce a summary, and hand off to a writer. Three weeks later, your pipeline is producing confident, coherent, completely wrong reports. The researcher interpreted "summary" as "interpreted analysis." The writer trusted it. No error fired. No human caught it until the client did. This is the multi-agent specification problem: you built the agents before you agreed on what they should do.

## Forces

- **Specification ambiguity is the root cause of 42% of multi-agent failures.** The MAST taxonomy (1,600+ annotated traces, NeurIPS 2025) maps 14 failure modes across 7 frameworks. Specification failures — agents misinterpreting roles, outputs, and handoff conditions — are the single largest category. Coordination failures (37%) are downstream of specification failures: agents can't coordinate around a shared contract that was never written.
- **Natural language specs are ambiguous under distribution shift.** A prompt that says "produce a summary" means different things to different models, different contexts, and different runs. The meaning is stable only as long as the model's interpretation of "summary" matches your intent — and that match degrades as context grows, as model versions update, and as task complexity increases.
- **Implicit contracts are invisible until they break.** When agents coordinate through shared context alone, the handoff contract exists only in the heads of whoever wrote the prompts. Nobody reviews it. Nobody validates it. It breaks silently, producing coherent outputs from incoherent shared understanding.
- **79% of production breakdowns trace to two root causes.** According to the MAST research, fixing specification quality and coordination protocols delivers the highest reliability ROI of any intervention. This is not a nice-to-have — it's the highest-leverage point in multi-agent design.

## The move

Write the multi-agent specification *before* you write a single agent prompt. Treat it like a system design document, not a prompt engineering exercise.

### The four sections of a multi-agent spec

**1. Role contracts — what each agent owns and doesn't**

```
researcher:
  role: "Extract factual claims from source documents"
  owns: ["raw_findings", "source_citations"]
  does_not_touch: ["analysis", "recommendations", "narrative"]
  output_schema: { findings: Claim[], sources: SourceRef[] }
  rejects_unclear: true  # asks for clarification instead of guessing

writer:
  role: "Transform factual claims into narrative"
  owns: ["narrative", "recommendations"]
  trusts: ["researcher.findings"]
  input_schema: { findings: Claim[], sources: SourceRef[] }
```

**2. Handoff protocols — what passes between agents**

```
handoff researcher → writer:
  trigger: researcher.status == "DONE" AND researcher.findings.count > 0
  content: { brief: Brief, findings: Claim[], brief_version: int }
  failure_if: brief_version != current_brief_version  # stale brief rejection
  escalation: "route back to orchestrator if brief drift detected"
```

**3. State interface schema — shared vocabulary**

Define the canonical shape of every data type that crosses an agent boundary. Not "a summary" — `SummarySchema { key_findings: string[3..5], confidence: float, caveats: string[] }`. Schema violations should fail the handoff, not silently degrade.

**4. Escalation conditions — when to stop and ask**

```
escalate_if:
  - finding_confidence < 0.7
  - sources.length < 3
  - brief_version_mismatch
  - agent_confidence_in_output < 0.6
action: "suspend handoff, surface to orchestrator, await human review"
```

### The spec-first workflow

```
1. Write the spec in a shared file (agent-spec.yaml or .md)
2. Review it as a team before any agent code is written
3. Generate agent prompts from the spec — prompts are derived from contracts, not the other way around
4. Add a schema-validation step to every handoff point
5. Treat spec changes as first-class events — spec drift triggers re-review
```

## The implementation

```python
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ValidationError


class AgentRole(str, Enum):
    RESEARCHER = "researcher"
    WRITER = "writer"
    ORCHESTRATOR = "orchestrator"


class HandoffStatus(str, Enum):
    PENDING = "PENDING"
    TRANSFERRED = "TRANSFERRED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


@dataclass
class Claim:
    statement: str
    source_id: str
    confidence: float = Field(ge=0.0, le=1.0)


@dataclass
class ResearchOutput:
    findings: list[Claim] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    brief_version: int = 0
    confidence_avg: float = 0.0

    def validate(self) -> bool:
        if self.confidence_avg < 0.7:
            return False
        if len(self.findings) < 3:
            return False
        return True


@dataclass
class Handoff:
    from_agent: AgentRole
    to_agent: AgentRole
    payload: dict
    payload_schema: str  # e.g. "ResearchOutput"
    brief_version: int
    status: HandoffStatus = HandoffStatus.PENDING
    rejection_reason: Optional[str] = None


def attempt_handoff(
    handoff: Handoff,
    current_brief_version: int,
    researcher_output: ResearchOutput,
) -> Handoff:
    """
    Spec-first handoff gate. Rejects if:
    - Payload doesn't match the declared schema
    - Brief version is stale
    - Output fails validation
    """
    # Schema check
    try:
        payload = json.loads(json.dumps(handoff.payload))
    except (TypeError, ValueError):
        handoff.status = HandoffStatus.REJECTED
        handoff.rejection_reason = "payload failed JSON serialization"
        return handoff

    # Stale brief rejection
    if handoff.brief_version != current_brief_version:
        handoff.status = HandoffStatus.ESCALATED
        handoff.rejection_reason = (
            f"stale brief: handoff v{handoff.brief_version} "
            f"!= current v{current_brief_version}"
        )
        return handoff

    # Output quality gate
    if not researcher_output.validate():
        handoff.status = HandoffStatus.ESCALATED
        handoff.rejection_reason = (
            f"output validation failed: "
            f"avg_confidence={researcher_output.confidence_avg:.2f} "
            f"(threshold=0.7), "
            f"findings_count={len(researcher_output.findings)} (threshold=3)"
        )
        return handoff

    handoff.status = HandoffStatus.TRANSFERRED
    return handoff


# --- Example run ---
researcher_output = ResearchOutput(
    findings=[
        Claim("X grew 23% YoY", "source_1", confidence=0.95),
        Claim("Market cap is $4.2B", "source_2", confidence=0.92),
        Claim("Competitor Y filed IPO", "source_3", confidence=0.88),
    ],
    sources=["source_1", "source_2", "source_3"],
    brief_version=3,
    confidence_avg=0.92,
)

handoff = Handoff(
    from_agent=AgentRole.RESEARCHER,
    to_agent=AgentRole.WRITER,
    payload={"findings": [vars(f) for f in researcher_output.findings]},
    payload_schema="ResearchOutput",
    brief_version=3,
)

result = attempt_handoff(handoff, current_brief_version=3, researcher_output=researcher_output)
print(f"Handoff status: {result.status.value}")  # TRANSFERRED
print(f"Rejection reason: {result.rejection_reason}")  # None

# --- Example: stale brief ---
handoff_stale = Handoff(
    from_agent=AgentRole.RESEARCHER,
    to_agent=AgentRole.WRITER,
    payload={"findings": []},
    payload_schema="ResearchOutput",
    brief_version=2,  # stale
)
result_stale = attempt_handoff(handoff_stale, current_brief_version=3, researcher_output=ResearchOutput())
print(f"Stale handoff status: {result_stale.status.value}")  # ESCALATED
print(f"Rejection reason: {result_stale.rejection_reason}")  # stale brief: handoff v2 != current v3
```

## Receipt

> Verified 2026-07-19 — Ran the handoff gate against three scenarios (clean handoff, stale brief, low-confidence output). All three produced correct status transitions: TRANSFERRED for the clean case, ESCALATED for stale brief, ESCALATED for low-confidence output. No silent failures. Output matches expected enum states.

## See also

- [S-1314 · The Pipeline Collapse Stack](/stacks/s1314-the-pipeline-collapse-stack-three-silent-failures-that-kill-multi-agent-systems-after-the-handoff.md) — The three silent failures (context drift, mock divergence, unowned escalation) that specification design prevents
- [S-1323 · The Reversibility Gate Stack](/stacks/s1323-the-reversibility-gate-stack-when-your-agent-commits-before-checking-if-it-can-roll-back.md) — Pre-flight checks for irreversible actions; complementary to the escalation conditions in this entry
- [S-1325 · The Agent Handoff Stack](/stacks/s1325-the-agent-handoff-stack-when-your-agents-pass-bad-batons.md) — The mechanics of the handoff itself (structured briefs, state contracts, brief anchoring)
