# S-1347 · The Agent Handoff Contract Stack — When Your Orchestration Layer Treats Handoffs as Routing Events Instead of Contract Enforcement Moments

Your multi-agent system ran perfectly in staging. Four specialized agents — parser, extractor, compliance checker, report generator — connected through an orchestration layer that had taken three months to build. On day three of production, it started returning factually wrong reports that nobody caught until the customer complained. The postmortem found the problem: nobody had defined what a valid output from the parser looked like, what the extractor was allowed to assume about its inputs, or what the compliance checker should do when required fields were absent. The orchestration layer treated handoffs as routing events, not as moments requiring contract enforcement. This is the Agent Handoff Contract problem — the silent killer of multi-agent production systems that never appears in single-agent evals.

## Forces

- **Agents are black boxes with invisible state.** Each agent accumulates context during execution. When two agents hand off data, neither can see the other's internal state — only the surface-level output. Subtle context drift between the handoff message and the receiver's interpretation produces errors that look like hallucinations but are really coordination failures.
- **Routing is a solved problem. Contract enforcement is not.** Every orchestration framework handles "which agent gets this task next" trivially. None handle "what must the upstream agent produce for the downstream agent to accept it" with any rigor. The result is that teams spend months building sophisticated routing logic and zero time on handoff schemas.
- **Failure at handoff is invisible failure.** A parser that produces malformed output silently passes it to the extractor, which produces confident-looking nonsense. There is no exception, no 500 error, no crash. The downstream agent processes the bad input as if it were good, because it has no schema to validate against. The failure surfaces three steps later as a wrong report — impossible to trace back to the handoff that started the corruption chain.
- **47 distinct failure modes are unique to multi-agent orchestration.** (Microsoft Research, 2026) These modes don't appear on single-agent dashboards, don't get caught by unit tests, and don't reproduce in isolation. Most of them originate at handoff boundaries.

## The move

Treat every agent-to-agent handoff as a contract enforcement moment, not a routing event. Build a five-layer handoff contract:

### Layer 1 — Schema Contract (what)

The upstream agent's output must conform to a declared schema before the downstream agent receives it. The schema is not a format suggestion — it is a gate. If the upstream produces output that fails schema validation, the handoff blocks, the upstream retries or escalates, and the downstream never receives invalid input.

```python
from pydantic import BaseModel, ValidationError
from typing import Optional

class ExtractorInput(BaseModel):
    raw_text: str
    entities: list[dict]
    confidence: float
    metadata: dict

    def validate_handoff(cls, output: dict) -> "ExtractorInput":
        try:
            return cls(**output)
        except ValidationError as e:
            # Block the handoff — do not pass invalid input downstream
            raise HandoffContractViolation(
                f"Upstream {cls.__name__} failed schema contract: {e}"
            ) from e
```

### Layer 2 — Capability Contract (who)

The downstream agent must declare what it can and cannot handle — and the orchestration layer must enforce these limits before routing. A compliance checker that cannot handle multilingual text must say so explicitly. If the parser produces multilingual output, the orchestration layer detects the mismatch at routing time, not at runtime.

```python
class AgentCapabilityContract:
    def __init__(
        self,
        agent_id: str,
        input_types: list[str],          # e.g., ["en_text", "structured_json"]
        max_input_length: int,            # tokens
        required_fields: list[str],        # schema fields that must be present
        optional_fields: list[str],
        failure_responses: dict[str, str], # field → what to do if missing
    ):
        self.agent_id = agent_id
        self.input_types = input_types
        self.max_input_length = max_input_length
        self.required_fields = required_fields
        self.optional_fields = optional_fields
        self.failure_responses = failure_responses

    def can_accept(self, upstream_output: dict) -> tuple[bool, str]:
        """Returns (accepted, reason). Orchestration layer gates on False."""
        if upstream_output.get("language") not in self.input_types:
            return False, f"{self.agent_id} cannot process language: {upstream_output.get('language')}"
        if len(upstream_output.get("raw_text", "")) > self.max_input_length:
            return False, f"Input exceeds {self.max_input_length} token limit"
        for field in self.required_fields:
            if field not in upstream_output:
                response = self.failure_responses.get(field, "BLOCK")
                if response == "BLOCK":
                    return False, f"Required field '{field}' missing from upstream output"
        return True, "accepted"
```

### Layer 3 — Escalation Contract (what when)

Define explicit escalation paths for each failure mode. Not a retry loop — a typed escalation. Missing field → use fallback → if fallback unavailable → escalate to human. Downstream agent receives malformed input → quarantine and flag → retry upstream → if retry fails → escalate with full context.

