# [S-2830] · The AILM Stack — When Your Agent Is Already the Bridge and Nobody Told Security

Your agent reads your email, queries your CRM, pushes to your GitHub, and accesses your cloud console. An attacker doesn't need to steal a credential. They need your agent to pivot for them — through the bridges it already holds.

## Forces

- **The bridge exists by design.** AI agents are built to connect multiple systems. That standing, legitimate access is what makes them useful — and what makes them a third axis of lateral movement. No new credential required. No network path to discover. The agent *is* the pivot.
- **Security teams can't see the agent as a network segment.** East-west traffic monitoring, microsegmentation, zero-trust identity controls — all built for credential-based or path-based movement. AILM traverses none of those. The agent's authorized tool calls look like legitimate behavior to every monitoring system that exists.
- **The attack surface isn't a vulnerability — it's the delegation.** Unlike a compromised server or a stolen credential, you can't revoke AILM by rotating a key. The agent holds *legitimate* access. The abuse is in the *direction*, not the *privilege*.
- **Tool-chain composition amplifies the bridge.** An MCP tool readEmail() chained with sendSlackMessage() through an agent gives an attacker a two-system pivot without touching a single credential. Each narrow tool, individually benign, becomes a multi-system bridge when routed through an agent's reasoning.

## The move

**1. Map your agent's blast bridges — not just blast radius.**

Before AILM, "blast radius" meant scope of damage if compromised. For AILM, the question is: which authorized tool combinations form bridges *between* security boundaries? An agent that can read a document store and send an email has a bridge between data and communication. One that can query a database and push to a repo has a bridge between state and code. Catalog the bridges, not just the tools.

```python
# Minimal bridge mapping: which tools span organizational boundaries?
AUTHORIZED_TOOLS = {
    "readEmail", "sendEmail",
    "querySalesforce", "updateSalesforce",
    "readGCS", "writeGCS",
    "gitPush", "gitClone",
    "queryDatabase", "executeScript",
}

# A bridge = two tools across different trust domains in one agent session
# (email + GCS = data exfiltration bridge)
# (database query + git push = state-to-code bridge)
```

**2. Enforce per-hop authorization — not per-session.**

Standard agent auth grants a session-level credential that persists across all tool calls. AILM exploits this: the session credential is trusted for every hop. The fix is step-level authorization: every tool call in a multi-step chain requires an explicit, auditable authorization decision anchored to the specific request context (user intent, task scope, tenant ID).

```python
# Per-call authorization gate — session cred alone is not sufficient
async def authorize_tool_call(
    agent_id: str,
    tool_name: str,
    request_context: RequestContext,  # user_id, task_id, tenant_id, scope
    prior_calls: list[ToolCall],
) -> AuthorizationResult:
    # Reject if this tool call traverses a new trust boundary not in the original intent
    intent_boundary = request_context.declared_boundaries
    tool_boundary = classify_boundary(tool_name)
    if not is_within_boundary(intent_boundary, tool_boundary):
        return AuthorizationResult(reject=True, reason="boundary_cross", audit=True)
    
    # Reject if tool call count exceeds task budget for this boundary
    boundary_calls = [c for c in prior_calls if classify_boundary(c.tool) == tool_boundary]
    if len(boundary_calls) > BOUNDARY_CALL_BUDGET[tool_boundary]:
        return AuthorizationResult(reject=True, reason="budget_exceeded", audit=True)
    
    return AuthorizationResult(reject=False)
```

**3. Instrument at the tool-call boundary — not the network boundary.**

Network-layer monitoring misses AILM entirely. Instrument at the tool invocation layer: log every tool call with its authorization context (who asked, what task, what declared scope, what was approved). This gives your SOC the audit trail that makes AILM visible.

```yaml
# OTel instrumentation at tool-call boundary
spans:
  - name: "tool.call"
    attributes:
      agent.id: "${AGENT_ID}"
      tool.name: "${TOOL_NAME}"
      auth.decision: "permitted" | "rejected"
      auth.context_boundaries: ["${BOUNDARY_1}", "${BOUNDARY_2}"]
      task.id: "${TASK_ID}"
      # A bridge-crossing call gets flagged for SIEM correlation
      bridge_crossing: true | false
```

**4. Treat MCP tool registration as a network ingress control.**

Adding an MCP server to your agent's toolset is equivalent to granting network access to a new service. Apply the same governance: security team review, least-privilege registration scope, audit logging of all added tool servers, and periodic capability review. The tool registry is your attack surface inventory.

**5. Add a "cross-boundary confirmation" step for high-sensitivity tool pairs.**

For tool combinations that form critical bridges (data export + communication, state mutation + external transmission), require an explicit confirmation step — not just a log entry. This mirrors how financial systems require dual authorization for high-value transfers. A human-in-the-loop or a signed API confirmation gate breaks the automated pivot chain.

## Receipt

> Verified 2026-08-18 — Research synthesized from: Orca Security (AILM Research Pod, Feb 2026), CSA AI Safety Initiative (CSA Research Note, March 2026), Microsoft Security Blog ("Securing AI Agents: When AI Tools Move from Reading to Acting," June 2026), Zero Networks (AILM threat analysis), GTFO.dev blog ("AI-Induced Lateral Movement: Agents Don't Need a Path or a Badge," July 2026), OWASP LLM Top 10. Core mechanism confirmed: AILM exploits the agent's *authorized* cross-system access as the pivot — structurally distinct from credential theft (which revokes) and network path exploitation (which blocks). The agent's delegated permissions ARE the bridge.

## See also

- [S-2760] · The MCP Server Hijack Stack — When Your Tool Server Becomes Your Attacker's Pivot Point (same attack surface family; S-2760 covers server compromise as the pivot; S-2830 covers agent-as-bridge pivot requiring no compromise)
- [S-2688] · The Agent Blast-Radius Stack — When the Agent Gets In and Everything Is on Fire (blast radius covers post-compromise containment; AILM doesn't require compromise — it uses authorized delegation)
- [S-1188] · The A2A Authorization Island — When Every Agent Is Its Own Security Perimeter (covers inter-agent auth boundaries; AILM crosses tool-domain boundaries within a single agent's session)
