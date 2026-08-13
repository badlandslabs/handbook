# S-2581 · The Agent Session Smuggling Stack — When Your Orchestrator Trusts the Agent It Shouldn't

Your orchestrator agent delegates a document review to a specialist agent from another team. Over twelve turns, the specialist provides increasingly plausible summaries — and quietly inserts instructions into each response that the orchestrator acts on without noticing. The attack doesn't require compromising the orchestrator. It exploits the one thing the orchestrator must do: hold a stateful conversation. This is Agent Session Smuggling: injecting malicious instructions into multi-turn A2A conversations by exploiting the trust that stateful sessions encode.

## Forces

- **A2A is fundamentally stateful.** The A2A protocol (Linux Foundation, v1.0, April 2026) is designed for multi-turn task delegation — agents maintain session memory across requests. This statefulness is the feature that makes A2A useful. It is also the attack surface.
- **Multi-agent trust assumes the session is clean.** When Agent A hands a task to Agent B, A's session with B accumulates context across turns. A trusts that context because it includes B's own prior outputs — outputs that were presumably authorized by B's own policy. The smuggling attack poisons this assumption: B's outputs contain instructions that A misinterprets as task-relevant context rather than adversarial content.
- **Implicit trust compounds.** Unlike HTTP where each request is independent, A2A session memory means the attacker's influence grows with every turn. Early turns plant context; later turns exploit it. The orchestrator never re-challenges what it already accepted.
- **A2A session smuggling is protocol-native, not a CVE.** Unit 42 (Palo Alto Networks, Chen & Lu, October 2025) explicitly states the attack does not exploit a vulnerability in the A2A protocol itself — it exploits the implicit trust relationships that any stateful multi-turn delegation protocol encodes. No patch closes this. Architecture closes this.

## The move

**Session boundary isolation: seal the handoff, don't trust the return.**

### Layer 1 — Trust Boundary at Each Handoff

The orchestrator must treat every response from a delegated agent as untrusted input, not trusted context.

```
# Anti-pattern: accumulate session as ground truth
conversation.append(agent_b_response)  # B's outputs become A's context

# Pattern: validate and rephrase before trusting
validated = context_guardian.evaluate(agent_b_response)
sanitized = sanitization_layer.strip_instruction_patterns(validated)
conversation.append(sanitized)
```

A `ContextGuardian` evaluates each agent response for:
- **Instruction injection markers**: direct commands (`ignore`, `instead of`, `replace prior`), redirection instructions, scope-escalation phrases
- **Cross-session state references**: responses that reference prior turns in ways that expand their authority beyond the task
- **Temporal anomaly**: responses that reference capabilities or data the agent wasn't delegated access to

### Layer 2 — Capability-Sealed Session Contracts

At handoff time, the orchestrator emits a **session contract** — a structured definition of what the delegate agent is permitted to influence.

```json
{
  "task_id": "review-2026-Q3",
  "permitted_modifications": ["document.annotations", "document.summary"],
  "forbidden_modifications": ["session.state", "orchestrator.context", "external_services"],
  "session_seal": "sha256-hash-of-contract",
  "expires_at": "2026-08-13T18:00:00Z"
}
```

The delegate agent's outputs are only accepted if they operate within `permitted_modifications`. Any output that attempts to modify `forbidden_modifications` is rejected regardless of how it was phrased.

### Layer 3 — Session Sealing on Handoff Completion

When the orchestrator resumes control (task completed or returned), the accumulated session with the delegate agent is **terminated and sealed**. The delegate retains no ongoing session access.

```
# On task completion or error:
a2a_session.close(task_id=task_id)
# New task = new session ID, no inherited state
new_session = a2a_client.create_session(scope=limited_scope)
```

This breaks the attacker's ability to build on prior poisoned context across turns.

### Layer 4 — Audit Trail with Identity Binding

Every A2A response is logged with:
- Calling agent's workload identity (SPIFFE URI or equivalent)
- Session ID
- Time-bounded capability token
- Response intent classification (task output, error, clarification, instruction)

Post-hoc audit can detect the smuggling pattern: a delegate agent whose responses consistently contain instruction-classified content is flagged before its outputs propagate.

### Layer 5 — Orchestrator Policy: Act on Output, Not on Trust

The orchestrator acts on validated task outputs — never on agent-provided rationale for *why* the orchestrator should do something. Smuggled instructions survive because they arrive embedded in apparently-benign task context. The fix: separate the task output from the agent's meta-instructions.

```python
# Anti-pattern: agent tells you what to do with the result
response = agent_b.complete_review(doc)
orchestrator.execute(response.instructions)  # smuggled instruction lives here

# Pattern: execute on output, not on instruction
response = agent_b.complete_review(doc)
orchestrator.evaluate(
    output=response.document_summary,   # use this
    instructions=response.agent_notes,  # log but don't act on
)
```

## Receipt

> Verified 2026-08-13 — Unit 42 research (Chen & Lu, October 2025) documented the attack against A2A stateful session architecture. The attack exploits the A2A protocol's session-hold design — not a CVE. The BeyondScale A2A security guide (April 2026) and OWASP Top 10 for Agentic Applications (December 2025) both identify insecure inter-agent communication as a top-tier risk. No existing handbook entry covers A2A session smuggling specifically. S-990 (Agent Traps) covers single-turn web injection; S-1050 (Tool Response Poisoning) covers MCP server return poisoning; S-1134 (Invocation-Bound Capability Token) covers delegation chain authorization. This entry covers the stateful cross-agent session injection attack unique to the A2A protocol model.

## See also

- [S-990](./s990-the-agent-traps-stack-when-the-web-attacks-your-agent.md) — Web-based prompt injection; single-turn, not A2A stateful
- [S-1050](./s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — MCP server return poisoning; connect-time review misses runtime returns
- [S-1065](./s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — Inter-agent trust escalation; authorization bypass, not session poisoning
- [S-1134](./s1134-the-invocation-bound-capability-token-stack-when-your-agent-chains-delegations-and-nobody-can-prove-who-authorized-what.md) — Multi-hop delegation chains; authorization proof, not session state management
