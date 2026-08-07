# S-2289 · The Failure-Driven Eviction Stack — When Your MCP Tools Are Drowning Your Agent in Tokens

Your agent is working an ERP expense itemization task: 50 hotel receipts, each routed through an MCP server to Dynamics 365 F&O. By task 8, your context is 1.4M tokens deep. Token cost: $4.20 per receipt. The agent has been running for 14 hours and is about 40% done. Something is wrong — and it is not the model. It is the tool responses.

Enterprise MCP servers return verbose payloads. A single `get_line_items` call might return 3,000 tokens of structured XML. A `search_vendors` call returns 5,000 tokens of JSON with fields the agent will never read. Your agent is not context-starved because the model forgot — it is context-starved because the tools generated more text than the model can meaningfully attend to.

## Forces

- **Verbose tool responses are the primary context driver in MCP-based agents.** Enterprise systems return full record dumps by default. A single MCP tool call can consume 5–15% of a 200K context window. After 10 tool calls, you are at 50–150% of capacity — before any conversation history is even considered.
- **More context does not mean better performance.** Microsoft researchers (arXiv:2606.10209, June 2026) tested four configurations on GPT-5 for automated hotel expense itemization: (C1) no user model, (C2) full conversation context, (C3) last-5 tool call/response pairs, (C4) last-N + summarization of evicted content. Full context (C2) achieved 71% task completion at 1.48M tokens and 14.56 hours. The hybrid approach (C4) hit 91.6% completion at 556K tokens and 5.78 hours. More context was actively harmful.
- **Retrying failed tool calls is the hidden token sink.** When a tool call fails and the agent retries without evicting the failure context, the same error payload accumulates across retries. A 3-retry loop on a 5K-token error response burns 15K tokens on failure alone — before any forward progress.
- **The agent needs signal, not noise.** Tool responses contain fields the agent will use (amount, category, vendor name) and fields it will never use (internal GUIDs, metadata timestamps, system flags). The eviction policy must distinguish these.

## The move

**Hybrid eviction: keep the last N tool pairs + summarize what you evict, but never evict a pair that contains a failure.**

This is the failure-driven eviction policy. Unlike LRU (evict oldest first) or random eviction, it treats tool failures as first-class signals that must be preserved in context.

```
[Python]
class FailureDrivenEviction:
    """
    Hybrid context manager for MCP tool-using agents.
    Prunes verbose tool responses while preserving failure context
    and summarizing evicted history.
    """

    def __init__(self, max_tool_pairs: int = 8, summary_model: str = "gpt-5"):
        self.max_tool_pairs = max_tool_pairs
        self.summary_model = summary_model
        self.evicted_summaries: list[str] = []

    def _is_failure(self, tool_response: dict) -> bool:
        """Detect tool failure across multiple failure signatures."""
        if tool_response.get("status_code", 200) >= 400:
            return True
        if "error" in tool_response:
            return True
        if tool_response.get("status") in ("failed", "timeout", "retry_exhausted"):
            return True
        # Semantic failure: returned empty when non-empty was expected
        if tool_response.get("_expected_count", 0) > 0:
            if tool_response.get("returned_count", 0) == 0:
                return True
        return False

    def _should_evict(self, history: list[dict]) -> bool:
        """Evict oldest pair only if it's not a failure."""
        if len(history) <= self.max_tool_pairs:
            return False
        oldest_pair = history[0]
        if self._is_failure(oldest_pair.get("response", {})):
            return False  # KEEP failures
        return True

    def _summarize_and_evict(self, history: list[dict]) -> list[dict]:
        """Summarize evicted pairs and append to summary cache."""
        if not self._should_evict(history):
            return history

        pair = history[0]
        summary = self.summary_model.summarize(
            f"Tool: {pair['tool_name']}\n"
            f"Args: {pair['args']}\n"
            f"Result: {pair['response']}",
            instruction="Extract: (1) what the tool was asked to do, "
                       "(2) key results extracted, (3) any decisions made. "
                       "Keep under 200 tokens."
        )
        self.evicted_summaries.append(summary)
        return history[1:]

    def get_context(self, history: list[dict]) -> str:
        """Build prompt context: recent pairs + summaries + original task."""
        ctx = []
        h = history[:]
        while h and len(ctx) < self.max_tool_pairs:
            h = self._summarize_and_evict(h)

        for pair in h:
            ctx.append(f"Tool: {pair['tool_name']}")
            ctx.append(f"Args: {json.dumps(pair['args'])}")
            ctx.append(f"Response: {json.dumps(pair['response'])[:500]}")

        if self.evicted_summaries:
            summary_block = "\n".join(self.evicted_summaries[-3:])
            ctx.append(f"\n[Prior context summary]\n{summary_block}")

        return "\n\n".join(ctx)
```

**The four key decisions:**

1. **Preserve failures, evict successes.** A failed `get_line_items` call must stay in context — the agent needs to know what failed to decide whether to retry, escalate, or skip. A successful call that returned 5K tokens of mostly-null fields can be summarized.

2. **Summarize evicted content, don't discard it.** The summary captures what the tool was asked to do and what key results were extracted. This lets the agent reason about the task arc without holding every intermediate response.

3. **Size the window by task type, not by model limit.** For a 10-step task: 8 tool pairs = ~40K tokens of recent context + ~3 summaries = well within attention. For a 50-receipt batch job: same policy, but the agent may see 8 pairs for the current receipt + summaries of prior receipts.

4. **Evict at token budget, not at pair count.** Count tokens, not messages. A verbose response from a poorly-designed MCP server might be 20K tokens alone. One pair can exceed your budget before you hit the pair count.

## Receipt

> Verified 2026-08-07 — Microsoft Dynamics 365 F&O + GPT-5 via MCP (arXiv:2606.10209, June 2026):
> - C2 (full context): 71.0% completion, 1,480,996 tokens, 14.56 hrs
> - C3 (last-5 pairs): 79.0% completion, 535,274 tokens, 5.39 hrs
> - C4 (last-N + summarization): 91.6% completion, ~556K tokens, 5.78 hrs
> - C4 vs C2: +20.6pp completion, -62.7% tokens, -60.2% time
> Key finding: the hybrid approach (C4) outperforms even the recency-only approach (C3) because the summary preserves task-level decisions from evicted pairs, enabling better cross-receipt reasoning.

## See also

- [S-1035 · The Context-Capacity Gap](s1035-the-context-capacity-gap-when-your-agent-reads-everything-and-knows-less.md) — the "lost in the middle" model-side problem; eviction is the agent-side solution
- [S-2288 · The Graceful Degradation Stack](s2288-the-graceful-degradation-stack-when-your-agent-fails-and-everyone-finds-out-at-3am.md) — what to do when eviction still leaves the agent in a broken state
- [S-1051 · The Memory Gap Stack](s1051-the-memory-gap-stack-when-your-agent-forgets-everything-the-moment-the-session-ends.md) — episodic vs semantic memory; eviction summaries are a form of semantic compression
