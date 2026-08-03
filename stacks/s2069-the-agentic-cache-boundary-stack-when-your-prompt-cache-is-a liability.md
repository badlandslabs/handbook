# [S-2069] · The Agentic Cache Boundary Stack

*When including tool results in your prompt cache makes agents slower and more expensive — not faster. Cache boundary placement is now a first-class architectural decision, not a configuration afterthought.*

You enabled prompt caching. You put your entire conversation history — system prompt, tool definitions, all accumulated tool results — into the cache. You expected 70-80% cost savings on the repeated prefix. Instead: costs went up, latency got worse, and the agent started making stranger errors as sessions grew longer.

The problem: you cached the wrong things. In agentic workloads, what looks like a stable prefix is actually three different types of content with different stability profiles — and naively caching all of them is actively counterproductive.

## Forces

- **Prompt caching promises dramatic savings** — provider-managed KV caches can reduce input token costs by 41-80% and improve time-to-first-token by 13-31% on agentic workloads (Lumer et al., arXiv:2601.06007, Jan 2026).
- **Agentic prompts are structurally heterogeneous** — a single "prefix" mixes genuinely stable content (system prompt, tool schemas) with dynamically generated content (tool results, retrieved documents, user context) that varies per request.
- **Naive full-context caching is the default mistake** — developers cache everything because it is all in the prompt. But the first comprehensive evaluation of prompt caching on agentic tasks shows that excluding tool results outperforms full-context caching on both cost and latency.
- **The cache breaks in ways that silently corrupt agent behavior** — when the cache is invalidated mid-session (e.g., a new MCP server connects, adding new tool definitions), the agent continues with a different effective context — and may not notice.
- **Session tree structures shatter the linear cache assumption** — branching conversations share a common prefix root but diverge at different points. A naive cache might serve the wrong branch's suffix when the agent rewinds and continues elsewhere.

## The move

Treat cache boundary placement as an explicit architectural decision. Partition your agent's prompt into three zones, each with a different caching strategy:

### The three-zone model

```
Zone 1: STABLE (cache aggressively)
├── System prompt
├── Tool definitions (static)
└── Fixed instructions / policies

Zone 2: SEMI-STABLE (cache with TTL or version key)
├── Tool schemas from MCP servers (if tools are stable)
├── Agent persona / role definitions
└── Retrieved document chunks (versioned)

Zone 3: DYNAMIC (never cache)
├── Tool results (unique per call)
├── User-provided context
├── Intermediate reasoning / memory state
└── Session-specific generated content
```

### Zone-specific implementation

**Zone 1 — Anthropic:**
```python
response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    system=[
        # Zone 1: ephemeral = cached aggressively
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
        # Zone 2: manually managed with version key
        {"type": "text", "text": f"[doc-v{DOC_VERSION}]{DOC_CONTENT}", "cache_control": {"type": "ephemeral"}},
    ],
    messages=[
        # Zone 3: no cache_control — never cached
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": assistant_reasoning},
        # Tool result inserted here — no cache_control
        {"role": "user", "content": f"<tool_result>{tool_output}</tool_result>"},
    ]
)
```

**Zone 1 — OpenAI:**
```python
# OpenAI caches the longest common prefix automatically.
# Strategy: structure the prompt so Zone 1 is ALWAYS at the start,
# Zone 3 content ALWAYS at the end.
messages = [
    # Zone 1: stable prefix (system + tools) — always identical
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "system", "content": json.dumps(TOOL_DEFINITIONS)},
    # Zone 3: dynamic content appended after stable prefix
    {"role": "user", "content": user_input},
]
# OpenAI cache write is free, cache hit = 50% discount on prefix tokens.
# Put ALL dynamic content AFTER the stable zone.
```

### Handling MCP dynamic tool registration

MCP servers can connect or disconnect at runtime, changing the available tool set. When tool definitions change, the cache is invalidated.

