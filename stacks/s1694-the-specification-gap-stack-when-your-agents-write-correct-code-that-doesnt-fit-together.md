# [S-1694] · The Specification Gap Stack

You wrote a spec. You listed the task, described the inputs, and gave examples. The agents ran — and each produced correct, well-formed code that crashes at the seams. No model limitation caused this. The specification did.

## Forces

- The human instinct to write instructions like emails to a colleague — who shares your context, your assumptions, your conventions
- Multi-agent parallel decomposition splits the spec before agents see each other's work — every implicit choice becomes a divergence point
- Individual capability benchmarking measures whether an agent can solve a task alone — it never measures whether two agents can solve it together
- Correctness is not composability: agents write provably correct methods that use incompatible data structures

## The move

The **specification gap** is the distance between instructions written for agents and the tasks agents actually interpret. Research on 51 multi-agent class-generation tasks shows it is structural, not fixable by switching models.

### The coordination tax (the empirical case)

The gap is measurable and severe:

| Condition | Pass Rate |
|-----------|-----------|
| Single agent, full spec (L0) | 89% |
| Two agents, full spec (L0) | 58% |
| Two agents, bare signature (L3) | 25% |
| Two agents, bare sig + merger agent with full spec | 89% |

The specification is **both the cause of failure and the sufficient instrument of recovery**. Adding a merger agent with full spec back to a bare-signature run restores the single-agent ceiling (89%) — no other intervention was needed.

The gap decomposes into two independent effects that approximately add:
- **Coordination cost**: +16 percentage points lost to implicit alignment
- **Information asymmetry**: +11 percentage points lost to divergent internal representations

### The four levels of specification detail

| Level | Description | Multi-Agent Effect |
|-------|-------------|-------------------|
| L0 | Full docstrings + examples + constraints | 58% pass rate |
| L1 | Docstrings without examples | ~42% |
| L2 | Inline comments + type hints | ~33% |
| L3 | Bare signatures only | 25% |

Single agents degrade gracefully as specs thin. Multi-agent systems don't degrade — they **collapse** once the spec stops specifying shared internal representations.

### The structural incompatibility problem

Traditional software engineering prevents this through design-by-contract and information hiding. LLM agents inherit those tools but don't reliably use them — because they have no shared contract enforcement layer.

Example: Agent A stores user records in a `list[dict]`. Agent B, given the same API signature, implements filtering assuming `dict[str, UserProfile]`. Both write correct, passing unit tests. The integration fails.

```python
# L0 spec — the minimum viable contract for multi-agent work
class UserStore:
    """
    Stores user records with idempotent upsert.
    Internally uses: dict[str, UserProfile]  ← MANDATORY
    Exposes list-like ordering via sorted() on creation_ts.
    Do NOT use list[dict] internally.
    All agents MUST agree on this representation before implementation.
    """
```

### The Pattern: Explicit Representation Contracts

```
1. Write the spec at L0 — full docstrings, explicit internal-type contracts,
   and a "Shared Abstractions" section listing every data structure
   both agents must agree on before implementation starts.

2. Enforce the contract as a pre-flight check.
   Before agents diverge, run: validate_shared_representations(spec)
   This catches implicit-gap risks before they become integration failures.

3. Use a merger agent with full L0 spec as the reconciliation layer.
   Its job is not to resolve conflicts — it's to enforce the shared
   contract and surface violations clearly.

4. Re-spec on merge conflict, never on silence.
   If two agents produce conflicting outputs, the problem is always
   that the original spec left something implicit. Fix the spec, not
   the agents.
```

```python
from typing import Protocol, Any
from pydantic import BaseModel, ValidationError

class RepresentationContract(BaseModel):
    """Every multi-agent task must declare this before agents diverge."""
    internal_types: dict[str, str]  # e.g. {"users": "dict[str, UserProfile]"}
    shared_apis: list[str]          # e.g. ["upsert", "query", "delete"]
    serialization_constraint: str    # e.g. "must round-trip through JSON"

    class Config:
        extra = "forbid"

def preflight_contract_check(contract: RepresentationContract) -> list[str]:
    """Run before agents diverge. Returns list of implicit-gap risks."""
    risks = []
    if not contract.internal_types:
        risks.append("No internal type contract declared — agents may diverge on data structures")
    if not contract.serialization_constraint:
        risks.append("No serialization contract — agents may use incompatible formats")
    return risks

# Example usage
contract = RepresentationContract(
    internal_types={"users": "dict[str, UserProfile]"},
    shared_apis=["upsert", "query", "delete"],
    serialization_constraint="must round-trip through JSON"
)
risks = preflight_contract_check(contract)
if risks:
    raise ValueError(f"Specification gap risks detected: {risks}")
```

## Receipt

> Verified 2026-07-26 — Research synthesis from arXiv:2603.24284 (Sartori, Mar 2026) and tianpan.co analysis. The paper establishes the gap empirically: 51 class-generation tasks, 4 specification levels, 3 runs per condition. Key finding: specification alone is both cause and cure. Sprint data: single agent L0 = 89%; two agents L3 = 25%; two agents L3 + merger with L0 = 89%. Gap decomposition: coordination cost (+16 pp) + information asymmetry (+11 pp) ≈ total gap. Context: 41.77% of multi-agent failures are spec-related; 79% of production breakdowns trace to task specification, not model capability (AugmentCode, 2026).

## See also

- **[S-1008 · The Orchestration Pattern Match Stack](/stacks/s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md)** — orchestration decisions that compound when specs are thin
- **[S-1656 · The Agent Drift Stack](/stacks/s1656-the-agent-drift-stack-when-your-agent-was-brilliant-at-step-10-and-confused-by-step-30.md)** — behavioral divergence over time; the spec gap is its static cousin
- **[S-1650 · The Tool Interface Stack](/stacks/s1650-the-tool-interface-stack-when-your-tool-description-works-for-humans-but-not-for-agents.md)** — interface contracts between agents and tools; same problem, different layer
