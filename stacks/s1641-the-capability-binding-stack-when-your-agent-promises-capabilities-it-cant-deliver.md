# S-1641 · The Capability Binding Stack — When Your Agent Promises Capabilities It Can't Deliver

An orchestration agent routes a task to a specialized sub-agent based on the sub-agent's self-description: "I can analyze financial documents and extract structured risk metrics." The orchestration agent binds to it and sends a 40-page loan application PDF. The sub-agent has a 200KB context window, no document chunking tool, and a tokenizer that silently drops content past the limit. It returns garbage. The orchestration agent doesn't know — it assumed the self-description was a binding, not a hope. This is the **capability binding problem**: agents assert capabilities they cannot verifiably deliver, and the system has no mechanism to catch the gap before it causes downstream failure.

The problem isn't dishonesty. The sub-agent's developer wrote an accurate description at deployment time. But the agent's actual effective capability at inference time depends on the current context window state, the tools currently registered, the model's current load, and the data currently in memory — all of which change between the description being written and the binding being executed. The gap between declared capability and runtime capability is where agentic workflows quietly fall apart.

## Forces

- Capability declarations are written statically at deployment but evaluated dynamically at runtime — the moment of evaluation never matches the moment of declaration
- Agents that self-describe honestly at deployment become dishonest at runtime through no fault of their own: context saturation, tool registry drift, model version changes, rate-limit throttling
- Pre-flight checks add latency but are required for safe binding; without them, failed bindings cascade through downstream agents and corrupt results silently
- The **capability binding gap** is distinct from the **protocol gap** (S-1040): A2A/MCP solve communication and discovery; binding solves pre-flight verification of what the other agent can actually do *right now*
- Binding without verification is the multi-agent equivalent of trusting user input — the same mistake at a different layer

## The move

The three-layer capability binding stack closes the gap between declaration and delivery.

### Layer 1 — Capability Self-Declaration with Runtime Scope

Agents publish a capability manifest that distinguishes between *declarable* and *observable* properties:

```
# AgentCard (capability manifest)
{
  "agent_id": "financial-risk-agent-v2",
  "version": "2.4.1",
  "declared_capabilities": {
    "document_analysis": {
      "max_document_size_kb": 2048,
      "supported_formats": ["pdf", "docx", "xlsx"],
      "structured_output_schema": "RiskMetricsV1"
    },
    "context_aware": true   # uses current memory
  },
  # These are set by the binding infrastructure, not the agent:
  "binding_observations": {
    "effective_context_window": null,    # measured at bind time
    "actual_tool_registry": null,       # verified at bind time
    "current_load_score": null          # measured at bind time
  }
}
```

The key discipline: **observable properties are not self-reported**. The binding infrastructure measures them at bind time.

### Layer 2 — Pre-Flight Binding Protocol

Before routing any task, the orchestrator runs a binding handshake:

```
def bind_capability(orchestrator, target_agent, task_requirements):
    # Step 1: Pull the target's AgentCard
    card = target_agent.get_agent_card()

    # Step 2: Negotiate a binding — agent must prove it can handle
    # the specific task, not just that it has the general capability
    binding_request = {
        "task_type": task_requirements.type,
        "input_constraints": task_requirements.constraints,
        "output_schema": task_requirements.output_schema,
        "binding_id": uuid4(),
        "max_latency_ms": task_requirements.deadline_ms
    }

    binding_response = target_agent.accept_binding(binding_request)

    # Step 3: Binding infrastructure measures actual capability
    # (this is the "binding observation" layer — not self-reported)
    observation = measure_agent_runtime_state(target_agent)

    # Step 4: Verify binding covers requirements
    if not verify_binding(binding_response, observation, task_requirements):
        raise BindingMismatchError(
            f"Agent {target_agent.id} cannot deliver required capability "
            f"at this runtime state. Declared: {card.declared_capabilities}, "
            f"Observed: {observation}"
        )

    return BindingTicket(
        binding_id=binding_request.binding_id,
        target=target_agent.id,
        scoped_capabilities=observation,
        expires_at=time() + 300  # binding expires, must re-verify
    )
```

The critical insight: the binding is scoped and time-limited. An agent bound for document analysis at 10:00 AM may not be bindable at 10:05 AM if context has saturated.

### Layer 3 — Cascading Fallback with Binding Transparency

When a binding fails, the system doesn't just route to the next agent — it propagates *why* the binding failed:

```
def route_with_binding_fallback(orchestrator, task, candidates):
    errors = []
    for agent in candidates:
        try:
            binding = bind_capability(orchestrator, agent, task.requirements)
            return execute_via_binding(task, binding)
        except BindingMismatchError as e:
            errors.append({"agent": agent.id, "reason": str(e)})
            continue

    # All bindings failed — surface the failure taxonomy, not just "no agent available"
    raise AllBindingsFailedError(
        task_type=task.type,
        failures=errors,
        suggestion=infer_task_restructure(task, errors)
    )
```

This transforms binding failures from silent degradation into structured governance signals. The orchestrator can distinguish "no agent has this capability" (system design problem) from "all candidates have the capability but are context-saturated right now" (capacity problem) from "the capability declaration doesn't match any agent's actual behavior" (measurement problem).

### The ACNBP Reference Architecture

ACNBP (Agent Capability Negotiation and Binding Protocol, arXiv:2506.13590, Huang et al., June 2025) provides the canonical reference for this stack. Its three-phase binding model maps directly:

| ACNBP Phase | This Stack's Layer | What Happens |
|---|---|---|
| **Discovery** | AgentCard publication | Agent exposes declared capabilities + version |
| **Negotiation** | Pre-flight binding handshake | Orchestrator proposes task constraints; agent accepts or negotiates |
| **Binding** | Runtime observation + verification | Infrastructure measures actual capability; binding ticket issued with scoped guarantees |

The protocol also introduces an Agent Name Service (ANS) — a DNS-equivalent for agents that maps capability queries to bound agents, rather than requiring orchestrators to know agent IDs upfront. Instead of `route_to("financial-risk-agent-v2")`, the orchestrator queries `find_agent(capability="document_analysis", max_document_kb>=2048)` and gets a bound agent as the result.

## Receipt

> Verified 2026-07-25 — arXiv:2506.13590 (Huang et al., June 2025) formally defines ACNBP with the Discovery/Negotiation/Binding three-phase model and ANS architecture. The binding observation layer (measuring runtime state rather than trusting declarations) is the key contribution over A2A/MCP which handle communication but not pre-flight verification. Pydantic's Agents Week (Bill Easton, July 13, 2026) articulates the "right agent vs right answer" problem from the orchestrator perspective, observing that routing decisions are made on declared capabilities that don't reflect runtime state. The capability binding stack is the engineering response to this observation: a structured pre-flight protocol that transforms capability declarations into binding guarantees. Receipt pending — live ACNBP implementation not available in this environment; the code above is pattern-level.

## See also

- [S-1040 · The Protocol Gap](s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — covers A2A and MCP for communication; this entry covers pre-flight capability verification before communication happens
- [S-1603 · The A2A Task Lifecycle Stack](s1603-the-a2a-task-lifecycle-stack-when-your-agent-hands-off-work-and-loses-contact.md) — covers task handoff reliability; binding failures upstream cascade into task lifecycle failures downstream
- [S-1613 · The Multi-Agent Handoff Eval Stack](s1613-the-multi-agent-handoff-eval-stack-when-every-agent-passes-its-test-but-your-system-fails.md) — covers evaluation of handoff quality; binding is the pre-flight condition that determines whether a handoff is even possible
