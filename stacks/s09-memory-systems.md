# S-09 · Memory Systems

What persists between LLM calls — and how to make agents remember things without stuffing everything in context.

## Forces
- LLMs are stateless by default — each call starts fresh
- Stuffing all history into context gets expensive and hits limits fast
- You need some memory to be fast (sub-millisecond), some to be rich (semantic search)
- Wrong memory architecture makes agents either amnesiac or slow

## The move

**Three tiers of agent memory:**

### Tier 1: In-context (fastest, most expensive at scale)
The conversation history, injected directly. Use for: the current session, short task state.  
Limit: whatever fits in the window. Prune old turns aggressively.

### Tier 2: File / key-value (fast, structured)
Persist state to disk or a database between sessions. Use for: user preferences, task progress, known facts.
```python
import json, pathlib

def save_memory(key: str, value: dict, path="memory.json"):
    store = json.loads(pathlib.Path(path).read_text()) if pathlib.Path(path).exists() else {}
    store[key] = value
    pathlib.Path(path).write_text(json.dumps(store, indent=2))

def load_memory(key: str, path="memory.json") -> dict:
    store = json.loads(pathlib.Path(path).read_text()) if pathlib.Path(path).exists() else {}
    return store.get(key, {})
```

### Tier 3: Vector / semantic (richest, highest latency)
Embed facts and retrieve by semantic similarity. Use for: large personal knowledge bases, long-running agents with thousands of memories.  
Tools: Chroma (local), pgvector (Postgres), Pinecone (hosted).

**Dual-tier production pattern:**
- Hot path: in-context + key-value (fast)
- Cold path: vector search for older, large, or fuzzy memories
- Write to both; read hot path first, fall back to cold

**Forgetting is a feature:** not everything needs to be remembered. Decide on a TTL and eviction policy, or your memory grows without bound.

## Receipt
> Receipt pending — 2026-06-25. File-based pattern above is minimal Python; test it. Vector DB integrations vary by provider — verify current API shapes before use.

## See also
[S-07](s07-rag.md) · [S-17](s17-embeddings.md) · [S-02](s02-context-budget.md) · [S-05](s05-multi-agent-patterns.md)

## Go deeper
Keywords: `agent memory` · `Mem0` · `Letta` · `Zep` · `episodic memory` · `semantic memory` · `pgvector` · `Chroma`
