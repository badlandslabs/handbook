# S-1845 · The ACS Intervention-Point Stack — When Runtime Governance Lives in the Prompt

Your agent silently deleted 50,000 rows from the database. Not because of an injection — because it decided the operation was "reasonable" given the context. Your governance policy was in the system prompt. Prompts drift. Context shifts. Policies degrade. The enforcement you thought was there was advisory.

This is the failure mode that prompt-based guardrails cannot address: the agent doing exactly what the LLM can tokenize, with full authorization, no anomaly to flag, no circuit breaker to trip. The agent is compliant with its instructions and catastrophic to your infrastructure. You need enforcement that does not live inside the thing it enforces.

## Forces

- **Prompts are advisory, not authoritative.** A policy statement in a system prompt is a suggestion to the model — not a constraint the infrastructure enforces. Under token pressure, adversarial context, or model drift, the same instruction produces different behavior. Studies show prompt-delegated policy enforcement has a ~40% bypass rate compared to structurally enforced controls. — *ArXiv:2605.20874 (CUGA, ACM CAIS '26)*
- **The intervention gap is structural.** Agent frameworks execute a loop: input → model → tool call → tool result → output. Every agentic framework implements this loop. None of them standardly expose a governance interface at each point. You get the loop; you don't get the hooks to make the loop safe.
- **Governance must be outside the agent's trust boundary.** A guardrail implemented inside the agent can be bypassed by the agent. A kill switch the agent can modify is not a kill switch. Effective governance requires a policy enforcement point that the agent cannot influence — including by generating the input it is being judged against.
- **Real-time inference leaves no latency budget for heavyweight evaluation.** Runtime governance that adds seconds to every tool call is not deployable. The enforcement must be fast, stateless, and deterministic — the same snapshot always produces the same verdict, with sub-millisecond latency.

## The move

**ACS (Agent Control Specification)** — an open, stateless, deterministic, fail-closed policy decision runtime from Microsoft's Agent Governance Toolkit (AGT 5.0, public preview as of mid-2026) — addresses this by defining eight intervention points across the agent loop and a standard interface for enforcing policy at each one.

### The eight intervention points

```
Input → pre_model_call → post_model_call → pre_tool_call → [Tool Execute] → post_tool_call → pre_output → post_output
         ↑                                                           ↑
      agent_startup                                           agent_shutdown
```

| Point | What is evaluated | Typical policy |
|---|---|---|
| `agent_startup` | Agent identity, capability manifest, policy compliance of tool registry | Allow/deny based on agent version, required capabilities, policy manifest presence |
| `input` | User/system input assembled into context | Sensitivity classification, PII detection, policy-triggering content |
| `pre_model_call` | Prompt being sent to the LLM | Prompt injection markers, policy-forbidden content, token budget gate |
| `post_model_call` | Model response before tool parsing | Confidence floors, forbidden content generation, policy violation in output |
| `pre_tool_call` | Tool name + arguments being executed | Capability clearance, parameter bounds, NHI authorization scope |
| `post_tool_call` | Tool return value | Sensitivity escalation, data exfiltration patterns, error masking |
| `pre_output` | Final response before delivery | PII leakage, unauthorized disclosure, policy violation in delivery |
| `agent_shutdown` | Session closure | Audit log completeness, pending action reconciliation |

### Core properties

- **Stateless**: The runtime retains no mutable state. The host (agent framework) supplies a complete snapshot at every intervention point. Nothing is carried forward internally between evaluations.
- **Deterministic**: Same policy manifest + snapshot + intervention point → identical verdict every time. Reproducible enforcement is a prerequisite for auditability.
- **Fail-closed**: Runtime errors return `deny` with a reserved reason code. There is no silent pass on failure — the default outcome is no action.
- **Vendor-neutral**: Pure Rust core with bindings for Python, Node.js, .NET, and Rust. Runs embedded in the agent process or as a sidecar. No dependency on a specific framework or cloud.

### The canonical policy input

At each intervention point, the host (agent framework adapter) assembles a snapshot and submits it to the ACS runtime alongside a policy manifest. The runtime returns a normalized verdict.

```
{
  "intervention_point": "pre_tool_call",
  "policy_target": { "kind": "tool_args", "path": "table_name", "value": "users" },
  "snapshot": {
    "session_id": "...",
    "agent_id": "...",
    "tool_name": "sql_execute",
    "prior_tool_calls": [...],
    "accumulated_sensitivity": ["pii", "financial"],
    "user_clearance": "read_only",
    "approval_state": "pending"
  },
  "annotations": { /* LLM-judge results, classifier outputs */ },
  "tool": {
    "name": "sql_execute",
    "clearance": ["write", "admin"],
    "security_labels": ["database", "pii_handling"]
  }
}
```

The policy manifest declares what verdicts are required at each intervention point. The runtime evaluates the snapshot against the manifest and returns `{ "verdict": "allow" | "transform" | "deny", "reason": "...", "transformations": [...] }`.

### The three verdict types

- **`allow`**: Proceed. The action is within policy scope for this session's clearance level.
- **`transform`**: Modify the action. Common for parameter bounds — `sql_execute("DROP TABLE users")` becomes `deny`; `sql_execute("SELECT * FROM users LIMIT 100")` with an `ORDER BY` injection in the WHERE clause gets the injection stripped. Transformations preserve the agent's intent while enforcing the constraint.
- **`deny`**: Stop. Log the denial with the full snapshot context. The agent receives a structured error, not a silent drop.

### Contrast with prior approaches

| Approach | Strength | Gap ACS fills |
|---|---|---|
| System-prompt governance | Zero infrastructure | Degrades under context pressure; agent can override itself |
| LLM-as-judge monitoring | Flexible, semantic | Non-deterministic; adds latency; circular dependency |
| Hard enforcement plane (S-340) | Fast, deterministic | Enforces only pre-defined rules; no semantic awareness |
| Policy-Kernel (S-1458) | Ecosystem-level MCP control | Deny-by-default at capability level; no per-step semantic evaluation |
| **ACS** | **Stateless, deterministic, 8-point, semantic** | **Bridge between hard enforcement and flexible governance** |

### Implementation pattern

```
Agent Framework (LangGraph, AutoGen, etc.)
    ↓  [Adapter: serialize snapshot per intervention point]
ACS Runtime (Rust, embedded or sidecar)
    ↓  [Evaluate against policy manifest]
Verdict → { allow | transform | deny }
    ↓  [Adapter: enforce verdict]
Agent Framework continues or halts
```

The adapter is the only framework-specific code. Once written, the policy manifest drives all governance — change the manifest, change the behavior, without touching the adapter or the agent code.

### When to reach for this

- **Multi-agent systems with cross-boundary authorization** — each agent presents its clearance level; downstream tool calls are evaluated against the originating user's authorization scope (cf. S-1843 Authorization Propagation)
- **Financial or data-sensitive operations** — where `allow` on a tool call requires proof of authorization, not just capability presence
- **Compliance environments** — where every tool invocation must be attributable, auditable, and replayable from the snapshot log
- **High-stakes MCP ecosystems** — MCPKernel v0.3.0 (Jul 2026) has 344+ published security advisories; structural enforcement is the only scalable response

## See also
- [S-340 · Agent Hard Enforcement Plane](s340-agent-hard-enforcement-plane.md) — hard cost caps, loop bounds, escalation gates; the non-semantic enforcement layer ACS sits above
- [S-1458 · The Policy-Kernel Agent Stack](S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — MCP ecosystem-level deny-by-default; ACS enforces at the semantic level within that boundary
- [S-1843 · Authorization Propagation](s1843-the-authorization-propagation-stack-when-your-agent-delegates-across-a-boundary-and-authorization-invariants-break-silently.md) — NHI authorization across agent boundaries; ACS evaluates authorization scope at each `pre_tool_call`
