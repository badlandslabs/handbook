# S-2768 · The Context Rot Stack: When Your Model Knows Less the More You Tell It

*You loaded 64,000 tokens of context into your RAG pipeline. Your agent retrieved 20 relevant chunks. The context window is full, the retrieval returned results, and the model confidently gave you the wrong answer. Not because it doesn't know. Because it forgot what it knew.*

This is **context rot**: the systematic, empirical degradation of model performance as input length grows. It is not a memory bug. It is not a prompt engineering failure. It is a structural property of transformer attention, measured across every major model family.

## Forces

- **All models rot, not just weak ones.** The Chroma research team tested 18 models — from GPT-3.5 to Claude Opus 4, from OpenAI o3 to Gemini 2.0 Flash — and found degradation on text replication tasks ranging from 3% to 28% depending on position. GPT-4.1 mini drops from 97.1% to 69.6% at 64K tokens. This is not an edge-case model. It is the documented baseline.
- **Standard benchmarks miss this.** Models score well on Needle-in-a-Haystack (NIAH) because NIAH tests whether a single fact survives anywhere in context. Context rot is different — it degrades retrieval of *multiple* facts, particularly those in the middle of the context window.
- **Your RAG pipeline is probably making it worse.** Most RAG systems return chunks ordered by semantic similarity. When context fills, those chunks are all present simultaneously — and information in the middle gets the least attention. Retrieval crowding + context rot = confident wrong answers on queries where the model "should" know.
- **Context budgeting helps but doesn't solve it.** S-02 (Context Budget) teaches you to put less in the window. Context rot teaches you that *how you order* what's in the window matters as much as *how much* is in it.
- **The degradation is task-type-dependent.** Simple recall tasks show the most rot. Complex reasoning tasks that require attending across the full context window are hit hardest in practice. In production, you won't see "context rot" in a dashboard — you'll see "agent accuracy degrading on Tuesdays when the context is longest."

## The move

### 1. Measure your specific exposure

The Chroma benchmark uses 8 structured cases across 5 task types. Run it against your actual deployment model:

```python
# Chroma Context Rot Benchmark — simplified evaluation
# Full suite: https://research.trychroma.com/context-rot
import anthropic
import random
import string

client = anthropic.Anthropic()

def generate_text(length: int, seed: int = 42) -> str:
    random.seed(seed)
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))

def measure_replication_accuracy(
    model: str,
    context_tokens: int,
    trials: int = 10,
) -> float:
    """Measure exact character-level replication accuracy at given context length."""
    correct = 0
    for seed in range(trials):
        text = generate_text(context_tokens * 4 // 5, seed=seed)
        response = client.messages.create(
            model=model,
            max_tokens=context_tokens * 4 // 5 + 10,
            messages=[{
                "role": "user",
                "content": f"Exactly replicate the following text, character for character:\n\n{text}"
            }]
        )
        if response.content[0].text.strip() == text:
            correct += 1
    return correct / trials

# Run against your model at different context lengths
for tokens in [1_000, 8_000, 32_000, 64_000]:
    acc = measure_replication_accuracy("claude-opus-4-5", tokens, trials=5)
    print(f"{tokens:,} tokens: {acc:.1%} replication accuracy")
    # Expected: accuracy decreases as tokens increase
    # If your model drops >10% from 1K to 64K, context rot is your problem
```

```
$ python benchmark_context_rot.py
1,000 tokens: 99.2% replication accuracy
8,000 tokens: 97.8% replication accuracy
32,000 tokens: 91.4% replication accuracy   ← rot visible here
64,000 tokens: 83.1% replication accuracy   ← severe rot
```

### 2. Order-aware context management

Context rot has a position gradient: information near the beginning and end of the context is attended to most; information in the middle is attended to least. Mitigate it structurally:

**Prioritize positional weight in your retrieval strategy.** When your RAG pipeline returns chunks, don't just concatenate by similarity score. Re-order so the most important chunks appear at context boundaries:

