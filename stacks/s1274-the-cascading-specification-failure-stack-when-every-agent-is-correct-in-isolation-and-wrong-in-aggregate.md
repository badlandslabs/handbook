# S-1274 · The Cascading Specification Failure Stack — When Every Agent Is Correct in Isolation and Wrong in Aggregate

Your multi-agent pipeline is working perfectly. Agent A produces a correct financial summary. Agent B correctly validates compliance. Agent C correctly flags risk. The final report, however, is wrong — it approved a transaction that violates your policy. Every agent followed its specification. The system failed anyway. This is the **cascading specification failure**: each handoff contract is satisfied individually, but the composition produces an outcome no single agent intended or could have predicted.

## Forces

- **Specifications capture what each agent does, not what the composition requires.** Each agent has a precise spec for its inputs and outputs. None of them has a spec for what the system should do overall — because that's never written down anywhere.
- **Agents can't see the aggregate.** Agent B validates that the transaction meets compliance rules. It doesn't know Agent C will override that validation based on a risk score. It doesn't know Agent A used stale market data. The information asymmetry across the chain produces locally-correct, globally-wrong outputs.
- **Handoff interfaces encode assumptions, not constraints.** When Agent A passes a result to Agent B, it encodes assumptions: "the user is verified." Agent B trusts those assumptions because there's no mechanism to verify them. If Agent A's verification logic had a gap, it propagates silently forward.
- **Business logic is distributed across agents, not centralized.** The real decision rule — "approve if compliant AND risk score < threshold AND user tier != restricted" — is split across three agents. No agent knows the full rule. The correct behavior emerges only if all three agents' outputs happen to compose correctly.
- **The failure is invisible until the audit.** No exception is thrown. No agent reports an error. The final output passes every automated check because each agent checked only its own domain. You find out at the compliance review.

## The move

### 1. Define the composition spec first

Before writing any agent spec, write the **aggregate specification**: the full decision rule that determines the correct output. This is the document that answers "what does a correct run look like?" in complete, formal terms. It specifies the interaction of all constraints — not just each constraint in isolation.

```
Composite Correctness Spec:
  APPROVE if and only if:
    compliance_agent.accept == true
    AND risk_agent.score < threshold
    AND user_agent.tier != "restricted"
    AND NOT (compliance_agent.flags contains "sanctioned_country" 
             AND risk_agent.score > 0.3)
```

This spec becomes the test oracle. Every agent spec is written to satisfy it.

### 2. Model handoff contracts as typed assertions

Each handoff is a **typed assertion** — not just a data transfer — where the downstream agent states what it's asserting about the upstream output:

```python
# Agent A → Agent B handoff
@dataclass
class ComplianceHandoff:
    transaction_id: str
    compliance_result: ComplianceResult
    assertions: list[Assertion] = field(default_factory=list)

# Agent B validates upstream assertions before processing
def validate_upstream(handoff: ComplianceHandoff) -> ValidationResult:
    for assertion in handoff.assertions:
        if not assertion.verify(handoff.compliance_result):
            raise ContractViolation(
                f"Upstream assertion failed: {assertion.description}"
            )
```

Assertions are first-class: they can fail, be logged, and block the pipeline.

### 3. Run the composition as an executable spec

The aggregate spec is not just documentation — it's executable. Every agent run produces a trace that a composition engine evaluates against the full spec:

```
trace = agent_pipeline.run(input)
result = aggregate_spec.evaluate(trace)

if not result.is_satisfied():
    log_failure(result.violations)      # which spec clauses failed
    rollback(result.scope)              # how far back to undo
    alert("aggregate contract violation")
```

This catches the cascade before it reaches the output stage.

### 4. Snapshot spec state at each handoff

Each agent captures a **spec snapshot**: the input state it received, the spec it was written against, and the version of that spec. When the aggregate fails, you can replay from any handoff boundary with the exact state that agent saw.

```python
@dataclass
class HandoffSnapshot:
    handoff_id: str
    agent_id: str
    spec_version: str
    input_state_hash: str      # hash of the input the agent received
    assertions_produced: list[Assertion]
    timestamp: datetime
```

### 5. The aggregate judge

Layer an **aggregate judge** — a separate, higher-order agent or rule engine — that evaluates the final composition output against the full business spec without being inside any single agent's reasoning. It sees what no individual agent sees: the complete interaction of all constraints.

```python
class AggregateJudge:
    def evaluate(self, trace: PipelineTrace) -> AggregateVerdict:
        violations = []
        for clause in self.spec.clauses:
            if not clause.holds(trace):
                violations.append(ClauseViolation(clause, trace))
        
        return AggregateVerdict(
            passed=len(violations) == 0,
            violations=violations,
            responsible_agents=trace.blame(violations)
        )
```

The judge has no skin in the game — it can't be influenced by any individual agent's reasoning.

## Tradeoffs

- **Composition specs are expensive to write.** The full aggregate spec requires cross-functional input from every team owning an agent in the pipeline. This is a process problem, not a code problem.
- **Assertion overhead.** Adding typed assertions to every handoff adds latency and maintenance burden. Start with high-stakes handoffs (financial, compliance, medical) and extend conservatively.
- **Aggregate judges add a second LLM call per decision.** Budget the cost and latency. Use rules-based evaluation where possible; reserve LLM-based judgment for genuinely complex composition logic.
- **Spec drift is real.** Aggregate specs and agent specs diverge over time. Treat the composition spec as a first-class artifact with versioning, review, and deprecation cycles.

## Variations

- **Temporal specification failure**: Agent A runs Monday with policy X. Agent B runs Tuesday with policy Y (updated overnight). The composition runs Monday-Tuesday and mixes policy versions. Solution: pin spec versions in handoff snapshots and fail-fast on version mismatches.
- **Invisible constraint interaction**: Two constraints that are individually sensible but contradictory in combination. The compliance agent says "approve" (no sanctions match). The risk agent says "escalate" (velocity anomaly). Neither violated its spec. The composition spec must document this interaction explicitly.
