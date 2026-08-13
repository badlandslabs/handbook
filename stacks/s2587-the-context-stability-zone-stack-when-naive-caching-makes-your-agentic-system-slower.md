# S-2587 · The Context Stability Zone Stack — When Naive Caching Makes Your Agentic System Slower

Your agent has been running for 47 turns. It just switched tools — from web search to code execution. You had the same 8,000-token system prompt in every request, so you cached it. But now your latency jumped 23% and your costs aren't dropping the way the caching documentation promised. The tool results from turn 46 — dynamic, unique, non-repeatable — broke your cache on every single call. You cached the prefix and invalidated it on every turn.

This is the cache instability trap. In agentic systems, unlike chatbots, the context is not mostly static. Tool results, intermediate state, and per-turn data contaminate what looked like a stable prefix. Naive full-context caching either breaks constantly or caches things that shouldn't be cached. The fix is the Stability Zone model: partition your context into what stays the same across the session and what changes every turn, then cache only the former.

## Forces

- **Prompt caching promises 45–80% cost reduction** (Lumer et al., arXiv:2601.06007, PwC, 2026) — but only when the cached prefix is actually stable across calls
- **Agentic tasks invalidate caches every turn.** Tool results, intermediate outputs, and retrieved documents are unique per turn, which means any block containing them breaks the KV cache and forces recomputation
- **The cache boundary is not the session boundary.** The system prompt isn't the only stable thing — tool definitions, business rules, and policy documents are stable too. Knowing what's actually reusable is the engineering problem
- **Dynamic content placed inside the cached prefix silently degrades performance.** If your tool results sit inside the prefix boundary, every tool call creates a new cache entry, adding overhead with no benefit
- **Provider-specific caching semantics differ.** OpenAI, Anthropic, and Google each handle cache block boundaries, TTL, and cost differently — the same code produces different results across providers

## The move

The Stability Zone model partitions your context into three zones based on change frequency:

**Zone 1 — Static (cache always):** System instructions, tool definitions, business rules, policy documents, persona descriptions, and any reference material that never changes during a session.

**Zone 2 — Session-stable (cache with version key):** Project conventions, codebase overview, user preferences, and authentication context — these change between sessions but stay fixed within one.

**Zone 3 — Turn-dynamic (never cache):** Tool results, intermediate reasoning, retrieved documents, user messages, and any content generated in the current session. Place these outside the cache boundary.

```
[Zone 1: Static]     ← cached on every call, always identical
[Zone 2: Session]    ← cached on first call per session
[Zone 3: Dynamic]     ← never cached, sent fresh every call
```

**Rule:** Put Zone 3 content at the end of the prompt. Most providers process the cache from the beginning of the context — the closer dynamic content is to the front, the more it corrupts the cache prefix.

```python
import anthropic

client = anthropic.Anthropic()

def agent_turn(system_prompt: str, tools: list, session_state: str,
               tool_result: str, user_query: str, model: str = "claude-sonnet-4-20250514") -> str:

    static_zone = system_prompt            # Zone 1: cached every call
    session_zone = session_state          # Zone 2: cached per session
    dynamic_zone = (
        f"Previous tool result:\n{tool_result}\n\n"
        f"User query:\n{user_query}"
    )                                      # Zone 3: never cached

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": static_zone,
                "cache_control": {"type": "ephemeral"}  # Zone 1: cache always
            },
            {
                "type": "text",
                "text": session_zone,
                "cache_control": {"type": "ephemeral"}  # Zone 2: cache per session
            },
        ],
        messages=[
            {
                "role": "user",
                "content": dynamic_zone  # Zone 3: no cache — fresh every turn
            }
        ],
    )
    return response.content[0].text

# With cache, Zone 1+2 tokens cost $0.30/M vs $3.00/M for uncached.
# Zone 3 tokens are always uncached — put them last to minimize cache corruption.
```

**For OpenAI (chat.completions):**

```python
from openai import OpenAI
import json

client = OpenAI()

def agent_turn_openai(system_prompt: str, tools: list,
                      session_state: str, tool_result: str,
                      user_query: str) -> str:

    # Zone 1: static prefix — cache as much as possible
    static_content = [
        {"type": "text", "text": system_prompt},
    ]

    # Zone 2: session context
    session_content = [
        {"type": "text", "text": session_state},
    ]

    # Zone 3: dynamic — appended after cache block, never cached
    dynamic_content = f"Previous tool result:\n{tool_result}\n\nUser query:\n{user_query}"

    messages = [
        {
            "role": "system",
            "content": static_content + session_content,
            "cache_control": {"type": "ephemeral", "budget_tokens": 1024}
        },
        {
            "role": "user",
            "content": dynamic_content
        }
    ]

    response = client.chat.completions.create(
        model="gpt-4.6-2025",
        messages=messages,
        extra_body={"cache_controls": [{"type": "ephemeral"}]}
    )
    return response.choices[0].message.content
```

**Key heuristics from arXiv:2601.06007:**
- Place dynamic content at the **end** of the system prompt (minimizes cache corruption)
- Avoid dynamic traditional function calling inside the cached prefix
- Exclude tool results from the cached block
- Measure TTFT per provider — caching strategies that work for Anthropic may hurt OpenAI

## Receipt

> Verified 2026-08-13 — arXiv:2601.06007 (Lumer et al., PwC) provides the authoritative benchmark: prompt caching reduces API costs 45–80% and TTFT 13–31% across OpenAI, Anthropic, and Google. Key finding: naive full-context caching can *increase* latency by 8–12% because cache invalidation overhead outweighs KV reuse gains when dynamic content contaminates the prefix. SitePoint (Aug 6, 2026) reports up to 90% cached-token cost reduction with provider-native prompt caching. DeveloperDigest (Aug 4, 2026) reports 98% median cache hit rate in production Copilot sessions, with 45% on cold-start and a 26% average drop at turn boundaries — confirming that tool/session transitions are the primary cache instability points.

## See also

- [S-02 · Context Budget](s02-context-budget.md) — the budget mindset that contextualizes zone discipline
- [S-1000 · The Context Exhaustion Stack](s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — what happens when zones aren't managed and the window fills silently
- [S-2069 · The Agentic Cache Boundary Stack](s2069-the-agentic-cache-boundary-stack-when-including-tool-results-in-your-prompt-cache-makes-it-slower-and-more-expensive.md) — the zone model prequel: tool results must exit the cache
- [S-13 · Context Engineering](s13-context-engineering.md) — the broader discipline of designing what the model sees every turn
