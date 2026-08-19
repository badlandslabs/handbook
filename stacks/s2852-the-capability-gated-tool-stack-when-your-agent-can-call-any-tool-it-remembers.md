# S-2852 · The Capability-Gated Tool Stack — When Your Agent Can Call Any Tool It Remembers

Your MCP ecosystem has 47 registered tools. Your agent only needs 6. The rest are a threat surface — because your agent's tool selection isn't gated by a manifest, it's gated by context. When it needs a capability it doesn't have, it pattern-matches from training data and calls `export_user_data_v3`, a function that has never existed. Or it calls `delete_records` because it read similar patterns in the codebase it was trained on. The fix isn't a better model. It's a capability gate.

The **Capability-Gated Tool Stack**: bind every agent to a pre-registered, versioned tool manifest that defines the exact set of tools it may invoke. Every tool call is intercepted and verified against the manifest before execution. No manifest entry, no call.

## Forces

- **LLMs are trained on API documentation, not your deployment state** — they know what tools *could* exist, not which ones *do* exist in your current registry. This creates phantom tool calls (S-1913) and overprivileged attempts.
- **MCP and A2A expose full tool surfaces by default** — framework defaults and tutorial examples show "here's all available tools." Production requires the inverse: here are only the tools this agent may use.
- **Permission creep is the default** — agents granted broad tool access to unblock a pilot keep that access as workflows stabilize, creating compound overprivilege across systems.
- **Tool binding and tool execution are different security concerns** — the policy kernel (S-1458) enforces *what happens* when a permitted tool is called; the capability gate enforces *which tools* may be called at all.
- **NHI and tool binding are orthogonal** — an agent may have a perfect identity credential (S-2847) but still attempt invocations outside its authorized scope. Capability gates close that gap.

## The move

**1. Define a Tool Manifest per Agent Role**

Every agent role gets a versioned manifest listing exactly the tools it may call:

```yaml
# manifest:customer-triage-agent/v2
version: "2.1"
agent_role: customer_triage
tools:
  - name: lookup_order
    scope: read          # least-privilege: read-only
    params:
      allowed_fields: [order_id, status, created_at]
      max_results: 10
  - name: create_support_ticket
    scope: write
    params:
      allowed_priorities: [low, medium]
      max_per_hour: 20
  - name: get_customer_profile
    scope: read
    params:
      allowed_fields: [email, tier, account_age]
# No delete_record. No export_user_data. Not in the manifest = not callable.
```

**2. Intercept Tool Calls Against the Manifest**

Every agent invocation path routes through a capability gate:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ToolManifest:
    role: str
    version: str
    allowed_tools: dict[str, ToolPolicy]

class CapabilityGate:
    """Intercepts every tool call and verifies against the manifest."""

    def __init__(self, manifest: ToolManifest):
        self.manifest = manifest

    def resolve_tool(self, requested_tool: str, params: dict) -> tuple[bool, str]:
        """Returns (allowed, reason). 'reason' explains the gate decision."""
        if requested_tool not in self.manifest.allowed_tools:
            return False, (
                f"Tool '{requested_tool}' not in manifest "
                f"'{self.manifest.role}@{self.manifest.version}'. "
                f"Agent must refuse: 'I don't have access to that tool.'"
            )

        policy = self.manifest.allowed_tools[requested_tool]

        # Scope enforcement
        if policy.scope == "read" and self._is_write_operation(params):
            return False, f"Tool '{requested_tool}' is read-only per manifest."

        # Parameter field restriction
        if policy.params:
            disallowed = set(params.keys()) - set(policy.params.get("allowed_fields", params.keys()))
            if disallowed:
                return False, (
                    f"Tool '{requested_tool}' params {disallowed} not in manifest. "
                    f"Allowed: {policy.params.get('allowed_fields')}"
                )

        # Rate limit enforcement
        if policy.params and "max_per_hour" in policy.params:
            if not self._check_rate_limit(requested_tool, policy.params["max_per_hour"]):
                return False, f"Tool '{requested_tool}' rate limit exceeded."

        return True, "allowed"

    def _is_write_operation(self, params: dict) -> bool:
        # Heuristic: params containing destructive keys are write operations
        return any(k in params for k in ("delete", "remove", "drop", "update", "create"))

# Usage in the agent loop
gate = CapabilityGate(manifest)
allowed, reason = gate.resolve_tool(tool_name, tool_params)
if not allowed:
    # Return structured refusal to the agent
    return {"status": "gate_denied", "reason": reason}
```

**3. Bind Tool Manifest to Non-Human Identity**

The manifest should be co-bound with the agent's NHI credential (S-2847):

```python
# When provisioning an agent session, bind identity + manifest together
async def provision_agent_session(agent_id: str, role: str) -> AgentSession:
    identity = await nhi_registry.issue_credential(agent_id)
    manifest = await manifest_registry.get_for_role(role)
    return AgentSession(
        credential=identity,          # proves WHO this agent is
        tool_manifest=manifest,       # defines WHAT this agent may do
        session_id=uuid4(),
        expires_at=datetime.utcnow() + timedelta(hours=8),
    )
```

**4. Version and Audit the Manifest**

- Every manifest change is a code review event — tools added/removed require the same review as IAM permission changes
- Manifest revisions are immutable — never modify in production, only add new versions
- Log every gate denial: `DENIED tool=export_user_data agent_role=customer_triage session=abc reason=not_in_manifest`

**5. Tool Manifest as Supply Chain Defense**

Before adding a new MCP server or tool to any manifest:
1. Is this tool required for this agent's role? If "nice to have," it doesn't go in.
2. What is the worst action this tool enables? (export, delete, write, admin)
3. Is there a read-only variant? Prefer `lookup_*` over `get_*` where possible.
4. What data does this tool expose, and is it within the agent's data classification scope?

## Receipt

> Verified 2026-08-19 — Research sources: Microsoft Security Blog "Least privilege for AI agents: Identity, access, and tool binding" (July 16, 2026, Yser & Kohlenberg, Microsoft Entra Agent ID with tool binding); OWASP Agentic AI Security ASI Top 10 (June 2026, over-privileged agent access); Microsoft Learn "Least privilege for AI agents with Microsoft Entra Agent ID" (2026); CSA/Strata Identity survey (285 IT/security professionals, March 2026); Fine-grained authorization (FGA) patterns for agents (Okta, 2026). Key stats: 88% of enterprises have no formal agent tool access policies; 74.6% of agent social engineering bypasses succeed with model-only defense vs 0% with OAP policy; agents inherit user privileges dangerously. Decision tree validated: gate → manifest → scope → params → rate limit → log.

## See also

- [S-1458 · The Policy Kernel Stack](s1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — deterministic enforcement at the MCP/A2A gateway; this entry covers the *capability* layer upstream
- [S-1913 · The Phantom Invocation Stack](s1913-the-phantom-invocation-stack-when-your-agent-calls-a-tool-that-doesnt-exist.md) — when the agent calls a tool that doesn't exist; capability gates prevent the call from being generated
- [S-2847 · The Non-Human Identity Void Stack](S-2847-the-non-human-identity-void-stack-when-your-agent-has-no-birth-certificate-no-passport-and-full-admin-access.md) — agent identity; tool binding is the capability layer orthogonal to identity
- [S-2805 · The MCP Schema Contract Stack](s2805-the-mcp-schema-contract-stack-when-your-mcp-server-update-quietly-breaks-your-production-agents.md) — MCP schema drift; capability gates should verify schema version alignment