```python
# Strategy: version your MCP tool set as part of the cache key
mcp_tool_hash = hashlib.sha256(
    json.dumps(sorted([s.name for s in connected_mcp_servers]), separators=(',', ':')).encode()
).hexdigest()[:8]

session_key = f"{model}:{mcp_tool_hash}:{session_id}"

# When MCP servers change, you get a cache miss — which is correct.
# Continuing with a stale cached prefix that assumes different tools
# would produce a structurally corrupted context.
```

### Handling tree-shaped sessions

If your agent supports session branching (rewind + continue on a different branch):

```python
# Each branch node tracks its own "divergence point" from the shared prefix
branch_metadata = {
    "shared_prefix_tokens": shared_root_hash,
    "divergence_turn": branch_start_turn,
    "unique_tool_results": [tr1, tr2, tr3],  # Zone 3 content — never shared
    "shared_zone_content": [sys_prompt, tool_defs, doc_chunks],  # Zone 1+2
}

# When replaying a branch, reconstruct only the relevant zones.
# Do NOT assume the continuation suffix from branch A applies to branch B.
```

### Measuring what your cache actually does

```python
# Instrument at the zone level, not the request level
def log_cache_metrics(response, zone_breakdown):
    # Provider returns cache metadata
    if hasattr(response, 'usage') and response.usage:
        cached_tokens = getattr(response.usage, 'prompt_tokens_details', {})\
                          .get('cached_tokens', 0) if hasattr(response.usage, 'prompt_tokens_details') else 0
        
        # Map cached tokens to zones by counting tokens in each zone
        zone_cached = estimate_zone_cache_breakdown(cached_tokens, zone_breakdown)
        
        logger.info({
            "total_cached_tokens": cached_tokens,
            "zone1_cached_pct": zone_cached["zone1"] / cached_tokens if cached_tokens else 0,
            "zone3_cached_tokens": zone_cached["zone3"],  # Should be 0
            "cache_hit": cached_tokens > 0,
        })

# A zone3_cached_tokens > 0 is a bug report, not a feature.
```

### The counter-intuitive result that changes everything

From Lumer et al. (Jan 2026): on long-horizon agentic tasks, **caching only the system prompt outperforms caching the system prompt + tool definitions + all accumulated tool results**, in both cost savings and TTFT. The reason: tool results are interleaved with the dynamic content, so their inclusion shortens the contiguous stable prefix that can be cached. Excluding them extends the cacheable prefix dramatically.

| Strategy | Cost Savings | TTFT Improvement |
|---|---|---|
| System prompt only | 65-78% | 20-31% |
| System + tools (no results) | 70-80% | 13-30% |
| Full context (incl. tool results) | 41-55% | 5-15% |

The agentic sweet spot: Zone 1 + Zone 2 (versioned stable content), never Zone 3.

## Receipt

> Verified 2026-08-03 — arXiv:2601.06007 (Lumer et al., Jan 2026) tables 1-4, 6.1-6.3; Agent Harness Engineering checklist (`mcp-prompt-caching-checklist.md`); Fireworks AI cache boundary documentation. Zone boundary token counting verified against Anthropic API `prompt_tokens_details.cached_tokens` response field. MCP tool hash versioning pattern implemented in agent-harness-engineering repo.

## See also

- [S-1192 · The Five-Layer Caching Stack](stacks/s1192-the-five-layer-caching-stack-for-agentic-workloads.md) — the broader caching hierarchy; this entry is the Zone 1 boundary decision within it
- [S-1063 · The Context Lifecycle Stack](stacks/s1063-the-context-lifecycle-stack-when-your-agent-remembers-everything-and-knows-less.md) — session lifecycle management; branching sessions are a context lifecycle concern
- [S-1019 · The Ghost Loop Stack](stacks/s1019-the-ghost-loop-stack-when-your-agent-decides-its-own-workflow-and-nobody-traced-it.md) — traced sessions make cache corruption visible; untraced sessions silently diverge
