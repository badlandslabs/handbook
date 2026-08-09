# S-2388 · The Context Rot Stack — When Your Agent Slowly Forgets What You Already Told It

Your agent's context window has 200,000 tokens of headroom. You never hit it. But in a 50-turn conversation, your agent starts ignoring instructions you gave at the start, losing track of constraints from the middle, and contradicting itself three turns later. You didn't overflow — you *rotted*. Context rot is the silent degradation of model attention and instruction-following fidelity as context length grows, even well below hard token limits. The failure looks like confusion, not crash.

## Forces

- **Attention is not uniform.** Models concentrate on the most recent tokens and the system prompt; middle-context tokens receive progressively less attention weight as the sequence grows. This is a property of transformer architectures, not a bug.
- **Hard overflow and soft rot are different failure modes.** Overflow fires an exception; rot produces a plausible wrong answer. Observability tooling that only monitors token counts misses rot entirely.
- **You can't tell the difference from traces alone.** A rotted agent completes every step successfully — the trace looks fine. The output is subtly wrong. You need outcome-level verification, not trace-level success signals.
- **Compression strategies trade fidelity for length.** Summarization and truncation prevent overflow but introduce their own errors: lost specifics, shifted tone, forgotten edge cases. The cure can resemble the disease.
- **Rot compounds with multi-agent pipelines.** When agents pass context to each other, each handoff resets the relative-position dynamics — but the cumulative conversation with any shared context tool still rots. The rot is shared, not distributed.

## The move

**Three-layer strategy: prevent, detect, recover.**

### Prevention — Priority-Aware Context Management

```python
import tiktoken

def context_priority(tokens: list[str], model: str = "gpt-4o") -> list[str]:
    """Rank tokens by retention priority before eviction."""
    enc = tiktoken.encoding_for_model(model)
    PRIORITY = ["instruction", "constraint", "schema", "example", "history"]
    
    scored = []
    for i, msg in enumerate(tokens):
        tkn_count = len(enc.encode(msg))
        recency_score = i / len(tokens)  # newer = higher
        keyword_score = max(
            (0.5 if any(p in msg.lower() for p in PRIORITY) else 0),
        )
        priority_score = 1 - (recency_score * 0.6 + keyword_score * 0.4)
        scored.append((priority_score, tkn_count, msg))
    
    scored.sort()
    return [msg for _, _, msg in scored]

# First eviction candidate: oldest low-priority tokens
def evict_least_important(messages: list[dict], budget_tokens: int, model: str) -> list[dict]:
    enc = tiktoken.encoding_for_model(model)
    total = sum(len(enc.encode(m["content"])) for m in messages)
    
    if total <= budget_tokens:
        return messages
    
    # Preserve: system prompt (always first), last N messages
    preserved = [messages[0]] + messages[-3:]
    evictable = messages[1:-3]
    
    kept = list(preserved)
    for msg in evictable:
        if len(enc.encode("".join(m["content"] for m in kept))) + len(enc.encode(msg["content"])) <= budget_tokens:
            kept.append(msg)
    
    return kept  # Maintains system + recent + some middle
```

### Detection — Rot Signal Without Ground Truth

```python
def rot_signal(messages: list[dict], checkpoint_constraints: list[str]) -> float:
    """
    Estimate rot severity by checking if early constraints are still honored.
    Each constraint is a simple pattern to detect in recent messages.
    Returns 0.0 (no rot) to 1.0 (severe rot).
    """
    recent_content = "\n".join(m["content"] for m in messages[-5:])
    violations = 0
    for constraint in checkpoint_constraints:
        if constraint.lower() not in recent_content.lower():
            violations += 1
    return violations / len(checkpoint_constraints) if checkpoint_constraints else 0.0

# Usage: track what the user first asked for, what constraints were set early
checkpoint_constraints = [
    "format: json",
    "no personally identifiable information",
    "currency: USD",
]

async def check_and_rotate(session_id: str, messages: list[dict], budget: int):
    rot = rot_signal(messages, checkpoint_constraints)
    if rot > 0.5:
        # Summarize and re-inject: compress history, re-state constraints
        summary_prompt = (
            "Summarize this conversation, preserving all constraints and user requirements. "
            "Output ONLY a JSON object with keys: summary (string), constraints (list of strings)."
        )
        enc = tiktoken.encoding_for_model("gpt-4o")
        if len(enc.encode(str(messages))) > budget * 0.7:
            # Force compression before rot becomes critical
            messages = evict_least_important(messages, budget, "gpt-4o")
            await memory.update(session_id, {"messages": messages, "rot_alert": True})
```

### Recovery — Semantic-Preserving Compression

```python
SYSTEM_PROMPT = """You are a compression assistant. Reduce the message history to its essential 
semantic content for a continuation task. Preserve: (1) all user requirements and constraints, 
(2) any schema or format specifications, (3) the core goal, (4) any intermediate decisions 
already made. Discard: redundant examples, exploratory reasoning, failed attempts.
Output a JSON array of messages."""

def compress_with_fidelity(messages: list[dict], model: str = "gpt-4o") -> list[dict]:
    """
    Compress history while explicitly preserving constraint-critical content.
    Different from naive summarization which loses specificity.
    """
    # Extract and preserve hard constraints first
    constraint_prompt = "Extract all hard constraints from this conversation as JSON."
    constraints = call_llm(messages, constraint_prompt)  # Keep these separately
    
    # Compress the rest
    compressed = summarize_messages(messages, SYSTEM_PROMPT)
    
    # Re-inject constraints as a reminder in the compressed context
    return [
        messages[0],  # system prompt
        {"role": "user", "content": f"Active constraints (must follow): {constraints}"},
        *compressed,
    ]
```

## Receipt

> Verified 2026-08-09 — arXiv 2511.22729 ("Solving Context Window Overflow in AI Agents") establishes that truncation/summarization fails to preserve complete outputs in workflows requiring full data fidelity. Redis.io (2026) documents context rot as a performance cliff distinct from hard overflow. statebase.org's 7 failure modes taxonomy lists "context loss" as its own class. Key metric from OrchestraBench (arXiv:2608.05263): at GPQA-Diamond, 95.5% of cases have at least one correct agent, yet orchestration reaches only 87.4% — a gap partly attributable to context degradation in multi-step pipelines. Production validation: SIVARO (2026) confirms logical correctness failures outnumber crash failures in production agents.

## See also

- [S-02 · Context Budget](s02-context-budget.md) — hard token budgeting
- [S-1000 · Context Exhaustion](s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — when you actually hit the limit
- [S-1063 · Context Lifecycle](s1063-the-context-lifecycle-stack-when-your-agent-remembers-everything-and-knows-less.md) — memory management across turns
- [S-2359 · Inter-Agent Trust Propagation](s2359-the-inter-agent-trust-propagation-stack-when-your-security-boundary-is-the-agent-you-trust.md) — rot compounds across agent handoffs
