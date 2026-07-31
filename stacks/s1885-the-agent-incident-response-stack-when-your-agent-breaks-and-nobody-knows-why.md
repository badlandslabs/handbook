# S-1885 · The Agent Incident Response Stack — When Your Agent Breaks and Nobody Knows Why

Your agent starts producing systematically wrong outputs on Tuesday. By Wednesday it's costing $3,000/hr instead of $200/hr. By Thursday a customer escalates — it sent the wrong pricing tier to 40 accounts. No error logs. No exceptions. HTTP 200 on every request. Your on-call engineer opens the trace viewer and sees 47,000 spans but can't tell which one caused the problem. This is the agent incident response gap: the tooling for investigating AI agent failures in production doesn't exist in most stacks, and the discipline to do it systematically is even rarer.

## Forces

- **Agents fail with the surface appearance of success.** Unlike a crashed service, a degraded agent returns plausible-looking responses. Standard alerting on error rate, latency, and CPU is blind to behavioral regressions. The agent is "working" by every metric your APM captures, and broken by every metric that matters to your users.
- **Debugging an agent means reconstructing one execution from six moving parts.** A failure typically traces to the interaction of model output, tool behavior, memory state, retrieval quality, prompt version, and external API response — each from a different system with different logs. Isolating the root cause without a structured methodology means staring at traces until someone gets lucky.
- **Production context is ephemeral.** The exact user message, the exact retrieval results, and the exact tool outputs that led to the bad outcome are often gone by the time you open the incident. Most tracing platforms capture spans but not the full environmental context needed to reproduce the failure.
- **Changing prompts during an incident makes it worse.** The instinct to "just fix the prompt" during a live incident is the single most common error. It ships untested changes under pressure, erases the pre-incident baseline, and often addresses the symptom rather than the cause.

## The move

### 1. Declare the incident around impact, not provider metrics

Activate incident response on **user-visible or safety-relevant symptoms** — not on model error rates or API latency:

- Unauthorized writes or data exposure
- Materially wrong outputs (verified by a human)
- Stuck workflows consuming tokens with no output
- Duplicate actions against external systems
- Rapid cost escalation without outcome improvement
- Any safety-relevant output deviation

Assign roles immediately: Incident Commander (owns timeline and comms), Technical Lead (owns trace investigation), and Observer (documents without intervening).

### 2. Preserve privacy-safe evidence before touching anything

```bash
# Export the full trace as a structured artifact before cleanup runs
# (most platforms purge after 7-30 days)
export TRACE_ID="abc123"
python -m your_observability_platform.export_trace \
    --trace-id $TRACE_ID \
    --output /incident-artifacts/trace-$TRACE_ID.jsonl \
    --include-spans --include-messages --include-tool-results

# Snapshot the agent's current configuration state
python -m your_platform.snapshot_agent_config \
    --agent-id $AGENT_ID \
    --output /incident-artifacts/config-$TRACE_ID.json

# Tag the incident in your eval tracking
python -m your_platform.tag_incident \
    --trace-id $TRACE_ID \
    --incident-id INC-$(date +%Y%m%d-%H%M) \
    --severity high
```

### 3. Reconstruct the root workflow across all systems

The root workflow is the sequence of agent decisions — not just tool calls — that led from input to bad output. Build it by threading through spans:

```
User input → [Retrieval results] → [LLM call #1: decision] →
[Tool call: search_pricing] → [Tool response: pricing_v2.json] →
[LLM call #2: synthesis] → [Final output]
```

Identify the **first deviation**: the first point where the trace shows the agent's reasoning or action diverging from the expected path. Everything before that is context; everything after is consequence. Most incidents have one root deviation.

### 4. Classify the failure mode

Use the 14-mode failure taxonomy from Tian Pan's field guide (2026):

| Mode | Signal | Typical cause |
|------|--------|---------------|
| Context poisoning | Wrong retrieval dominates context window | RAG returning stale/incorrect chunks |
| Schema misalignment | Agent asks for fields that don't exist | Tool schema drift since last deployment |
| Confidence miscalibration | Agent commits to low-confidence answer | Prompt didn't establish uncertainty threshold |
| Tool simulation | Agent produces tool output without calling | Missing tool; agent fills gap |
| Boundary drift | Agent acts outside stated scope | Context window compaction eroding system prompt |
| Loop escalation | Token cost spirals; output quality falls | No cost circuit breaker; agent re-reasoning |

