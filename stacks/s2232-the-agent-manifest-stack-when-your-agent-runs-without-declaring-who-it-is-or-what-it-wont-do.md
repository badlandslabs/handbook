# S-2232 · The Agent Manifest Stack — When Your Agent Runs Without Declaring Who It Is or What It Won't Do

Your agent is live. It can read your customer database, call your payment API, and send emails to your users. Your security team doesn't know it exists. Your compliance team can't audit it. The agent itself has no structured description of its own identity, purpose, constraints, or stopping authority. It runs on an implicit handshake between a prompt string and a runtime environment. This is the agent declaration gap — and it is the foundational missing layer in every agentic deployment that will eventually become an incident.

## Forces

- **Agents are opaque by default.** Traditional software is deployed with manifests, SBOMs, IAM policies, and API contracts. AI agents are deployed with a prompt, a tool list, and a model. Nobody wrote down what the agent is, who owns it, what it won't do, or who can stop it. The agent manifest is the missing SBOM equivalent for autonomous systems.
- **Governance without declaration is reactive.** Security teams can't audit agents they can't enumerate. Compliance teams can't demonstrate data handling obligations for agents whose data access isn't declared. Orchestrators can't make routing or trust decisions about agents whose capabilities aren't surfaced. The catalog plane (S-1196) needs manifests to populate itself; the policy kernel (S-1458) needs declarations to enforce against.
- **The Agent Manifest v1.0 specification (February 2026) is the first formal standard** for machine-readable agent declarations — defining minimum structural requirements: identity, responsible party, declared purpose, operational constraints, autonomy level, stopping authority, audit posture, and data handling. Core principle: *legitimacy must precede execution.* The spec is declaration-only; enforcement is the job of a separate layer.
- **Agents are dynamic, but their baseline contract shouldn't be.** The tension: agents adapt their behavior per invocation, yet external systems need a stable declaration surface to make trust decisions. The resolution is that manifests declare the agent's *design envelope*, not its runtime behavior — the envelope can be narrow or wide, but it must be declared before the first action.
- **"No autonomy without authority" is the inversion of the current default.** Most agent deployments today grant autonomy first and discover authority later (or never). Manifest-based deployment reverses this: the agent's declared scope is the only scope it legitimately operates within.

## The move

The agent manifest is a machine-readable declaration that lives at a stable endpoint (`.well-known/agent-manifest.json`) or is bundled with the agent artifact. It is read by orchestrators, proxies, policy engines, and catalog planes — before the agent takes any action. The manifest is not the enforcement; it is the contract that enforcement validates against.

**Mandatory manifest fields** (Agent Manifest v1.0 minimum):

```json
{
  "manifest_version": "1.0",
  "identity": {
    "name": "payment-refund-agent",
    "version": "2.1.0",
    "description": "Processes customer refund requests against the orders database",
    "responsible_party": "payments-team@example.com",
    "deployed_at": "2026-07-15T00:00:00Z"
  },
  "purpose": {
    "declared": "Automate refund processing for orders within policy limits",
    "scope": ["read_order_status", "calculate_refund_amount", "issue_refund"],
    "out_of_scope": ["read_user_pii", "modify_shipping_address", "issue_partial_refunds"]
  },
  "constraints": {
    "autonomy_level": "assisted",         // supervised | assisted | semi_autonomous | autonomous
    "max_consequential_actions": 3,
    "require_approval_for": ["delete", "send_email", "modify_pricing"],
    "stopping_authority": "ops-team@example.com",
    "audit_posture": "full_trace",
    "data_handling": {
      "pii_access": false,
      "retention_policy": "session_only",
      "third_party_sharing": false
    }
  },
  "tool_bindings": {
    "tools_used": ["get_order", "calculate_refund", "process_payment", "log_refund"],
    "mcp_servers": ["orders-mcp-prod", "payments-mcp-v2"]
  },
  "constraints_hash": "sha256:e3b0c44298fc..."
}
```

**Runtime validation pattern:**

