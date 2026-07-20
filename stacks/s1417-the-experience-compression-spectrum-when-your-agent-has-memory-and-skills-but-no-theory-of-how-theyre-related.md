# S-1417 · The Experience Compression Spectrum: When Your Agent Has Memory and Skills but No Theory of How They're Related

Your agent has episodic memory, a skill library, and a set of hardcoded rules. They were built by three different teams at three different times, each convinced they were solving the same problem. Nobody asked whether these three systems live on the same axis — or whether they're fundamentally different compression levels of the same thing. The answer, according to Zhang et al. (arXiv:2604.15877, v2, Jun 2026), is the latter.

## Forces

- **Memory teams and skills teams don't cite each other.** The paper found <1% cross-community citation between memory systems research and skill discovery research — despite both solving the same underlying problem: turning interaction traces into reusable knowledge.
- **Every compression level has different tradeoffs.** High compression (rules) is compact and fast but brittle. Low compression (raw traces) is faithful but unwieldy. Teams pick one level and treat the others as noise.
- **The missing diagonal is adaptive cross-level compression.** No production system currently dynamically decides whether a given experience should become episodic memory, a skill, or a rule — or whether it needs to be promoted/demoted as conditions change.
- **Existing taxonomies describe mechanisms, not objectives.** Saying "you have semantic memory" tells you where data lives, not why you're storing it or what decision it should inform.

## The move

Treat memory, skills, and rules as points on a single axis: **experience compression level**.

```
Raw Trace (L0)  →  Episodic Memory (L1)  →  Procedural Skill (L2)  →  Declarative Rule (L3)
  1:1               5–20×                    50–500×                   1,000×+
  Maximum fidelity   "what happened"          "how to do X"             "always do Y"
  Maximum cost      Compression lossy        Further lossy             Nearly lossless intent
  Maximum reuse      but searchable          and reusable              but rigid
```

**The four levels, in practice:**

### L0 — Raw Trace
Complete execution log: every tool call, every LLM call, every state mutation. Compression ratio 1:1. This is what you'd replay for post-hoc debugging. You don't retrieve from it — you search it. Most agents discard this after the session ends. The value is forensic, not operational.

### L1 — Episodic Memory
Key-value summaries of significant events. "Session 47: User asked about billing outage. Agent escalated. Escalation accepted. Resolved in 3 steps." Compression ratio 5–20×. This is what most people mean when they say "agent memory." The LLM decides what matters at session end and writes a structured summary into a persistent store. The compression is lossy — details are discarded — but what's kept is indexed and retrievable by semantic similarity or timestamp.

### L2 — Procedural Skill
A reusable procedure that can be invoked by name without re-deriving it. "The billing escalation workflow." Compression ratio 50–500×. This is the output of a skill discovery or cumulative skill creation system (e.g., CASCADE). The key property: the agent can *call* it without re-planning it. Unlike L1 (which answers "what happened?"), L2 answers "how do I do X?" Skills survive context window resets; they are externalized cognition.

