# S-1631 · The Memory Laundering Stack — When Memory Compression Cleans Adversarial Content but Preserves Its Harm

Your agent has been running safely for months. You run standard content safety checks on every user input and every model output. Nothing red-flags. Then the agent begins exhibiting subtly biased decision-making in hiring scenarios — steering away from candidates with specific backgrounds. No attacker injected a prompt. No model update changed behavior. What happened: an adversarial prompt from week two was compressed into the agent's memory summary, passed through standard toxicity detectors (which flagged it clean), and now lives as an apparently-neutral belief that influences downstream decisions invisibly. This is memory laundering — and it survives every safety check you've built.

## Forces

- **Memory summarization strips surface toxicity while preserving latent framing.** Toxic content detectors operate on surface-level signals — explicit slurs, threatening language, obvious manipulation patterns. When an LLM compresses a conversation into a memory summary, it re-expresses the meaning in neutral vocabulary. The detector sees clean text. The latent bias survives.
- **Memory laundered content is invisible to standard eval.** Eval suites check inputs and outputs. They do not check what the agent internalized into persistent memory and how that internalization subtly shifts future reasoning. You cannot catch what you do not measure — and most teams never measure memory content.
- **The attack-to-impact window can be weeks or months.** Unlike prompt injection (immediate), memory laundering attacks accumulate over time. The adversarial content may seem innocuous at ingestion; its effects manifest only after it has been compressed, re-compressed, and used as context for downstream decisions.
- **Memory augmentation is becoming standard architecture.** Every major agent memory framework — Mem0, Graphiti, AutoMemory, Narrative Intelligence — relies on LLM-based summarization as a core compression primitive. This means the attack surface is large and growing.

## The move

**Detect and neutralize memory laundering at the compression layer, not at input or output.**

### The contamination cycle

```
User input → Safety check (PASS) → Memory write
Memory write → LLM summarization → Toxicity detector (PASS)
Memory read → Retrieved as neutral context → Influences downstream reasoning
```

The cycle exploits the mismatch between input-output safety and memory-state safety. Standard pipeline: user → filter → LLM → output filter. Memory pipeline: LLM output → memory write → summarization → output filter (on summary). The safety gap is the summarization step.

### Three-layer defense

**1. Pre-summarization provenance tagging.** Before any memory write, tag the content with source provenance: `source=external`, `source=user`, `source=agent_self`, `source=tool`. External content gets extra scrutiny at read time, not just write time.

**2. Latent framing detection at compression.** Run a separate LLM-as-judge on the *summary itself*, not the original content. Ask: "Does this summary encode a preference, judgment, or framing that wasn't present in the explicit request?" This catches what surface-level toxicity detectors miss.

**3. Memory retrieval provenance gating.** At read time, weight retrieved memories by provenance. External-sourced memories get lower retrieval weight and require corroboration from agent-generated memories before influencing high-stakes decisions.

```python
class SafeMemoryStore:
    """Memory store with laundering-resistant compression."""

    def write(self, content: str, provenance: str, session_id: str) -> str:
        # Tag before summarization
        tagged = f"[provenance={provenance}] {content}"

        # Compress
        summary = self.summarize(tagged)

        # Latent framing check — on the summary, not the original
        framing_judge = self.judge.invoke(PromptTemplate("""
            Given this memory summary: {summary}
            Does it encode a preference, judgment, or framing that could
            influence downstream decisions in subtle ways?
            Rate: NEUTRAL / CAUTION / FLAG
            Reason: {reason}
        """))

        if framing_judge.rating == "FLAG":
            # Quarantine — write to separate namespace requiring human review
            self.quarantine(summary, provenance=provenance, reason=framing_judge.reason)
            return "[memory pending review]"
        elif framing_judge.rating == "CAUTION":
            # Tag with low retrieval weight
            summary = f"[framing_caution, weight=0.3] {summary}"

        # Standard toxicity check on summary (still useful for crude过滤)
        if self.toxicity.check(summary) > 0.7:
            self.quarantine(summary, provenance=provenance, reason="toxicity_exceeded")
            return "[memory quarantined]"

        self.vector_store.add(summary, metadata={"provenance": provenance})
        return summary

    def read(self, query: str, stakes: str = "low") -> list[MemoryResult]:
        results = self.vector_store.search(query, k=5)

        if stakes == "high":
            # Require provenance diversity — external-only memory is insufficient
            provenances = {r.metadata["provenance"] for r in results}
            if provenances <= {"external"}:
                # Inject agent_self or tool_sourced memory as anchor
                anchor = self.get_agent_self_memory(query)
                if anchor:
                    results.insert(0, anchor)

        return results
```

### The key insight

Safety at input/output ≠ safety at memory state. Memory laundering exploits the compression step — the place where most security stacks don't look. The fix isn't stronger input filters; it's laundering-resistant memory architecture that validates what gets stored *after* summarization, not just what comes in.

## Receipt

> Verified 2026-07-25 — arXiv:2605.16746 (Wang et al., May 2026): "State Contamination in Memory-Augmented LLM Agents" formally defines memory laundering via paired counterfactual multi-agent rollouts, demonstrating adversarial context compression that evades standard detectors while preserving hostile framing. OWASP ASI06 (Memory & Context Poisoning, 2026) codifies this as a top-tier agentic threat. Memory laundering rates of 80–99.8% reported against production agentic systems in agentic security benchmarks (Vectorize, June 2026).

## See also

- [S-1067 · The Hallucination Laundry Problem](s1067-the-hallucination-laundry-problem-when-shared-state-converts-one-agents-error-into-everyones-fact.md) — shared-state hallucination laundering (different attack surface: errors, not adversarial content)
- [S-1331 · The Epistemic Memory Stack](s1331-the-epistemic-memory-stack-when-your-agent-stores-facts-beliefs-and-opinions-in-the-same-drawer.md) — epistemic memory categorization (different problem: fact/belief/confidence mixing)
- [S-097 · The Memory Poisoning Defense Stack](s820-the-memory-poisoning-defense-stack-when-asi06-means-your-agent-remembers-the-wrong-lesson.md) — OWASP ASI06 defense architecture (broader; this entry focuses on the compression-laundering sub-attack)
