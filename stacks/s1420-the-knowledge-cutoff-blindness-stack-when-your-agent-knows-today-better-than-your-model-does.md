# S-1420 · The Knowledge Cutoff Blindness Stack — When Your Agent Knows Today Better Than Your Model Does

Your agent books meetings on past dates. Your research agent tells users a product launched in "early 2025" when it launched last week. Your compliance agent cites tax law that changed six months ago. The agent never errors, never flags uncertainty, never asks for clarification. The user acts on the answer. The failure only surfaces when someone notices the date was wrong.

This is **knowledge cutoff blindness**: the agent operates on a snapshot of reality frozen 6–18 months before deployment, and nothing in the system signals that the snapshot is stale. Error rates look fine. Latency looks fine. User sessions complete normally. The silent damage accumulates invisibly.

## Forces

- **Models don't know what they don't know.** LLMs trained on a fixed corpus interpolate confidently into post-training time. They don't return null or raise an exception — they generate a plausible answer from the training distribution.
- **Date anchoring is unreliable.** When asked "what day is it?", Claude defaulted to its knowledge cutoff date instead of the system date (GitHub #11728, confirmed by Anthropic). The model has no reliable self-reporting mechanism for its temporal position.
- **RLHF happens on stale data.** The alignment pipeline (RLHF, safety, instruction tuning) is trained on data that predates the base model's cutoff by months. The model's stated values and behaviors may reference facts that were true in 2024 but wrong in 2026.
- **Cutoff failures compound in agentic contexts.** A chatbot hallucinating a product launch date is embarrassing. An agent that auto-books a meeting room for a date in the past, or approves a workflow step based on superseded policy, causes real operational damage.
- **No alert fires.** Your observability stack monitors uptime, latency, token errors. None of these metrics cross a threshold when the model confidently answers a post-cutoff question. The failure is invisible to monitoring.

## The move

Treat knowledge cutoff as a production systems problem, not a model quality problem. The fix is architectural — at the boundary between the model and the world it reasons about.

### 1. Date injection as a mandatory system prompt prefix

Never rely on the model's self-reported date. Always inject:

```
Current date: {ISO_DATE}
Model knowledge cutoff: {MODEL_CUTOFF_DATE}
```

Track per-model cutoff dates explicitly in your LLM gateway config:

```
CLAUDE_3_5_SONNET_CUTOFF = "2025-11"
GPT_5_CUTOFF = "2026-03"
GEMINI_2_5_PRO_CUTOFF = "2026-05"
```

This is not a prompt engineering nicety — it is a correctness requirement. Without it, relative time expressions ("last quarter," "recently," "next month") are ungrounded.

### 2. Cutoff-aware content routing

Not all queries need live grounding. Classify at routing time:

| Query type | Route |
|---|---|
| Policy, law, compliance | Mandatory live retrieval |
| Market data, prices, inventory | Mandatory live retrieval |
| "Recent" or "current" without date anchor | Mandatory live retrieval |
| Historical facts, completed events | Model OK |
| Code, technical concepts | Model OK |

This is the pattern from tianpan.co's three-category model (April 2026): policy/compliance, current-state, and relative-time questions must never route to a bare LLM without freshness handling.

### 3. Uncertainty qualification on post-cutoff claims

When live grounding isn't available and the query touches post-cutoff territory, force the model to qualify its confidence:

```python
CUTOFF_AWARE_PROMPT = """
Answer the user's question. If your answer relies on facts that may post-date
your training cutoff ({model_cutoff}), prepend:
  ⚠️ Note: This information may be outdated. My training data ends {model_cutoff}.
  Verify with {recommended_source} before acting on this.
"""
```

### 4. Cutoff observability signal

Add a dedicated production metric: **retrieved-document-age distribution** — the age of the most recent document retrieved per query. Track continuously, alert on threshold crossings:

```python
def log_retrieval_age(query: str, docs: list[Document], cutoff_date: str):
    freshness = [(doc.updated_at, cutoff_date) for doc in docs]
    for updated_at, cutoff in freshness:
        age_days = (date.today() - updated_at).days
        metrics.gauge("retrieval_doc_age_days", age_days, tags={
            "query_type": classify_query(query),
            "above_cutoff": updated_at > parse_cutoff(cutoff)
        })
```

This metric is owned explicitly. When it crosses a threshold, someone is paged — not when a user reports wrong information.

### 5. Scheduled model recency audits

Pick the top 20 post-cutoff queries from production traces each quarter. Run them against current web search. Diff results. If accuracy drops below threshold, escalate. This catches the gradual drift between cutoff and now before it becomes a user-visible failure.

## The organizational gap

Knowledge cutoff failures fall between three teams that each correctly assess their own slice:

- **ML team**: "The model hasn't changed." True. The problem is pre-deployment.
- **SRE team**: "Infrastructure is fine." True. The problem is pre-inference.
- **Product team**: "The behavior is wrong." True. But they have no mechanism to surface it.

The fix is explicit ownership of a single metric: **cutoff-age exposure** — how often are users receiving answers that rely on post-cutoff facts? This must be a first-class production signal owned by the AI SRE function, not left to emerge from user complaints.

## Receipt

> Verified 2026-07-20 — Tian Pan (tianpan.co, April 2026) documents the structural gap. GitHub #11728 (Anthropic claude-code, 2179+ reactions) confirms date-anchoring failure at the model level. Zylos Research (2026-04-08) formalizes the four sub-problems of temporal reasoning. Three-category routing from tianpan.co used as the query-classification framework.

## See also

- [S-100 · Live Data Freshness Contracts](s100-live-data-freshness-contracts.md) — freshness contracts for live API data sources (different from model cutoff)
- [S-1002 · Memory Consolidation Debt](s1002-the-memory-consolidation-debt-stack-when-your-agent-gets-confused-about-what-it-already-knows.md) — memory staleness patterns
- [S-1013 · Trace Replay Harness](s1013-the-trace-replay-harness-when-your-agent-breaks-in-production-and-you-cannot-reproduce-it.md) — debugging production failures
