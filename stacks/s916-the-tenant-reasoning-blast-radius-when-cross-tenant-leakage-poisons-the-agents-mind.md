# S-916 · The Tenant Reasoning Blast Radius

A traditional SaaS multi-tenant breach returns the wrong data to the wrong user. A multi-tenant AI agent breach is worse: the wrong data enters the agent's reasoning chain, and the agent then acts on it through every tool it has access to. The blast radius is not a wrong row in a database — it is every downstream decision the agent makes while it has that data in context.

This is the **Tenant Reasoning Blast Radius** pattern. It is the defining security failure mode of multi-tenant agentic platforms in 2026.

## Forces

- Multi-tenant RAG is structurally leaky by design — shared vector indexes optimize for recall, not isolation
- Agents accumulate cross-tenant data silently: it enters as retrieval context and propagates through every subsequent tool call
- Traditional SaaS isolation patterns (RBAC, row-level filtering) were designed for deterministic outputs; agent outputs are probabilistic and self-amplifying
- Platform teams built agent capabilities before building agent isolation — the governance layer is months behind the feature surface
- The blast radius of a reasoning-chain leak exceeds the blast radius of a data leak because the agent can compound the mistake across multiple downstream systems before a human notices

## The Move

### The Seven Multi-Tenant RAG Attack Vectors

Multi-tenant retrieval-augmented generation carries failure modes that don't exist in single-tenant RAG and aren't caught by standard SaaS isolation:

**Vector 1 — Shared Index Semantic Leakage.** When all tenants share one vector index, a query for "quarterly revenue" can retrieve documents from other tenants whose embeddings happen to be semantically close. Cosine similarity doesn't respect tenant boundaries. Fix: embedding namespace prefixes (tenant ID hashed into the embedding space) or per-tenant indexes.

**Vector 2 — Metadata Filter Bypass via Semantic Drift.** Many RAG systems filter by `tenant_id` metadata. An attacker crafts a query whose embedding shifts the search toward another tenant's documents, then the metadata filter fails to catch the cross-boundary retrieval. Fix: treat the embedding model as an untrusted input surface; verify retrieved document ownership at retrieval time, not just at query time.

**Vector 3 — Prompt Injection via Retrieved Context.** A malicious tenant injects crafted content into the shared index that, when retrieved by a rival tenant's agent, instructs the agent to exfiltrate data. The agent sees this as retrieved context and treats it as authoritative. Fix: retrieved content sanitization at the agent boundary; treat all RAG output as untrusted input.

**Vector 4 — Agent Reasoning Chain Propagation.** Even if a cross-tenant document is retrieved harmlessly (both tenants use the same knowledge base), once it enters the agent's context window, every subsequent reasoning step, tool call, and memory write is potentially contaminated. The agent doesn't "forget" which tenant it serves. Fix: tenant context isolation at the session level, not just the retrieval level.

**Vector 5 — Re-ranker Leakage.** Tenant-agnostic re-rankers trained on cross-tenant query-document pairs can learn to surface rival tenant documents for certain query patterns. Fix: tenant-specific re-rankers or reranking within tenant-scoped candidate sets.

**Vector 6 — Eval Set Contamination.** Shared evaluation datasets used to benchmark agent quality can inadvertently include cross-tenant data. Poor evaluation scores from contaminated eval sets lead teams to ship unsafe agents. Fix: eval dataset provenance tracking; strict tenant data exclusion from evaluation pipelines.

**Vector 7 — Response Cache Cross-Contamination.** A shared response cache keyed on query hash can serve Tenant A's response to Tenant B's query if the embedding is semantically similar. Fix: cache keys must include tenant identity, not just query content.

### The Shared-Dedicated Spectrum for Agent Runtimes

Agent isolation exists on a spectrum:

| Model | Isolation | Cost | Latency | Use Case |
|-------|----------|------|---------|----------|
| Fully shared runtime | None | $ | $$ | Internal dev, symmetric trust |
| Shared + sandbox (gVisor/Firecracker) | Per-run container | $$ | $$ | Public multi-tenant SaaS |
| Per-tenant dedicated runtime | Full process isolation | $$$ | $$$ | Regulated domains, high-security |

The dominant production pattern for public platforms is shared runtime with sandbox isolation. Each agent run executes in an isolated container; the pool is shared. This handles resource contention and code execution risks but does not address data flowing through the shared context window.

