# [S-1171] · The Claim Provenance Stack — When One False Claim Becomes Team Consensus in 3 Rounds

You deployed a multi-agent pipeline. Architect → Developer → Reviewer → QA. The architect misread the requirements and suggested SQLite for the caching layer. Three rounds later, the entire system is built around SQLite, the review passed, QA signed off, and the sprint demo crashes on concurrent reads. One error, silently propagated and amplified through each handoff, until it became unanimous.

This is not a model hallucination. This is a structural failure of the collaboration architecture.

## Forces

- Multi-agent pipelines compound trust through repetition — each agent sees a claim that was already validated by a peer
- Messages carry semantic weight, not just data — a claim that survives one review is treated as harder to question
- Existing safeguards (circuit breakers, typed schemas, error thresholds) protect against crashes and timeouts, not against confidently wrong shared beliefs
- Adding more agents for "redundancy" makes this worse, not better — more validators mean faster false consensus

## The move

**Track claim provenance through the agent graph, and give each agent the ability to query a claim's lineage before acting on it.**

### 1. Model error cascades as a three-class vulnerability

Research across six frameworks (AutoGen, CrewAI, LangChain, LangGraph, MetaGPT, CAMEL) identified three distinct failure modes:

**Cascade amplification** — A single atomic error grows at each hop. The agent who receives the wrong output doesn't just fail; it produces downstream outputs that are themselves confidently wrong, and those get validated by the next agent in the chain.

**Topological sensitivity** — The shape of the agent graph determines how fast and how far errors spread. Fully connected graphs (all agents message all others) amplify fastest. Sequential pipelines (handoff chains) amplify slowest but most persistently — the error survives all stages because each stage trusts the prior stage.

**Consensus inertia** — Agents trained on large corpora have baked-in tendencies toward majority-aligned outputs. When multiple agents independently produce similar outputs, this signals "this is correct" even when all of them started from the same false premise. Self-consistency checks (S-24) rescue you when the model is usually right, but they *confirm the error* when the model is usually wrong, because conformity is also a learned behavior.

### 2. Build a claim genealogy graph

Every factual claim an agent produces is a node. Every time another agent acts on that claim (adopts it as context, builds on it, or validates it), that's an edge.

```python
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class ClaimStatus(Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNCERTAIN = "uncertain"

@dataclass
class Claim:
    id: str
    text: str
    source_agent: str
    source_turn: int
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    lineage: list[str] = field(default_factory=list)  # parent claim IDs
    supporting_evidence: list[str] = field(default_factory=list)
    adopted_by: list[str] = field(default_factory=list)  # agent IDs

class ProvenanceMiddleware:
    """Track claim provenance across agent handoffs.
    
    Wraps the message-passing layer. Before any agent acts on
    a claim, it can query lineage and confidence.
    """
    
    def __init__(self):
        self.claims: dict[str, Claim] = {}
        self.claim_counter = 0
    
    def register_claim(
        self, agent_id: str, text: str, parent_ids: list[str] = None
    ) -> str:
        claim_id = f"claim_{self.claim_counter}"
        self.claim_counter += 1
        self.claims[claim_id] = Claim(
            id=claim_id,
            text=text,
            source_agent=agent_id,
            source_turn=self.claim_counter,
            lineage=parent_ids or [],
        )
        return claim_id
    
    def adopt_claim(self, claim_id: str, adopting_agent: str) -> None:
        if claim_id in self.claims:
            self.claims[claim_id].adopted_by.append(adopting_agent)
    
    def get_lineage_depth(self, claim_id: str) -> int:
        """Count how many hops from the root claim.
        Deeper lineage = higher contamination risk."""
        if claim_id not in self.claims:
            return 0
        return len(self.claims[claim_id].lineage)
    
    def get_adoption_count(self, claim_id: str) -> int:
        return len(self.claims.get(claim_id, Claim("", "", "", 0)).adopted_by)
    
    def should_flag(self, claim_id: str, depth_threshold: int = 3,
                    adoption_threshold: int = 2) -> bool:
        """Flag claims that are deep in lineage AND widely adopted.
        These are high-risk consensus anchors."""
        if claim_id not in self.claims:
            return False
        claim = self.claims[claim_id]
        return (
            len(claim.lineage) >= depth_threshold
            and len(claim.adopted_by) >= adoption_threshold
            and claim.status == ClaimStatus.UNVERIFIED
        )
    
    def trace_lineage(self, claim_id: str) -> list[Claim]:
        """Walk back to root claims. High-value for RCA."""
        if claim_id not in self.claims:
            return []
        result = []
        visited = set()
        queue = [self.claims[claim_id]]
        while queue:
            claim = queue.pop(0)
            if claim.id in visited:
                continue
            visited.add(claim.id)
            result.append(claim)
            for parent_id in claim.lineage:
                if parent_id in self.claims and parent_id not in visited:
                    queue.append(self.claims[parent_id])
        return result
```

