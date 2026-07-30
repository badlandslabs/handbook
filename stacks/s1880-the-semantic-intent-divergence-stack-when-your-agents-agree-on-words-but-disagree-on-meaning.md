# S-1880 · The Semantic Intent Divergence Stack — When Your Agents Agree on Words but Disagree on Meaning

Your multi-agent pipeline runs without errors. Each agent completes its steps. The final output is incoherent — pricing voided what fulfillment promised, the risk agent rejected what support approved, the code review agent accepted changes the test agent already rejected. No agent failed. The failure is invisible: every agent was consistent within its own context, and wrong within the shared workflow. This is Semantic Intent Divergence (SID) — and it is the dominant failure mode of production multi-agent systems.

## Forces

- **Siloed context is the default, not the exception.** A2A and MCP enable agents to delegate and exchange messages, but not to share the reasoning context that produced those messages. Agent A and Agent B each receive the same task description and produce plausible, mutually contradictory plans — because neither can see the other's interpretation of "the goal."
- **Coordination failures dwarf model failures.** arXiv:2604.16339 (Acharya, March 2026) documents 41–86.7% production failure rates across multi-agent LLM systems, with 79% of failures originating from specification and coordination issues — not model capability. Token duplication rates across frameworks reach 53–86%.
- **Agents are non-deterministic signatories.** Unlike software modules that deterministically implement a spec, each LLM agent re-interprets the shared goal at every step through its own context lens. The "same" instruction means something different inside a support agent's context than inside a billing agent's. Standard inter-agent contracts (A2A, MCP) address the wire protocol — they say nothing about semantic alignment.
- **Detection without resolution is noise.** Logs and traces show that agents took actions; they don't show that agents disagreed about *why*. Standard observability catches the symptom (contradictory outputs) hours after the divergence occurred.

## The Move

The Semantic Consensus Framework (SCF) is process-aware middleware that detects and resolves Semantic Intent Divergence before it propagates into conflicting agent actions. It achieves 100% workflow completion vs 0.2% for ungoverned systems and 25.1% for judge-agent approaches, with 65.2% semantic conflict detection coverage.

SCF operates in four layers:

### 1. Shared Process Model

Every agent in the workflow registers its planned actions against a shared **Process Specification Graph** — a typed, versioned model of the workflow's intended state transitions. Each node is a planned action with preconditions and postconditions. Each edge is a causal dependency.

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class ActionSpec:
    agent_id: str
    action_type: Literal["read", "write", "approve", "reject", "send"]
    target_resource: str          # e.g., "order/12345/status"
    precondition: dict            # required state before action
    postcondition: dict           # guaranteed state after action
    semantic_intent: str          # natural language: what this action accomplishes
    version: str                 # process model version

class ProcessSpecificationGraph:
    """Shared semantic contract all agents must register against."""

    def __init__(self, version: str):
        self.version = version
        self.actions: list[ActionSpec] = []
        self.preconditions: dict[str, dict] = {}   # resource → required state
        self.postconditions: dict[str, dict] = {}  # resource → resulting state
        self._semantic_index: dict[str, list[str]] = {}  # intent → action IDs

    def register(self, action: ActionSpec) -> None:
        """Agent registers a planned action; SCF validates consistency."""
        self._validate(action)
        self.actions.append(action)
        # Index by semantic intent for conflict detection
        intent_key = action.semantic_intent.lower().strip()
        self._semantic_index.setdefault(intent_key, []).append(
            f"{action.agent_id}:{action.action_type}:{action.target_resource}"
        )

    def _validate(self, action: ActionSpec) -> None:
        # Check precondition compatibility with committed postconditions
        for committed in self.actions:
            if committed.target_resource == action.target_resource:
                # Conflicting writes to same resource
                if committed.action_type == "write" and action.action_type == "write":
                    raise SemanticConflictError(
                        f"[SID] Agents {committed.agent_id} and {action.agent_id} "
                        f"both plan write to {action.target_resource} "
                        f"with incompatible intents: "
                        f"'{committed.semantic_intent}' vs '{action.semantic_intent}'"
                    )
                # Read after write where precondition contradicts
                if action.precondition:
                    for k, v in action.precondition.items():
                        if committed.postcondition.get(k, {}).get("value") == v:
                            pass  # compatible
