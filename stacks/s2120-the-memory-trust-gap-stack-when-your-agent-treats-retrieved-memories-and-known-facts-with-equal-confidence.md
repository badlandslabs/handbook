# S-2120 · The Memory Trust Gap Stack — When Your Agent Treats Retrieved Memories and Known Facts with Equal Confidence

Your persistent agent has been running for three weeks. It retrieved "User prefers PDF reports" from memory. It retrieved "API endpoint is v2.1" from memory. Both are correct — as of two months ago. Both are wrong now. The user switched formats and the API is on v3.0. The agent acts on both memories as current facts and nobody notices until the wrong output lands. This is not a memory retrieval failure. It is not a staleness problem. It is the Memory Trust Gap: your agent has no mechanism to distinguish "I retrieved this from persistent memory" from "I know this to be true." It treats all retrieved content with equal epistemic weight as directly observed information. The failure is invisible because nothing breaks — facts are retrieved, outputs are generated, and the answer is confidently wrong.

## Forces

- **Memory systems retrieve correctly but don't encode trust.** Vector stores return relevant content. The retrieval pipeline fetches it accurately. Nobody records whether it was written by the agent itself, by a user, or by a tool. Nobody records when it became true, when it might expire, or whether the world has since changed. The agent receives untyped facts and uses them as if they carry source guarantees they don't.
- **The model has no native epistemic status.** LLMs don't track how they acquired knowledge. "I read this in context two turns ago" and "I generated this response" and "this was stored in memory last week" all feel identical from the inside. The model has no internal flag saying "this is retrieved content with unknown freshness." Without explicit provenance, it defaults to equal confidence — which is wrong.
- **Persistence amplifies silent contamination.** OWASP ASI06 (Memory and Context Poisoning, 2026) maps the full attack surface: injected memories treated as ground truth, cross-session leakage of another user's data, corrupted episodic records influencing future decisions. The moment memory persists, every untrustworthy write becomes a durable, compounding error that grows across sessions.
- **Confidence gaps compound across the act loop.** MOMENTO benchmark (arXiv:2606.00832, 2026) found the primary failure mode of persistent agents is misestimation of user state — treating prior session history as reliable current context rather than stale information requiring re-validation. An agent with 95% per-step accuracy makes a 10-step memory-dependent decision with ~60% reliability. Each step amplifies the epistemic uncertainty from an untyped retrieval.

## The move

Three-layer stack: provenance labeling, confidence-gated action, and write-path hygiene.

### Layer 1 — Provenance as First-Class Attribute

Tag every memory entry with metadata the model can reason about:

```
Source: agent | user | tool | external_api | injected
Type: fact | preference | constraint | plan | context
Timestamp: ISO 8601 (written)
TTL: duration or null
Confidence: 0.0–1.0 (retrieval-score derived)
Verified: bool (cross-source confirmed)
```

The agent sees `[memory:fact|pref|src=user|t=2026-07-15|c=0.94|v]` not "User prefers PDF." Provenance becomes an epistemic signal the model can weight — retrieved content with low confidence or stale timestamp gets a different treatment than recent user-attested preference.

**Implementation:** Extend your memory schema to include these fields. Populate them at write-time. Return provenance alongside content on every retrieval. Add a system-prompt element: *"Distinguish [retrieved:memory] from [generated:response]. Retrieved content may be stale, poisoned, or low-confidence — flag uncertainty before acting on it."*

### Layer 2 — Confidence-Gated Action

Not all memories warrant action. Gate memory-dependent decisions behind explicit confidence thresholds:

- **Confidence < 0.7**: Flag as uncertain. Re-verify against live source-of-record before acting.
- **Confidence < 0.5 or age > 30 days**: Treat as hypothesis, not instruction. Surface to user for confirmation.
- **Memory vs. live-data conflict**: Always prefer live data. Log the divergence as a staleness signal.
- **Critical paths** (financial, security, permissions): Require cross-source verification — at least two independent provenance-confirmed entries agree.