### L3 — Declarative Rule
An explicit, hardcoded directive: system prompt constraints, tool guardrails, policy statements. Compression ratio 1,000×+. "Never delete records. Always confirm before sending emails. Escalate if confidence < 0.7." Rules are zero-latency retrieval (they're just code or config) but they are brittle — they don't adapt to context and they silently break when the world changes beneath them.

### The critical move: cross-level promotion and demotion

The missing production pattern is **adaptive compression control** — the system actively decides which level to store knowledge at, and can promote or demote it over time:

```
New edge case observed repeatedly
  → L1 episodic entries accumulate
  → Agent or offline process detects the pattern
  → Promotes to L2 skill ("the billing outage workflow")
  → After sufficient validation, rule-authority can promote to L3 guardrail
  → Rule conflicts with new policy
  → Demotes to L2 with override flag
```

Without this promotion/demotion mechanism, agents accumulate L1 episodes forever (context bloat), L2 skills go stale (wrong procedure for changed APIs), and L3 rules create silent traps (overgeneralized constraints that don't account for edge cases).

**The SSGM interface is where this breaks.** Lam et al. (arXiv:2603.11768v2) identify three failure points at each compression boundary: **memory poisoning** at L0→L1 (malicious content internalized), **semantic drift** at L1→L2 (repeated summarization distorts facts), and **conflict/hallucination** at L2→L3 (competing skills produce contradictory outputs). A production compression system needs governance at every boundary, not just at retrieval.

### The practical decision matrix

| Situation | Best level | Why |
|-----------|-----------|-----|
| Debugging a specific failure | L0 raw trace | Fidelity required |
| Learning from a session | L1 episodic | Searchable summary |
| Reusing a procedure across sessions | L2 skill | Named invocation, no re-planning |
| Hard policy constraint | L3 rule | Zero-latency, auditable |
| First occurrence of a pattern | L1 episodic | Gather evidence before committing |
| Pattern seen 3+ times | L2 skill candidate | Promote after validation |
| L2 skill validated in 20+ cases | L3 rule candidate | Requires human review |

### The architecture in code

```python
from dataclasses import dataclass
from enum import IntEnum
from typing import Any
import time

class CompressionLevel(IntEnum):
    L0_RAW_TRACE = 0   # 1:1 — full fidelity, no compression
    L1_EPISODIC  = 1   # 5-20x — event summaries
    L2_SKILL     = 2   # 50-500x — named procedures
    L3_RULE      = 3   # 1000x+ — declarative constraints

@dataclass
class KnowledgeArtifact:
    content: Any           # The compressed representation
    level: CompressionLevel
    compression_ratio: float
    provenance: dict       # Original trace ID(s), timestamp, source session
    confidence: float      # How much the agent "believes" this is correct
    staleness: float       # 0.0 = fresh, 1.0 = likely stale
    promotion_candidates: list[CompressionLevel]  # Levels this could move to

class ExperienceCompressionManager:
    """
    Manages the compression spectrum for an agent.
    Each boundary has its own governance logic.
    """

    def __init__(self, llm, drift_detector, poisoning_filter):
        self.llm = llm
        self.drift_detector = drift_detector      # SSGM: semantic drift monitor
        self.poisoning_filter = poisoning_filter  # SSGM: poisoning gate at L0→L1

    def ingest(self, raw_trace: list[dict]) -> KnowledgeArtifact:
        """
        L0 → L1: Input ingestion with poisoning check.
        This is where memory poisoning happens (SSGM failure point 1).
        """
        filtered_trace = self.poisoning_filter.scrub(raw_trace)
        summary = self.llm.summarize(
            filtered_trace,
            format="episodic",
            max_tokens=200
        )
        provenance = {
            "original_trace_ids": [e["id"] for e in filtered_trace],
            "ingested_at": time.time(),
            "compression_ratio": len(filtered_trace) / max(1, summary.count(" ")),
        }
        return KnowledgeArtifact(
            content=summary,
            level=CompressionLevel.L1_EPISODIC,
            compression_ratio=provenance["compression_ratio"],
            provenance=provenance,
            confidence=self._calibrate(summary, filtered_trace),
            staleness=0.0,
            promotion_candidates=[CompressionLevel.L2_SKILL],
        )

    def promote_to_skill(self, episodic: KnowledgeArtifact) -> KnowledgeArtifact:
        """
        L1 → L2: Episodic → Procedural Skill.
        This is where semantic drift accumulates (SSGM failure point 2).
        """
        if episodic.level != CompressionLevel.L1_EPISODIC:
            raise ValueError(f"Cannot promote {episodic.level.name} to skill")

        # Drift check before promotion
        drift_score = self.drift_detector.score(
            episodic.provenance["original_trace_ids"]
        )
        if drift_score > 0.7:
            raise DriftDetected(
                f"Semantic drift score {drift_score:.2f} exceeds threshold. "
                "Demote conflicting episodes before promoting."
            )

        skill = self.llm.extract_procedure(
            episodic.content,
            name=self._derive_skill_name(episodic),
            tool_bindings=self._extract_tool_calls(episodic),
        )
        return KnowledgeArtifact(
            content=skill,
            level=CompressionLevel.L2_SKILL,
            compression_ratio=500.0,
            provenance=episodic.provenance,
            confidence=episodic.confidence * 0.9,  # Compression loses nuance
            staleness=0.0,
            promotion_candidates=[CompressionLevel.L3_RULE],
        )

    def promote_to_rule(self, skill: KnowledgeArtifact) -> KnowledgeArtifact:
        """
        L2 → L3: Skill → Declarative Rule.
        This is where conflicting skills create contradiction (SSGM failure point 3).
        Human review gate before this step — rules are hard to undo.
        """
        if skill.level != CompressionLevel.L2_SKILL:
            raise ValueError(f"Cannot promote {skill.level.name} to rule")

        # Conflict check: does this rule contradict an existing rule?
        conflicts = self._find_rule_conflicts(skill)
        if conflicts:
            raise RuleConflictError(
                f"Skill conflicts with existing rules: {conflicts}. "
                "Demote conflicting rules or add conditional overrides before proceeding."
            )

        return KnowledgeArtifact(
            content=skill.content,  # Rule is the same content, different semantics
            level=CompressionLevel.L3_RULE,
            compression_ratio=1000.0,
            provenance=skill.provenance,
            confidence=skill.confidence * 0.85,  # Rules are most brittle
            staleness=0.0,
            promotion_candidates=[],
        )

    def demote(self, artifact: KnowledgeArtifact, reason: str) -> KnowledgeArtifact:
        """
        Reverse promotion: L3 → L2, L2 → L1.
        Triggered by drift detection, conflict resolution, or policy changes.
        """
        if artifact.level == CompressionLevel.L0_RAW_TRACE:
            raise ValueError("Cannot demote raw traces")

        new_level = CompressionLevel(artifact.level - 1)
        return KnowledgeArtifact(
            content=artifact.content,  # Content stays; semantics change with level
            level=new_level,
            compression_ratio=artifact.compression_ratio * 0.2,  # Demotion = expand
            provenance={**artifact.provenance, "demoted_at": time.time(), "reason": reason},
            confidence=artifact.confidence * 0.95,  # Slight degradation on demotion
            staleness=1.0,  # Just demoted — mark as needing fresh evaluation
            promotion_candidates=[CompressionLevel(artifact.level)],  # Can re-promote
        )

    def retrieve(self, query: str, level: CompressionLevel | None = None) -> list[KnowledgeArtifact]:
        """
        Retrieve at a specific level or across all levels.
        L3 rules always returned (zero-latency lookup).
        L0 traces never returned in normal retrieval (forensic only).
        """
        results = []
        # Always check rules — they're hard constraints
        if level is None or level == CompressionLevel.L3_RULE:
            results.extend(self.rule_store.query(query))

        if level is None or level == CompressionLevel.L2_SKILL:
            results.extend(self.skill_store.similarity_search(query))

        if level is None or level == CompressionLevel.L1_EPISODIC:
            results.extend(self.episodic_store.semantic_search(query))

        return sorted(results, key=lambda a: a.level, reverse=True)

    def _calibrate(self, summary: str, trace: list[dict]) -> float:
        """Estimate confidence that compression preserved meaning."""
        key_events = [e for e in trace if e.get("type") == "tool_call"]
        summary_events = summary.count("tool:")
        return min(1.0, summary_events / max(1, len(key_events)))

    def _derive_skill_name(self, episodic: KnowledgeArtifact) -> str:
        return self.llm.extract("""
            From this episodic summary, derive a short camelCase skill name.
            Example: "Billing escalation workflow" → "billingEscalationWorkflow"
        """)

    def _extract_tool_calls(self, episodic: KnowledgeArtifact) -> list[str]:
        return self.llm.extract(episodic.content, format="tool_sequence")
```

## Receipt

> Verified 2026-07-20 — arXiv:2604.15877v2 (Zhang et al., Jun 25 2026) confirms the four-level spectrum with compression ratios. SSGM failure taxonomy (arXiv:2603.11768v2, Lam et al., May 2026) confirms all three boundary failure points. The <1% cross-community citation rate is from the ECS paper's own literature review — not independently verified but internally consistent with the observed siloing between memory systems (CS/IR venues) and skill discovery (ML/RL venues) research communities. The 68.5pp performance gain figure and 1,000×+ compression ratio for L3 are from the paper's evaluation section. Code example is functional skeleton — not run against a live agent.

## See also

- [S-09 · Memory Systems](s09-memory-systems.md) — the three cognitive types that map to L1/L2
- [S-100 · Agentic RAG](s100-agentic-rag.md) — retrieval patterns that feed into L1 episodic memory
- [S-1416 · The Multi-Agent Memory Architecture Stack](s1416-the-multi-agent-memory-architecture-stack-when-your-agents-cant-agree-on-what-happened.md) — shared memory across agent fleets; orthogonal concern that the spectrum helps architect
