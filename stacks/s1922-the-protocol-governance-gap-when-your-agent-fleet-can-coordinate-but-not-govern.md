# S-1922 · The Protocol Governance Gap — When Your Agent Fleet Can Coordinate But Not Govern

You have three agents: a researcher, a reviewer, and an executor. MCP lets the researcher call tools. A2A lets the researcher hand off to the reviewer. ACP lets them negotiate a plan. But now the reviewer disagrees with the executor's risk assessment. Who decides? No protocol answers that. You built the coordination layer — you're now staring at the governance void above it.

## Forces

- **Coordination ≠ governance.** MCP/A2A/ACP all answer "which agent can do this?" and "how do they exchange messages?" — none answer "who has the authority to decide?" or "what happens when agents disagree?"
- **Enterprise agent fleets need community governance.** YC 2026 data shows a median of 37 agents per company. When heterogeneous agents from different vendors must collectively decide — approve a transaction, retire a knowledge artifact, allocate a shared resource — you need primitives none of these protocols provide.
- **The gap is structural, not a missing feature.** Voting, deliberation, dissent preservation, and structured human escalation are not absent from the current protocol specs — they are architecturally impossible within them. You cannot patch this in; you must build the layer above.
- **The NSA flagged MCP's security model** in late 2025, and the EU AI Act is moving autonomous decision authority into compliance scope — both pressures are pushing governance from "nice to have" to "deployable only if."

## The Move

The six missing dimensions from the governance taxonomy (Kang & Diponegoro, arXiv:2606.31498, June 2026):

| Dimension | Coordination Answer | Governance Gap |
|-----------|---------------------|----------------|
| Membership | "Who is in the network?" | No protocol encodes admission, role assignment, or removal |
| Deliberation | "Messages exchanged" | No structured debate or argument exchange before a decision |
| Voting | N/A | **Universally absent** across MCP, A2A, ACP, ANP, ERC-8004 |
| Dissent preservation | N/A | **Universally absent** — minority opinions are not recorded |
| Human escalation | N/A | No structured trigger for human review of a collective decision |
| Audit/replay | N/A | No mechanism for reconstructing why a decision was made |

**The fix: build a governance layer above your protocol stack.**

```
Governance Layer (you build this)
    ├── Membership registry (who participates in each decision)
    ├── Deliberation channel (structured argument exchange)
    ├── Voting primitive (majority / weighted / conviction-based)
    ├── Dissent log (minority opinions preserved for review)
    ├── Escalation gate (route to human reviewer on threshold breach)
    └── Decision ledger (append-only audit trail)
            │
    ┌───────┴───────┐
    ▼               ▼
  MCP/A2A/ACP   Tool calls & task handoff
  (coordination)  (execution)
```

**The practical pattern: governance by contract.**

Every inter-agent agreement that crosses a risk threshold carries a governance manifest:

```python
@dataclass
class GovernanceManifest:
    task_id: str
    participants: list[str]              # agent IDs or roles
    decision_rule: str                   # "majority", "weighted:compliance=3,specialist=1"
    dissent_log: list[DissentEntry]      # captured minority opinions
    escalation_threshold: float          # e.g., risk_score > 0.7
    escalation_route: str               # "human:compliance-team"
    decision_ledger_entry: str          # immutable audit ID

    def record_dissent(self, agent_id: str, reason: str, risk_delta: float):
        self.dissent_log.append(DissentEntry(agent_id, reason, risk_delta))
        if risk_delta > self.escalation_threshold:
            raise EscalationRequired(
                f"Risk delta {risk_delta} exceeds threshold {self.escalation_threshold}. "
                f"Routed to {self.escalation_route}."
            )

    def vote(self, votes: dict[str, str]) -> DecisionRecord:
        tally = Counter(votes.values())
        outcome = tally.most_common(1)[0][0]
        return DecisionRecord(
            task_id=self.task_id,
            outcome=outcome,
            votes=votes,
            dissent_log=deepcopy(self.dissent_log),
            ledger_id=self._append_to_ledger(outcome),
        )
```

**Three governance patterns from 2026 production systems** (CallSphere, June 2026):

1. **Jury voting** — N specialist agents independently assess, vote blind, majority wins. Cost: N × 1 inference. Best when quality > speed and you need defensible decisions.
2. **Debate** — agents see each other's positions before voting. Cost: N × M turns. Best when reasoning transparency matters for downstream trust.
3. **Conviction voting** — agents accumulate voting power over time based on track record. Cost: weighted inference. Best for continuous governance of long-running agent communities.

**Implement governance at the protocol boundary, not inside individual agents.** The governance layer intercepts before a handoff completes, not after an agent has already acted.

## Receipt

> Verified 2026-07-31 — Pattern extracted from arXiv:2606.31498v1 (Kang & Diponegoro, June 2026), CallSphere blog "Consensus Mechanisms for Agent Teams" (June 2026), and tutorialQ Agentic AI Landscape 2026.

## See also

- [S-1000 · Structural Agent Governance](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — single-agent governance enforcement vs. prompt-based approaches
- [S-1040 · The Protocol Gap](s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — MCP/A2A coordination, the layer below this entry
- [S-1853 · The Handoff Contract Stack](s1853-the-handoff-contract-stack-when-your-agent-hands-off-without-passing-proof.md) — provenance and attestation at individual handoff level
