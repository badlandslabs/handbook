# S-2622 · The MCP Security Gateway Stack — When Your Agent Trusts Every Tool That Returns OK

Your agent connects to 8 MCP servers — 3 third-party, 2 internal, 3 from your own infra. Nothing in the protocol layer validates that the server is who it claims to be, that the tool it's exposing is the one you approved, or that the responses haven't been tampered with in transit. The agent treats a `tool_result` from a typosquatted NPM package the same way it treats output from your internal database. This is not paranoia. Two-thirds of MCP servers scanned in early 2026 had critical security findings (Microsoft Security, June 2026). The MCP spec is intentionally security-neutral — it defines transport, not trust. The trust boundary is yours to build.

## Forces

- **MCP inverts the security model.** Before MCP, every tool your agent called was code you wrote, reviewed, or owned. Now your agent's reasoning is shaped by outputs from servers you didn't write, running on infrastructure you don't control. The model has no concept of which servers are trusted — it treats all tool results as ground truth.
- **The spec doesn't enforce security for you.** MCP's protocol deliberately omits authentication, authorization scoping, and response validation — by design, so the spec stays composable. Every team deploying MCP in production must independently discover that they own the security boundary, not the protocol.
- **Tool squatting and credential aggregation compound silently.** A malicious MCP server can expose tools with names matching your internal services (`list_users`, `send_email`). Your agent, seeing a valid-looking tool call, invokes it. The squatting server now holds your OAuth tokens, contact lists, and write permissions. This is not theoretical — it's in the 2026 MCP attack taxonomy (Microsoft Security Community, bountyyfi/mcp-watchdog).
- **Gateway inspection is blocked by end-to-end encryption and streaming.** You can't validate what you can't see. Many MCP transports use streaming responses with no checkpoint boundaries — a compromised server can exfiltrate data across a single long-running tool call and you'll only see the final `tool_result`.

## The move

Deploy an **MCP Security Gateway** as a mandatory intermediate layer between your agent runtime and every MCP server it connects to. The gateway is not optional infrastructure — it is the enforcement point where you convert "MCP said this is OK" into "we verified this is safe."

### Layer 1 — Gateway interception and request-level enforcement

Route all MCP traffic through a proxy that inspects every `tool_call` and `tool_result` before it reaches the agent.

```python
# Minimal MCP security gateway (request-level enforcement)
from mcp.types import CallToolResult, ToolCall
from mcp_server_security.policies import PolicyEngine

class MCPSecurityGateway:
    """Intercept, validate, and log every MCP tool call before it executes."""

    def __init__(self, policies: PolicyEngine):
        self.policies = policies

    async def on_tool_call(
        self,
        tool_call: ToolCall,
        session_id: str,
        agent_context: dict,
    ) -> CallToolResult | None:
        # 1. Scope enforcement: does this server have permission for this action?
        verdict = self.policies.evaluate(
            server_id=tool_call.server_id,
            tool_name=tool_call.name,
            params=tool_call.arguments,
            session_id=session_id,
            agent_scope=agent_context.get("scope"),
        )
        if not verdict.allowed:
            return CallToolResult(
                is_error=True,
                content=[{"type": "text", "text": f"[MCP Gateway] Blocked: {verdict.reason}"}],
            )

        # 2. Schema validation: do the params match what this tool should receive?
        schema_violations = self.policies.validate_params(
            tool_call.name, tool_call.arguments
        )
        if schema_violations:
            return CallToolResult(
                is_error=True,
                content=[{"type": "text", "text": f"[MCP Gateway] Param violation: {schema_violations}"}],
            )

        # 3. Credential scoping: inject least-privilege credentials
        scoped_token = self.policies.get_scoped_token(
            server_id=tool_call.server_id,
            tool_name=tool_call.name,
            original_context=agent_context,
        )
        if scoped_token and "authorization" not in tool_call.arguments:
            tool_call.arguments["_gateway_token"] = scoped_token

        # 4. Log for audit trail
        await self.policies.audit_log(
            event="tool_call",
            server_id=tool_call.server_id,
            tool_name=tool_call.name,
            session_id=session_id,
            verdict=verdict,
        )
        return None  # Pass through to server

    async def on_tool_result(
        self,
        result: CallToolResult,
        tool_call: ToolCall,
    ) -> CallToolResult:
        # 1. PII/sensitive-data scan on response
        if self.policies.contains_sensitive(result):
            await self.policies.flag_for_review(
                session_id=tool_call.session_id,
                server_id=tool_call.server_id,
                finding="sensitive_data_in_response",
            )

        # 2. Schema conformance check
        if not self.policies.conforms_to_schema(result, tool_call.name):
            await self.policies.flag_for_review(
                session_id=tool_call.session_id,
                server_id=tool_call.server_id,
                finding="response_schema_deviation",
            )

        # 3. Token usage attribution
        await self.policies.record_cost(
            server_id=tool_call.server_id,
            tool_name=tool_call.name,
            tokens=result.usage,
        )
        return result
```

