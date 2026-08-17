# S-280 · The Lossy Hand-Off Stack — When Your Agents Communicate but Your System Loses

Your five-agent pipeline passes every integration test. Each agent's individual eval is green. Then production reveals the planner agent decided to cancel an order based on a billing flag, the billing agent received only "flag raised" without the flag's context, and shipped the wrong decision to the fulfillment agent — which acted on it. Three agents, zero errors, one disaster.

The failure wasn't in any agent. It was in the seam between them.

## Forces

- **Every hand-off is lossy compression.** An agent's full working state — what it knows, what it tried, what it is uncertain about — cannot be fully transferred in a message. The recipient reconstructs intent from surface tokens. At each boundary, information degrades.
- **LLMs hallucinate confidence on uncertain information.** Uncertain guesses get packaged with the same JSON shape as confirmed facts. A `billing_flag: "raised"` from a failing API lookup looks identical to `billing_flag: "confirmed"`. The downstream agent has no basis to treat them differently.
- **Cross-boundary constraints decay asymmetrically.** Commission constraints (things the agent *must* do) hold under context pressure. Omission constraints (things the agent *must not* do) decay — prohibition compliance drops from ~100% at turn 5 to ~33% at turn 16 in susceptible models (arXiv:2604.20911, 4,416 trials across 12 models). When an agent hands off to another, this decay profile may shift depending on how constraints are encoded in the message.
- **Semantic drift compounds across depth.** Same words mean different things to different agents. The planner's "escalate" means "pause and request human review." The executor's "escalate" means "retry with higher priority." Without shared terminology encoding, the handoff silently changes intent.
- **Coordination tax punishes completeness.** Carrying every context signal forward causes quadratic token growth in deep pipelines. Agents are incentivized to compress aggressively, which maximizes lossy behavior at exactly the points where fidelity matters most.

## The move

**Encode the hand-off as a typed, versioned contract — not a freeform message.**

- **Distinguish confirmed vs. inferred.** Every field in a hand-off message should carry its provenance: `source: "api_call"`, `source: "llm_inference"`, `source: "heuristic"`. Flag inferred fields with a confidence weight. Downstream agents can then apply appropriate skepticism — and routes can enforce that critical paths require minimum confidence thresholds.

```json
{
  "task_id": "ORD-48291",
  "handoff_version": "1.2",
  "provenance": {
    "billing_flag": {
      "source": "api_call",
      "endpoint": "/billing/v2/orders/{id}/flags",
      "status": 200,
      "confidence": 1.0
    },
    "customer_tier": {
      "source": "llm_inference",
      "prompt": "derived_from_order_history",
      "confidence": 0.73
    },
    "urgency": {
      "source": "heuristic",
      "rule": "premium_flag_if_balance_gt_5000",
      "confidence": 0.91
    }
  }
}
```

- **Encode constraint state explicitly.** Don't rely on system-prompt carry-over. Pass active prohibitions and requirements as structured metadata: `active_constraints: { "do_not_refund": false, "require_human_for_cancellation": true }`. This is especially critical for agents operating under Security-Recall Divergence conditions — explicit constraints survive context pressure that would erode implicit ones.
- **Typed failure receipts.** When an agent encounters an error it cannot resolve, the handoff message must include what was tried, what failed, and the error type — not just a status code. The downstream agent can then skip already-failed approaches rather than rediscovering failure modes.

```python
@dataclass
class HandoffReceipt:
    task_id: str
    version: str
    provenance: dict[str, ProvenanceEntry]
    active_constraints: dict[str, bool]
    attempts: list[AttemptRecord]  # what was tried, outcome, error if any
    pending_clarifications: list[str]  # things the sender was uncertain about

    def is_above_confidence_floor(self, threshold: float = 0.7) -> bool:
        low_conf = [k for k, v in self.provenance.items()
                    if v.confidence < threshold]
        return len(low_conf) == 0
```

- **Shared intent vocabulary.** Define a hand-off glossary per pipeline. "Escalate," "retry," "pause," and "abort" must have unambiguous definitions in the schema — not just in the system prompts. When the schema and the prompt diverge, the schema wins in production.
- **Coordination budget, not just token budget.** Track hand-off fidelity as a first-class metric. At each handoff, measure: fields that changed meaning (semantic drift), fields dropped below confidence floor, and constraints missing from the receipt. Alert on degradation trends, not just absolute cost or latency.
- **Fail loudly at the seam.** A hand-off that fails the provenance or confidence floor check should not silently proceed. Route to a reconciliation agent or human reviewer — do not let lossy handoffs propagate to downstream action.

## Receipt

> Verified 2026-08-16 — Research from: Cognilium AI "Multi-Agent Hand-Offs: Why Context Gets Lost Between Agents" (July 2026, 2,172 words), arXiv:2604.20911 "Omission Constraints Decay While Commission Constraints Persist in Long-Context LLM Agents" (Gamage, USF, Apr 2026, 4,416 trials, 12 models, 8 providers, CC BY 4.0), arXiv:2605.01604 "Evaluating Agentic AI in the Wild" (Pandey, May 2026, 7 production failure modes, billion-event scale), TheCodeForge "$40k A2A handshake failure" (partial handshake = HEARTBEAT/DISCOVERY state mismatch, 15% dropped tasks from heartbeat interval mismatch), linesncircles.com "60% of agentic AI pilots fail" (root cause: automation illusion, architectural redesign needed). Deduplication: S-986 (coordination breakdown) covers architectural state inconsistency and shared-state failures; this entry covers information degradation at hand-off seams — lossiness, semantic drift, confidence laundering, and asymmetric constraint decay across boundaries. No existing entry covers the typed provenance-contract pattern.

## See also

- [S-986 · The Coordination Breakdown Pattern](s986-the-coordination-breakdown-pattern-when-your-multi-agent-system-is-its-own-worst-enemy.md) — shared-state failures and temporal gaps between agents
- [S-1340 · The Spend Guardrail Stack](s1340-the-spend-guardrail-stack-when-your-01-request-costs-5000.md) — cost explosion from unchecked multi-agent loops
- [S-14 · A2A Protocol](s14-a2a-protocol.md) — the agent-to-agent protocol layer where hand-offs actually happen
