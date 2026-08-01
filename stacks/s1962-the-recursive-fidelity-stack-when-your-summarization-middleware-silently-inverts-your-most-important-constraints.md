# S-1962 · The Recursive Fidelity Stack — When Your Summarization Middleware Silently Inverts Your Most Important Constraints

*When your agent learns a critical constraint, follows it for 30 turns, then violates it — not because the model forgot, but because the compression middleware stripped the constraint out three compression cycles ago and nobody noticed until the violation was already live.*

## Forces

- **Generic summarizers destroy constraints predictably.** A "never approve without ID" or "do NOT use eval()" is high-information for your domain but low-entropy for a general-purpose summarizer — so it gets dropped. This is not random noise; it's a systematic blind spot.
- **Recursive compression compounds loss across cycles.** Each summarization run takes the *previous summary* as input. If that summary already dropped a caveat, the next one drops more. By cycle 10-15, the constraint has been inverted silently. The agent isn't misbehaving — it's faithfully following the compressed version of what you told it.
- **Fidelity loss is invisible at evaluation time.** You unit-test the model. You don't unit-test every compression artifact. The violation shows up in production, not in the test suite.

## The move

**Preserve constraint, caveat, and exception signals through compression cycles — structurally, not stylistically.**

### 1. Isolate constraints from compressible content

Mark hard boundaries in context with structural delimiters the summarizer cannot ignore:

```
=== CONSTRAINT === (never remove this)
- Do NOT use eval() under any circumstances
- Require valid government ID before approving claims
- Escalate to human before executing any delete operation
=== /CONSTRAINT ===
```

Generic summarizers respect section headers as structural signals. A dedicated `=== CONSTRAINT ===` section forces the summarizer to treat its contents as a mandatory output slot, not compressible prose.

### 2. Incremental compression over wholesale regeneration

Full regeneration accumulates drift — each pass can drop different details. Instead, summarize only the newly-truncated span and merge into the existing summary:

```
existing_summary + newly_truncated_span → merge_prompt → new_summary
```

This caps the maximum information loss per cycle to the size of the new span, rather than the entire context history. ACE (Agentic Context Engineering, arXiv:2510.04618, ICLR 2026) formalizes this as the correct pattern — results match top production agents with smaller open-source models.

### 3. Structured compression output with mandatory slots

Freeform summarization can omit anything. Structured output with required slots prevents selective omission:

```json
{
  "constraints": ["<never-remove constraints>"],
  "exceptions": ["<conditions that override constraints>"],
  "decisions": ["<conclusions reached>"],
  "open_questions": ["<things not yet resolved>"],
  "sources": ["<evidence that must be preserved>"]
}
```

The summarizer must populate all slots. An empty slot is immediately visible. A dropped constraint surfaces as an absent field.

### 4. Measure fidelity drift, not just compression ratio

Track what compression destroys, not just how much it saves:

- **Delta probe**: After each compression, run a targeted probe asking "what are the hard constraints?" and diff against the pre-compression version
- **Constraint preservation rate**: Fraction of `=== CONSTRAINT ===` markers present in summary vs. original
- **Exception boundary check**: Feed the summary + a test exception case; verify the agent still refuses

Compression ratio is the wrong metric. 57% token savings with 0% accuracy loss is fine for闲聊. For compliance-gated actions, 15% savings with 100% constraint preservation beats it.

### 5. Audit compression artifacts in CI, not just in prod

Add compression artifact testing to your agent CI pipeline:

```python
def test_compression_preserves_constraints():
    original_constraints = extract_constraints(system_prompt)
    compressed = compressor.summarize(full_context, budget=tokens)
    recovered_constraints = probe_constraints(compressed)

    missing = original_constraints - recovered_constraints
    assert missing == set(), f"Compression dropped constraints: {missing}"
```

Run this against every compression version of every critical system prompt. Treat a dropped constraint as a test failure, not a warning.

## Receipt

> Verified 2026-08-01 — arXiv:2606.29251 (When Summaries Distort Decisions, June 2026) confirms decontextualization (retained evidence separated from caveats/qualifiers) and model dependency (compression-model assumptions leak into downstream decisions) as the two dominant fidelity-loss patterns. Tian Pan (tianpan.co, May 2026) documents real-world cases: "never use eval()" dropped by turn 30, "require valid ID" violated after 15 compression cycles — both compression failures, not model failures. Microsoft ACON (arXiv:2606.08162) classifies four compression failure modes: in-context information loss (F1), in-compression hallucination (F2), out-of-context information loss (F3), tool representation truncation (F4). ACE (ICLR 2026) demonstrates that incremental merge compression prevents the drift accumulation inherent in wholesale regeneration.

## See also

- [S-1002 · The Memory Consolidation Debt Stack](stacks/s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — consolidation debt is the consequence when fidelity loss goes uncorrected
- [S-1000 · The Context Exhaustion Stack](stacks/s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — the eviction problem that triggers compression in the first place
- [S-1035 · The Context-Capacity Gap](stacks/s1035-the-context-capacity-gap-when-your-agent-reads-everything-and-knows-less.md) — why models lose effective attention before the window is full
