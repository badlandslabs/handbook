# S-2419 · The Memory Drift Stack — When Your Agent Answers Correctly Once, Then Wrongly Forever

Your RAG pipeline retrieves the right documents. Your agent generates the right answer. Three weeks later, on the exact same query, it generates the wrong answer — even though nothing in your knowledge base has changed. The retriever still works. The model is the same. The failure is in between: your agent has absorbed its own past outputs into memory, and those outputs are now overriding fresh retrieval. This is memory drift — and unlike memory poisoning (S-2151), no attacker is involved. The agent did it to itself.

## Situation

You deploy an agent that uses RAG over your internal knowledge base. On day one, it retrieves the correct policy and gives correct answers. Over weeks of production use, the agent accumulates a growing body of its own reasoning traces, summaries, and retrieved passages stored in session and long-term memory. Some of those stored items contain errors — wrong interpretations, hallucinated facts, stale answers the user accepted. As the agent's memory grows, it increasingly retrieves *its own past outputs* rather than the authoritative source. The parametric knowledge override (S-947) then amplifies these: the model's training biases align with its own stored errors, and fresh retrieval is silently bypassed. The agent is no longer answering from your knowledge base — it is answering from a slowly degrading echo of itself.

## Forces

- **Agents learn from their own history.** Any agent that stores past reasoning, summaries, or retrieved passages in memory will eventually retrieve and act on those stored items. When those items contain errors, the errors compound.
- **RAG retrieval is not authority-aware.** A standard vector similarity search ranks by relevance to the query, not by trustworthiness of the source. An agent's own confident past answer — rich with task-specific keywords — often ranks higher than a neutral policy document.
- **Parametric priors amplify stored errors.** When a stored item partially conflicts with authoritative retrieval, the model's pretraining weights (which encode "common" answers) act as a tiebreaker. If the model's prior aligns with the stored error rather than the fresh document, retrieval loses.
- **Cross-session contamination spreads without prompt injection.** Unlike prompt injection attacks (S-2151), memory drift requires no adversary. It emerges from normal agent operation: the agent generates an answer, that answer gets stored, subsequent sessions retrieve it, and the cycle compounds. WorkOS (June 2026) and MemoryGraft research (December 2025) document this as distinct from malicious memory poisoning.
- **The failure is invisible until it isn't.** No error is raised. Logs show successful retrieval, successful reasoning, a confident answer. The degradation is gradual — correct answers become less frequent over weeks — and the disconnect from source material is structural, not a bug.
- **Evaluation detects it late.** Standard QA evals test against ground truth, not against source-of-truth tracking. An agent can score 90% on eval while systematically drifting from the authoritative knowledge base, because the eval ground truth may itself reflect the drifted state.

## The move

**Enforce source provenance in memory, not just in retrieval.**

### Separate agent memory from authoritative knowledge

```
Memory tier          | Content                     | Retrieval priority
---------------------|-----------------------------|------------------
Agent-authored       | Past summaries, reasoning   | Lowest (tagged)
User/system-provided | Policies, docs, RAG hits    | High
Tool-call results    | API outputs, search hits    | Medium
```

Never mix agent-authored content into the same retrieval space as authoritative sources. Tag every memory entry with `source: agent | user | tool | system`. At retrieval time, weight by source tier before semantic similarity.

### Gate memory writes with source filtering

Before storing any agent output in long-term memory, run it through a contamination check:

1. Retrieve the authoritative source for the same query.
2. If agent output conflicts with source, flag the divergence.
3. Store the conflict metadata alongside the memory entry — or discard the agent-authored entry entirely if the source is definitive.

This mirrors the generator-retriever mismatch fix (S-626) but applied to the agent's own output rather than third-party RAG.

### Stamp every retrieved item with freshness metadata

```json
{
  "content": "...",
  "source": "policy-v3.pdf",
  "retrieved_at": "2026-08-10T14:00:00Z",
  "agent_authored": false,
  "freshness_score": 0.95
}
```

Query-time: only surface entries with `freshness_score > threshold`. Evict agent-authored entries older than N days unless explicitly confirmed against authoritative source.

### Run periodic drift audits

Schedule a automated check: for each high-frequency query, compare the agent's current answer against the authoritative RAG answer. Track drift rate over time. Alert when drift exceeds 5% on critical queries. This is the production analog of regression testing for knowledge contamination.

### Use source-conditioned prompting at generation time

Force the agent to cite the specific source document for each factual claim:

```
Answer using only information from [RETRIEVED_DOCS].
If you are drawing on information not present in [RETRIEVED_DOCS],
state explicitly: "This is not from the retrieved documents."
```

This makes contamination visible in the output rather than silent in the trace.

## Receipt

> Verified 2026-08-10 — Research basis: Tian Pan (April 17, 2026, tianpan.co) formally defines knowledge contamination as a distinct failure mode from parametric knowledge override — contamination is self-generated, not training-induced. arXiv:2606.21666 (Rodrigues, June 2026) introduces Context Divergence Score (CDS) for measuring knowledge-state mismatch between concurrent agents, applicable to cross-session drift measurement. WorkOS (June 9, 2026) confirms memory poisoning and knowledge contamination are distinct attack classes — contamination requires no adversary, only normal agent operation. arXiv:2604.21131 (Azarafrooz, April 2026) provides Cross-Session Threats benchmark with memory contamination as a named category. Dedup: S-947 (Parametric Knowledge Override) covers model training weights overriding explicit context — not self-generated memory contamination. S-626 (Generator-Retriever Mismatch) covers retrieval bypass at call time — not cross-session memory accumulation. S-2151 (Memory Poisoning) covers adversarial injection — not self-compounding error. S-2088 (Forgotten Context) covers forgetting between sessions — not the inverse problem of remembering wrong things. The cross-session compounding mechanism (correct → stored → retrieved as authoritative → drifts → re-stored) is not covered by any existing entry.

## See also

- S-947 · The Parametric Knowledge Override Stack — When Your Agent Knows Better Than What You Told It
- S-626 · The Generator-Retriever Mismatch: When RAG Silently Fails
- S-2151 · The Memory Poisoning Stack — When Your Agent Stores What Attackers Want It to Remember
- S-2088 · The Forgotten Context Stack — When Your Agent Remembers Nothing the Moment the Session Ends
