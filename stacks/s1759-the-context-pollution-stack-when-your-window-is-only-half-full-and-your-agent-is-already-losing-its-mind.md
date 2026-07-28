# S-1759 · The Context Pollution Stack

When your agent degrades at 40–60% context utilization — repeating itself, ignoring fresh instructions, hallucinating facts that were refuted three turns ago — the problem is not model capability and not context capacity. Your window isn't full. It is polluted. Heterogeneous noise has diluted the signal before the hard limit ever arrives.

## Forces

- **The five polluters consume equal attention.** Tool results, system instructions, conversation history, retrieved documents, and execution artifacts each compete for the same attention budget. A 5,000-token API response from a 6am automated email sits beside the current task and gets equal treatment by the model.
- **Stale content outlasts its usefulness.** Tool outputs from early steps — searches, database queries, file reads — remain in context and continue consuming attention long after the agent has acted on them. They are noise masquerading as history.
- **Signal-to-noise is invisible at the token level.** Token count dashboards show 60% utilization and green lights. They cannot distinguish between 60% high-signal content and 60% mixed signal and noise. The degradation is semantic, not mechanical.
- **Pollution is subtler than overflow.** Context overflow is dramatic — the model errors, truncates, or tells you it failed. Context pollution is silent: the model keeps generating, keeps producing well-formed output, and keeps being wrong.
- **The counter-intuitive insight:** reducing context is the wrong instinct. Teams that trim context aggressively often remove signal alongside noise. The fix is not fewer tokens — it is smarter token curation.

## The move

The solution is **context hygiene**: actively filtering, tagging, and evicting content based on semantic relevance rather than age or token count. Three layers:

### Layer 1 — Result Grafting: Keep Signal, Drop Noise

Every tool output gets filtered before entering context. The full 5,000-token database result is a candidate for the context; the answer it contains is what belongs there.

```python
from anthropic import Anthropic
from tenacity import retry, stop_after_attempt
import json

client = Anthropic()

@retry(stop=stop_after_attempt(2))
def grafted_tool_call(tool_name: str, tool_input: dict, system_context: str) -> str:
    """
    Calls a tool, extracts only the signal-relevant portion, and returns
    a grafted (filtered) result instead of the raw output.

    Args:
        tool_name: MCP tool name (e.g., 'database_query')
        tool_input: Arguments to the tool
        system_context: Current task context (injected for relevance scoring)
    """
    # Step 1: Raw call (fast-fail if tool itself errors)
    raw_result = call_mcp_tool(tool_name, tool_input)

    # Step 2: Extract signal via a small model
    extraction_prompt = f"""You are a context hygiene filter. Your job is to extract
only the information from this tool result that is relevant to the current task.

TASK CONTEXT:
{system_context}

TOOL RESULT:
{json.dumps(raw_result, indent=2)}

INSTRUCTIONS: Return a JSON object with two keys:
- "signal": the 1-3 sentences or values most relevant to the task context
- "excerpt": a 1-2 sentence plain-English summary of what the tool found

If nothing in the tool result is relevant, return {{"signal": "", "excerpt": "No relevant information found."}}"""

    extraction = client.messages.create(
        model="claude-haiku-4-20250514",
        max_tokens=300,
        system="You are a strict relevance filter. Be concise. Do not add information not present in the input.",
        messages=[{"role": "user", "content": extraction_prompt}]
    )

    grafted = json.loads(extraction.content[0].text)
    return f"[{tool_name}] {grafted['excerpt']} | Signal: {grafted['signal']}"
```

This keeps the graft small — 300 tokens instead of 5,000 — and preserves the signal. The filtering model is a cheap fast model; it is called on every tool result, not on every turn.

### Layer 2 — Pollutant Tagging and Active Eviction

Tag every context chunk with metadata at insertion time, then evict based on a **pollution score** that factors in age, relevance decay, and noise classification.