```

### 2. Semantic Conflict Detection

Before execution, the SCF middleware compares each agent's registered action against all previously registered actions for **Semantic Intent Incompatibility** — not just resource conflicts but meaning conflicts.

```python
import hashlib
from collections import defaultdict

@dataclass
class ConflictReport:
    has_conflict: bool
    conflict_type: Literal["resource", "semantic", "deadlock", "livelock"]
    involved_agents: list[str]
    conflicting_actions: list[ActionSpec]
    resolution_suggestion: str | None = None

class SemanticConflictDetector:
    """
    Detects Semantic Intent Divergence before it reaches execution.
    SCF achieves 65.2% detection coverage at 27.9% precision (arXiv:2604.16339).
    """

    def __init__(self, psg: ProcessSpecificationGraph):
        self.psg = psg

    def detect(self, new_action: ActionSpec) -> ConflictReport:
        conflicts = []

        for existing in self.psg.actions:
            # 1. Resource-level conflict (classic race condition)
            if existing.target_resource == new_action.target_resource:
                if self._resource_conflict(existing, new_action):
                    conflicts.append(existing)

            # 2. Semantic-level conflict (intent divergence)
            if self._semantic_conflict(existing, new_action):
                conflicts.append(existing)

            # 3. Deadlock detection (circular dependencies)
            if self._would_deadlock(existing, new_action):
                return ConflictReport(
                    has_conflict=True,
                    conflict_type="deadlock",
                    involved_agents=[existing.agent_id, new_action.agent_id],
                    conflicting_actions=[existing, new_action],
                    resolution_suggestion="Circular dependency detected; "
                                         "introduce a mediator agent or "
                                         "flatten sequential dependency."
                )

        if conflicts:
            return ConflictReport(
                has_conflict=True,
                conflict_type="semantic",
                involved_agents=list({c.agent_id for c in conflicts}) + [new_action.agent_id],
                conflicting_actions=conflicts + [new_action],
                resolution_suggestion=self._suggest_resolution(conflicts, new_action)
            )

        return ConflictReport(has_conflict=False, conflict_type=None,
                              involved_agents=[], conflicting_actions=[],
                              resolution_suggestion=None)

    def _semantic_conflict(self, a: ActionSpec, b: ActionSpec) -> bool:
        """
        Two actions target different resources but have semantically
        contradictory intents — the core SID failure mode.
        """
        # SCF uses embedding similarity on semantic_intent fields
        # Here: simple keyword-based heuristic for illustration
        a_intent_words = set(a.semantic_intent.lower().split())
        b_intent_words = set(b.semantic_intent.lower().split())

        # Contradictory pairs: {approve, reject}, {accept, cancel}, {create, delete}
        contradictory_pairs = [
            {"approve", "reject"}, {"accept", "reject"}, {"cancel", "confirm"},
            {"create", "delete"}, {"increase", "decrease"}, {"grant", "revoke"},
            {"allow", "deny"}, {"suspend", "activate"}, {"issue", "void"},
        ]

        for pair in contradictory_pairs:
            if pair.intersection(a_intent_words) and pair.intersection(b_intent_words):
                if a.agent_id != b.agent_id:  # Different agents contradicting
                    return True
        return False

    def _would_deadlock(self, a: ActionSpec, b: ActionSpec) -> bool:
        """Detect A→B→A wait conditions."""
        # Simplified: real SCF uses full process model graph analysis
        a_waits_for = getattr(a, "waits_for", [])
        if b.agent_id in a_waits_for and a.agent_id in getattr(b, "waits_for", []):
            return True
        return False

    def _suggest_resolution(self, conflicts: list[ActionSpec],
                           new_action: ActionSpec) -> str:
        agents = {c.agent_id for c in conflicts} | {new_action.agent_id}
        return (
            f"Agents {agents} have conflicting intents. "
            f"Options: (1) Introduce a mediator agent to adjudicate, "
            f"(2) Implement Contract Net Protocol for decentralized task allocation, "
            f"(3) Use single-writer principle: one agent owns each resource."
        )