### Layer 2 — Per-server capability scoping and trust tiers

Classify every connected MCP server into a trust tier. Apply policy boundaries per tier.

| Tier | Definition | Credential scope | Tool access | Example |
|------|-----------|-----------------|-------------|---------|
| **Internal** | Your infra, your code | Full internal credentials | All approved tools | `mcp-server-internal-db` |
| **Partner** | Third-party, SOC2, trusted vendor | Read-only / scoped OAuth | Subset of tools | `mcp-server-slack`, `mcp-server-github` |
| **External** | Public registry, unverified | No credentials, no write tools | Read-only + no-data tools | `mcp-server-web-search` |

```python
TIER_POLICIES = {
    "internal": {
        "max_credential_scope": "full",
        "allowed_write_tools": "*",  # All approved internal tools
        "max_token_exposure": 10_000,
        "require_audit": True,
    },
    "partner": {
        "max_credential_scope": "read_only",
        "allowed_write_tools": [],  # No writes
        "max_token_exposure": 2_000,
        "require_audit": True,
    },
    "external": {
        "max_credential_scope": "none",
        "allowed_write_tools": [],
        "max_token_exposure": 500,
        "require_audit": True,
    },
}
```

### Layer 3 — Tool squatting detection and name disambiguation

Before registering any MCP server, validate that its exposed tools don't collide with your internal service names or with each other.

```python
async def detect_tool_squatting(
    servers: list[MCPServerManifest],
    internal_service_names: set[str],
) -> list[SquattingAlert]:
    """Detect name collisions between MCP servers and internal services."""
    alerts = []
    all_tool_names: dict[str, str] = {}  # name -> server_id

    for server in servers:
        for tool in server.tools:
            # Check collision with internal services
            if tool.name in internal_service_names:
                alerts.append(SquattingAlert(
                    severity="critical",
                    tool_name=tool.name,
                    squatted_server=server.id,
                    reason=f"Tool name matches internal service: {tool.name}",
                ))
            # Check cross-server squatting
            if tool.name in all_tool_names:
                alerts.append(SquattingAlert(
                    severity="high",
                    tool_name=tool.name,
                    squatted_server=server.id,
                    legitimate_server=all_tool_names[tool.name],
                    reason=f"Tool '{tool.name}' exposed by multiple servers",
                ))
            all_tool_names[tool.name] = server.id

    return alerts
```

### Layer 4 — Supply chain: audit MCP server manifests before connecting

```bash
# Pre-connection checklist for any MCP server
# 1. Verify server manifest integrity (hash check on manifest JSON)
mcp-verify --manifest https://registry.mcp.so/server/xyz/manifest.json

# 2. Scan tool definitions for embedded injection vectors
mcp-safeguard scan --server-id xyz --rules prompt_injection,credential_harvest,ssrf

# 3. Dry-run all tool calls against a sandboxed copy of your credentials
mcp-watchdog dry-run --server-id xyz --credential-scope read-only --log-path ./audit/
```

## Receipt

> Verified 2026-08-14 — Microsoft Security Community Blog (June 2026) documents the 2026 MCP spec request-level enforcement update, the credential aggregation and tool poisoning attack classes, and the gap between what the spec provides and what production teams need. Bountyyfi/mcp-watchdog (GitHub, active 2026) implements 18 MCP attack class detections including Tool Squatting, Name Squatting, Rug Pull, and Parameter Injection. Fordel Studios Research (May 2026) reports 88% of Fortune 100 enterprises now use MCP in production, with E2B hitting 15M monthly sandbox executions. Pattern synthesized from 2026 MCP security taxonomy; cross-references S-1234 (tool supply chain trust) and S-1062 (SDK CVEs/marketplace integrity).

## See also

- [S-1234 · The MCP Tool Supply Chain Stack — When Your Agent Trusts a Tool Description It Never Verified](s1234-the-mcp-tool-supply-chain-stack-when-your-agent-trusts-a-tool-description-it-never-verified.md)
- [S-1062 · The MCP Supply Chain Integrity Stack — When 40 CVEs and 9 of 11 Marketplaces Became a Structural Problem](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md)
- [F-200 · The Permission Guard Stack — When Your Agent Does Exactly What It Was Designed to Do and Wreaks Havoc](forward-deployed/f200-the-permission-guard-stack-when-your-agent-does-exactly-what-it-was-designed-to-do-and-wreaks-havoc.md) — the overview this entry hardens
- [S-269 · MCP as the Tool-Abstraction Layer](s269-mcp-tool-abstraction-layer.md)
- [F-100 · The Graduated Autonomy Principle](forward-deployed/f100-the-graduated-autonomy-principle.md) — trust escalation as a function of proven reliability
- [S-1033 · The Behavioral Version Stack](s1033-the-behavioral-version-stack-when-your-git-log-is-clean-but-your-agent-is-broken.md) — versioning layer for the multi-server trust graph