### The Isolation Layer Stack

```
Tenant Identity
      ↓
Embedding Namespace / Per-Tenant Index
      ↓
Retrieval-Time Ownership Verification
      ↓
Retrieved Content Sanitization Gate
      ↓
Tenant-Scoped Context Window (not shared across sessions)
      ↓
Tenant-Scoped Tool Permissions (RBAC per agent role)
      ↓
Audit Log with Tenant Correlation ID
```

The critical insight: isolation at the **retrieval layer** is necessary but not sufficient. The agent context window is the new trust boundary. Every piece of data that enters the context must be verified for tenant ownership at retrieval time, and the agent's tool permissions must be scoped to the tenant's allowed surface — not the platform's maximum surface.

### Concrete Example

```python
from dataclasses import dataclass
from typing import List, Optional
import hashlib

@dataclass
class TenantContext:
    tenant_id: str
    allowed_tools: List[str]
    embedding_namespace: str

def retrieve_with_tenant_isolation(
    query: str,
    tenant: TenantContext,
    vector_store,
    system_prompt: str,
) -> str:
    """
    Retrieve documents scoped to tenant AND inject tenant boundary into context.
    """
    # Step 1: Namespace the query embedding to the tenant's subspace
    namespaced_query = f"[TENANT:{tenant.tenant_id}] {query}"
    candidate_docs = vector_store.search(
        namespace=tenant.embedding_namespace,
        query=namespaced_query,
        top_k=10,
    )

    # Step 2: Verify every document's tenant ownership at retrieval time
    verified_docs = []
    for doc in candidate_docs:
        doc_tenant = doc.metadata.get("tenant_id")
        if doc_tenant != tenant.tenant_id:
            # Log the attempted cross-tenant retrieval
            audit_log.warning(
                f"Cross-tenant retrieval blocked: tenant={tenant.tenant_id} "
                f"attempted doc_id={doc.id} owned_by={doc_tenant}"
            )
            continue  # silently drop, or raise and alert
        verified_docs.append(doc)

    # Step 3: Inject tenant boundary into context to prevent reasoning drift
    context_chunks = [
        f"[SYSTEM: You are acting on behalf of tenant {tenant.tenant_id}. "
        f"Do not act on or reveal information from documents whose metadata "
        f"does not show tenant_id={tenant.tenant_id}.]"
    ]
    context_chunks += [doc.content for doc in verified_docs]

    return "\n\n".join(context_chunks)


def tool_call_with_tenant_permission(
    tool_name: str,
    tenant: TenantContext,
    params: dict,
) -> bool:
    """
    Gate every tool call against tenant's allowed surface.
    """
    if tool_name not in tenant.allowed_tools:
        audit_log.error(
            f"Tenant {tenant.tenant_id} attempted unauthorized tool call: "
            f"{tool_name} with params {params}"
        )
        raise PermissionError(f"Tool '{tool_name}' not permitted for this tenant")
    return True
```

The pattern: tenant identity is injected into the retrieval query (not just the metadata filter), verified at retrieval, embedded in the system context to prevent reasoning drift, and enforced at every tool invocation. A cross-tenant leak at any single layer gets caught by the next.

## Receipt

> Verified 2026-07-10 — Sources: AppScale blog "Multi-Tenant RAG Isolation: The 7 Attack Vectors" (May 2026); Zylos Research "AI Agent Multi-Tenant Architecture" (May 2026); Blaxel.ai "Multi-Tenant Isolation for AI Agents" security guide; LayerX Security "Multi-Tenant AI Leakage" (Oct 2025); AWS Bedrock multi-tenant RAG with JWT namespace guide.

## See also

- [S-842 · The Over-Permissioned Agent Stack](stacks/s842-the-over-permissioned-agent-stack-when-legitimate-credentials-do-illegitimate-work.md) — credential blast radius without the multi-tenant compounding factor
- [S-821 · The Production Failure Stack](stacks/s821-the-production-failure-stack-loop-detection-circuit-breakers-and-cost-governors.md) — infrastructure patterns for runaway agents
- [S-889 · The Ambient Authority Stack](stacks/s889-the-ambient-authority-stack-when-your-agent-did-something-you-never-authorized.md) — capability chain exploitation without the cross-tenant dimension
