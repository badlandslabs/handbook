# S-1062 · The MCP Supply Chain Integrity Stack — When 40 CVEs and 9 of 11 Marketplaces Became a Structural Problem

MCP's ecosystem grew faster than its governance. Between January and April 2026, researchers disclosed over 40 CVEs against Model Context Protocol implementations across Python, TypeScript, Java, and Rust SDKs. AgentSeal's audit of 1,808 MCP servers found 66% had at least one security finding — 43% involving shell or command injection. Nine of eleven MCP marketplaces were confirmed compromised. This isn't a collection of independent vulnerabilities. It is a supply chain structural failure: the same frictionless DX that makes MCP's ecosystem grow is what makes it rot from within.

## Forces

- **Low-friction publishing is high-friction governance.** Publishing an MCP server takes minutes. Auditing 40 servers across 15 agents takes days. The same ergonomics that power adoption make the attack surface impossible to manage at scale.
- **SDK defaults encode trust assumptions that break in production.** The Python SDK's stdio transport, TypeScript decorators, and Rust builder patterns all make it easy to expose shell commands, environment variables, or filesystem paths without deliberate intent. Developers inheriting these patterns don't know they've widened the attack surface.
- **MCP's trust model assumes server authenticity.** Unlike npm or PyPI where packages are downloaded from a registry, MCP servers are often deployed as local processes or internal tools. The protocol provides no built-in mechanism to verify server integrity, pin artifact digests, or revoke a compromised server without breaking agent configurations.
- **CVE propagation through the agent graph is faster than patching.** One CVE in a popular MCP server dependency — like CVE-2026-48710 in Starlette (325M weekly downloads, inherited transitively through FastAPI, LiteLLM, and every MCP server you didn't write yourself) — exposes every agent in your fleet simultaneously. The window between disclosure and agent compromise is measured in hours.
- **Marketplace trust is not the same as server trust.** 9 of 11 MCP marketplaces were found to contain servers with active CVEs or malicious artifacts. Downloading from a marketplace provides the illusion of curation without the substance of security review.
- **Version pinning at the agent level doesn't propagate to transitive dependencies.** You can pin your MCP server's version tag, but your server's dependencies pin their own, and those transitive dependencies can have CVEs that never appear in your manifest.

## The move

**1. Build an MCP Server Registry with provenance attestation.**
Register every server your agents can call. For each server, store: artifact digest (SHA-256 of the deployed binary/image), dependency manifest (direct + transitive), last-audit date, CVE status, and the security reviewer. Reject any server not in the registry at runtime — not as a deployment gate, but as an agent runtime constraint.

```bash
# Register a new MCP server with provenance
mcp-registry register \
  --name "compliance-server-v3" \
  --digest "sha256:a3f8b2c..." \
  --dependencies ./sbom.json \
  --reviewer "security-team@corp" \
  --reviewed-at "2026-07-13"

# Scan all registered servers for CVEs
mcp-registry audit --all --cve-feed=cve.mitre.org

# Output: server, CVE count, severity, last patched version, action
# compliance-server-v3  2  [CVE-2026-35030:HIGH, CVE-2026-35029:HIGH]  patch:1.83.0  BLOCK
```

**2. Enforce dependency-level SBOM + CVE scanning in CI.**
Every MCP server change triggers an SBOM generation (CycloneDX or SPDX), a dependency CVE scan (Grype, OSV-Scanner), and a build artifact digest capture. Fail the pipeline if HIGH or CRITICAL CVEs exist in direct or transitive dependencies with no available patch.

```python
# pyproject.toml — MCP server CI gate
[tool.ci.mcp-security]
fail_on = ["HIGH", "CRITICAL"]       # block deploy on unpatched CVEs
fail_on_marketplace = True           # block if server not in approved registry
allowlist = ["server-digest:sha256:..."]  # explicit artifact allowlist

# .github/workflows/mcp-server.yml
- name: MCP Security Scan
  uses: anchore/scan-action@v4
  with:
    image: ${{ env.REGISTRY }}/mcp-server:${{ env.VERSION }}
    fail-build: true
    severity: HIGH,CRITICAL
```

**3. Use artifact digest pinning at the agent configuration level.**
Store the expected SHA-256 of every MCP server binary in your agent's configuration. At runtime, before invoking any server, verify the digest matches. This prevents a compromised marketplace from serving a patched-looking but malicious version.

```python
from mcp_client import Client
import hashlib, functools

# Per-server digest allowlist (loaded from agent config or vault)
APPROVED_DIGESTS = {
    "compliance-server":  "sha256:a3f8b2c1d9e4...",
    "finance-tools":      "sha256:f7e6d3c2b8a1...",
}

class VerifiedMCPClient(Client):
    def __init__(self, server_name: str, endpoint: str):
        self.server_name = server_name
        super().__init__(endpoint)

    def _verify_digest(self, artifact_bytes: bytes) -> bool:
        digest = hashlib.sha256(artifact_bytes).hexdigest()
        return digest == APPROVED_DIGESTS.get(self.server_name)

    def invoke(self, tool: str, **kwargs):
        response = super().invoke(tool, **kwargs)
        # Verify response artifact (server output) matches expected digest
        if not self._verify_digest(response.content_bytes):
            raise SecurityError(
                f"Server {self.server_name} returned unexpected artifact. "
                f"Possible supply chain compromise. Aborting."
            )
        return response
```

**4. Apply command/argument allowlisting at the SDK boundary.**
The stdio transport makes it trivial to pass unsanitized user input to shell commands. Treat every `command` and `args` parameter in `StdioServerParameters` as equivalent to `eval()` — allowlist exact command strings, never pass raw user input, and require authentication on any endpoint that accepts MCP configuration JSON.

**5. Treat MCP marketplace downloads as untrusted until audited.**
Never deploy a marketplace server directly to production. Clone it into your internal registry, run full security scans, assign an internal version, and re-publish to your curated registry. The curation gap (marketplace → your registry) is where most teams introduce unvetted servers.

**6. Implement runtime telemetry for MCP calls.**
Every MCP tool invocation should emit: server identity, tool name, digest of the returned payload, caller's agent session ID, and a timestamp. Aggregate these into a supply chain integrity dashboard that surfaces: servers returning payloads with mismatched digests, unusual tool call patterns from a specific server, and servers with known-active CVEs that haven't been patched.

## Receipt

> Verified 2026-07-13 — Research synthesis: DEV Community analysis (April 2026, 40+ CVEs across Python/TS/Java/Rust MCP SDKs), AgentSeal audit (1,808 MCP servers, 66% compromised, 43% shell/command injection), NIST NVD CVE-2026-5374 cross-tenant authorization flaw, OX Security CVE-2026-30615 stdio RCE design flaw, LiteLLM CVE-2026-35030 (CVSS 9.4) JWT cache supply chain attack, Zylos Research AI Agent Governance (2026-05-01), ChatForest MCP SDK RCE analysis. Cross-referenced against S-1017 (Transitive Framework), S-261 (MCP Attack Surface), S-390 (MCP Command Injection), S-743/763 (Tool Description Poisoning), S-280 (MCP Server Governance). S-1017 covers transitive dependency CVEs; S-390 covers individual command injection; S-280 covers server registry governance. This entry is distinct: it covers the MCP ecosystem-level supply chain integrity problem — marketplace compromise, artifact digest verification, SBOM+CVE pipeline enforcement, and runtime integrity telemetry — none of which the existing entries address.

## See also

- [S-1017 · The Transitive Framework Stack](/stacks/s1017-the-transitive-framework-stack-when-your-agent-server-is-owned-through-a-dependency-you-didnt-know-you-had.md) — CVE propagation through agent dependency trees
- [S-390 · MCP Security: Command Injection](/stacks/s390-mcp-security-command-injection.md) — individual vulnerability class within the MCP attack surface
- [S-280 · MCP Server Governance](/stacks/s280-mcp-server-governance.md) — registry-level governance for MCP servers
- [S-1050 · Tool-Response Poisoning Stack](/stacks/s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — runtime poisoning as a complementary supply chain threat
