# [S-2899] · The Multi-Agent Consensus Arbitration Stack — When Your Agents Vote on Wrong and Nobody Is In Charge

Multi-agent systems let agents disagree productively — until the disagreement becomes the product. You have three agents analyzing a financial transaction. Two say refund, one says escalate to fraud. Majority vote ships the refund. Three days later, the fraud team asks why you auto-approved a known chargeback pattern. The vote was legitimate. The answer was wrong. Nobody was in charge of knowing why.

## Forces

- **Naive voting amplifies shared blind spots.** Agents trained on overlapping data, similar RLHF pipelines, and shared context share systematic blind spots too. Majority vote doesn't cancel errors — it concentrates them into a confident consensus. Studies show 23.9% of disputed questions converge to unanimous wrong answers by round 3.
- **Disagreement type determines resolution strategy.** A stylistic disagreement (same answer, different format) is trivially mergeable. A factual disagreement requires evidence. A reasoning disagreement requires tracing the logic chain. A calibration disagreement (same data, different confidence thresholds) requires a shared reference. Throwing a LLM judge at every disagreement inherits twelve documented bias types.
- **Agents that share context lose independent judgment.** Once Agent B sees Agent A's answer, B's vote is no longer independent. LLM conformity bias means later votes cluster toward earlier ones regardless of merit.
- **There's always a "tie goes to..." problem.** When arbitration is needed, someone must hold the tie-breaking authority. In distributed agent systems, this authority is often undeclared — which means it goes to whoever speaks last or loudest.

## The Move

Classify the disagreement type first. Then route to the correct resolution:

| Type | Signal | Resolution |
|------|--------|------------|
| **Stylistic** | Same substance, different format | Safe to merge — auto-synthesize |
| **Factual** | Different claims about the world | Evidence anchor: external source, database, tool call |
| **Reasoning** | Same facts, different logic chain | Trace both chains to divergence point; surface to human |
| **Calibration** | Same answer, different confidence | Shared confidence reference or statistical baseline |
| **Competency** | One agent lacks domain capability | Capability-aware routing; escalate to specialist |
| **Competing** | Goals actually conflict | Escalate to binding arbitration (human or policy engine) |

Then implement a three-tier arbitration protocol:

**Tier 1 — Self-resolution.** Agents exchange disagreement type tags, not answers. Style differences merge automatically. Factual differences defer to a shared evidence source. Nothing else proceeds to Tier 2.

**Tier 2 — Binding arbitration.** A designated arbiter agent — structurally different from the disagreeing agents (different model, different context) — receives the disagreement type and supporting evidence, not the raw outputs. The arbiter decides, not votes. Its decision is binding for non-escalation cases (cost below threshold, no policy implications).

**Tier 3 — Human escalation.** Competency disagreements, competing goals, and cost/policy threshold breaches route to a human decision-maker with the full disagreement trace. The human sees: what each agent saw, why they disagree, what each proposes — not just the final vote.

The key architectural constraint: agents must declare their disagreement type before sharing outputs. Once outputs are shared, independence is compromised. Design the handoff protocol so that disagreement is surfaced before evidence is pooled.

```python
from enum import Enum
from dataclasses import dataclass
from typing import Protocol, Optional

class DisagreementType(Enum):
    STYLISTIC = "style"
    FACTUAL = "factual"
    REASONING = "reasoning"
    CALIBRATION = "calibration"
    COMPETENCY = "competency"
    COMPETING = "competing"  # goals actually conflict

@dataclass
class AgentOutput:
    agent_id: str
    answer: str
    confidence: float
    reasoning_chain: list[str]
    evidence_refs: list[str]
    disagreement_type: Optional[DisagreementType] = None

@dataclass
class ArbitrationResult:
    winner: AgentOutput
    loser: Optional[AgentOutput]
    reason: str
    binding: bool
    escalated_to: Optional[str] = None

class ConsensusArbiter:
    def __init__(self, escalation_threshold: float = 0.85):
        self.escalation_threshold = escalation_threshold
        self.human_policy_agents = {"COMPETING", "COMPETENCY"}

    def arbitrate(self, outputs: list[AgentOutput]) -> ArbitrationResult:
        # Step 1: Classify disagreement type (agents self-classify first)
        types = [o.disagreement_type for o in outputs if o.disagreement_type]
        disagreement = types[0] if types else self._classify(outputs)

        # Step 2: Route by type
        if disagreement == DisagreementType.STYLISTIC:
            return self._merge_styles(outputs)

        if disagreement == DisagreementType.FACTUAL:
            return self._resolve_factual(outputs)

        if disagreement in self.human_policy_agents:
            return self._escalate_human(outputs, disagreement)

        # Default: binding arbiter with confidence-weighted evidence
        return self._binding_arbitrate(outputs)

    def _classify(self, outputs: list[AgentOutput]) -> DisagreementType:
        # Structural classifier — compares reasoning chains, not answers
        if len(set(o.answer for o in outputs)) == 1:
            return DisagreementType.STYLISTIC
        confidence_spread = max(o.confidence for o in outputs) - min(o.confidence for o in outputs)
        if confidence_spread > 0.3:
            return DisagreementType.CALIBRATION
        return DisagreementType.REASONING

    def _escalate_human(self, outputs: list[AgentOutput], dtype: DisagreementType) -> ArbitrationResult:
        return ArbitrationResult(
            winner=outputs[0],
            loser=outputs[1] if len(outputs) > 1 else None,
            reason=f"{dtype.value} disagreement requires human arbitration",
            binding=False,
            escalated_to="human_review_queue"
        )

    def _binding_arbitrate(self, outputs: list[AgentOutput]) -> ArbitrationResult:
        # Weight by confidence * evidence_count (not confidence alone)
        scores = {o.agent_id: o.confidence * (1 + len(o.evidence_refs) * 0.1) for o in outputs}
        winner_id = max(scores, key=scores.get)
        winner = next(o for o in outputs if o.agent_id == winner_id)
        loser = next((o for o in outputs if o.agent_id != winner_id), None)
        return ArbitrationResult(
            winner=winner,
            loser=loser,
            reason=f"Evidence-weighted arbitration: {scores[winner_id]:.3f} vs {scores[loser.agent_id]:.3f}",
            binding=True
        )
```

## Receipt

> Verified 2026-08-20 — Taxonomy and resolution strategy from Tian Pan's "When Your Agents Disagree" (April 2026), arXiv consensus research (Käesberg et al., 2025 on Voting vs Consensus in Multi-Agent Debate), and Zylos Research Specification Gaming report (June 2026). Code is a working pattern sketch — instantiate with actual agent outputs from your orchestration layer. The core insight — classify before sharing answers — is implementable in any multi-agent framework (CrewAI, LangGraph, Mastra, ADK) as a pre-handoff gate.

## See also

- [S-1559 · The Structured Debate Stack](s1559-the-structured-debate-stack-when-your-multi-agent-panel-confidently-agrees-on-wrong-answers.md) — debate panel design; this entry covers what happens when debate fails
- [S-2441 · The Cascade Amplification Stack](s2441-the-cascade-amplification-stack-when-one-agents-wrong-output-becomes-everyones-ground-truth.md) — cascade risk from confident wrong consensus
- [S-1286 · The Handoff Contract](s1286-the-handoff-contract-when-your-agent-hands-off-work-and-the-context-goes-missing.md) — handoff integrity; disagreement is a handoff failure mode
