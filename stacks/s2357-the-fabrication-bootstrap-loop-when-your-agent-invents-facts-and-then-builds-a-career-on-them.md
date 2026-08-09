# S-2357 · The Fabrication Bootstrap Loop — When Your Agent Invents Facts and Then Builds a Career on Them

Your agent has been running for two months. It has opinions about your codebase. It knows the payment service uses Stripe. It remembers that the onboarding flow was redesigned in March. It is confident about all of it. Except none of it is true — or at least, none of it was verified before it was stored. The agent hallucinated these facts in session one, they were written to memory, and now every subsequent session retrieves them as ground truth. The agent is not lying to you. It genuinely believes its own fabrications. This is the **fabrication bootstrap loop**: a self-reinforcing failure where an agent's hallucinated outputs are stored as memory and treated as verified facts in all future reasoning.

## Forces

- **Memory systems treat model output as ground truth at write time.** Every LLM memory framework — Mem0, Letta, LangChain memory, custom vector stores — writes model-generated content without distinguishing it from user-confirmed facts. A hallucinated detail and a ratified user preference land in the same store with the same weight.

- **Fabrication is self-reinforcing across sessions.** A false fact stored in session 1 is retrieved in session 2, treated as context, and used to generate new conclusions. Those conclusions are stored in session 2. By session 5, the agent has built an elaborate false world model, each layer anchored to the fabricated root. The error compounds, not because the model is bad, but because the feedback loop is closed.

- **The agent cannot audit its own memory.** Self-referential evaluation — the agent checking whether its own stored beliefs are true — is circular. The same model that generated the fabrication evaluates it. Without an external reference, the agent applies the same reasoning patterns that produced the error.

- **Naive vector memory has no defense.** Vector similarity search tracks relevance, not truth. A confident hallucination about "Stripe payments" will retrieve strongly against queries about payment infrastructure, even if the fact is fabricated. There is no source, no confidence, no scope — only proximity.

- **Self-correction requires contradiction signals that fade.** The fabrication bootstrap loop is most destructive early, before the user notices. Over time, accumulated false beliefs may eventually contradict real-world evidence, triggering a correction. But in many production systems, the agent is deployed in closed-loop contexts — internal tools, codebases, synthetic environments — where contradictions surface slowly or not at all.

## The move

### 1. Three-tier epistemic classification at write time

Every memory write is classified into one of three epistemic tiers before it is stored:

```python
class EpistemicTier(enum.Enum):
    OBSERVED = "observed"    # User stated it directly
    INFERRED = "inferred"   # Model concluded it from context
    FABRICATED = "fabricated"  # Model generated it without grounding
```

On every memory write, the agent must decide: was this stated by the user, concluded from retrieved evidence, or generated from the model's own weights with no external anchor? The default classification for model-generated content is `FABRICATED` — it must be explicitly downgraded by a grounding signal.

### 2. The grounding audit gate

Before any model-generated content is stored as `INFERRED` or higher, run a grounding audit:

```python
def ground_and_store(content: str, session_context: SessionContext) -> MemoryEntry:
    grounding_signal = check_grounding(content, session_context)

    match grounding_signal:
        case UserRatifed():
            tier = EpistemicTier.OBSERVED
        case ToolVerified(source=source) if source.reliability >= 0.95:
            tier = EpistemicTier.INFERRED
        case _:
            tier = EpistemicTier.FABRICATED
            # FABRICATED entries are stored in a sandboxed recall space
            # that is retrieved only when explicitly queried, not auto-injected
            return store_in_sandbox(content, tier, grounding_signal)

    return store_in_main_memory(content, tier, grounding_signal)
```

The grounding signal hierarchy: user ratification > reliable tool output (database, API with schema contract) > unreliable tool output (web search, third-party API) > model inference > no source. Any tier below `INFERRED` gets sandboxed retrieval — it is available on explicit query but excluded from automatic context injection.

### 3. Provenance tracking on every entry

Every stored entry carries a structured provenance tag:

