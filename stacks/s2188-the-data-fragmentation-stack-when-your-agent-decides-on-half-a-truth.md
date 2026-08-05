# S-2188 · The Data Fragmentation Stack — When Your Agent Decides on Half a Truth

Your customer-service agent is live. It can access your CRM and your support ticket system. It cannot access your product catalog, your order management system, or your billing API. A customer asks about a delayed international order — the agent sees the open ticket, pulls the CRM contact, and confidently tells the customer their order will arrive Thursday. The order was cancelled three days ago. The agent never saw the cancellation. It wasn't wrong by model standards. It was wrong by data standards.

This is the data fragmentation stack: the failure mode where an agent makes a decision that is locally consistent but globally false because it operated on a partial, stale, or systemically incomplete view of the world.

## Forces

- **Agents reason over context, not systems.** An agent with access to N systems reasons correctly about the union of what it retrieved — not about what it failed to retrieve. Missing data looks identical to true negatives in a retrieval system. The agent has no concept of "systems I cannot see."
- **Partial data is worse than no data.** A no-data response triggers human escalation or explicit uncertainty. Partial data triggers confident wrong answers. The agent acts on what it has, not on what it is missing.
- **Data boundaries do not map to task boundaries.** A customer task spans billing, orders, support, and product — four systems with four schemas, four auth contexts, and four update frequencies. Agents are task-oriented. Data is system-oriented. The mismatch is structural.
- **Fragmentation compounds with autonomy.** A human agent cross-referencing two systems does so consciously and notices contradictions. An agent auto-retrieving from three systems silently picks the most recent or most confident result when sources disagree.

## The Move

**1. Map the data topology before you build the agent.**
Before defining tools, document which systems contain ground-truth state for each entity type the agent touches. For a customer entity: CRM (contact), billing (payment status), orders (fulfillment state), support (ticket state). Every system that can contradict another system is a data boundary you must make visible to the agent.

**2. Explicitly name "absence" as a signal.**
When an agent's retrieval step yields no results, do not treat this as a neutral outcome. Return a structured `retrieval_status: "not_found" | "unauthorized" | "out_of_scope"` field alongside any results. Instruct the agent to treat `not_found` on a critical entity type as a reason to pause and either re-route or declare uncertainty — not a green light to proceed on remaining context.

```python
@dataclass
class RetrievalResult:
    data: Any
    status: Literal["found", "not_found", "unauthorized", "out_of_scope", "stale"]
    source_system: str
    entity_type: str
    last_updated: datetime | None

def query_agentic(customer_id: str, query: str) -> AgentResponse:
    results = [retrieve(entity_type=e, customer_id=customer_id) for e in ENTITY_TYPES]

    # Key: surface absence explicitly
    absent_systems = [r.source_system for r in results if r.status != "found"]

    if absent_systems:
        # Flag the data boundary to the agent
        agent_context = f"[DATA BOUNDARY] Could not retrieve from: {absent_systems}. "
        agent_context += "Proceed only if query does not require these systems. "
        agent_context += "If the question requires absent systems, respond: Unable to determine — data access incomplete."

    # Continue with agent reasoning over results + boundary signal
    ...
```

**3. Implement cross-system contradiction detection.**
Store a `last_checked` timestamp per system per entity. Before the agent produces a final decision, run a lightweight consistency check: if the support system shows an open ticket and the orders system shows "cancelled" for the same order_id, surface this as a `CONTRADICTION` event before the agent produces its response.

**4. Govern agent autonomy by data completeness.**
Define a `required_systems` tag on every agent task. A task tagged `requires=[billing, orders, support]` cannot produce a final answer until all three return `status="found"`. If any required system returns `not_found` or `unauthorized`, route to human escalation instead of proceeding with partial data.

**5. Design the data mesh for agents, not just humans.**
Treat agent data access as a first-class API design problem. Create an agent-facing aggregation layer — a single `customer_context` endpoint that returns a merged, timestamped view across all relevant systems, with a `completeness_score` field (0.0–1.0) indicating what fraction of relevant systems were reachable. The agent queries one endpoint; the endpoint handles the fragmentation internally.

## Receipt

> Verified 2026-08-05 — Draft written from cross-source synthesis: Airbyte agent connector research (2026), AgentMarketCap tool-call failure data (April 2026), aiautomationglobal pilot failure analysis (March 2026), agILITY-at-Scale enterprise agent challenges (2026), and Zylos Research agent observability framework. No live system run. Receipt pending.

## See also

- [S-1057 · The Tool-Call Hallucination Plateau](/stacks/s1057-the-tool-call-hallucination-plateau-when-your-agent-gets-20-percent-of-tool-invocations-wrong-in-production.md) — wrong tool calls compound similarly to partial data
- [S-1001 · The Agent Evaluation Stack](/stacks/s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — production failures that eval misses often stem from data boundary conditions
- [S-1019 · The Three-Pillar Observability Stack](/stacks/s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — traces help detect which system the agent never queried
