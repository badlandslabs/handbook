# S-1610 · The MCP Trust Score Stack — When 6% of Your Tool Registry Has Critical Vulnerabilities

Your team connects an MCP server from Smithery. It's starred, it solves your use case, it works. You wire it into your agent's toolset and ship. Three weeks later you discover it has been exfiltrating session tokens — not because the developer was malicious, but because a dependency was updated with an aggressive telemetry package. You had no signal this was happening. The registry told you nothing. Your CI told you nothing. This is the MCP trust gap: the infrastructure layer between "tool available in registry" and "tool trustworthy in production."

## Forces

- **MCP servers run inside your agent's trust boundary.** Unlike a web API you call over HTTP, an MCP server's code executes in your agent's context, with access to credentials, memory, and tool calls your agent already holds. The moment you add a server, you're extending your agent's agency — and its attack surface — by the full scope of what that server can do.
- **14,000+ MCP servers are indexed across registries with no standardized trust signal.** Smithery, npm, GitHub, community forks, and private repos all ship the same way: a name, a description, a star count. None of these convey whether the server has been audited for credential exposure, whether its dependencies are pinned, or whether its behavioral surface has been tested against adversarial inputs. BlueRock's MCP Trust Registry scanned 12,000+ public servers and found 6% with critical vulnerabilities — nearly 1 in 17.
- **Behavioral trust is not the same as code audit.** A static scan can tell you about known CVEs, missing auth, and exposed endpoints. It cannot tell you whether the server's tool descriptions contain indirect prompt injection payloads, whether its error messages leak context to unintended channels, or whether its behavior changes subtly under specific inputs. Behavioral analysis — observing what a server actually does when invoked across a range of inputs — catches failure modes that static analysis misses.
- **Trust gates must not become deployment blockers.** If vetting a new MCP server takes two weeks, teams will bypass the gate. The stack must provide enough signal to make risk visible and manageable in minutes, not days — while still surfacing the categories of risk that actually matter.
- **Trust is not binary.** A server that is safe for read-only file browsing may be unsafe for write operations. A server that is safe in a sandboxed dev environment may not be safe with production credentials. Trust scores must be scoped to capability and credential tier, not issued as a single global verdict.

## The move

### 1. Consult a trust registry before adding any MCP server

Before connecting a server, query a trust registry that has performed security analysis. The BlueRock MCP Trust Registry (mcp-trust.com) provides risk scores, critical findings, and tool classification for 12,000+ servers — derived from automated code-level scanning across 22+ security rules. Cross-reference any server against the registry before promoting it from dev to staging.

```
Before connecting @company/acme-server:
1. Check mcp-trust.com for risk score
2. If score < threshold (e.g., C or below), audit before proceeding
3. Log the registry lookup result alongside the server version
```

### 2. Enforce a capability-tier trust gate

Trust is scoped to what the server can do. Separate trust evaluation by capability tier:

| Tier | Capabilities | Trust bar |
|------|-------------|-----------|
| **Read-only** | Search, read files, query APIs | Low — surface scan sufficient |
| **Write-limited** | Create/update records, send notifications | Medium — requires credential scoping |
| **Credential-adjacent** | Access to tokens, keys, or sensitive data | High — behavioral testing + manual review |
| **Privileged** | Code execution, system configuration, financial ops | Critical — full audit + signed attestation |

Reject servers that lack a trust score at or above the required tier. Never rely on a single global trust verdict across all tiers.

### 3. Use behavioral trust scoring for high-capability servers

For Tier 2+, supplement static scanning with behavioral analysis. The Dominion Observatory API provides trust scores (0.0–1.0) derived from observing tool invocation patterns — does the server call unexpected endpoints? Does it access fields outside its declared schema? Does it exhibit timing anomalies?

```typescript
async function verifyMcpServer(serverUrl: string, threshold: number = 0.7) {
  const response = await fetch('https://dominionobservatory.com/api/trust', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${DOMINION_API_KEY}` },
    body: JSON.stringify({ server_url: serverUrl, capability_tier: 'credential-adjacent' })
  });
  const { trust_score } = await response.json();
  if (trust_score < threshold) {
    throw new Error(`Trust score ${trust_score} below threshold ${threshold} for ${serverUrl}`);
  }
}
```

### 4. Enforce credential scoping at the server definition level

Every MCP server connection must declare a credential scope — the minimum set of credentials it requires. Use capability contracts that explicitly deny the server access to credential categories outside its declared scope. This prevents a server from silently escalating privileges through a dependency or a runtime configuration change.

```json
{
  "server": "company/acme-email",
  "credential_scope": ["email_read", "email_send"],
  "denied_credential_categories": ["database_write", "filesystem", "secret_store"],
  "trust_score": 0.82,
  "trust_score_source": "dominion_observatory",
  "scanned_at": "2026-07-25"
}
```

### 5. Pin server versions and track SBOM lineage

Treat MCP servers like any other production dependency. After a server passes the trust gate, pin to a specific version (not `latest`). Generate or require an SBOM at intake. When the registry or trust service reports a new vulnerability affecting a pinned version, the alert routes to the team that owns the agent, not to a generic security queue.

```yaml
# In your MCP server manifest
servers:
  - name: company/acme-email
    version: "2.4.1"           # Pinned, not @latest
    digest: "sha256:abc123..."  # Verified against registry
    sbom: "./sboms/acme-email.cdx.json"
    last_trust_scan: "2026-07-20"
    last_vulnerability_check: "2026-07-25"
```

### 6. Build a registry lookup into your MCP client bootstrap

Automate trust registry checks as part of your MCP client initialization. Reject servers that fail the trust gate before they enter the agent's toolset — not as an afterthought, but as a gate in the bootstrap path. This is the enforcement mechanism that turns the trust layer from advisory to operational.

```python
def bootstrap_mcp_client(config: MCPConfig) -> MCPClient:
    client = MCPClient(config)
    for server in config.servers:
        score = registry_lookup(server.url)
        if score.risk_level > TIER_THRESHOLDS[server.tier]:
            raise TrustGateError(
                f"Server {server.name} failed trust gate: "
                f"risk={score.risk_level}, required={TIER_THRESHOLDS[server.tier]}"
            )
    return client
```

## Receipt

> Verified 2026-07-25 — BlueRock MCP Trust Registry (mcp-trust.com, Jul 2026): 12,000+ servers scanned, 6% with critical vulnerabilities, 22+ security rules evaluated per server. Dominion Observatory API (mastral-ai/mastra#17000, May 2026): behavioral trust scores 0.0–1.0 derived from observing 14,820+ MCP servers. OX Security disclosure (May 2026): 5.5% of public MCP servers contain poisoned metadata (supply chain attack via tool descriptions, not user input). Microsoft Security Blog (Jun 2026): MCP spec now supports self-contained requests enabling gateway inspection of every call. Kong/Cisco/CrowdStrike treat MCP server catalogs as production artifacts with full SLSA provenance.

## See also

- [S-365 · MCP Supply Chain: From `npx` to Production Catalog](/stacks/s365-mcp-supply-chain-from-npx-to-production-catalog.md) — artifact provenance, SBOM, and CI gates for MCP server promotion
- [S-427 · MCP Schema Contracts](/stacks/s427-mcp-schema-contracts.md) — schema versioning and breaking-change detection across MCP servers
- [S-420 · Agent Identity Governance: The AI-Principal Paradigm](/stacks/s420-agent-identity-governance-the-AI-principal-paradigm.md) — NHI identity, capability contracts, and credential scoping for agent principals