### 5. Roll back first, investigate second

If a behavioral regression is suspected — especially after a recent prompt, model, or tool update — roll back before continuing the investigation:

```python
# Using git.agentic (git-for-agent-behavior)
# Rollback restores (code, prompts, tools, model, memory, schema) atomically
$ git.agentic rollback HEAD~1

# Using LangGraph checkpointing
from langgraph.checkpoint.memory import MemorySaver
checkpointer = MemorySaver()
# Restore to last known good state
config = {"configurable": {"thread_id": "incident-123", "checkpoint_id": "last-good"}}

# Using prompt versioning / prompt-git
$ prompt-git rollback --env production --steps 1
Rolled back: system-prompt-v42 → system-prompt-v41
Agent behavior snapshot: agentic-snapshot-2026-07-30-143022
```

This stops ongoing user harm while preserving the ability to compare the broken and fixed states side-by-side.

### 6. Write the post-mortem as a regression test

The most valuable output of an incident is a test case that would have caught it:

```python
def test_pricing_tier_routing_no_cross_contamination():
    """
    Regression: agent must not route to wrong pricing tier
    after INC-2026-0730 (pricing_v2.json schema change).
    """
    result = agent.run({
        "user_message": "Upgrade my account to enterprise",
        "context": {"account_tier": "starter", "eligible": ["pro", "enterprise"]}
    })
    assert "pro" not in result.output.lower() or "enterprise" in result.output.lower()
    assert result.cost_usd < 0.50
```

Add every post-mortem as a regression test. After six months, your test suite is a map of every way your agent has actually failed — far more valuable than any benchmark.

### The incident response checklist

```
[ ] Declare incident (severity, roles, timeline)
[ ] Preserve trace artifact to cold storage
[ ] Snapshot agent config state
[ ] Tag incident in eval platform
[ ] Reconstruct root workflow from spans
[ ] Identify first deviation point
[ ] Classify failure mode
[ ] Roll back if behavioral regression suspected
[ ] Compare broken vs. fixed trajectories
[ ] Write regression test
[ ] Update runbook with new failure mode
[ ] Close: document root cause + contributing factors
```

## Receipt

> Verified 2026-07-30 — Sources: Stanley Yang "How to Debug a Production AI Agent Incident" (stanleycyang.com, Jul 2026): structured 6-role incident framework, privacy-safe evidence preservation, root workflow reconstruction. GitHub "ai-incident-response-agent" (neehanayak, Apr 2026): FastAPI + LangGraph production implementation with log analysis + runbook retrieval. IBM "Revolutionizing Incident Management with Agentic AI" (ibm.com, 2026): automated DLP incident response flow. Velsof AI Agent Reliability Engineering guide (velsof.com, 2026): 3 a.m. runbook requirement. AgentMarketCap "Agent Reliability Engineering" (Apr 2026): SLO + error budget patterns for non-deterministic pipelines. git-agentic.com (May 2026): atomic behavioral rollback across six dimensions.

## See also

- [S-844 · Agent Incident Forensics](s844-the-agent-incident-forensics-stack-when-your-agent-failed-and-you-cant-reconstruct-why.md) — forensic artifact capture; AgentIncident open spec; S-844 covers the black-box recording layer; this entry covers the active investigation and response methodology. Read forensics first to know what artifacts to capture, then use this stack to work through them.
- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — SLOs, error budgets, and on-call discipline; S-1005 defines the reliability targets; this entry defines how to investigate when they're violated
- [S-235 · Production Failure to Regression Test](s235-production-failure-to-regression-test.md) — the test-writing step in this stack directly implements the pattern from S-235
- [S-1018 · Component-Level Attribution](s1018-the-component-level-attribution-stack-when-your-agent-is-wrong-but-says-200-ok.md) — the 14-mode failure taxonomy from S-1018 maps to the "Classify failure mode" step in this stack's incident workflow