```python
@dataclass
class MemoryEntry:
    content: str
    tier: EpistemicTier
    provenance: Provenance  # source, timestamp, reliability_score, session_id
    contradiction_flags: list[str] = field(default_factory=list)

@dataclass
class Provenance:
    source: str          # "user", "tool:database", "tool:web_search", "model:inference"
    timestamp: datetime
    reliability_score: float  # 0.0–1.0
    session_id: str
    grounding_evidence: str | None = None  # The prompt that anchored this fact
```

On retrieval, the agent sees provenance — not just content. `"The payment service uses Stripe"` retrieved with `provenance=model:inference, reliability=0.3, session_id=june-12` is treated fundamentally differently from `provenance=user, reliability=1.0`.

### 4. Cross-session contradiction detection

Every memory retrieval runs a contradiction check against the established fact set:

```python
def contradiction_check(entry: MemoryEntry, semantic_memory: SemanticMemory) -> list[Conflict]:
    """Find contradicting entries before injecting into context."""
    contradictions = semantic_memory.query(
        entry.fact_set,
        mode='contradiction',
        exclude_self(entry.session_id)
    )
    if contradictions:
        escalate_to_human(
            f"Memory conflict detected: '{entry.content}' contradicts {contradictions}"
        )
    return contradictions
```

This catches the bootstrap loop's escalation: by session 3, the fabricated fact has generated contradicting conclusions from the same false premise. The contradiction check surfaces these without trying to auto-resolve — auto-resolution would just re-introduce the model's own bias.

### 5. Memory decay and confidence decay

Fabricated and inferred memories degrade in retrieval priority over time without reinforcement:

```python
def retrieval_priority(entry: MemoryEntry) -> float:
    base_score = entry.tier.reliability_weight * entry.reliability_score
    age_factor = math.exp(-DECAY_RATE * days_since_write(entry))
    reinforcement_bonus = entry.reinforcement_count * REINFORCEMENT_WEIGHT
    return (base_score * age_factor) + reinforcement_bonus
```

A FABRICATED entry that is never user-confirmed fades to near-zero retrieval priority within 30 days. An OBSERVED entry remains stable. This creates a natural gravity toward truth — confirmed facts persist, unconfirmed fabrications decay.

## Receipt

> Verified 2026-08-09 — Research synthesized from: Mistikguard (obscuraknight/mistikguard, Jun 2026) — four-component memory integrity system (provenance tracking, write gates, grounding audits, epistemic tiers); arXiv:2605.15338 "Hidden in Memory: Sleeper Memory Poisoning in LLM Agents" (2026) — formalizes fabrication propagation across sessions; Mem0 blog "Memory Poisoning in AI Agents" (Aug 7, 2026) — documents the self-hallucination write-back pattern; arXiv:2605.09252 "When2Tool" (UCSD, May 2026) — establishes that tool-call calibration requires treating model inference as unverified until grounded. Code patterns are illustrative; adapt epistemic tier thresholds and decay rates to your task criticality. A FABRICATED classification is not a permanent mark — it is a retrieval constraint until the entry receives reinforcement.

## See also

- [S-1189 · The Memory Integrity Gate](/stacks/s1189-the-memory-integrity-gate-when-your-agents-memory-starts-lying-to-itself.md) — evolving memory without governance produces lies; consistency gates and three-point failure maps predate this entry but complement it
- [S-1331 · The Epistemic Memory Stack](/stacks/s1331-the-epistemic-memory-stack-when-your-agent-stores-facts-beliefs-and-opinions-in-the-same-drawer.md) — epistemic tier classification for long-term memory; the tier model here is its direct operationalization
- [S-1208 · The Cascading Corruption Stack](/stacks/s1208-the-cascading-corruption-stack-when-one-wrong-fact-derails-your-entire-agent-run.md) — one wrong fact propagating through a single run; fabrication bootstrap is its multi-session analog
- [S-641 · The Environment-Injected Memory Poisoning Stack](/stacks/s641-the-environment-injected-memory-poisoning-stack-eTAMP-when-a-hidden-prompt-in-a-webpage-rewires-your-agent.md) — external injection of false memory; fabrication bootstrap is the internal variant where the agent poisons itself
