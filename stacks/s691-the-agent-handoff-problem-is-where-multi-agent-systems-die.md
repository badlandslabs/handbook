# S-691 · The Agent Handoff Problem Is Where Multi-Agent Systems Die

[Multi-agent demos dazzle. Multi-agent handoffs fail silently. The context that falls through the crack between agents — the schema versioning bug, the lost escalation flag, the supervisor that handed off but never confirmed — is the dominant production failure mode, and most teams discover it only after the incident.]

## Forces

- **The agent is not the failure point. The boundary is.** 89% of teams have observability tooling, but only 52% have evals. You know the agents are running; you do not know if they handed off correctly. — [Raft Labs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Multi-agent costs 2–5× more in tokens for the same work.** Gravity calls this out directly: the overhead is only justified when work has genuine boundaries that make the cost worthwhile. Most teams add agents for the wrong reason. — [Gravity](https://gravity.fast/blog/ai-agent-multi-agent-coordination)
- **Untyped handoffs kill multi-agent workflows faster than any other issue.** Every agent-to-agent boundary needs a validated schema with version numbering. Without it, you get silent data corruption between agents, not a crash. — [Raft Labs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **The observability gap is an eval gap.** Tracing shows you what happened. Evals tell you if it was right. Most multi-agent debugging is guesswork because teams have the former but not the latter.

## The move

**Treat handoffs as the hard problem. Design the contract before you design the agents.**

### Four coordination patterns, four failure modes

| Pattern | Best for | Failure mode | Debugging |
|---------|----------|--------------|-----------|
| **Supervisor** | Controller delegates to specialists | Supervisor never hands back | Easiest — supervisor trace = full decision path |
| **Peer / handoff** | Stage-based work (sales → support) | Context dropped mid-handoff | Moderate — trace shows both agents, verify schema |
| **Market / bidding** | Task allocation with trade-offs | No bid wins, task stalls | Hard — need bid trace + timeout circuit breaker |
| **Shared-state** | Collaborative workspace | Conflicting writes, stale state | Hardest — need versioning + conflict resolution |

Source: [Gravity](https://gravity.fast/blog/ai-agent-multi-agent-coordination)

### Typed schema at every handoff boundary

```python
# Every handoff must carry a versioned, validated payload
@dataclass
class HandoffPayload:
    schema_version: str = "1.2.0"   # must match receiver's expected version
    payload: dict                     # pydantic-validated before send
    trace_id: str                     # for correlating across agent boundaries
    escalation_flags: Optional[dict]  # explicit, not implicit
    retry_count: int = 0

# Receiver validates on arrival — reject and escalate, never silently proceed
```

### Circuit breakers at every layer

- **Per-agent:** Max 3 retries with exponential backoff; log failure reason to persistent store before escalating.
- **Per-handoff:** Timeout with fallback — if the downstream agent doesn't confirm within N seconds, route to human-in-the-loop or return partial result.
- **Per-workflow:** Cap total spend per execution regardless of complexity.

Source: [QASkills](https://qaskills.sh/blog/multi-agent-system-testing-guide-2026), [Agile Leadership Day](https://agileleadershipdayindia.org/blogs/ai-agent-orchestration-production-deployment-playbook/multi-agent-system-failure-modes-enterprise.html)

### Default to single-agent

Gravity's rule: multi-agent earns its place only when work has real boundaries — different access controls, different tools, or different models. If a single agent with tool selection and memory can do the job, it will be cheaper, faster, and easier to debug. The 4-agent orchestrator-worker workflow that looks elegant on a whiteboard costs $5–8 per complex task in inference spend.

## Evidence

- **Engineering blog:** Multi-agent architecture adoption surged 1,445% from Q1 2024 to Q2 2025 — yet the #1 failure point is not the agents, it's the contracts between them. — [Raft Labs](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Framework comparison:** LangGraph (graph nodes), CrewAI (role-based teams), and Microsoft Agent Framework 1.0 (conversational chains) each represent different coordination philosophies. The choice matters less than the schema discipline you apply at every boundary. — [TURION.AI](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)
- **Coordination taxonomy:** Supervisor pattern is easiest to debug because the supervisor's trace shows the full decision path. Peer/handoff is cleanest for stage-based work but requires explicit context injection at every transition. — [Gravity](https://gravity.fast/blog/ai-agent-multi-agent-coordination)
- **Production costs:** 4-agent orchestrator-worker workflows cost $5–8 per complex task in inference. Enterprise monthly AI op costs averaged $85,521 in 2025, with 60–85% recoverable through caching, routing, and budget enforcement — but teams discover this after runaway loops costing $15 in 10 minutes to $47,000 over 11 days. — [Zylos Research](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)

## Gotchas

- **Silent context loss is worse than loud crashes.** A failed tool call returns an error. A handoff that drops an escalation flag returns a plausible-looking wrong answer. Always validate handoff payloads explicitly — never trust implicit context transfer.
- **Schema versioning at handoffs is non-optional.** When you update an agent's output schema, every downstream consumer breaks silently unless you version and validate. Treat it like an API contract.
- **Retry without backoff is a cost attack on yourself.** A looping agent with no exponential backoff can exhaust your monthly budget in minutes. Every agent needs a hard retry cap.
- **Eval coverage must match observability coverage.** You are not watching your system if you are watching its traces but not checking whether its outputs are correct. Traces show you what happened; evals show you if it was right.
