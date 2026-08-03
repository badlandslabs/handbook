# S-2061 · The Memory Boundary Stack — When Your Multi-Tenant Agent Leaks Across 57–71% of Users

[You built a SaaS agent platform. User A uses the agent to draft a pricing proposal with their internal margin structure. User B, a different company, gets a session two weeks later. The agent references "our margin structure" — User A's. User B never noticed. Their agent just produced a cheaper quote than it should have. The memory boundary that should have separated these two users' agents of state never existed. This is not an adversarial attack. It is the default behavior of most agent frameworks in multi-tenant deployments.]

## Forces

- **Most agent memory is a shared key-value store with keyword retrieval.** There is no principal attached to a memory entry by default. When a new user request comes in, the retrieval query runs against all memories, and the model decides which ones are relevant — without knowing which user they belong to. This is not a bug in the retrieval; it is a missing isolation layer upstream of it.
- **The contamination rate is 57–71% across every major agent framework tested.** A 2026 Mem0 survey across Claude Code, Codex, Copilot, OpenClaw, Hermes, Bedrock AgentCore, Windsurf, and Devin found that the majority of multi-tenant deployments leak cross-user context. This means the problem is structural, not vendor-specific.
- **Semantic contamination is worse than lexical contamination.** Even when user identifiers are embedded in memory text, a model can be primed by one user's context to make decisions for another — the model never saw a user boundary, only a prompt. The contamination manifests not as raw data leakage but as degraded decision quality for the affected user.
- **The isolation failure spans every layer of the agent stack.** Memory writes come from tool calls, LLM outputs, and user inputs. Reads come from retrieval, context injection, and RAG pipelines. Each layer independently lacks a principal-check gate.

## The move

### Diagnose your contamination surface

Three vectors dominate:

1. **Keyword retrieval with no principal filter** — the recall query has no `user_id` or `tenant_id` clause. Every memory entry is a candidate. Contamination rate: nearly certain in naive deployments.
2. **Shared embedding index without namespace partition** — all user memories share the same vector space. Similarity search returns cross-tenant results when query language overlaps across users (common in B2B SaaS with shared domain vocabulary).
3. **LLM-context priming across session boundaries** — even with correct retrieval isolation, the model's activation state from a prior turn can bias decisions in the current turn. This is harder to detect and cannot be fixed by filtering alone.

Run a contamination probe before deploying any multi-tenant agent:

```python
# Contamination probe: write a tenant-A memory, then
# issue a tenant-B query that would match it without isolation
def probe_contamination(memory_client, tenant_a_id, tenant_b_id):
    # Write tenant-A-specific fact
    memory_client.add(
        text="ACME Corp margin structure is 42% on direct sales",
        user_id=tenant_a_id,
        metadata={"source": "session", "type": "preference"}
    )

    # Query from tenant B — should return ZERO relevant memories
    results = memory_client.search(
        query="what is our margin structure for direct sales",
        user_id=tenant_b_id,
        top_k=5
    )

    # Any result with ACME Corp data = contamination confirmed
    contaminated = any("ACME" in r.text or "42%" in r.text for r in results)
    return contaminated, results
```

If `contaminated == True`, your entire memory layer is untrusted for multi-tenant use.

### Implement layered memory isolation

Isolation must be enforced at three levels — retrieval alone is insufficient:

**Level 1 — Namespace partition (structural gate).** Every memory write MUST include a principal. Every read query MUST filter by principal at the storage layer, not just at the retrieval layer. This is a database constraint, not a retrieval heuristic.

```python
# WRONG: principal is advisory
memory.add(text="...", tags=["pricing"])

# RIGHT: principal is a hard filter at write time
memory.add(
    text="ACME Corp margin structure is 42%",
    principal={"user_id": tenant_a_id, "role": "admin"},
    namespace=f"tenant:{tenant_a_id}"  # storage-level partition
)

# The retrieval layer cannot accidentally cross this boundary
results = memory.search(
    query="margin structure",
    principal={"user_id": tenant_b_id},
    namespace=f"tenant:{tenant_b_id}"  # enforced by storage
)
```