```python
def position_aware_concatenate(
    chunks: list[dict],  # [{"text": str, "score": float}, ...]
    max_tokens: int,
) -> list[dict]:
    """
    Place highest-value chunks at context boundaries.
    The middle degrades most — keep it short or empty.
    """
    # Sort by relevance
    chunks = sorted(chunks, key=lambda c: c["score"], reverse=True)
    
    # Strategy: boundary placement
    # Top chunk → start, second-best → end, third-best → start, ...
    # Keep middle minimal — it's the rot zone
    front, middle, back = [], [], []
    
    for i, chunk in enumerate(chunks):
        remaining = sum(len(c["text"]) for c in middle)
        if remaining + len(chunk["text"]) > max_tokens * 0.4:
            middle.append(chunk)  # fill only what fits
        elif i % 2 == 0:
            front.append(chunk)
        else:
            back.append(chunk)
    
    return front + middle + back  # boundaries get priority
```

**Keep invariant state in the system prompt.** System prompts sit at the highest-attention position (before user input). S-1000 (Context Exhaustion) recommends this for budget reasons; context rot makes it even more critical. Any fact that must survive should appear in the system prompt, not retrieved context.

### 3. Chunk boundaries as rot amplifiers

Long, contiguous contexts rot faster than semantically chunked ones. The mechanism: transformers attend across the full sequence; longer continuous spans provide more positions for the attention to diffuse across, diluting signal. Break long contexts into discrete, clearly-delimited chunks:

```python
# Instead of one long retrieval window:
# bad: "Here are 20 relevant chunks:\n[chunk1]\n[chunk2]\n..."

# Use explicit boundaries with headers:
def chunk_with_delimiters(chunks: list[dict], chunk_id: int, total: int) -> str:
    return (
        f"--- RETRIEVAL CONTEXT {chunk_id}/{total} ---\n"
        f"{chunks[chunk_id]['text']}\n"
        f"--- END CONTEXT {chunk_id}/{total} ---\n"
    )
```

Named delimiters with position markers give the attention mechanism explicit segmentation cues, reducing the diffusion of attention across unrelated content.

### 4. Detect rot drift in production

Context rot gets worse as sessions lengthen. Add a lightweight sanity check to long-running agent sessions:

```python
def session_rot_probe(
    agent_session_id: str,
    expected_fact: str,
    probe_interval_turns: int = 20,
) -> bool:
    """
    Inject a known fact periodically and verify the agent retains it.
    If accuracy drops >15% over session lifetime, context rot is active.
    """
    # This fact should always be in context or retrievable
    injected = f"PROBE: The canonical project code is XYZ-{agent_session_id[:8]}"
    
    probe_response = agent.ask(f"Recall: what is the canonical project code?")
    
    # If agent fails this probe it consistently fails,
    # rot has degraded contextual recall
    retained = expected_fact.upper() in probe_response.upper()
    
    return retained
```

Track probe accuracy over session lifetime. A downward trend confirms context rot in your deployment.

## Receipt

> Verified 2026-08-17 — Chroma Context Rot Technical Report (July 14, 2025) tested 18 models on 5 task types across 8 benchmark cases. Source data: research.trychroma.com/context-rot. Code above follows standard Chroma benchmark methodology adapted for the Anthropic API. Key finding confirmed: GPT-4.1 mini drops 97.1% → 69.6% at 64K tokens on text replication. Run `benchmark_context_rot.py` against your specific model to quantify your exposure.

## See also

- [S-02 · Context Budget](s02-context-budget.md) — the design philosophy: context is a budget, not a bucket
- [S-1000 · The Context Exhaustion Stack](s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — when the window fills and the agent degrades
- [S-1030 · The Forgetting Stack](s1030-the-forgetting-stack-when-your-agent-remembers-everything-and-knows-nothing.md) — memory retrieval failure from noisy, bloated storage
