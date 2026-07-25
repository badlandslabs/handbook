# S-1575 · The Memory Pointer Pattern — When Your Tool Outputs Cost More Than Your Model

A tool returns 20,000 tokens of JSON. Your model has a 200K context. The call "succeeds." The agent processes it. Then at message 47, quality silently degrades — the agent's responses get shorter, it drops references to earlier tool results, it starts repeating itself. No error fires. The model technically has access to everything. It just doesn't attend to it.

Large tool outputs are the fastest-growing context consumer in agentic systems, and the standard pattern — dump the output into the prompt — hits a hard ceiling at 60-80% context fill where quality degrades silently before any exception fires.

## Forces

- **Token cost compounds non-linearly** — doubling output size doesn't double cost, it doubles context pressure on every subsequent turn for the remainder of the session
- **Context quality degrades before the limit** — the "lost in the middle" problem intensifies as context grows; a 200K context with 80K of tool JSON performs worse than a 100K context with 5K
- **Hard overflow failures are rare in practice** — most truncation is silent: the model continues, but earlier context gets progressively weighted lower
- **The model doesn't know what it needs** — it receives the full output but only reads parts; there's no mechanism for it to say "summarize rows 10-20 of this table"

## The move

The Memory Pointer Pattern offloads large tool outputs to external content-addressable storage, replacing raw tokens in the context with lightweight pointer references. The model receives a summary of what the pointer refers to, and can request full materialization on demand.

Key results from arxiv 2511.22729 (Bulle Labate et al., IBM Research, 2025): this approach reduced LongFuncEval failure rate from 91% to under 5%, with ~7x token reduction enabling workflows that previously required 200K+ context windows to run on 32K context models.

**Architecture:**

```
Tool call fires
       ↓
Tool executor runs
       ↓
Output exceeds threshold? (default: 4K tokens)
       ↓ yes
Store in external cache (Redis/S3/DB) with content hash
       ↓
Return { "type": "pointer", "ref_id": "sha256:abc123",
         "summary": "50-row JSON array of user records",
         "materialize_endpoint": "/context/materialize/{ref_id}",
         "token_cost_saved": 48500 } to model
       ↓ no
Return raw output (unchanged behavior)
```

**On-demand materialization:**

The model decides what to retrieve. A tool output of 50,000 tokens that the model reads at 200-token precision summary costs ~200 tokens of context pressure instead of 50,000. The model's materialization request becomes a signal for what it actually needs to reason about.

```python
import hashlib, json
from functools import wraps
from typing import Any

# External store: Redis, S3, or any K/V store with TTL
_context_store: dict[str, dict] = {}
_POINTER_SUMMARY_MAX = 256  # tokens kept in context per pointer
_MODEL_CONTEXT_BUDGET = 160_000  # your model's effective context

class ToolOutputPointer:
    """A lightweight reference to a tool output stored externally."""
    def __init__(self, ref_id: str, summary: str,
                 materialize_fn: str, content_type: str, size_k: int):
        self.ref_id = ref_id
        self.summary = summary
        self.materialize_fn = materialize_fn
        self.content_type = content_type
        self.size_k = size_k  # original size in tokens

    def materialize(self, selection: str | None = None) -> Any:
        """Fetch full or partial content from external store."""
        raw = _context_store[self.ref_id]["content"]
        if selection:
            # Let the model specify row ranges, keys, etc.
            return self._slice(raw, selection)
        return raw

    def _slice(self, raw: Any, selection: str) -> Any:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, list):
                # selection like "rows 10-30" or "filter status=active"
                return data[10:30]  # simplified
            return data
        except Exception:
            return raw  # fall back to full on parse failure


def tool_with_pointer(threshold_tokens: int = 4096):
    """Decorator: store large tool outputs externally, pass pointer to model."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)

            # Estimate token count (rough: 4 chars per token)
            serialized = json.dumps(result, default=str)
            estimated_tokens = len(serialized) // 4

            if estimated_tokens <= threshold_tokens:
                return result

            # Generate content-addressable reference
            ref_id = hashlib.sha256(serialized.encode()).hexdigest()[:16]
            _context_store[ref_id] = {
                "content": result,
                "original_fn": fn.__name__,
                "size_tokens": estimated_tokens,
            }

            # Build summary for model (model reads this, not the raw output)
            summary = _build_summary(result, max_tokens=_POINTER_SUMMARY_MAX)

            return ToolOutputPointer(
                ref_id=ref_id,
                summary=summary,
                materialize_fn=f"materialize_pointer('{ref_id}')",
                content_type=type(result).__name__,
                size_k=estimated_tokens // 1000,
            )
        return wrapper
    return decorator


def _build_summary(result: Any, max_tokens: int = 256) -> str:
    """Extract a lightweight description for the model context."""
    if isinstance(result, list):
        return f"[{len(result)} items]: first item keys={list(result[0].keys()) if result else []}"
    if isinstance(result, dict):
        return f"dict with keys={list(result.keys())}"
    if isinstance(result, str):
        return result[:512] + ("..." if len(result) > 512 else "")
    return f"{type(result).__name__}, len={len(str(result))}"


# --- Usage ---
@tool_with_pointer(threshold_tokens=4096)
def query_database(sql: str) -> list[dict]:
    """Tool: executes SQL, returns rows. Large result sets get pointers."""
    # Actual DB call here
    rows = [{"id": i, "name": f"user_{i}", "status": "active"} for i in range(5000)]
    return rows


def materialize_pointer(ref_id: str, selection: str = None) -> Any:
    """Tool: fetches materialized content from pointer reference."""
    if ref_id not in _context_store:
        raise ValueError(f"Pointer {ref_id} not found or expired")
    ptr = ToolOutputPointer(
        ref_id=ref_id, summary="", materialize_fn="", content_type="", size_k=0
    )
    return ptr.materialize(selection)
```

## Receipt

> Receipt pending — 2026-07-24

Core pattern validated against: arxiv 2511.22729 (LongFuncEval benchmark, IBM Research), AWS samples repo (context-overflow-demo), Redis context overflow analysis. Pattern is production-deployed at multiple shops per practitioner reports on HN/Reddit r/LocalLLaMA. The ~7x token reduction figure and 91%→5% failure rate reduction come from the arxiv paper's controlled evaluation on the LongFuncEval benchmark. Full end-to-end run with production tool traces not yet executed in this handbook's environment.

## See also

- [S-1244 · The Context Fill Cliff](stacks/s1244-the-context-fill-cliff-when-your-agent-runs-great-at-message-5-and-terrible-at-message-50.md) — message-count degradation pattern; this entry is the tool-output complement
- [S-757 · Token Budget as Architecture](stacks/s757-the-token-budget-as-first-class-architecture-phase-allocation-pattern.md) — budget enforcement as architectural constraint; memory pointers reduce burn rate
- [S-1567 · The Tool Explosion Stack](stacks/s1567-the-tool-explosion-stack-when-your-agent-has-300-tools-and-uses-none-of-them-right.md) — tool output quality and selection; pointers address the retrieval problem that explosion creates
- [S-100 · Agentic RAG](stacks/s100-agentic-rag.md) — retrieval as first-class pattern; pointers extend the same principle to tool outputs
