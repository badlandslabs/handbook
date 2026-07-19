# S-1331 · The Epistemic Memory Stack — When Your Agent Stores Facts, Beliefs, and Opinions in the Same Drawer

Your agent has been running for three weeks. It remembers that the user prefers Claude Code over Cursor. It also remembers that Claude Code is "better for large refactors." And it remembers a support conversation where a customer said Claude was "overhyped." Last Tuesday, the agent recommended Cursor to a new user based on the third memory. The agent cannot tell you which of these three memories is a verified fact, a concluded opinion, or a recalled experience — because it stored them identically. This is the epistemic memory problem: agents conflate evidence with inference with preference, and the retrieval layer has no way to distinguish them.

## Forces

- Standard agent memory treats all stored content as equally valid — facts, inferences, preferences, and past episodes all land in the same vector store
- The LLM then retrieves and uses all of them with equal confidence, creating confabulation chains where an inferred belief becomes treated as an observed fact
- Memory poisoning (OWASP ASI06) is more dangerous when injected content fills the same epistemic role as legitimate observations
- Standard RAG memory is built around *storage* optimization — what to extract and compress at ingestion time — but relevance is query-dependent and unknown at storage time
- Agents that conflate evidence types resist correction: updating a belief requires knowing it was a belief, not a fact

## The move

Separate memory into **epistemic tiers** — at minimum, distinguish *what was observed* from *what was inferred* from *what was stated*. Layer retrieval-aware preservation over epistemic classification.

**1. Build epistemic provenance into every memory write.**

Every memory record needs at minimum three provenance fields:

```
memory_record = {
  "content": "...",
  "epistemic_type": "observed" | "inferred" | "stated" | "experienced",
  "confidence": 0.0-1.0,          # source's reliability
  "provenance": "observation" | "llm_inference" | "user_statement" | "tool_result",
  "revision_chain": [...],         # prior versions if updated
  "surprise_score": None           # filled on read for Bayesian systems
}
```

**2. Classify at ingestion — but preserve verbatim first.**

Don't extract and discard at ingestion. Preserve the raw event (tool result, user statement, observation) verbatim, then classify its epistemic type. *True Memory* (Adler & Zehavi, arxiv:2605.04897) shows that content discarded before the query is known cannot be recovered at retrieval time — keep the full event, add the epistemic layer on top. Two systems handle this well:

- **Hindsight** (Latimer et al., arxiv:2512.12818): four-network epistemic architecture — World facts (objective observations), Beliefs (subjective inferences), Opinions (preference statements), and Self (agent identity/policy). Three operations govern lifecycle: Retain (add evidence), Recall (retrieve type-filtered), Reflect (update beliefs conditioned on preferences).
- **Nous** (Singh, arxiv:2606.22030): represents knowledge not as stored facts but as *predictive probability distributions* over entity-attribute pairs. Surprise-driven revision: information-theoretic surprise `S = -log₂ P(obs | D)` triggers Bayesian update. Forgetting is entropy decay, not deletion. This eliminates the evidence/inference blur entirely — the model *predicts* rather than *retrieves*.

**3. Use epistemic type as a retrieval filter, not just a metadata tag.**

At recall time, filter by type. A coding agent handling a refactor query should pull experienced-events + stated-preferences, not inferred-beliefs (which may be outdated). A compliance agent auditing past decisions should pull observed + experienced, not stated (user statements are not proof). Query-time filtering is more reliable than storage-time extraction because relevance is only known at query time.

**4. Make confidence conditional on source reliability.**

Reliability-conditional updating (Nous v2 finding): Bayesian updates provide real benefit only when source reliability is incorporated. A tool result from a reliable API gets a high reliability weight; a user statement in a heated support ticket gets low weight. Scale the update step accordingly:

```
reliability_weight = source_reliability * observation_relevance
posterior = Bayesian_update(prior, observation, weight=reliability_weight)
```

This also caps memory poisoning: provenance-capped poisoning defense (Nous v2) limits how much an injected observation can shift beliefs by bounding its reliability weight, regardless of surprise score.

**5. For simpler systems, use a three-tier epistemic schema.**

If the full probabilistic or four-network architecture is too much, fall back to:

| Tier | Label | Retrieval rule |
|------|-------|---------------|
| Observed | `🔵 fact` | Always retrieve — trusted source, verifiable |
| Stated | `🟡 said` | Retrieve with provenance tag — user statement, not confirmed |
| Inferred | `🔴 belief` | Retrieve last; treat as revisable |

Tag every memory write with one of these three. At retrieval, display the tag so the LLM reasons with epistemic awareness.

## Receipt

> Verified 2026-07-19 — Research from arxiv:2512.12818 (Hindsight, Dec 2025), arxiv:2606.22030 (Nous, Jun 2026 v2 Jul 2026), arxiv:2605.04897 (True Memory, May 2026). All three architectures independently converge on the same core problem: standard RAG-based memory blurs evidence and inference. Hindsight's four-network evaluation on PersonaBench (87.3% vs 61.4% baseline on epistemic consistency) and Nous's LoCoMo benchmark both quantify the gap. Key tradeoff: epistemic memory adds ingestion overhead and retrieval complexity for the benefit of reduced confabulation — evaluate whether your agent's epistemic confusion is actually causing failures before adding this layer.

## See also

- [S-09 · Memory Systems](s09-memory-systems.md) — episodic / semantic / procedural types (what to remember)
- [S-1002 · Memory Consolidation Debt](s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — why memory gets stale and how to consolidate
- [S-999 · Orchestration and Memory](s999-the-orchestration-and-memory-stack-when-your-agent-needs-to-know-what-it-already-knew.md) — the context window and what to store vs. retrieve
- [S-1193 · Context Scope Covenant](s1193-the-context-scope-covenant-stack-when-your-agent-decides-what-your-llm-vendor-knows.md) — data governance at the memory layer
