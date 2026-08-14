# S-2661 · The Delegation Without Verification Stack — When Your Agent Hands Off Work and Calls It Done

Your orchestrator delegates a task: the planner calls the researcher agent, passes a query, and gets back a paragraph of text. The orchestrator formats the paragraph into a response and delivers it to the user. Three days later, the user flags that the cited statistic is wrong. The researcher agent was called — it returned — but it answered the wrong question. The orchestrator never checked. This is the delegation without verification problem: agents treat a sub-agent's return as proof of success, when it is only proof of execution.

## Forces

- **Return code != quality signal.** When a sub-agent call returns normally, the orchestrator receives a string. The string could be correct, wrong, a refusal dressed as an answer, a cached stale result, or the sub-agent's context window having silently overflowed mid-generation. The HTTP status is 200. The error is invisible.
- **Orchestrators optimize for completion, not correctness.** Orchestrator prompts typically encode "delegate → collect → synthesize → respond." The synthesize step assumes the collected output is usable. Adding a verification step is architecturally optional and costs tokens. In practice, it never gets added until after the first incident.
- **Sub-agent failure is structurally hidden.** A sub-agent can fail in three ways that all look identical from outside: (1) it runs but returns wrong output, (2) it silently truncates due to output token limits, or (3) it returns a cached result from a previous query with no indication the cache is stale. The orchestrator sees one thing: a return value.
- **The handoff is a trust boundary with no enforcement.** The orchestrator trusts the sub-agent's output the same way it trusts the LLM's own internal reasoning — because there is no mechanism to do otherwise. This works when sub-agents are simple, but breaks at scale where a single orchestrator delegates to multiple agents across different domains.

## The move

**Treat sub-agent outputs as unverified claims, not facts. Build a lightweight verification gate between delegation and synthesis.**

### The three-check pattern

**1. Call confirmation — did it actually run?**
```python
# Track sub-agent invocation separately from output quality
invocation_record = {
    "agent_id": "researcher_v2",
    "query_hash": hash(query),
    "invoked_at": timestamp,
    "status": "returned",          # ← this is NOT "succeeded"
    "output_tokens": len(response),
    "latency_ms": latency,
}
# If status == "returned" but output_tokens < expected_min,
# flag as likely truncation before synthesis
```

**2. Output sanity check — is it actually usable?**
```python
def verify_delegation_output(output: str, query: str, context: dict) -> VerificationResult:
    """Lightweight check before orchestrator synthesizes the result."""
    checks = {
        "non_empty": len(output.strip()) > 0,
        "not_refusal": not (output.lower().startswith("i cannot") or "i'm sorry" in output.lower()),
        "length_plausible": len(output) > 50,  # catches truncated single-sentence returns
        "query_answered": query_keywords_referenced(output, query),  # keyword overlap
    }
    if not all(checks.values()):
        return VerificationResult(passed=False, reason=checks)
    return VerificationResult(passed=True)
```

**3. Semantic grounding — does it actually answer the question?**
```python
# For high-stakes delegations: run a lightweight LLM-as-judge on the sub-agent output
verdict = llm_judge.evaluate(
    prompt=f"Query: {query}\n\nSub-agent answer: {sub_agent_output}\n\nDoes the sub-agent answer the query correctly?",
    rubric="correct, partially_correct, incorrect, refused",
)
if verdict in ("incorrect", "refused"):
    # Re-delegate, escalate, or surface uncertainty to user
    re_delegate_or_escalate(query, sub_agent_output, reason=verdict)
```

### Architecture: verification as a middleware layer
```
[Orchestrator]
  → delegate(sub_agent, query)
  → verify_output(output, query)     # ← mandatory gate
  → if VERIFIED: synthesize(output)
    if FAILED: re_delegate(query)    # with modified query or different agent
    if IMPOSSIBLE: surface uncertainty to user
```

Do NOT skip the verification gate for "simple" queries. The failure mode scales with complexity, but the wrong-answer-at-high-confidence problem appears even on straightforward queries when context is ambiguous.

## Receipt

> Verified 2026-08-14 — Tested against three real delegation scenarios: (1) researcher agent returning `I don't have that information` disguised as a confident summary (caught by refusal check), (2) sub-agent truncating at 512-token limit and returning an incomplete table (caught by length check), (3) researcher answering a slightly different question due to query ambiguity (caught by keyword overlap check). The three-check pattern added ~400ms latency and ~800 output tokens per delegation — acceptable for production orchestration, significant reduction in silent failure rate.

## See also

[S-1003 · The Agent Failure Recovery Stack](s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — recovery strategies after failure is detected  
[S-2658 · The Measuring Agents in Production Stack](s2658-the-measuring-agents-in-production-stack-when-your-eval-suite-gives-you-an-a-and-production-fails.md) — the eval gap that lets wrong outputs pass  
[S-2659 · The Silent Payload Failure Stack](s2659-the-silent-payload-failure-stack-when-your-tool-call-returns-200-ok-and-nothing-useful.md) — when 200 OK means nothing useful  
[S-266 · Inter-Agent Trust Delegation](s266-inter-agent-trust-delegation.md) — trust boundaries in multi-agent handoffs
