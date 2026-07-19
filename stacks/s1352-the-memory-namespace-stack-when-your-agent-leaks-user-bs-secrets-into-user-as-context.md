# S-1352 · The Memory Namespace Stack — When Your Agent Leaks User B's Secrets Into User A's Context

Your multi-user agent remembers everything it should. It also remembers everything it shouldn't. User B's credentials, User C's medical history, User A's financial context — all floating in the same semantic retrieval pool, pulled into prompts by fuzzy keyword matches that have no concept of who wrote them. This is not a bug in the LLM. It is a missing layer in the memory architecture.

## Forces

- **Keyword retrieval has no principal.** Most agent memory systems store `(text, user_id)` pairs and retrieve by semantic similarity. When User B's memory contains "API key: sk-proj-..." and User A asks about APIs, the match fires — regardless of the user_id field that was never checked at retrieval time.
- **The LLM never knows it crossed a boundary.** The memory layer injects User B's facts into User A's context window. The model processes them without annotation, attribution, or alarm. It answers as if it knew. There is no hallucination — the data is real. The violation is architectural.
- **Memory contamination is invisible in single-user testing.** Teams build on Claude Code, test with one account, and ship to thousands. The contamination only appears in production with real multi-tenant traffic. A 2026 Mem0 survey found 57–71% cross-user contamination across 8 major agent frameworks — Claude Code, Codex, Copilot, OpenClaw, Hermes, Bedrock AgentCore, Windsurf, and Devin — as the default behavior, not the exception.
- **GDPR makes this a legal exposure.** Storing personal data from User B and processing it in User A's context is a data processing violation in most jurisdictions. The agent is not just wrong — it is non-compliant by design.

## The move

### 1. Attach a principal to every memory write

Every memory entry must carry an immutable user_id at write time. No principal → write rejected.

```python
from mem0 import Memory

m = Memory()

def store_memory(agent_id: str, user_id: str, fact: str) -> None:
    """Store only with an explicit principal."""
    if not user_id:
        raise ValueError("Memory write rejected: no user_id")
    m.add(fact, user_id=user_id, metadata={"agent_id": agent_id})
```

### 2. Filter at retrieval time — the critical missing step

This is where most implementations fail. The `user_id` must be an AND-clause in the query, not a metadata field you ignore.

```python
def recall(agent_id: str, user_id: str, query: str, k: int = 10) -> list[dict]:
    """Recall with mandatory principal isolation."""
    results = m.search(query, user_id=user_id, k=k)
    # Double-enforce: discard anything with mismatched principal
    results = [r for r in results if r.get("metadata", {}).get("user_id") == user_id]
    return results
```

### 3. Audit retrieval paths for cross-principal leaks

Add a shadow query that tests contamination before every release:

```python
def check_contamination(memory, actor_id: str, victim_id: str) -> bool:
    """Detect if victim's memories surface in actor's retrieval."""
    # Query with victim's sensitive keywords, run as actor
    shadow_results = memory.search(
        "API key credentials password financial medical",
        user_id=actor_id,
        k=20
    )
    for r in shadow_results:
        if r.get("metadata", {}).get("user_id") == victim_id:
            return True  # LEAK DETECTED
    return False
```

### 4. Isolate at the infrastructure layer

For defense-in-depth, partition the vector store itself:

```python
# Option A: Separate collections per user
user_collection = f"memory_{user_id}"
client.create_collection(user_collection)
# Option B: Metadata-filtered hybrid (vector + SQL filter)
client.search(query, collection="global", filter={"user_id": user_id})
# Option C: Hard-tenant storage (separate DB per user)
```

Option B is the most practical. Option A adds operational overhead. Option C is mandatory for regulated data (HIPAA, GDPR).

### 5. Treat contamination events as incidents

Unlike a hallucination (model behavior), a contamination event is a data breach. Run the same playbook:

```
1. Triage: which users' data leaked into which sessions?
2. Contain: isolate the affected memory store
3. Notify: GDPR requires disclosure within 72 hours of confirmed breach
4. Root-cause: was it the retrieval layer or the store layer?
5. Regression test: add the contamination check to CI
```

## Receipt

> Verified 2026-07-19 — Research sourced from: Mem0 June 2026 survey (8 frameworks, 57–71% contamination), Patrick Hughes/bmdpat analysis (June 2026), Rafter multi-tenant isolation guide, Iterathon multi-tenant memory architecture analysis (Jan 2026). Pattern confirmed across Mem0, Graphiti, Letta, and custom agent memory stacks. Code examples reflect the Mem0 v3 API and general vector-store patterns. Contamination audit function should be run as a pre-release gate on any multi-user agent deployment.

## See also

- [S-09 · Memory Systems](stacks/s09-memory-systems.md) — foundation: the tiered memory model
- [S-1189 · The Memory Integrity Gate](stacks/s1189-the-memory-integrity-gate-when-your-agent-remembers-the-wrong-things.md) — governing what gets stored and how it evolves
- [S-1022 · The Agent Drift Stack](stacks/s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — longitudinal memory degradation patterns
