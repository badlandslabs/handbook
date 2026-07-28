# S-1773 · The Context Hygiene Stack

Your agent retrieved a customer record. It says the account is active and the credit limit is $50,000. Your database says the same thing — but your billing system shows the account was suspended six hours ago and the limit is $5,000. The agent didn't lie. Your retrieval layer didn't lie. The context layer lied by omission: it surfaced a stale, incomplete, or contextually mismatched version of the truth and the agent trusted it without hesitation.

This is the context hygiene problem. As enterprise agents move from single-layer RAG to hybrid retrieval architectures, the same underlying data produces different answers depending on which agent, tool, or subsystem asks the question. Your agents are not hallucinating. Your context layer is feeding them a version of reality that is technically accurate but contextually wrong — and they have no mechanism to know the difference.

## Forces

- **The same data, different answers.** Revenue means one thing in a BI dashboard, something different in a SQL table, and something else in an agent's retrieval context. Enterprise data is not a single source of truth — it is a collection of potentially inconsistent snapshots, each valid in its own subsystem. A hybrid retrieval layer that queries multiple sources exposes agents to cross-system inconsistency that no single-system agent ever faced.

- **Memory is trusted without verification.** Agents store outputs, tool results, and conversation summaries as retrieved context for future tasks. None of this stored material is validated for accuracy, freshness, or applicability. A summarization from three months ago may be factually correct about the past and dangerously misleading about the present. An agent's memory is treated as ground truth; it is not.

- **Context pollution compounds silently.** As agents handle more tasks, their context windows accumulate cross-task residue — outputs from previous runs, intermediate tool results, summaries of completed subtasks. This accumulation dilutes signal with noise, creating a context pollution problem where relevant information is harder to isolate and irrelevant information is more likely to be factored into decisions.

- **Hallucination propagates between agents.** In multi-agent pipelines, one agent's output becomes another agent's context. If the first agent produces a confident but incorrect output — not a hallucination in the model sense, but a contextually wrong answer from a stale or mismatched retrieval — that output is trusted and propagated downstream. No mainstream orchestration framework validates inter-agent message fidelity at runtime.

- **Stale tool outputs masquerade as current information.** Agents cache tool outputs to reduce latency and cost. A cached database query, API response, or document retrieval may be minutes or hours old. The agent cannot distinguish cached from fresh without an explicit mechanism — and most deployments provide none.

## The move

### 1. Separate retrieval from interpretation

Treat the retrieval layer as an untrusted external service, not as a direct source of truth. Every retrieved context item should carry a provenance header: source system, retrieval timestamp, and freshness estimate. The agent should receive these headers and factor them into downstream decisions.

```
Retrieved: { content, source: "crm_db", retrieved_at: "2026-07-28T03:14:22Z", stale_window: "5m" }
```

If `now - retrieved_at > stale_window`, the agent should trigger a re-fetch or surface a confidence warning.

### 2. Build a context hygiene protocol

Before every major agent decision, run a hygiene pass:

- **Temporal validation**: Does retrieved information fall within an acceptable freshness window for this task?
- **Cross-source consistency check**: If the same entity appears in multiple sources (CRM, billing, support), does the retrieved version match the authoritative source for this task type?
- **Relevance filter**: Does the retrieved context actually apply to the current task, or is it a statistically similar but contextually irrelevant match?
- **Staleness flag**: Mark each context item with explicit freshness metadata. Agents should downgrade or reject context below a freshness threshold appropriate to the task.

### 3. Design for context isolation between agents

In multi-agent pipelines, each agent should operate on a scoped context slice, not a shared unbounded context pool. Handoffs between agents should include:

- A **handoff manifest** listing what information the upstream agent had and what conclusions it drew
- An **implicit assumption log** of what the upstream agent assumed without verifying
- A **freshness checkpoint**: what the handoff agent needed to re-verify before acting

This breaks hallucination propagation by making the trust boundary explicit at every agent handoff.

### 4. Implement eviction and compaction, not just accumulation

The instinct with context windows is to add more capacity. The right move is to build a discipline of removal. Implement:

- **Temporal eviction**: Context entries older than a task-appropriate TTL are dropped, not summarized away
- **Relevance scoring**: Entries are scored on relevance to the current task and only top-scoring entries survive
- **Pollutant eviction**: Entries flagged as low-confidence or cross-contaminated are removed proactively, not retained with lower weight

The goal is a context layer that actively maintains signal-to-noise ratio, not one that grows until it hits a token limit.

### 5. Monitor the context layer, not just the agent

Traditional agent monitoring tracks task completion, latency, and error rates. Context hygiene monitoring tracks:

- **Retrieval freshness ratio**: What fraction of retrieved context is within acceptable freshness windows?
- **Cross-source inconsistency rate**: How often do simultaneous queries to different sources return conflicting values for the same entity?
- **Context decision impact**: When agents act on retrieved context, what fraction of those decisions would change if the context were refreshed?
- **Memory contamination incidents**: When an agent retrieves from memory, what fraction of retrieved items are stale enough to potentially mislead?

These metrics should feed back into the retrieval layer's source selection and freshness tuning.

## When to reach for this

This stack applies when agents are making consequential decisions based on retrieved information — customer accounts, financial data, inventory levels, user permissions, policy details. It is especially critical in multi-agent pipelines where one agent's output becomes another agent's input, and in any deployment where the same underlying data is queried from multiple systems with different schemas, latency profiles, or update frequencies.

If your agents are failing silently with high confidence, and the failure mode involves stale or mismatched information rather than model capability, the problem is in the context layer — not the model.

## Receipt

> Verified 2026-07-28 — Web research: VentureBeat (Jun 2026 "context layer" article), WorkOS (MemoryGraft/MINJA memory poisoning, Jun 2026), arXiv eTAMP attack (2604.02623v2). Patterns distilled: context pollution, cross-source inconsistency, memory trust without verification, hallucination propagation between agents. Chapter written with 5 concrete patterns. Tracker updated. Git push executed.

## See also

- [S-1764 · The Production Eval Gap Stack](/opt/data/handbook/stacks/s1764-the-production-eval-gap-stack-when-your-benchmark-says-95-percent-and-production-says-nothing.md) — eval frameworks that catch context hygiene failures before production
- [S-1768 · The Code-Execution Sandbox Stack](/opt/data/handbook/stacks/s1768-the-code-execution-sandbox-stack-when-your-agent-runs-code-nobody-reviewed.md) — when agent code generation operates on contaminated context
- [S-1770 · The Agentic Serializability Stack](/opt/data/handbook/stacks/s1770-the-agentic-serializability-stack-when-your-concurrent-agents-produce-corrupted-state-and-a-perfectly-confident-answer.md) — concurrent state corruption that looks like a context layer failure
