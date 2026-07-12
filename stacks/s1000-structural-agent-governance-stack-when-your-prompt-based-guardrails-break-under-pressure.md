# S-1000 · The Structural Agent Governance Stack — When Your Prompt-Based Guardrails Break Under Pressure

Your agent behaves perfectly in staging. In production it hallucinates a tool call, exfiltrates data through an MCP server you trusted, and violates your business policy — because all three protections lived in the system prompt. As context shifts, prompts drift, and policies evolve, instruction-based governance silently degrades. You need enforcement that doesn't live or die with the model's attention.

## Forces

- **Prompt brittleness is structural, not a tuning problem.** Prompt-based guardrails couple governance logic to instruction structure. When context grows, policies evolve, or the model switches providers, the same constraint statement produces different behavior. You cannot engineer brittleness away — only move the enforcement layer.
- **Governance duplication across multi-agent deployments multiplies risk.** A policy written into every agent prompt is a policy that silently diverges across every agent prompt. One update, seventeen agents, zero coordination. The enforcement point needs to be shared and consistent.
- **Model reasoning cannot audit model reasoning.** Putting "block if intent is harmful" in the prompt means the model decides whether to block itself. CUGA benchmarks show 40% policy bypass rates when intent detection is delegated to the governed model versus structural enforcement. Auditability requires a separation of concerns.
- **Runtime conditions break static policy.** A "no financial transactions" rule in the system prompt doesn't know about the agent's current budget, the user's elevated session state, or the MCP server's altered schema. Governance needs runtime context that lives outside the context window.

## The move

Implement **policy-by-construction**: explicit, typed, runtime-enforced control primitives that operate independently of the model's instruction following. The CUGA architecture (Shlomov et al., arXiv:2605.20874, ACM CAIS '26) defines five structurally-separated checkpoints:

### Five Structural Checkpoints

1. **Intent Guard** (upstream of planning)
   - Block harmful or out-of-scope requests before the agent processes them
   - Runs a lightweight classifier on the user request, not on the agent's interpretation
   - Separately maintained intent taxonomy — does not live in the agent's system prompt

2. **Plan Verification** (after planning, before execution)
   - A static analysis layer that maps the planned action sequence against the policy schema
   - Identifies prohibited tool combinations, policy violations, and escalation requirements
   - Checksums the plan against the governance code version — enables non-regression

3. **Resource Guard** (runtime, per action)
   - Budget gates: monetary, token, API call, and time limits enforced at the infrastructure layer
   - Separate from the agent's self-reported resource awareness
   - Triggers circuit-breaker if agent attempts to exceed declared limits

4. **Execution Sandbox** (at the tool call boundary)
   - The tool invocation runs in an isolated context — MCP server credentials scoped per call, not per session
   - Output classification before it enters the agent's context window
   - Prevents prompt injection in tool responses from reaching the model unchecked

5. **Output Guard** (after execution, before response)
   - Structural check on the agent's final output against policy constraints
   - PII redaction, compliance flagging, hallucination surface detection
   - Deterministic — same output always produces the same governance decision

### Key Design Principle: The Governance-to-Agent Wire

The critical separation is the **governance-to-agent wire** — a typed interface between the policy enforcement layer and the agent execution layer:

```
Policy Layer (trusted)     →     Agent Layer (untrusted for enforcement)
─────────────────────────────────────────────────────────────────────────
Intent taxonomy            →     Agent request
Policy schema (versioned)  →     Plan verification
Resource budget (opaque)   →     Execution budget
Capability grants         →     Tool access grants
```

The agent never sees the governance code. The governance layer never reads the agent's context. This is the structural separation that makes enforcement non-brittle.

### Policy-as-Code Example

```python
# Policy schema (version-controlled, reviewed like code)
from cuga_policy import Policy, Checkpoint

policy = Policy(
    version="2026.07.12",
    intent_taxonomy=IntentTaxonomy.from_file("intent taxonomy.yaml"),
    resource_limits=ResourceLimits(
        monetary_per_task=10.00,
        token_budget=128_000,
        api_calls_max=50,
        time_limit_seconds=300,
    ),
    capability_grants=CapabilityGrants(
        allowed_tools=["search", "read_file", "write_file"],
        denied_tools=["delete_db", "send_email"],
        escalation_required=["payment", "user_data_export"],
    ),
)

# Checkpoints fire at their designated phase
@policy.check(Checkpoint.INTENT)
def block_malicious_intent(agent, request):
    intent = classify_intent(request, policy.intent_taxonomy)
    if intent.prohibited:
        return EscalationResult(block=True, reason=intent.flag)

@policy.check(Checkpoint.PLAN)
def verify_plan_compliance(agent, plan):
    violations = policy.schema.check(plan)
    if violations:
        return EscalationResult(escalate=True, violations=violations)

@policy.check(Checkpoint.RESOURCE)
def enforce_resource_budget(agent, action):
    if agent.budget_spent + action.estimated_cost > agent.budget_limit:
        return EscalationResult(block=True, reason="budget_exceeded")
```

### Implementation Patterns

| Concern | Prompt-Based (brittle) | Structural (resilient) |
|---------|------------------------|------------------------|
| Financial limit | "Do not spend more than $10" in system prompt | Infrastructure-layer budget gate; agent never sees limit |
| Prohibited tools | "Never call delete_db" in system prompt | Capability grant list checked at execution sandbox |
| Intent detection | Agent classifies own intent | Separately-operated classifier; agent cannot override |
| Policy update | Re-prompt all agents | Update policy version; enforcement layer auto-updates |
| Audit trail | "Check what the model said it was doing" | Checksummed plan + structural log; model cannot falsify |

## Receipt

> Verified 2026-07-12 — ArXiv:2605.20874 (CUGA, ACM CAIS '26) structural checkpoint architecture; MCP Best Practices guide (mcp-best-practice.github.io, verified July 2026) capability scoping; arxiv:2601.10338 empirical skill vulnerability data (26.1% of community skills contain vulnerabilities — supports structural enforcement over prompt-based trust). 40% policy bypass rate in prompt-delegated vs. structurally-enforced benchmarks cited from CUGA paper.

## See also

- [S-095 · Guard Agent Pattern](s095-guard-agent-pattern.md) — action-intercept and propose-dispose; does not cover structural policy separation
- [S-349 · Constitutional Guardrails](s349-constitutional-guardrails.md) — rule layers; enforcement is still prompt-mediated
- [S-695 · MCP Security Model](s695-mcp-is-winning-but-the-security-model-is-not-ready.md) — ambient authority in MCP; complementary to structural governance
- [S-902 · Scaffold Supply Chain Stack](s902-the-scaffold-supply-chain-stack-when-your-agent-builds-a-backdoor-into-your-own-infra.md) — supply chain poisoning; execution sandbox (Checkpoint 4) is the structural mitigation
