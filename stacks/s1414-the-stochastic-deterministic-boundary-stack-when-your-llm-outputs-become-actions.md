# S-1414 · The Stochastic-Deterministic Boundary Stack — When Your LLM Outputs Become Actions

Every production agent has the same hidden seam: the moment an LLM output transitions from a prediction into a system action. That seam — stochastic core meeting deterministic execution — is where reliability lives or dies. It has no name in most architectures. This chapter gives it one: the stochastic-deterministic boundary (SDB).

## Forces

- **LLMs are stochastic by design.** Even at temperature=0, GPU cluster scheduling, floating-point non-determinism, and batching interactions at token sampling boundaries produce different outputs on identical inputs. "Nearly deterministic" is not determinism.
- **Execution systems are deterministic by contract.** Databases, APIs, and file systems commit writes atomically. The moment an LLM output crosses into a write — a tool call, an API request, a state mutation — it enters territory where "different output" means "different reality."
- **The seam is load-bearing but unnamed.** The composition between stochastic and deterministic layers is the actual engineering surface of production agents. Most teams treat it as implicit scaffolding rather than a first-class contract, which means it fails silently at the worst moments.
- **Naive compositions fail in predictable ways.** Appending a raw LLM output to a database query is not a boundary — it is a vulnerability. The boundary must be explicit, with typed acceptance and rejection signals.

## The Move

The SDB is a **four-part contract** that governs every LLM-to-action transition:

```
LLM Output → [PROPOSE] → [VERIFY] → [COMMIT] or [REJECT]
```

Each part is distinct and independently replaceable:

### 1. Proposer (LLM)
The LLM generates a candidate output — a tool call, a decision, a message. No constraints here other than output format. This is the stochastic core.

### 2. Verifier (Deterministic)
A deterministic check validates the proposal before it becomes an action. The verifier is NOT another LLM — it is structured logic operating on the proposal:

```python
# Example: tool-call SDB verifier
def verify_tool_call(proposal: dict, schema: dict, policy: dict) -> str:
    # Schema conformance
    if not conforms_to_schema(proposal, schema):
        return "REJECT"  # wrong shape
    # Policy check
    if proposal["name"] in policy["blocked_tools"]:
        return "REJECT"  # forbidden by policy
    # Parameter bounds
    for param, val in proposal["params"].items():
        if param in policy["bounds"] and val > policy["bounds"][param]:
            return "REJECT"  # out of bounds
    return "ACCEPT"
```

Verifier failure modes are **deterministic and auditable** — you can reproduce every rejection.

### 3. Commit (Durable Write)
On ACCEPT, the verified proposal is executed as a durable write. The commit step is idempotent — re-running the same accepted proposal has the same result.

### 4. Reject Signal (Typed Response)
On REJECT, a structured response is returned to the proposer. Critically, the reject signal is **typed** — it carries the reason for rejection in a format the LLM can use to修正 (e.g., `"REJECT: schema_violation, field='amount', expected<=1000, got=5000"`). This closes the loop: the LLM can self-correct on the next attempt.

### Six Composable Patterns

Srinivasan (arXiv:2605.20173) catalogs six SDB patterns by where and how the boundary is enforced:

| Pattern | Boundary Location | Verification Style |
|---|---|---|
| **Direct Execution** | No boundary — LLM output → action | None (highest risk) |
| **Guard Rails** | Pre-action, rule-based | Static policy checks |
| **Try/Catch Wrapper** | Post-action, error-based | Exception handling |
| **Two-Phase Commit** | Pre + post action | Dual verification |
| **Human-in-the-Loop** | Pre-action, human approval | Manual gate |
| **Multi-Party Consensus** | Multi-agent agreement | Cross-verification |

The pattern you choose depends on **action reversibility and blast radius**:

```python
# Decision matrix for SDB pattern selection
def select_sdb_pattern(action: Action, context: AgentContext) -> str:
    reversibility = get_reversibility(action)
    blast_radius = get_blast_radius(action)
    latency_budget = context.latency_sla
    
    if blast_radius == "critical" and reversibility == "none":
        return "human_in_the_loop"
    if blast_radius == "high" and reversibility == "none":
        return "multi_party_consensus"
    if blast_radius == "medium" and reversibility == "compensatable":
        return "two_phase_commit"
    if blast_radius == "low" and latency_budget < 50ms:
        return "guard_rails"
    return "try_catch_wrapper"
```

### Replay Divergence: The SDB Failure Mode

Named failure: **replay divergence** — the SDB produces different outcomes on identical reruns because the stochastic layer was not fully reset between attempts. This is distinct from the LLM nondeterminism everyone knows about:

- **Same input, different sampling path** → same SDB outcome (proposer stochastically self-corrected)
- **Same input, different state from prior steps** → diverging SDB outcome (unintended state carryover)
- **Same input, different proposer model version** → diverging SDB outcome (model drift)

The fix: **state snapshot + deterministic replay** — store the full SDB state (proposal, verification input, decision) and replay from that snapshot, not from the original prompt.

```python
@dataclass
class SDBStateSnapshot:
    step: int
    proposer_output: str
    verification_input: dict
    decision: str  # ACCEPT | REJECT
    llm_version: str
    rng_seed: Optional[int]

def replay_from_snapshot(snapshot: SDBStateSnapshot) -> str:
    """Deterministic replay. Same state → same decision."""
    reset_rng(snapshot.rng_seed)
    verified = verify_proposal(snapshot.proposer_output, snapshot.verification_input)
    return verified  # deterministic
```

## Receipt

> **Receipt pending — 2026-07-20**
>
> Source: Srinivasan, V. (May 2026). *A Methodology for Selecting and Composing Runtime Architecture Patterns for Production LLM Agents.* arXiv:2605.20173. Stanford School of Engineering. Methodology is theoretically grounded; six patterns and replay divergence taxonomy are directly applicable to handbook entry. Pattern selection matrix and SDBStateSnapshot code are concrete instantiations. Production validation: empirical evaluation on three real-world agent deployments described in paper.

## See also

- [S-1015 · The Stability Gradient](s1015-the-stability-gradient-when-your-agent-works-once-and-fails-twice.md) — nondeterminism sources in agent loops
- [S-1314 · The Pipeline Collapse Stack](s1314-the-pipeline-collapse-stack-when-multi-agent-handoffs-silently-fail.md) — boundary failures across agent hops
- [S-1412 · The Agent Evaluation Stack](s1412-the-agent-evaluation-stack-when-your-benchmarks-say-pass-but-production-fails.md) — pinned eval sets for regression across SDB changes
- [S-1054 · The Agent Interrupt Stack](s1054-the-agent-interrupt-stack-when-your-agent-is-going-off-rails-and-you-cant-stop-it-cleanly.md) — rollback semantics when SDB commit needs reversal
