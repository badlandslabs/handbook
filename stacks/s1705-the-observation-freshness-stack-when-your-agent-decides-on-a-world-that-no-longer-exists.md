# S-1705 · The Observation Freshness Stack — When Your Agent Decides on a World That No Longer Exists

Your agent reads the world, decides, and acts. The plan was perfect. The output was wrong. Not because the model hallucinated — because between the observation and the action, reality changed. A policy was updated. An inventory level shifted. A user cancelled. The agent's decision was made on a snapshot of a state that no longer exists. Every step in the chain was correct. The chain itself was stale.

This is not a reasoning failure. It is a **concurrency failure**: the observe-decide-act loop has no contract governing how old an observation can be before it stops authorizing action.

## Forces

- **Agent traces preserve what was returned, not what state produced it.** Content identity is easy to log. Version identity — which version of the resource generated the result — is almost never tracked. An agent that reads `account.balance = $500` has no idea if that figure was computed against the current ledger or a 40-minute-old snapshot.
- **The loop runs without boundary checks.** A ReAct loop continues until a termination condition fires. Nothing in the standard architecture checks whether the observations the agent is reasoning from are still valid. The world can change completely between step 3 and step 4 without the agent knowing.
- **"Live" is not the same as "fresh."** Calling a live API at 9:47am does not mean the data is current — it means the call succeeded. Many providers batch updates on 15-minute or hourly intervals. A stock price, a seat count, an inventory level, or a policy version can be stale for minutes or hours while the agent treats it as current.
- **Observation is conflated with fact.** The agent reads a value, reasons from it, and treats the resulting belief as grounded. But a retrieval result is not a fact — it is a claim about a state that existed when the claim was made. Most systems treat the distinction as irrelevant.
- **Post-action state revalidation is absent.** After an agent acts, nothing systematically re-reads the world to confirm that the preconditions for that action still hold. The agent trusts its own reasoning without checking whether the world agreed with the premises.

## The Move

### 1. Tag Every Observation with Version Identity

Distinguish three identities every observation carries:

| Identity | What It Tracks | Preservation Rate |
|---|---|---|
| **Content identity** | What value was returned | Most traces |
| **Resource identity** | Which object/endpoint was queried | Some traces |
| **Version identity** | Which state of that resource produced it | Almost none |

Add version headers or `observed_at` + `resource_version` stamps to every tool result. Before acting on any observation, check its age against the action's tolerance. A decision to ship an item requires knowing not just that inventory was ≥ 1, but *which* inventory snapshot that count came from.

```python
@dataclass
class TaggedObservation:
    value: Any
    resource_id: str          # which object was queried
    resource_version: str     # etag, sequence number, updated_at hash
    observed_at: datetime
    source: str               # tool or API name

def check_freshness(obs: TaggedObservation, max_age: timedelta) -> FreshnessStatus:
    age = now() - obs.observed_at
    if age > max_age:
        return FreshnessStatus.STALE  # re-observe before acting
    return FreshnessStatus.VALID
```

### 2. Enforce Precondition Windows Before Commit Actions

Classify agent actions by consequence severity. Read-only observations and idempotent reads tolerate stale data. Any action that modifies state — a payment, a reservation, a configuration change, a status update — requires a **freshness window**: a maximum acceptable age for the observations that authorized it.

The pattern is a **precondition header** on every mutating action: the agent stores the version identity of every resource it read as authorization for the action. Before committing, it re-reads those resources. If the version has changed, the precondition is invalidated and the agent must re-decide.

```
Step 12: Read inventory[SKU-7743] → count=3, version=v8921
Step 13: Decide: ship order → preconditions=[inventory[SKU-7743]=v8921]
Step 14: Pre-commit revalidation: inventory[SKU-7743] current version?
        → v8921 ✓ still valid → proceed
        → v8923 ✗ changed → abort, re-decide
```

This is optimistic concurrency control — the same pattern databases use to prevent lost updates — applied to the agent's reasoning chain.

### 3. Detect Version Conflicts Across Concurrent Agents

When two agents act on the same resource simultaneously, one will observe a state that the other has already changed. Without version tracking, the second agent proceeds on a stale premise and corrupts state. With version headers, the second agent's precondition check fails explicitly — it observes a version conflict, stops, and re-plans.

Tag resources with optimistic-locking version counters. If an agent's precondition version does not match the current version at commit time, surface the conflict as a structured error, not a silent override.

### 4. Bind Observations to Action Scopes

Not all observations need the same freshness. Distinguish:

- **Observation-scoped actions**: the decision depends only on this specific resource. Re-read immediately before commit.
- **Globally-scoped actions**: the decision depends on a consistent state across multiple resources. Require all involved resources to be re-read within the same freshness window, or use a distributed snapshot mechanism.
- **Idempotent reads**: no state modification. Accept higher staleness tolerance.

Annotate the agent's action plan with scope metadata so the runtime knows which observations to revalidate.

### 5. Surface Uncertainty When Freshness Cannot Be Proven

When revalidation fails — the resource is unavailable, the API has no version header, the network is degraded — the agent must surface uncertainty rather than proceed on assumption. This is not a fallback; it is the correct behavior when preconditions cannot be checked.

Explicitly log: `Precondition for action X could not be verified (resource Y unavailable). Acting on assumption.`

This creates an audit trail that distinguishes reasoned risk-taking from silent staleness-induced failure.

## References

- **rokoss21.tech** — "Freshness Contracts for AI Agent Decisions" (Jul 18, 2026) — concurrency failure framing, three identities of a result, precondition headers, version conflict detection
- **arxiv:2605.06527** — Chao et al., "STALE: Can LLM Agents Know When Their Memories Are No Longer Valid?" (May 2026) — implicit vs. explicit belief invalidation, memory staleness taxonomy
- **S-100** — Live Data Freshness Contracts — data-level freshness stamps; this entry covers *observation-level* freshness for agent decision authorization
- **S-1239** — Runtime Verification Loop — inline step verification; this entry covers *pre-decision* state validity, not post-decision correctness
- **S-1320** — The Dead End Stack — stuck loops from inability to recover; this entry covers the opposite failure: smooth execution on wrong premises

## Deduplication

- **vs. S-1063 (Context Lifecycle):** Context lifecycle covers memory management within the agent's context window. Observation freshness covers whether the *world state* the agent observed is still current — a different boundary (the agent's memory vs. the external world's state).
- **vs. S-1022 (Agent Drift):** Agent drift covers gradual degradation in multi-agent systems over time. Observation freshness covers single-action concurrency failures where the world changes between observe and act within one agent's run.
- **vs. S-100 (Live Data Freshness Contracts):** S-100 covers data-level freshness — timestamps and staleness detection on API responses. This entry covers decision-level freshness — whether observations authorize specific actions — and adds the version-identity + precondition revalidation pattern.