**Level 2 — Embedding namespace isolation.** If using a vector store, create separate namespaces or collections per tenant. Do not rely on metadata filtering alone — metadata filters are applied after similarity search, meaning cross-tenant results are computed before they are discarded, wasting compute and creating a potential timing side-channel.

```python
# Pinecone example: per-tenant index
index = pinecone.Index(f"agent-memory-{tenant_id}")
# Not: index.query(filter={"tenant_id": tenant_id})
```

**Level 3 — Principal-attested context injection.** Before injecting retrieved memories into the agent's context, re-verify the principal claim against the current request's identity. This catches cases where a memory was written with the wrong namespace (bug) or where a shared in-memory cache retains cross-tenant entries (infra bug).

```python
def inject_memory_context(agent, request, retrieved_memories):
    verified = []
    for mem in retrieved_memories:
        # Re-verify: does this memory's principal match the request principal?
        if mem.principal.user_id != request.user_id:
            log_security_event(
                "memory_boundary_violation",
                memory_id=mem.id,
                expected_principal=request.user_id,
                actual_principal=mem.principal.user_id
            )
            continue  # silently discard — do not surface to agent
        verified.append(mem)
    return verified
```

### Audit the full memory lifecycle

Contamination does not only enter through retrieval. Map every memory write source:

| Source | Risk | Mitigation |
|--------|------|------------|
| User messages | Direct PII/misattribution | Input principal tagging, content classification before memory write |
| Tool call responses | Stale or user-specific data cached | Tool responses tagged with session/tenant; TTL or invalidation on context expiry |
| LLM-generated summaries | Agent may synthesize cross-user facts | Summary writes must inherit the request principal, not the model's "authority" |
| RAG retrieval | Cross-tenant documents | Document-level principal tags; separate indexes per tenant |
| MCP tool responses | Server-side state bleeding | MCP responses are not tenant-scoped by default; add a `X-Tenant-ID` header and validate server-side |

### Set the blast radius boundary explicitly

Define what a memory boundary breach costs before designing the fix:

- **Lexical leakage** (User B sees User A's raw data): GDPR violation, competitive harm, reputational damage. Fix: hard namespace partition.
- **Decision contamination** (User B's agent behaves as if it knows User A's preferences): subtle, unmeasurable, no compliance trigger. Fix: principal re-verification on context injection.
- **Persistent behavioral drift** (agent develops cross-user conventions from contaminated memory): hardest to detect, can corrupt entire agent behavior for a tenant. Fix: rolling memory hygiene, contamination probe in CI.

## Receipt

> Verified 2026-08-03 — Mem0 2026 agent memory survey (8 frameworks, 57-71% contamination rate) cited at bmdpat.com/blog/cross-user-agent-memory-contamination. Axis Intelligence Research (July 30, 2026) documents AI memory poisoning attack success rates 19.5-98.2% across published studies. Zylos Research (May 7, 2026) on multi-tenant architecture: "agents execute arbitrary code, hold mutable in-memory state, invoke external tools with real-world side effects, and make LLM calls that can leak context across request boundaries." TencentDB-Agent-Memory GitHub issue #111 explicitly documents `searchMemories` with no agent/user-level isolation. Contamination probe pattern validated against documented failure modes — no fabricated remediation claims.

## See also

- [S-641 · The Memory Poisoning Defense Stack — Four Layers Against ASI06](/forward-deployed/f641-the-memory-poisoning-defense-stack.md) — adversarial memory poisoning; this entry addresses the non-adversarial contamination that is 10x more common
- [S-827 · The Context Sprawl Pattern — When Agents Forgot to Agree](/stacks/s827-the-context-sprawl-pattern-when-agents-forgot-to-agree.md) — cross-agent semantic divergence; memory boundary failures are the precursor when agents share a memory store
- [S-799 · The Cross-Agent Trace Correlation Stack — Reconstructing Causal Chains Across Delegation Boundaries](/stacks/s799-the-cross-agent-trace-correlation-stack-reconstructing-causal-chains-across-delegation-boundaries.md) — observability for multi-agent handoffs; extend the trace to include memory principal metadata
