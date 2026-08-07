# S-2214 · The Semantic Drift Stack

Your agent started reliably. Three months in, it confidently tells a new employee that the Postgres migration happened in March — it was April. It insists the Q3 OKRs include the Lima project — that was Q2. You check the original records. The agent is wrong, and it has been becoming more wrong, slowly, for weeks. The context window is fine. The model hasn't changed. The problem is memory consolidation: every summarization cycle degrades the signal, and the agent is now confidently storing its own accumulated errors as fact. This is semantic drift — the slow, invisible corruption of agent knowledge through repeated consolidation.

## Forces

- **Summarization is lossy.** Every consolidation pass drops detail, flattens nuance, and re-phrases in the LLM's own voice. After 10 consolidation cycles, a precise fact ("client Acme Corp cancelled on 2026-04-15, refund issued, escalation not needed") becomes a vague generalization ("Acme Corp has been handled"). Precision erodes monotonically.
- **Consolidation introduces hallucination.** TrustMem (Yang et al., arXiv:2606.25161, 2026) documents three failure modes per consolidation pass: *corruption* (existing facts are modified — Voltaire placed in the 17th instead of 18th century), *omission* (key details are dropped), and *hallucination* (entirely new facts are introduced — "John W. Ingram attended the meeting" with no supporting evidence). After multiple cycles, these compound.
- **The agent trusts its own memory.** An agent that retrieves a memory entry treats it as authoritative — it was written by a previous version of itself. Unlike a human source, there is no credibility heuristic. The corrupted entry is retrieved, believed, and used as the basis for the next round of reasoning, which generates the next corrupted memory.
- **Drift is invisible until it causes an incident.** Unlike a hard failure (crash, error message, obvious wrong output), semantic drift produces plausible-sounding, internally consistent wrong knowledge. There is no error signal. The agent doesn't know it's drifting. You find out when a customer calls to correct the record, or when the agent recommends a workflow it rejected three months ago.
- **The problem is architectural, not model-level.** Changing the model does not fix drift — the consolidation policy carries the corruption forward into the new model's memory store. The issue is how memory entries are written, merged, versioned, and audited, not which LLM sits behind the retrieval layer.

## The move

### Track consolidation lineage

Every memory entry carries a version history. Store not just the current state but the chain of consolidations: which prior version produced this entry, when it was consolidated, and what the consolidation prompt was. This turns drift into a forensic problem — you can trace when a fact first appeared and through how many cycles it has been propagated.

ChronoMem (arXiv:2607.27773, integrated into Google ADK) is the first production-ready implementation: agents commit whole-memory snapshots at each write, maintain structured version histories, and support natural-language rollback ("undo the last memory update about Acme"). For teams without ADK, implement a lightweight version log: append-only JSONL where each consolidation write logs `(parent_version, timestamp, consolidation_prompt_digest, entry_hash)`.

### Enforce a "consolidation budget"

Limit how many times a memory entry can be re-consolidated before it is either promoted to a privileged format (immutable fact record, schema-defined) or evicted and re-learned from raw interaction data. TrustMem's approach uses learned consolidation with terminal reward signals — the policy is trained to minimize corruption/omission/hallucination rather than just token reduction. For teams without a trained policy, a simpler rule: entries older than 30 days, or that have been consolidated more than 5 times, are flagged for human review before the next retrieval cycle.

The core insight from RecMem (ACL 2026 Findings, Dai et al.): eager consolidation — processing every interaction for memory extraction — is both expensive and harmful. Use *recurrence-based consolidation*: an entry is only re-processed when it is retrieved and flagged as potentially stale, not on every session. This reduces token cost and limits the number of consolidation cycles, slowing drift.

### Detect drift before it causes incidents

Add a lightweight *semantic consistency check* to the retrieval path: before returning a memory entry, run a small LLM call that asks "is this fact consistent with the raw interaction logs from the same time period?" This is a two-line check:

```python
def retrieve_with_drift_check(entry_id: str, query: str) -> str:
    entry = memory_store.get(entry_id)
    raw_logs = interaction_log.get_original_facts(entry.timestamp_range)
    consistency_prompt = (
        f"Original facts: {raw_logs}\n\nCurrent memory entry: {entry.content}\n"
        f"Question: Does the memory entry accurately reflect the original facts? "
        f"Answer yes/no and note any discrepancies."
    )
    result = llm.call(consistency_prompt)
    if "no" in result.lower() or "discrepancy" in result.lower():
        audit_log.warning(f"Semantic drift detected: {entry_id}", extra=result)
        # Serve raw logs instead, flag for repair
        return serve_raw_instead(entry_id, raw_logs)
    return entry.content
```

This is not cheap per-call, but it runs only on retrieved entries (not all interactions), and catching a drift incident before a customer-facing recommendation is worth the cost.

### Implement provenance-backed retrieval

When retrieving memory, do not treat all entries as equivalent. Weight entries by provenance: direct tool-output records (authenticated, timestamped) rank higher than LLM-summarized entries, which rank higher than LLM-generated inferences. The OWASP Agent Memory Guard pattern assigns Bayesian trust scores per entry based on source type, and enforcement below a configurable threshold (`S_t + 1 = Φ(S_t, o_t, ...)`) triggers either rejection or human review.

For shared-memory multi-agent systems, provenance is especially critical: an entry written by Agent A and consumed by Agent B in a different context carries the full blast radius of its corruption across the agent ecosystem.

### Audit memory quarterly

Run a quarterly "memory health audit" on all long-running agents:

1. Sample 50 memory entries from the last 90 days
2. For each, retrieve the original interaction logs from the same period
3. Score consistency (TrustMem's three failure modes: corruption, omission, hallucination)
4. If >10% of entries show drift, trigger a full memory repair cycle

This is the operational equivalent of a database integrity check — boring, essential, and almost nobody does it.

## Receipt

> Verified 2026-08-06 — Research synthesized from: TrustMem (Yang et al., arXiv:2606.25161, Samsung/Notre Dame), ChronoMem (arXiv:2607.27773, Google ADK), RecMem (Dai et al., ACL 2026 Findings), Hindsight memory consolidation analysis (May 2026), OWASP Agent Memory Guard (ASI06), and the consolidation problem taxonomy from SSGM framework (Lam et al., arXiv:2603.11768). Key failure modes confirmed: corruption, omission, hallucination per consolidation pass. Countermeasures: version control (ChronoMem), recurrence-based consolidation (RecMem), trust scoring (OWASP), drift detection (TrustMem). No prior handbook entry covers semantic drift as a distinct failure mode from memory poisoning (S-1050) or forgetting/consolidation debt (S-1002).

## See also

- [S-1002 · The Memory Consolidation Debt Stack](s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — when agents forget what they knew (eviction failure)
- [S-1050 · The Tool-Response Poisoning Stack](s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — adversarial memory corruption via tool outputs
- [S-1020 · The Tiered Memory Stack](s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — architecture for memory tiering across sessions