The agent doesn't just retrieve and act. It retrieves, reads the provenance, and decides whether the epistemic weight of the retrieval actually justifies the action.

**Implementation:** Wrap the retrieval layer with a confidence evaluator. Derive confidence from: retrieval score × recency factor × source reliability. Return `(content, provenance, confidence_score)` on every call. Fail closed on critical paths.

### Layer 3 — Write-Path Hygiene

Memory trust is only as good as what gets written. Lock the write path:

- **Write attestation**: Every memory write records who/what wrote it (agent, user, tool) and under what context. Tool-written memories carry higher poisoning risk — flag them explicitly.
- **Poisoning resistance**: Input sanitization on memory write fields. Reject writes with embedded instructions (OWASP ASI06 pattern). Use a verification pass before committing.
- **Version, don't overwrite**: Store `(value, timestamp, invalidated_by)` tuples. The agent can audit when a memory changed and why, not just see the current state in isolation.
- **Retention policy**: TTL-based expiration. Confidence decay over time. Explicit invalidation when source-of-record changes. Don't let correct facts accumulate into confidently wrong ones.
- **Cross-session isolation**: User A's memory must not contaminate User B's context. Session-scoped memory boundaries are not optional.

**Implementation:** Memory writes go through a validation gate that checks format, scans for injection patterns, records provenance, and applies retention policy before committing. Treat your memory store like a database with ACID semantics — don't let dirty writes persist.

## Tradeoffs

- **Provenance overhead**: Tagging every entry adds storage and retrieval complexity. Start with the critical fields (source, timestamp, confidence) — add type and TTL as you learn what matters.
- **Confidence calibration drift**: Derived confidence scores need periodic re-calibration. Retrieval score distributions shift as your corpus changes.
- **Write-path friction**: Validation gates slow down memory persistence. Tune thresholds — production reads can be fast if write-path hygiene is strict.
- **User notification cost**: Surfacing uncertainty to users (Layer 2, confidence < 0.5) creates UX friction. Reserve it for high-stakes decisions; use silent verification for low-stakes ones.

## What This Is Not

- **Not context hygiene** (S-1773): That entry covers the problem of your context layer feeding agents technically accurate but contextually wrong data. This entry covers the meta-problem: the agent has no epistemic mechanism to notice the difference even when provenance is available.
- **Not memory staleness** (S-1574): That entry covers the symptom — old facts acting as current. This entry covers the root cause — the agent's equal-confidence treatment of retrieved vs. generated knowledge makes staleness invisible.
- **Not tiered memory** (S-1020): That entry covers the architecture of working/episodic/semantic memory layers. This entry covers the epistemic problem inside any memory layer: without provenance metadata, the agent cannot distinguish a reliable retrieval from a contaminated one.
- **Not memory poisoning** (OWASP ASI06): That covers the attack pattern. This covers the architectural defense — provenance labeling, confidence gating, and write-path hygiene make poisoning survivable rather than catastrophic.

## See also

- [S-1020 · The Tiered Memory Stack](s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — memory layer architecture
- [S-1574 · The Memory Staleness Spiral](s1574-the-memory-staleness-spiral-when-your-agent-knows-less-than-it-remembers.md) — symptom of the trust gap
- [S-1773 · The Context Hygiene Stack](s1773-the-context-hygiene-stack-when-your-agents-remember-things-that-never-happened.md) — context-layer data quality
- [S-1647 · The Memory Architecture Stack](s1647-the-memory-architecture-stack-when-your-agent-remembers-everything-and-knows-nothing.md) — comprehensive memory architecture
- OWASP ASI06 (Memory and Context Poisoning, 2026) — the security threat this stack defends against
- MOMENTO benchmark (arXiv:2606.00832, 2026) — the misestimation-of-user-state failure this stack addresses