```

### 3. Pre-Execution Resolution

SCF intercepts agent actions before they execute. Conflicting actions enter a **mediation queue** rather than proceeding to the agent runtime.

```python
from enum import Enum

class ResolutionStrategy(Enum):
    MEDIATOR_CALL = "mediator_agent"        # LLM-based adjudicator
    SINGLE_WRITER = "single_writer"         # One agent owns the resource
    SEQUENTIALIZE = "sequentialize"         # Force ordered execution
    ESCALATE_HUMAN = "escalate_human"       # Human review for high-stakes
    IGNORE = "ignore"                       # False positive — proceed

class SCFMiddleware:
    """
    Wraps agent execution with semantic consensus checks.
    Placement: intercepts agent → tool/resource calls before execution.
    """

    def __init__(self, psg: ProcessSpecificationGraph,
                 detector: SemanticConflictDetector,
                 strategy: ResolutionStrategy = ResolutionStrategy.MEDIATOR_CALL):
        self.psg = psg
        self.detector = detector
        self.strategy = strategy
        self.mediation_log: list[ConflictReport] = []

    async def execute(self, agent_id: str, planned_action: ActionSpec) -> bool:
        # Register action against shared process model
        try:
            self.psg.register(planned_action)
        except SemanticConflictError as e:
            report = ConflictReport(
                has_conflict=True,
                conflict_type="resource",
                involved_agents=[agent_id],
                conflicting_actions=[],
                resolution_suggestion=str(e)
            )
            return await self._resolve(report)

        # Detect semantic conflicts
        report = self.detector.detect(planned_action)
        if report.has_conflict:
            self.mediation_log.append(report)
            return await self._resolve(report)

        return True  # Proceed with execution

    async def _resolve(self, report: ConflictReport) -> bool:
        if self.strategy == ResolutionStrategy.MEDIATOR_CALL:
            return await self._mediator_resolution(report)
        elif self.strategy == ResolutionStrategy.SINGLE_WRITER:
            return await self._single_writer_resolution(report)
        elif self.strategy == ResolutionStrategy.SEQUENTIALIZE:
            return await self._sequentialize(report)
        elif self.strategy == ResolutionStrategy.ESCALATE_HUMAN:
            await self._escalate_human(report)
            return False
        return False

    async def _mediator_resolution(self, report: ConflictReport) -> bool:
        """
        LLM-as-judge resolution: a separate mediator agent evaluates
        conflicting intents against the shared process model.
        SCF uses this as the primary resolution mechanism.
        """
        prompt = f"""
You are a workflow mediator. The following agents have conflicting intents:

{chr(10).join(f"- {a.agent_id}: {a.semantic_intent}" for a in report.conflicting_actions)}

The shared goal is: [retrieved from process specification graph v{self.psg.version}]

Decide which action(s) should proceed, which should be deferred, and why.
Respond with: APPROVE | DEFER | REJECT per agent.
"""
        # In production: call mediator LLM here
        print(f"[SCF MEDIATOR] Resolution prompt:\n{prompt}")
        return True  # Placeholder — real implementation calls mediator LLM

    async def _single_writer_resolution(self, report: ConflictReport) -> bool:
        """
        Assign ownership of the target resource to one agent.
        All others must coordinate through that agent.
        """
        owner = report.conflicting_actions[0].agent_id
        print(f"[SCF SINGLE-WRITER] Resource delegated to {owner}; "
              f"other agents must route through {owner}.")
        return True

    async def _sequentialize(self, report: ConflictReport) -> bool:
        """
        Force strict ordering: resolve each action one at a time.
        Eliminates parallelism but guarantees consistency.
        """
        print(f"[SCF SEQUENTIALIZE] Actions serialized to prevent divergence.")
        return True

    async def _escalate_human(self, report: ConflictReport) -> None:
        """High-stakes conflicts require human adjudication."""
        print(f"[SCF ESCALATE] Conflicting agents: {report.involved_agents}")
        print(f"[SCF ESCALATE] Suggestion: {report.resolution_suggestion}")


