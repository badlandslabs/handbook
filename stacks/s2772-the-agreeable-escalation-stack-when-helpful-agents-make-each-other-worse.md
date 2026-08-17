# S-2772 · The Agreeable Escalation Stack — When Helpful Agents Make Each Other Worse

Your A2A procurement agent and the vendor's pricing agent are negotiating a contract. Both are designed to be helpful and collaborative — that's the point. Your agent advocates for the best terms. Their agent does the same. After twelve rounds of messaging, your agent has committed to 14 concessions. Their agent has committed to 11. Neither has moved closer to agreement — they've each escalated to their principal's maximum position. Neither can back down without betraying their mandate. This is **agreeable escalation**: agents trained to be cooperative getting trapped in mutual reinforcement loops that amplify rather than resolve disagreement.

## Forces

- **Helpfulness and assertiveness are not opposites in negotiation.** When two agents serve different principals (buyer/seller, employer/candidate, insurer/claimant), both "helpful" behaviors — advocating strongly for your side, holding firm on your position, not conceding without return — compound destructively. Each concession from agent A looks like a signal to agent B that there's more to extract, prompting B to hold firmer. The agents are doing exactly what they were designed to do. The outcome is worse than if either had been less cooperative.

- **A2A removes human intervention by design.** The value proposition of A2A is autonomous agent-to-agent commerce: agents that negotiate, hire, contract, and resolve disputes without human review. This removes the safety valve that human judgment provides — a human negotiator recognizes the other party has hit their limit and pivots to closing; an agent continues optimizing for its principal until it hits a hard constraint.

- **LLMs are trained to be agreeable and responsive — not to recognize coordinated manipulation.** The training objective for helpfulness rewards the model for maintaining the conversation, acknowledging the other party's points, and producing coherent responses. None of these behaviors are negotiation-negative in isolation. In a two-agent loop, they become amplification signals: acknowledgment = validation = escalate.

- **Agents lack objective commitment points.** In human negotiation, parties signal willingness to walk away through body language, phrasing, or explicit statements. Agents have none of these signals. The protocol doesn't carry commitment thresholds. Without explicit stop conditions encoded in the negotiation protocol, agents have no signal that the other party has reached their limit — they only see the messages they receive.

## The move

**Encode explicit commitment boundaries into the negotiation protocol before deployment.** The failure is architectural, not prompt-level. You cannot fix it by telling the agent to "be less aggressive" — that's antithetical to its purpose.

Three concrete mechanisms:

### 1. Commitment ledger with decrementing budget
Each agent maintains a finite concession budget. Every concession decrements it. When the budget reaches zero, the agent transitions to a terminal state: `ACCEPT`, `WALK_AWAY`, or `ESCALATE_TO_HUMAN`. The protocol carries the budget state in message metadata, so both agents can see when the other is running low.

```
class NegotiationState:
    concession_budget: int        # starts at N
    hard_floor: float             # below this, no concession possible
    escalation_threshold: int    # N remaining → trigger human review
    terminal_states: list[str]    # ACCEPT | WALK_AWAY | ESCALATE

def make_concession(state: NegotiationState, proposed: float, last_offer: float) -> Message:
    if state.concession_budget <= 0:
        return Message(state=TerminalState.ESCALATE_TO_HUMAN, reason="budget_exhausted")
    delta = last_offer - proposed
    if proposed < state.hard_floor:
        return Message(state=TerminalState.WALK_AWAY, reason="below_hard_floor")
    state.concession_budget -= 1
    return Message(state=State.CONTINUE, offer=proposed, budget_remaining=state.concession_budget)
```

### 2. Structured offer-and-response protocol (not free-form)
Replace free-form agent-to-agent messaging with a constrained protocol: `OFFER`, `COUNTER`, `ACCEPT`, `REJECT`, `WALK_AWAY`. Each message type has strict semantics. Agents cannot deviate into narration, reassurance, or partial commitment — all of which are interpreted by the counterparty as softening.

```
# A2A negotiation protocol (constrained variant)
AGENT_MESSAGE_TYPES = ["OFFER", "COUNTER", "ACCEPT", "REJECT", "WALK_AWAY", "ESCALATE"]
# OFFER: { value: float, expires_in_turns: int }
# COUNTER: { value: float, rationale: str, expires_in_turns: int }
# ACCEPT: { value: float }  # binding
# REJECT: {}  # closes negotiation
# WALK_AWAY: { reason: str }  # final, no further messages
# ESCALATE: { reason: str, context: dict }  # pauses for human review
```

### 3. Simulated counterparty for pre-deployment stress testing
Before deploying any negotiation agent, run it against a simulated adversary that models escalation behavior. The simulation should include: (a) a mirror agent that matches every concession with a counter-demand, (b) a strategic adversary that intentionally signals weakness to trigger over-commitment, (c) a silent agent that accepts immediately — to verify your agent doesn't misinterpret acceptance as a trap. Run 200+ negotiation episodes in simulation before production.

## Receipt

> Verified 2026-08-17 — Framework described is derived from Salesforce AI Research "A2A Semantic Layer" (Savarese & Earle, November 2025) documenting the "echoing" failure mode in agent-to-agent negotiation, and NHI Governance's analysis of A2A v1.0 delegation semantics (reviewed August 2026). The commitment ledger and structured protocol patterns are architectural recommendations consistent with Cerbos A2A integration guidance and NHI Governance's monotonic scope narrowing principle. Specific code examples are illustrative — concrete implementations vary by A2A framework.

## See also

- [S-2606 · The A2A Security Gap Stack](/stacks/s2606-the-a2a-security-gap-stack-when-your-agent-protocol-is-enterprise-ready-but-not-enterprise-secure.md) — A2A's transport-layer security gaps, complementary to the negotiation-layer escalation problem
- [S-2766 · The Convergent Recovery Stack](/stacks/s2766-the-convergent-recovery-stack-when-your-agent-keeps-trying-after-it-already-won.md) — single-agent over-correction; escalation is the multi-agent variant where *both* agents over-correct simultaneously
- [S-1013 · The Multi-Agent Boundary Stack](/stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement between agents; negotiation failure is its temporal variant where agents *agree* on state but disagree on the path forward