### 3. Integrate at the message-passing layer

The middleware intercepts all inter-agent messages. Extract factual claims, register them, and annotate messages with provenance metadata:

```python
class AnnotatedAgent:
    """Wrapper that adds provenance headers to agent outputs."""
    
    def __init__(self, agent_id: str, llm, provenance: ProvenanceMiddleware,
                 claim_extractor, max_lineage_depth: int = 5):
        self.agent_id = agent_id
        self.llm = llm
        self.provenance = provenance
        self.claim_extractor = claim_extractor  # LLM or rule-based claim extraction
        self.max_lineage_depth = max_lineage_depth
    
    def send_message(self, content: str, context_claims: list[str] = None) -> dict:
        """Send a message with embedded provenance trace."""
        # Extract claims from the message
        new_claims = self.claim_extractor.extract(content)
        claim_ids = []
        for claim_text in new_claims:
            cid = self.provenance.register_claim(
                agent_id=self.agent_id,
                text=claim_text,
                parent_ids=context_claims or [],
            )
            claim_ids.append(cid)
        
        # Flag if this message builds on deep, widely-adopted unverified claims
        for cid in (context_claims or []):
            self.provenance.adopt_claim(cid, self.agent_id)
            if self.provenance.should_flag(cid):
                self._escalate_to_human(cid)
        
        return {
            "content": content,
            "claim_ids": claim_ids,
            "context_lineage": [
                {
                    "claim_id": cid,
                    "depth": self.provenance.get_lineage_depth(cid),
                    "adoptions": self.provenance.get_adoption_count(cid),
                    "text": self.provenance.claims[cid].text,
                }
                for cid in (context_claims or [])
            ],
        }
    
    def _escalate_to_human(self, claim_id: str) -> None:
        lineage = self.provenance.trace_lineage(claim_id)
        print(f"[PROVENANCE ALERT] Claim '{self.provenance.claims[claim_id].text}' "
              f"was adopted {len(lineage)} hops deep with no verification. "
              f"Escalating for human review.")
```

### 4. Evaluation metric: Genealogy Accuracy (GA)

The paper's key metric. Rather than just measuring whether the final output is correct, measure whether the system correctly identifies which claims propagated from which sources.

```
GA = (# of claims where attributed source is correct) / (# of claims evaluated)
```

Speed mode (fast genealogy, approximate): +57% tokens, +50% latency.
Strict mode (full trace + verification): +400% tokens, +100% latency.

Speed mode gives the best defense-per-token ratio for most production use cases.

## Receipt

> Verified 2026-07-16 — "From Spark to Fire" (Xie et al., arXiv:2603.04474, v2 May 2026) is the primary source. Blog summary at danilchenko.dev confirms: 5 of 6 frameworks (AutoGen, CrewAI, LangChain, LangGraph, MetaGPT, CAMEL) reached 100% false claim adoption within 3 rounds. Genealogy graph middleware raised cascade defense from 32% to 89%. Three vulnerability classes: cascade amplification, topological sensitivity, consensus inertia. GA metric introduced in the paper.

## See also

- [S-29 · False Consensus](s29-false-consensus.md) — correlated failure through majority vote; same root cause, different manifestation
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — typed handoff schemas catch cascade triggers before they propagate
- [S-1022 · The Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — behavioral degradation from drift; provenance tracking surfaces drift provenance
- [S-1089 · The Orchestration Model Stack](s1089-the-orchestration-model-stack-when-chaining-llm-calls-stops-working.md) — typed handoff schemas as non-negotiable cascade prevention