```python
from dataclasses import dataclass, field
from typing import Literal
from datetime import datetime, timedelta
import anthropic

@dataclass
class ContextChunk:
    content: str
    chunk_type: Literal["tool_result", "user_message", "system_instruction",
                        "retrieved_doc", "agent_output", "reasoning_trace"]
    inserted_at: datetime
    task_relevance_score: float  # 0.0–1.0, scored by a classifier
    pollution_flags: list[str] = field(default_factory=list)

class PollutionAwareContextManager:
    def __init__(self, max_pollution_score: float = 0.65):
        self.chunks: list[ContextChunk] = []
        self.max_pollution_score = max_pollution_score

    def add(self, chunk: ContextChunk):
        """Inject a chunk with pollution metadata."""
        self._tag_pollution(chunk)
        self.chunks.append(chunk)
        self._evict_if_needed()

    def _tag_pollution(self, chunk: ContextChunk):
        """Classify pollution type and flags at insertion time."""
        age_hours = (datetime.now() - chunk.inserted_at).total_seconds() / 3600

        if age_hours > 2 and chunk.chunk_type == "tool_result":
            chunk.pollution_flags.append("stale_tool_output")
        if chunk.task_relevance_score < 0.3:
            chunk.pollution_flags.append("low_relevance")
        if chunk.chunk_type == "reasoning_trace":
            chunk.pollution_flags.append("reasoning_bloat")
        if len(chunk.content) > 3000 and chunk.chunk_type == "retrieved_doc":
            chunk.pollution_flags.append("unpruned_document")

    def _evict_if_needed(self):
        """Run after every insertion. Evict the highest-pollution chunk if over budget."""
        if self.pollution_score() <= self.max_pollution_score:
            return

        # Score each chunk: higher score = more polluted
        scored = []
        for i, chunk in enumerate(self.chunks):
            score = 0.0
            score += len(chunk.pollution_flags) * 0.2
            score += max(0, 0.5 - chunk.task_relevance_score)
            age_hours = (datetime.now() - chunk.inserted_at).total_seconds() / 3600
            score += min(age_hours * 0.05, 0.3)
            scored.append((i, score))

        # Evict the most polluted non-essential chunk
        scored.sort(key=lambda x: x[1], reverse=True)
        for idx, score in scored:
            if self.chunks[idx].chunk_type not in ("system_instruction",):
                evicted = self.chunks.pop(idx)
                print(f"[Context Hygiene] Evicted {evicted.chunk_type} "
                      f"(pollution={score:.2f}, flags={evicted.pollution_flags})")
                break

    def pollution_score(self) -> float:
        """Returns 0.0 (clean) to 1.0 (heavily polluted)."""
        if not self.chunks:
            return 0.0
        total = sum(
            min(len(c.pollution_flags) * 0.15, 0.5) +
            max(0, 0.4 - c.task_relevance_score)
            for c in self.chunks
        )
        return min(total / len(self.chunks), 1.0)
```

### Layer 3 — Task-Directed History Compression

Before every agent turn, run a lightweight classifier that decides which prior turns to retain. The goal is a **task-specific context that looks nothing like the full conversation history.**

```python
SYSTEM_PROMPT_SUFFIX = """

CRITICAL CONTEXT RULE:
Before responding, silently classify every prior message as:
  [KEEP] — directly relevant to the current sub-task
  [PRUNE] — resolved, off-topic, or superseded

Only the [KEEP] messages exist in your working context for this turn.
Do not mention this process in your response.
"""

def build_turn_context(
    conversation_history: list[dict],
    current_task: str,
    max_turn_context: int = 8000
) -> list[dict]:
    """Build a pollution-minimized context window for the current turn."""
    if len(conversation_history) <= 4:
        return conversation_history  # Short history: no filtering needed

    # Score each historical message for current task relevance
    scores = []
    for msg in conversation_history[:-1]:  # Exclude the current message
        relevance = classify_relevance(
            message_content=msg.get("content", ""),
            current_task=current_task,
            model="claude-haiku-4-20250514"
        )
        scores.append(relevance)

    # Keep messages above threshold, or all recent ones
    threshold = sorted(scores, reverse=True)[min(3, len(scores) - 1)]
    keep_indices = {i for i, s in enumerate(scores)
                     if s >= threshold or i >= len(scores) - 3}

    filtered = [msg for i, msg in enumerate(conversation_history[:-1])
                if i in keep_indices]
    filtered.append(conversation_history[-1])  # Always keep current

    return filtered
```

### The Monitoring Signal

Pollution is invisible to token-count dashboards. Track what it actually looks like:

| Signal | What it measures | Pollution threshold |
|--------|-----------------|---------------------|
| Tool result / total context ratio | How much of context is raw tool output | > 40% = polluted |
| Age-weighted stale fraction | Portion of context older than 2h | > 25% = polluted |
| Cross-turn instruction consistency | Does agent follow instructions it received 3 turns ago? | < 80% consistent = degraded |
| Middle-position recall rate | Does agent reference information placed in the middle of context? | < 50% recall = attention pollution |

## Receipt

> Receipt pending — 2026-07-28

## See also
- [S-1300 · The Attention Gravity Well](stacks/s1300-the-attention-gravity-well-when-your-agent-forgets-instructions-it-read-three-hours-ago.md) — positional decay of instructions in growing context
- [S-1035 · The Context-Capacity Gap](stacks/s1035-the-context-capacity-gap-when-your-agent-reads-everything-and-knows-less.md) — the gap between advertised and usable context
- [S-1754 · The Context Surface](stacks/s1754-the-context-surface-stack-when-your-agent-knows-less-than-it-did-three-turns-ago.md) — attention degradation over session lifetime
- [S-1654 · The Stale Amplification Stack](stacks/s1654-the-stale-amplification-stack-when-caching-makes-wrong-answers-faster.md) — caching amplifies stale content (different from pollution, but related)