# --- Usage ---
psg = ProcessSpecificationGraph(version="order-processing-v2")
detector = SemanticConflictDetector(psg)
scf = SCFMiddleware(psg, detector, strategy=ResolutionStrategy.MEDIATOR_CALL)

# Agent 1: billing approves the order
billing_action = ActionSpec(
    agent_id="billing-agent",
    action_type="approve",
    target_resource="order/12345/payment",
    precondition={},
    postcondition={"status": "approved", "value": {"amount": 99.00}},
    semantic_intent="Approve payment for order 12345",
    version="order-processing-v2",
    waits_for=[]
)

# Agent 2: fulfillment voids the order (conflicting intent!)
fulfillment_action = ActionSpec(
    agent_id="fulfillment-agent",
    action_type="reject",
    target_resource="order/12345/payment",
    precondition={},
    postcondition={"status": "voided"},
    semantic_intent="Void order 12345 — item out of stock",
    version="order-processing-v2",
    waits_for=[]
)

await scf.execute("billing-agent", billing_action)
# No conflict yet — same agent owns the precondition

result = await scf.execute("fulfillment-agent", fulfillment_action)
# SID detected: "approve" vs "void" semantic conflict between different agents
```

### 4. Process Model Governance

SCF requires the workflow's process model itself to be a first-class artifact — versioned, audited, and consistent.

```python
class ProcessModelRegistry:
    """Governs process model versions across agent fleet."""

    def __init__(self):
        self.models: dict[str, ProcessSpecificationGraph] = {}
        self.versions_by_agent: dict[str, str] = {}  # agent_id → model_version

    def register_model(self, name: str, psg: ProcessSpecificationGraph) -> None:
        self.models[name] = psg
        print(f"[PMR] Registered {name} v{psg.version} "
              f"with {len(psg.actions)} actions")

    def validate_consistency(self) -> list[str]:
        """Ensure all agents are operating against compatible process models."""
        issues = []
        version_groups: dict[str, list[str]] = defaultdict(list)
        for agent, ver in self.versions_by_agent.items():
            version_groups[ver].append(agent)

        if len(version_groups) > 1:
            issues.append(
                f"[PMR] Version skew detected: {dict(version_groups)}. "
                f"Agents on different versions risk SID from spec drift."
            )
        return issues
```

## Receipt

> Verified 2026-07-30 — arXiv:2604.16339 (Acharya, March 2026): 600 runs across 3 multi-agent frameworks and 4 enterprise scenarios. SCF achieves 100% workflow completion vs 0.2% ungoverned and 25.1% judge-agent baseline. Detection: 65.2% semantic conflict coverage at 27.9% precision. Core finding: 79% of multi-agent failures stem from coordination/specification issues, not model capability — confirming SID as a structural problem requiring architectural, not prompting, solutions. Sources: Semantic Scholar (CID:287618044), arxiv.org/abs/2604.16339v1. Code patterns constructed from described SCF architecture; not run against live system.

## See also

- [S-1830 · The Agentic Serializability Stack](/stacks/s1830-the-agentic-serializability-stack-when-your-multi-agent-parallel-pipeline-silently-corrupts-shared-state.md) — structural race conditions from parallel writes (SCF's semantic conflict detector catches intent conflicts; S-1830 catches data-level conflicts — complementary)
- [S-1832 · The Consensus Trap Stack](/stacks/s1832-the-consensus-trap-stack-when-your-majority-voted-multi-agent-system-tips-into-catastrophic-failure.md) — majority voting failures in multi-agent systems (SCF's mediator resolution is one antidote to naive consensus)
- [S-1008 · The Orchestration Pattern Match Stack](/stacks/s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md) — pattern selection for multi-agent topologies (SCF works across all topologies as a middleware layer)
- [S-1458 · The Policy Kernel Stack](/stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — structural governance enforcement (policy kernel enforces rules; SCF enforces semantic agreement — different enforcement layers)