```python
class EscalationContract:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.escalation_paths: dict[str, "EscalationPath"] = {}

    def declare(self, trigger: str, path: "EscalationPath"):
        """Register: 'if trigger fires, follow path'."""
        self.escalation_paths[trigger] = path

    def evaluate(self, context: dict) -> Optional["EscalationSignal"]:
        for trigger, path in self.escalation_paths.items():
            if path.matches(context):
                return path.execute(context)
        return None
```

### Layer 4 — State Contract (what's true)

Before any handoff, assert the state invariants that the downstream agent requires. The compliance checker needs to know: is this a new document or an amendment? Has the client been verified? The upstream agent sets these as explicit state assertions, not as implicit context buried in the prose.

```python
class HandoffStateAssertion:
    def __init__(self, upstream: str, downstream: str):
        self.upstream = upstream
        self.downstream = downstream
        self.invariants: list[callable] = []

    def require(self, invariant_fn: callable, description: str):
        """Register a state invariant that must hold at handoff time."""
        self.invariants.append(invariant_fn)

    def assert_all(self, session_state: dict) -> list[str]:
        """Returns list of failed invariants with descriptions."""
        failures = []
        for inv in self.invariants:
            try:
                if not inv(session_state):
                    failures.append(inv.__doc__ or "unnamed invariant")
            except Exception as e:
                failures.append(f"invariant check error: {e}")
        return failures

# Example usage
assertion = HandoffStateAssertion("parser", "extractor")
assertion.require(
    lambda s: s.get("document_type") in ["invoice", "contract", "amendment"],
    "document_type must be one of [invoice, contract, amendment]"
)
assertion.require(
    lambda s: s.get("client_verified") is True,
    "client_verified must be True before entity extraction"
)
```

### Layer 5 — Termination Contract (when done)

Each agent declares what constitutes its completion and what the downstream must do with that output. Not "finished" — a typed completion signal with an attached output manifest. The report generator's termination contract specifies: these are the sections I produced, this is their confidence, this is what the downstream caller should do with low-confidence sections.

```python
from enum import Enum
from dataclasses import dataclass

class TerminationType(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"     # completed but low confidence
    BLOCKED = "blocked"     # could not complete
    ESCALATED = "escalated" # handed off to human

@dataclass
class HandoffTermination:
    agent_id: str
    termination_type: TerminationType
    output_manifest: dict   # field → confidence score
    downstream_recommendation: str  # what caller should do
    handoff_to: Optional[str] = None  # next agent ID if escalated
```

### Putting it together: the contract registry

```python
class HandoffContractRegistry:
    """Central registry of all handoff contracts in the system."""

    def __init__(self):
        self.schema_contracts: dict[tuple, type[BaseModel]] = {}
        self.capability_contracts: dict[str, AgentCapabilityContract] = {}
        self.escalation_contracts: dict[str, EscalationContract] = {}
        self.state_assertions: dict[tuple, HandoffStateAssertion] = {}
        self.termination_contracts: dict[str, TerminationContract] = {}

    def register_handoff(
        self,
        from_agent: str,
        to_agent: str,
        schema: type[BaseModel],
        capability: AgentCapabilityContract,
        escalation: EscalationContract,
        state: HandoffStateAssertion,
        termination: TerminationContract,
    ):
        key = (from_agent, to_agent)
        self.schema_contracts[key] = schema
        self.capability_contracts[key] = capability
        self.escalation_contracts[key] = escalation
        self.state_assertions[key] = state
        self.termination_contracts[key] = termination

    def enforce(self, from_agent: str, to_agent: str, output: dict, session: dict):
        key = (from_agent, to_agent)

        # Layer 1: Schema gate
        validated = self.schema_contracts[key].validate_handoff(output)

        # Layer 2: Capability gate
        accepted, reason = self.capability_contracts[key].can_accept(output)
        if not accepted:
            raise HandoffCapabilityMismatch(f"{key}: {reason}")

        # Layer 3: State invariants
        state_failures = self.state_assertions[key].assert_all(session)
        if state_failures:
            raise HandoffStateViolation(f"{key}: {state_failures}")

        return validated
```

## Receipt

> Receipt pending — 2026-07-19

## See also
- [S-1346 · Stigmergy Architecture](s1346-the-stigmergy-architecture-stack-when-your-multi-agent-system-spends-more-time-waiting-than-working.md) — shared-environment handoff as an alternative to direct message passing
- [S-1342 · The Specification-First Stack](s1342-the-specification-first-stack-when-you-build-the-handoff-before-the-agent-breaks-it.md) — pre-handoff role contracts and output schemas
- [S-1314 · The Pipeline Collapse Stack](s1314-the-pipeline-collapse-stack-when-your-multi-agent-system-drops-the-handoff-between-steps.md) — three silent failures that kill multi-agent systems after the handoff
- [I-176 · The Semantic Intent Divergence Stack](https://github.com/badlandslabs/handbook/issues) — when agents succeed locally but fail globally due to intent drift
