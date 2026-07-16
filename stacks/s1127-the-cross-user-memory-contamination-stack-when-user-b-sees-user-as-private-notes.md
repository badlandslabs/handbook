# S-1127 · The Cross-User Memory Contamination Stack — When User B Sees User A's Private Notes

An AI agent serves multiple users. User A mentions sensitive information — a medical diagnosis, a salary negotiation, a strategic decision. User B starts a new session. The agent recalls that information unprompted, cites it as context, or references it in a completely unrelated task. No breach occurred in the traditional sense. The data never left the agent's memory store. But User B should never have had access to it. This is Cross-User Memory Contamination: the failure mode where a memory system designed to personalize agent behavior leaks private context between users because it has no concept of user identity as a partition boundary.

## Forces

- **Keyword retrieval has no concept of principal.** Most agent memory systems store facts and retrieve them via semantic similarity or keyword match. Neither operation checks whether the retrieving user is the same principal who wrote the memory. A query for "Q3 targets" matches User A's memory just as well as User B's — because the words match.
- **Multi-tenant deployment is the default, not the exception.** Claude Code, Codex, Copilot, OpenClaw, Bedrock AgentCore, Windsurf, Devin — the Mem0 2026 survey found 57–71% cross-user contamination across all eight major frameworks. This is not a niche edge case. It is the default behavior of systems built without principal-aware storage.
- **Agents amplify the contamination.** A traditional app with a SQL injection flaw can leak data — but the data is typically structured and bounded. An agent that has "remembered" User A's sensitive context will *reason with it*, incorporate it into task plans, surface it in responses, and pass it to downstream tools — all invisibly, all in natural language, all without an API call that triggers a conventional access-control log.
- **The contamination is invisible to existing monitoring.** CSP headers, API gateway logs, DLP scanners — none of them inspect a model's retrieved context. The leak happens entirely inside the context window, invisible to every traditional security control.

## The move

**1. Tag every memory entry with a principal identifier at write time.**

Every fact stored in memory gets a `principal_id` (user UUID, session token, or agent-instance ID). This is not a metadata field — it is a first-class partition key, enforced at the storage layer, not just in the retrieval prompt.

```python
from mem0 import MemoryClient

client = MemoryClient()

def store_fact(principal_id: str, user_message: str, assistant_response: str):
    # Tag with principal at write time — storage layer enforces partition
    memories = client.add(
        messages=[
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_response},
        ],
        user_id=principal_id,      # principal partition key
        metadata={
            "principal": principal_id,
            "classification": "private",  # or "shared", "system"
        }
    )
    return memories
```

**2. Enforce principal filter at retrieval — not in the prompt, in the query.**

The recall query must include the principal as a hard filter, not as a soft instruction in the prompt. This prevents the LLM from retrieving cross-principal memories through semantic drift or prompt injection.

```python
def recall_for_principal(principal_id: str, query: str, top_k: int = 10):
    # Hard filter in the query — not a soft instruction
    results = client.search(
        query=query,
        user_id=principal_id,       # principal filter — not optional
        top_k=top_k,
    )
    # Post-filter: discard any entry whose stored principal != requesting principal
    return [r for r in results if r.get("metadata", {}).get("principal") == principal_id]
```

**3. Partition memory by trust level — not a flat store.**

Separate the memory architecture into tiers with different trust levels:

| Tier | Content | Write Access | Read Access |
|------|---------|-------------|-------------|
| System | Tool configs, policies, system prompts | Admin only | All agents (read-only) |
| Shared | Team knowledge, norms, shared context | Any agent | Any user |
| User-private | Preferences, private facts, session context | Agent (per-user) | Only the owning user |
| Ephemeral | Working memory, current task state | Agent | Current session only |

**4. Add provenance to every retrieved memory.**

Before injecting retrieved memories into the context, log the source principal alongside the fact. This makes contamination detectable in traces.

```python
def build_context(principal_id: str, query: str) -> list[dict]:
    memories = recall_for_principal(principal_id, query)
    context = []
    for mem in memories:
        context.append({
            "content": mem["content"],
            "source": f"memory:{mem['metadata']['principal']}",
            "classification": mem["metadata"].get("classification", "unknown"),
        })
    return context

# In the agent loop:
context_chunks = build_context(current_user_id, current_query)
# Inject with provenance visible to both human reviewer and LLM
formatted = "\n".join(
    f"[From {c['source']} ({c['classification']}): {c['content']}]"
    for c in context_chunks
)
```

**5. Run a contamination audit before multi-tenant deployment.**

```python
def audit_cross_user_contamination(memory_client, test_principal_a, test_principal_b):
    """
    Store a unique marker in User A's memory.
    Attempt to retrieve it from User B's context.
    If it's retrieved — contamination confirmed.
    """
    marker = f"UNIQUE_MARKER_7X9Z_{test_principal_a}"

    # Store in A
    memory_client.add(
        messages=[{"role": "user", "content": f"Important: {marker}"}],
        user_id=test_principal_a,
    )

    # Try to retrieve from B's context
    results = memory_client.search(query=marker, user_id=test_principal_b, top_k=5)
    contaminated = [r for r in results if marker in r.get("content", "")]

    return {
        "contamination_detected": len(contaminated) > 0,
        "contaminated_memories": contaminated,
    }
```

> Receipt pending — 2026-07-15

## Why this is non-obvious

Most teams assume memory isolation is a configuration problem, not an architecture problem. They add "don't share memories across users" to the system prompt and consider it done. But prompts are not enforcement. An agent whose retrieval pipeline has no principal filter will surface cross-user memories the moment the query semantics overlap — which in natural language, happens constantly. The fix requires treating principal identity as a storage-level partition key, not a retrieval-time instruction.

## See also

- [S-1020 · The Tiered Memory Stack](stacks/s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — memory tier design
- [S-1065 · The Inter-Agent Trust Escalation Stack](stacks/s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — principal identity failures in multi-agent pipelines
- [S-1083 · The Platform Credential Boundary](stacks/s1083-the-platform-credential-boundary-when-your-agent-has-a-secret-second-identity-on-the-cloud-platform.md) — credential isolation as a related trust boundary
