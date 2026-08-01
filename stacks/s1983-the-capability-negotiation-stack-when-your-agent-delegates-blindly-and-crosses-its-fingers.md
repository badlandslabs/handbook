# S-1983 · The Capability Negotiation Stack — When Your Agent Delegates Blindly and Crosses Its Fingers

[You have a researcher agent and a writer agent. The user asks for a competitive analysis. The researcher finishes and hands off to the writer. But the writer doesn't know the researcher used a 3-month-old data source. The writer doesn't know the researcher's context window was truncated at step 14. The writer doesn't know the researcher ran out of token budget and stopped early. The writer produces a report that is internally consistent, well-written, and based on stale, incomplete, and unverified findings. This is not a writer failure. It is a negotiation failure: the delegation was blind.]

## Forces

- **Delegation without capability disclosure is a guess.** The orchestrator agent must decide who to delegate to — but if the target agent hasn't explicitly declared its current state (token budget remaining, data freshness, completion confidence, known gaps), the orchestrator is delegating into fog.
- **A2A solves transport; it doesn't solve semantics.** The A2A protocol (v1.0, Linux Foundation, 150+ production orgs as of mid-2026) standardizes how agents exchange messages. It does not standardize what those messages mean, what guarantees the delegate is making, or what happens when the delegate can't fulfill the request.
- **Silent truncation compounds across handoffs.** If the researcher agent's context was truncated mid-analysis, and this isn't communicated in the handoff, the writer agent inherits an incomplete picture and produces output that appears authoritative but is systematically incomplete. Each additional handoff layer compounds this rather than corrects it.
- **The handoff contract is the missing artifact.** Most multi-agent systems treat delegation as a fire-and-forget event: send a task description, receive a result. There's no contract governing quality, completeness, confidence, or what constitutes failure on the delegate's side.

## The move

The fix is a **capability negotiation phase** before delegation — a structured exchange where the delegating agent and the candidate agent establish what the task is, what guarantees the delegate can make, what it knows it doesn't know, and what the handoff contract looks like.

### Step 1: Capability disclosure (before delegation)

The candidate agent exposes a **skill card** — a structured manifest covering:

```json
{
  "agent_id": "researcher-v3",
  "task_type": "competitive_analysis",
  "capabilities": ["web_search", "financial_data", "market_reports"],
  "known_gaps": ["pricing_data older than Q1-2026", "non-English sources limited"],
  "token_budget_remaining": 12000,
  "context_completeness": 0.73,
  "confidence_score": 0.68,
  "can_guarantee": ["factual claims with citations", "source URLs"],
  "cannot_guarantee": ["real-time pricing", "private company financials"]
}
```

The `context_completeness` field is non-obvious: it estimates what fraction of the relevant knowledge space the agent has covered given its token budget. A value of 0.73 means the agent believes it has explored 73% of the relevant space — the delegator can decide whether that's sufficient for the task.

### Step 2: Negotiation state machine

Rather than a binary accept/reject on a delegation request, implement a **negotiation protocol** with three states:

```
DELEGATOR                          DELEGATE
    |                                  |
    |--- propose(task, quality_bar) --->|
    |                                  |
    |<-- can_meet(guarantees, gaps) ---|
    |                                  |
    |<-- propose_alternate(task_v2) ---|  (if partial match)
    |                                  |
    |--- accept | withdraw --->|
```

The `propose_alternate` branch is the key pattern: if the delegate can partially fulfill the request, it returns a modified task specification with explicit gaps annotated. The delegator can then decide whether to proceed with degraded expectations or route to a different agent.

### Step 3: The handoff contract

Upon acceptance, both agents sign a lightweight **handoff contract**:

```python
class HandoffContract:
    task_id: str
    delegator: str
    delegate: str
    quality_guarantees: list[str]   # e.g., ["all_statements_cited", "data_freshness_confirmed"]
    explicit_gaps: list[str]        # e.g., ["pricing_data_as_of_Q1_2026"]
    abort_conditions: list[str]     # e.g., ["if_context_completeness_drops_below_0.5"]
    deadline: datetime | None
    escalation_agent: str | None    # who to notify if contract is violated
```

The `abort_conditions` field is the critical safety valve. If the delegate's `context_completeness` drops below 0.5 mid-task, it signals a contract breach and the delegator re-evaluates the routing decision rather than proceeding with degraded output.

### Step 4: Negotiation failure modes

Three things can go wrong at the negotiation layer:

**1. Capability inflation.** The delegate claims it can guarantee something it can't. Counter: require evidence chains for non-trivial guarantees — "all_statements_cited" should include a citation manifest, not just a confidence score.

**2. Negotiation deadlock.** Two agents can't agree on a quality bar — neither can meet it and neither can find an alternate. Counter: define a `fallback_agent` in the contract. If primary negotiation fails, route to fallback without re-negotiating from scratch.

**3. Silent gap propagation.** The delegate honestly reports a gap, the delegator accepts it, but downstream consumers of the output don't know the gap exists. Counter: the final output must include a `gap_disclosure` section listing every gap accepted during negotiation, surfaced to the end user.

## Receipt

> Verified 2026-08-01 — Research sources: Zylos Research (May 16, 2026) on A2A/MCP protocol landscape (150+ orgs, 22K+ GitHub stars, v1.0); SudoAll (June 24, 2026) on multi-agent coordination failure modes; Resomnium (2026) on the coordination breakdown pattern (five-step failure sequence: same information needed → different conclusions → concurrent action → downstream conflict → silent corruption); Conceptualise (May 31, 2026) on multi-agent failure modes and the 15x token multiplier from unoptimized delegation; Comet ML blog on multi-agent architecture patterns; Pockit Tools on MCP vs A2A decision tree.

## See also
- [S-1040 · The Protocol Gap](stacks/s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — foundational: MCP and A2A as complementary layers
- [S-1042 · The Protocol Stack](stacks/s1042-the-protocol-stack-when-your-agent-needs-to-talk-to-agents-and-tools.md) — protocol taxonomy and N×M integration problem
- [S-1036 · The Trajectory Quality Index](stacks/s1036-the-trajectory-quality-index-when-your-agent-passes-but-the-path-is-broken.md) — composite reliability compounding across steps
- [S-1067 · The Hallucination Laundry Problem](stacks/s1067-the-hallucination-laundry-problem-when-shared-state-converts-one-agents-error-into-everyones-fact.md) — how shared-state errors propagate across agents
- [S-1063 · The Multi-Agent Orchestration Stack](stacks/s1063-the-multi-agent-orchestration-stack-when-one-agent-isnt-enough-but-five-becomes-a-debugging-nightmare.md) — orchestration topology patterns
