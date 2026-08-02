# S-2005 · The Agentic Memory Dial Stack — When Your Agent Becomes a Memory Hoarder and a Slime Mold Teaches It to Let Go

Your agent works fine for the first ten tool calls. By the fiftieth, it's hallucinating cross-references to bugs it introduced three sessions ago. By the hundredth, it's timing out on a 180k-token context and producing nothing useful. Nobody touched the agent. It just grew. The fix isn't a bigger context window — it's a mechanism that lets the agent decide when to stop accumulating and start forgetting, on purpose.

## Forces

- **Context growth is automatic, forgetting is manual.** Every agent framework appends to history by default. None of them delete. At scale, this produces a context that is mostly noise, increasingly expensive to process, and demonstrably harder to reason within.
- **Passive summarizers are decoupled from the agent's intent.** External summarizers run on a schedule or a token budget, not on what the agent actually needs. The agent may have already been poisoned by failed attempts before the summarizer fires.
- **The model degrades inside its own context.** The "Lost in the Middle" phenomenon means that as trial-and-error logs accumulate, the agent's ability to find the signal inside its own history measurably declines. It's not memory loss — it's memory poisoning.
- **Agent-controlled compression requires trust in the agent's own judgment.** Most teams won't give an agent the ability to delete its own history without a human-in-the-loop gate. The design tension is autonomy vs. oversight.

## The move

The core move is **agent-controlled active context compression**: the agent autonomously decides when to consolidate key learnings into a persistent Knowledge block and prune the raw interaction history that produced them. This is not summarization-as-a-service. It is a first-class agent primitive.

### 1. The append-only failure mode

Standard agent scaffolds operate in append-only mode. Every thought, tool call, tool result, and failed attempt is permanently appended to the conversation history. For simple single-turn tasks this is fine. For long-horizon tasks — debugging a complex codebase, triaging a cascade of related incidents, exploring a multi-file refactor — the history grows faster than the context window and faster than the model's ability to stay grounded.

The failure cascade: history grows → context utilization drops → agent loses track of what matters → agent acts on irrelevant context → output degrades → cost compounds because every degraded step still requires full context reprocessing.

### 2. The Focus agent architecture

Verma (arXiv:2601.07190, Jan 2026) introduced the **Focus agent** — an architecture inspired by *Physarum polycephalum* (slime mold). The slime mold explores an environment, finds food sources, and physically retracts from explored dead-ends while reinforcing paths to resources. The Focus agent applies the same principle to context management.

Two parallel blocks:
- **History block**: raw interaction log, appended continuously
- **Knowledge block**: distilled learnings extracted by the agent itself

The agent evaluates the history block at each step and decides whether to:
- **Consolidate**: distill recent history into Knowledge block entries
- **Prune**: delete raw history entries that are now represented in the Knowledge block
- **Skip**: continue accumulating

This creates a **sawtooth context pattern** — sawtooth up during accumulation, sharp drop on compression — rather than the monotonic upward growth of append-only agents.

### 3. The compression decision

The agent triggers compression based on signals, not just thresholds:

- **Token threshold**: context hits N% of available window
- **Distraction signal**: recent failures suggest context poisoning
- **Confidence signal**: agent self-assesses its own grounding in recent history
- **Cadence signal**: configurable interval (every K tool calls or T minutes)

The decision to compress is itself an agent action — it uses a small model or a targeted prompt to distill history into Knowledge entries. The agent extracts:
- Decisions made and their rationale
- Key facts established
- Errors encountered and their causes
- Environmental state changes

### 4. Implementation pattern

```python
# Minimal active context compression scaffold
class AgenticMemoryDial:
    def __init__(self, max_context_tokens: int, compression_threshold: float = 0.7):
        self.max_tokens = max_context_tokens
        self.threshold = compression_threshold
        self.history: list[dict] = []   # raw interaction log
        self.knowledge: list[str] = []   # distilled learnings

    def append(self, entry: dict):
        self.history.append(entry)

    def should_compress(self) -> bool:
        # Agent-driven signal: assess context quality
        current_tokens = self.estimate_tokens(self.history + self.knowledge)
        return current_tokens > self.max_tokens * self.threshold

    def compress(self, agent):
        """Agent autonomously consolidates history into knowledge."""
        prompt = (
            "You are a memory consolidation engine. Review the raw interaction history "
            "and the current knowledge block. Extract key learnings into atomic entries:\n"
            "1. Decisions made and why\n"
            "2. Facts established that are still relevant\n"
            "3. Errors and their root causes\n"
            "4. Environmental state changes\n\n"
            f"Current Knowledge:\n{self.knowledge}\n\n"
            f"Raw History:\n{self.history}\n\n"
            "Return a JSON list of knowledge entries. Be precise — do not generalize."
        )
        new_entries = agent.generate(prompt, schema="list[string]")
        self.knowledge.extend(new_entries)
        self.history.clear()  # raw history replaced by distilled knowledge
        return new_entries

    def build_context(self) -> list[dict]:
        """Context is knowledge block + recent history, not all history."""
        recent = self.history[-10:]  # keep last N entries as short-term memory
        return [{"role": "user", "content": e} for e in self.knowledge] + recent
```

### 5. When not to use this

- **Short-horizon tasks**: compression overhead exceeds savings for tasks that complete in under 10 turns
- **High-stakes audit environments**: agents deleting their own history creates compliance gaps — prefer append-only with external summarization
- **Multi-agent shared contexts**: individual agents compressing independently desynchronizes the shared context — coordinate compression at the session or fleet level
- **When the cost of compression exceeds the cost of the bloated context**: compression itself costs tokens; measure before applying

### 6. The oversight gate

For production systems, wrap compression in an audit layer:

```python
class AuditedMemoryDial(AgenticMemoryDial):
    def compress(self, agent):
        new_entries = super().compress(agent)
        # Append-only audit log — agent cannot delete this
        audit_log.append({
            "timestamp": now(),
            "compressed_count": len(self.history),
            "knowledge_added": new_entries,
            "context_tokens_before": self.tokens_before,
        })
        return new_entries
```

This satisfies EU AI Act Article 12 logging requirements (tamper-evident audit trail) while giving the agent operational autonomy over its own context management.

## Receipt

> Verified 2026-08-02 — arXiv:2601.07190 (Verma, Jan 2026) reports: 22.7% token reduction (14.9M → 11.5M) with identical accuracy (3/5 = 60%) on SWE-bench Lite (N=5). 6.0 average autonomous compressions per task. Up to 57% savings on exploration-heavy instances. All evaluated using Claude Haiku 4.5 with an optimized scaffold (persistent bash + string-replacement editor). The sawtooth context pattern was empirically validated: compression fires at the right moment to prevent both token exhaustion and premature information loss.

## See also

- [S-854 · The Token Spiral Kill Switch Stack](/stacks/s854-the-token-spiral-kill-switch-stack-when-your-agent-runs-fine-and-your-invoice-doesnt.md) — cost compounding from unchecked context growth
- [S-945 · The Memory Decay Stack](/stacks/s945-the-memory-decay-stack-when-your-agent-forgets-who-you-are-by-the-third-turn.md) — external summarization as the alternative to in-agent memory management
- [S-2003 · The Agent Amnesia Stack](/stacks/s2003-the-agent-amnesia-stack-when-your-agent-forgets-everything-between-sessions.md) — session-to-session persistence vs. within-session compression