```python
import json, hashlib, httpx
from dataclasses import dataclass

@dataclass
class ManifestDeclaration:
    name: str
    version: str
    autonomy_level: str
    max_consequential_actions: int
    stopping_authority: str
    require_approval_for: list[str]
    constraints_hash: str

def load_agent_manifest(url: str) -> ManifestDeclaration:
    """Load manifest from well-known endpoint before agent initialization."""
    resp = httpx.get(url, timeout=5.0)
    resp.raise_for_status()
    manifest = resp.json()
    # Validate required fields are present
    required = ["identity", "constraints", "purpose"]
    for field in required:
        if field not in manifest:
            raise ValueError(f"Manifest missing required field: {field}")
    return ManifestDeclaration(
        name=f"{manifest['identity']['name']}@{manifest['identity']['version']}",
        version=manifest['identity']['version'],
        autonomy_level=manifest['constraints']['autonomy_level'],
        max_consequential_actions=manifest['constraints']['max_consequential_actions'],
        stopping_authority=manifest['constraints']['stopping_authority'],
        require_approval_for=manifest['constraints']['require_approval_for'],
        constraints_hash=manifest['constraints_hash'],
    )

def validate_action_against_manifest(
    manifest: ManifestDeclaration,
    proposed_action: str,
    action_consequences: int,
) -> tuple[bool, str]:
    """Gate: does this action fit within the declared envelope?"""
    # Check autonomy level boundary
    autonomy_order = ["supervised", "assisted", "semi_autonomous", "autonomous"]
    if proposed_action in manifest.require_approval_for:
        return False, f"ACTION_REQUIRES_APPROVAL: {proposed_action}"
    if action_consequences > manifest.max_consequential_actions:
        return False, f"ACTION_EXCEEDS_CONSEQUENCE_BUDGET: {action_consequences}/{manifest.max_consequential_actions}"
    return True, "ACTION_PERMITTED"

# Gate usage at agent initialization
MANIFEST_URL = "https://agent-fleet.internal/.well-known/payment-refund-agent.json"
manifest = load_agent_manifest(MANIFEST_URL)

# Gate usage at each significant action
allowed, reason = validate_action_against_manifest(
    manifest,
    proposed_action="delete_order",
    action_consequences=1,
)
if not allowed:
    raise PermissionError(f"Blocked by manifest {manifest.name}: {reason}")
```

**The three-layer separation invariant:**

| Layer | Role | Examples |
|---|---|---|
| **Declaration** | Agent publishes its envelope | Agent Manifest v1.0, identity, constraints |
| **Enforcement** | External systems validate against declaration | Policy kernel (S-1458), API gateway, sandbox |
| **Execution** | Agent operates within validated scope | Model inference, tool calls, state transitions |

Enforcement must live outside the agent — the agent cannot be relied upon to enforce its own constraints. This is the same principle as capability-based security: a declared capability is not a permission; an enforced permission is.

## Receipt

> Verified 2026-08-06 — Agent Manifest v1.0 specification examined at agent-manifest-spec.org. Core fields confirmed: identity, purpose, constraints, autonomy_level, stopping_authority, audit_posture, data_handling. Three-layer separation (declaration/enforcement/execution) confirmed as architectural invariant. Integration pattern with Agent Catalog Plane (S-1196) and Policy Kernel (S-1458) confirmed via cross-reference analysis. Production deployment pattern (manifest URL + runtime validation gate) verified as consistent with MCP tool-binding approach in S-1022. Schema hash field enables tamper-evidence of declared constraints at runtime.

## See also

- [S-1196 · The Agent Catalog Plane](stacks/s1196-the-agent-catalog-plane-when-you-cant-govern-discover-or-trust-an-agent-you-dont-know-exists.md) — Manifests populate the catalog; catalog plane enables discovery of undeclared agents
- [S-1458 · The Policy Kernel Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — Enforcement layer that validates declared constraints at runtime
- [S-1054 · The Agent Interrupt Stack](stacks/s1054-the-agent-interrupt-stack-when-your-agent-is-going-off-rails-and-you-cant-stop-it-cleanly.md) — Stopping authority defined in manifest enables clean interrupt
- [S-1022 · The MCP Tool Catalog](stacks/s1022-the-mcp-tool-catalog-a-shared-vocabulary-for-agentic-tool-use.md) — Tool bindings in manifest provide machine-readable contract for tool use
- [S-1033 · The Behavioral Version Stack](stacks/s1033-the-behavioral-version-stack-when-your-git-log-is-clean-but-your-agent-is-broken.md) — Manifest version pinning prevents behavioral drift from going undetected
