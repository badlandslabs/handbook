# S-1132 · The Semantic Intent Divergence Stack — When Your Agents All Succeed but Disagree on What Success Means

Two agents run the same task. Both return HTTP 200. Both pass their local evals. The final artifact contradicts itself — the planner wrote the report with Q3 assumptions; the data agent computed Q4 figures; the reviewer approved on grounds neither knew the other was using. No error was thrown. No agent failed. But the output is wrong.

This is **Semantic Intent Divergence** — formally identified in March 2026 by Acharya (arXiv:2604.16339) as the dominant failure mode in enterprise multi-agent LLM systems. Production deployment failure rates range from 41% to 86.7%. Critically, **79% of those failures originate from specification and coordination issues — not model capability**. The agents aren't too weak. They don't understand each other.

## Forces

- **Siloed context is the default, not the exception.** Each agent operates with a private context window. Without an explicit shared intent model, agents infer the goal from their local slice — which diverges from the moment they diverge in input data or role framing.
- **Local success ≠ global coherence.** An agent can be optimizing the correct objective for its role while producing output incompatible with the adjacent agent's output. Each local optimum produces a global failure.
- **Intent drift is invisible at execution time.** Unlike tool call failures or timeouts, intent divergence produces plausible-looking HTTP 200 responses. The failure surfaces in the final artifact — days later, in the wrong place, for the wrong reason.
- **The 79% statistic changes the priority.** If coordination failures account for nearly four-fifths of multi-agent production failures, then the default investment — better models, more tools, longer prompts — is aimed at the wrong target.

## The Move

### 1. Model intent explicitly, not implicitly

Replace "give agents a shared prompt" with a **typed intent manifest** — a machine-readable document the orchestrator writes and all agents read at every handoff. The manifest encodes:

- `goal`: the terminal objective in domain-specific terms
- `constraints`: hard boundaries (what must not happen)
- `success_criteria`: measurable conditions, not vibes
- `assumptions`: what each agent is entitled to assume about prior steps
- `schema_version`: prevents stale-context agents from using old data formats

```python
# IntentManifest — written by orchestrator, read at every agent handoff
class IntentManifest(BaseModel):
    task_id: str
    goal: str                           # "Generate Q3 revenue reconciliation report"
    constraints: list[str]              # ["exclude voided transactions", "round to nearest USD"]
    success_criteria: list[Criterion]   # revenue_delta < 0.01, line_items > 0
    assumptions: dict[str, str]        # {"data_agent": "data_agent used Q3 date filter"}
    schema_version: str                # "v2.1" — stale agents must re-sync
    parent_intent_id: str | None       # link to parent for sub-task trees

    def validate_agent_output(self, output) -> ValidationResult:
        for criterion in self.success_criteria:
            if not criterion.check(output):
                return ValidationResult(pass=False, reason=criterion.label)
        return ValidationResult(pass=True)
```

### 2. Detect divergence before it compounds

The **Semantic Consensus Check** (Acharya, 2026) runs as a lightweight middleware step between agent handoffs. Before agent B receives agent A's output, a consensus verifier compares:

- **Goal alignment**: Does B's interpretation of the goal match A's stated goal?
- **Schema compatibility**: Does B's expected data format match what A produced?
- **Assumption verification**: Are A's stated assumptions actually satisfied in the output?

```python
async def semantic_consensus_check(
    sender: Agent,
    receiver: Agent,
    manifest: IntentManifest,
    output: Any
) -> ConsensusResult:
    # Goal alignment: receiver re-states the goal in their own words
    receiver_goal = await receiver.reconcile_goal(manifest.goal)
    goal_match = semantic_similarity(manifest.goal, receiver_goal) > 0.85

    # Schema check: validate output against receiver's expected format
    schema_ok = receiver.validate_schema(output) if hasattr(receiver, 'validate_schema') else True

    # Assumption audit: did all stated assumptions hold?
    assumptions_held = all(
        check_assumption(output, assumption)
        for assumption in manifest.assumptions.values()
    )

    return ConsensusResult(
        goal_aligned=goal_match,
        schema_valid=schema_ok,
        assumptions_satisfied=assumptions_held,
        block_on_fail=True  # divergence → BLOCK, not WARN
    )
```

### 3. Use typed handoff contracts, not text messages

Replace freeform text handoffs between agents with **typed HandoffContracts** — structured summaries that the receiving agent must parse and acknowledge.

```python
class HandoffContract(BaseModel):
    sender_role: str                          # "revenue_data_agent"
    receiver_role: str                        # "report_planner_agent"
    manifest_id: str
    outputs: dict[str, Any]                   # typed, not prose
    output_metadata: OutputMetadata
    unresolved_ambiguities: list[str]         # what sender flagged as uncertain
    assumptions_guaranteed: list[str]         # sender certifies these hold

    async def receiver_acknowledge(self, receiver: Agent) -> bool:
        """Receiver confirms it parsed and accepted the contract."""
        parsed = receiver.parse_handoff(self)
        if parsed.ambiguities_requested:
            await self.sender.clarify(parsed.ambiguities_requested)
        return True
```

### 4. Add a process model — agents need a shared map

Most multi-agent failures happen because agents don't know what other agents are doing *right now*. A **process model** (lightweight state machine) gives every agent a shared view of the workflow's current phase.

```python
# Shared process state — every agent reads this at step start
PROCESS_STATE = {
    "current_phase": "data_extraction",       # vs. "analysis", "review", "delivery"
    "completed_phases": ["intent_manifest"],
    "blocked_on": None,                       # or agent_id waiting for clarification
    "divergence_log": [],                      # every consensus check result
}
```

The process model is not a rigid workflow — agents can branch. But every branch must update the model, so downstream agents can reconstruct *what actually happened* without reading every agent's private context.

## Receipt

> Verified 2026-07-15 — Research cross-validated against: arXiv:2604.16339 (Semantic Consensus, Acharya, March 2026 — 79% of enterprise multi-agent failures from coordination/specification issues, n=~500 production deployments); Zylos Research graph-based orchestration survey (April 2026 — explicit typed state + intent manifests as dominant 2026 pattern); Inferensys semantic alignment layer guide (June 2026 — shared ontology + context translation as implementation pattern). Real incident reconstructed from Agentbrisk real-incidents collection (March 2026, e-commerce reconciliation failure). Implementation pattern matches the typed-handoff approach from S-1013 (Multi-Agent Boundary Stack) extended with explicit intent modeling and divergence detection. Gap confirmed: no prior handbook entry covers Semantic Intent Divergence as a named failure mode with the SCF/typed-manifest resolution pattern.

## See also

- [S-1013 · The Multi-Agent Boundary Stack](/stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — untyped handoffs; this entry is the resolution
- [S-1065 · The Inter-Agent Trust Escalation Stack](/stacks/s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — intent drift in security-critical contexts
- [S-1055 · The Pattern Ladder Stack](/stacks/s1055-the-pattern-ladder-stack-when-youre-about-to-build-a-swarm-and-a-pipeline-wouldve-done.md) — pattern selection before multi-agent; coordinate with this entry's escalation gate
