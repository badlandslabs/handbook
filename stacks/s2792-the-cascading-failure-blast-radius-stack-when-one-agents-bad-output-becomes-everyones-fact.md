# S-2792 · The Cascading Failure Blast Radius Stack — When One Agent's Bad Output Becomes Everyone's Fact

A single agent hallucinated a price. Three downstream agents treated it as ground truth. By the time anyone noticed, the system had quoted 47 enterprise clients a fictional number and begun routing procurement workflows around it. The cascade didn't start with a crash — it started with a confident lie that propagated faster than any human could catch it. The blast radius wasn't a bug in one agent; it was a structural property of how the agents were wired together.

## Forces

- **Errors persist in shared memory**, contaminating every subsequent agent that reads from it. Unlike a stateless HTTP request that fails and completes, a bad output lingers in vector stores, episodic buffers, and inter-agent message queues.
- **Agents operate at machine speed**, exceeding the human detection window (4–8 hours without structured observability). A feedback loop that compounds 10 times per second reaches catastrophic scale before any alert fires.
- **Natural language inter-agent communication lacks typed error contracts**. There's no `HTTP 500` between agents — only confident outputs that downstream agents treat as authoritative.
- **Agents change each other's context**, creating positive feedback loops where a cascade can amplify rather than dampen.
- **Retry loops, retry storms, and handoff gaps are partial mitigations at best** — they fix local faults but can widen the blast radius if the corrupted state is retried without isolation.

## The move

Contain blast radius across three axes. Measure it as:

```
Blast Radius = Access Scope × Operating Velocity × Detection Window
```

### Contain the scope

```python
# Least-privilege tool scoping per agent role
AGENT_TOOLS = {
    "research_agent":  ["web_search", "read_file"],
    "price_agent":     ["db_query",   "calculate"],
    "dispatch_agent":  ["send_email", "create_ticket"],
    # No agent gets all tools — a compromised agent can only propagate within its scope
}

def invoke_tool(agent_role: str, tool: str, params: dict) -> dict:
    allowed = AGENT_TOOLS.get(agent_role, [])
    if tool not in allowed:
        raise PermissionError(f"{agent_role} cannot invoke {tool}")
    # Every invocation is scoped — a hallucination cannot trigger out-of-scope tools
    return _dispatch(tool, params)
```

### Cap the velocity

```python
# Workflow depth cap + rate limiter on autonomous actions
MAX_WORKFLOW_DEPTH = 5      # cascade cannot grow beyond 5 hops
MAX_ACTIONS_PER_MINUTE = 20 # operating velocity cap per agent
ACTION_COUNTER = Counter()   # sliding window, reset every 60s

def check_velocity(agent_id: str) -> None:
    if ACTION_COUNTER[agent_id] >= MAX_ACTIONS_PER_MINUTE:
        raise VelocityExceeded(f"{agent_id} rate-limited at depth boundary")
    ACTION_COUNTER[agent_id] += 1
```

### Shrink the detection window

```python
# Structured orchestration-layer observability
# Every inter-agent handoff emits a trace span to Grafana Tempo / OTel
@dataclass
class HandoffSpan:
    source_agent: str
    target_agent: str
    output_hash: str          # detect when same output propagates
    belief_entropy: float      # measure confidence variance post-handoff
    propagation_depth: int    # increment on each hop

# Cascade circuit breaker: fire when belief_entropy spikes across handoff
def cascade_circuit_breaker(span: HandoffSpan) -> bool:
    if span.belief_entropy > ENTROPY_THRESHOLD:
        # Output looks confident but propagated entropy is high → trigger halt
        halt_workflow(span.source_agent, reason="cascade_entropy_threshold")
        alert_security_team(span)
        return True
    return False
```

### Separate planning from execution

```python
# Planner proposes → Executor acts. A corrupt plan cannot auto-execute.
class PlanAgent:
    def propose(self, task: str) -> Plan:
        return Plan(steps=[...], risk_score=self._assess_risk())

class ExecutorAgent:
    def execute(self, plan: Plan) -> Result:
        if plan.risk_score > APPROVAL_THRESHOLD:
            # High-risk plan gates on human or governance-agent approval
            await human_approval(plan)
        return self._execute_steps(plan.steps)
```

### Replay-gate before propagation

```python
# Before a high-stakes output propagates downstream,
# re-run the action sequence in an isolated clone and verify blast-radius caps
def replay_gate(agent_sequence: list[str], action: Action) -> bool:
    blast_radius = simulate_blast_radius(agent_sequence, action, sandbox=True)
    if blast_radius.confidence_variance > 0.3:
        return False  # gate: reject propagation of high-uncertainty outputs
    if blast_radius.depth > MAX_WORKFLOW_DEPTH:
        return False  # gate: reject depth overflow
    return True
```

## Receipt

> Verified 2026-08-17 — OWASP ASI08 (Cascading Failures) is the newest OWASP category for agentic AI, released December 2025. BeyondScale reports median detection window of 4–8 hours without structured observability. The blast radius formula (`Access Scope × Operating Velocity × Detection Window`) provides the first quantitative containment target for this class of failure. The planning/execution separation pattern is implemented in LangGraph's `checkpointer` + human-in-the-loop gating, and in CrewAI v0.5's redesigned task handoff tracing. Replay-gate testing is described in Microsoft's `hve-core` reference for OWASP agentic security.

## See also

- [S-2790 · The Context Drift Stack](s2790-the-context-drift-stack-when-your-multi-agent-system-hallucinates-but-no-model-is-broken.md) — memory contamination is the persistence layer of the cascade
- [S-2788 · The Silent Handoff Stack](s2788-the-silent-handoff-stack-when-your-a2a-protocol-succeeds-but-nothing-happens.md) — handoffs without contracts are the propagation medium
- [S-1603 · The A2A Task Lifecycle Stack](s1603-the-a2a-task-lifecycle-stack-when-your-agent-hands-off-work-and-loses-contact.md) — task state divergence across agents is a cascade vector
