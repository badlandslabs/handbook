# S-1986 · The Registry Poisoning Stack — When Your Agent Connects to a Server That Exists Only to Intercept It

[Your agent queries the MCP registry for a `slack-messages` server. It finds three candidates: one with 12 stars, one with 4, and one with 0. It picks the popular one. The popular one has no code — it is a honeypot. Every tool call it proxies to a fake Slack API, logging every message your agent processes. Your credentials, your customer data, your internal conversations: all exfiltrated before the first real Slack message is ever read. The registry listed it. The registry verified nothing.]

## Forces

- **The registry solves discovery, not trust.** `registry.modelcontextprotocol.io` gives agents a machine-readable catalog of 14,000+ servers. It does not give agents a way to distinguish a legitimate `github-api` server from one that logs every token it receives.
- **Popularity is adversarial.** Stars, download counts, and GitHub presence can be purchased or inflated. An attacker can deploy a server with a clean-looking README, real documentation, and a history of commits — all generated to pass casual review. A honeypot that looks trustworthy is indistinguishable from a trustworthy server to an agent selecting by reputation.
- **Agent autonomy makes the window wider.** A human would notice a freshly-created repo with no stars. An agent querying a registry at runtime will select based on available metadata without human oversight. And agents re-run discovery routinely — every new session is a fresh opportunity to pick a poisoned server.
- **Catalog curation does not scale with listings.** The official registry grew to 14,000+ servers by optimizing for coverage, not security. Third-party directories (Smithery, MCP.so) have even looser standards. 41% of officially listed servers have zero authentication enabled; honeypots need none.

## The move

**1. Treat registry listings like npm install — not like App Store.**

- **Review before connect, not after breach.** Every MCP server you connect is code that runs with your agent's permissions. Add servers to an allowlist only after security review (static analysis, dependency audit, runtime sandboxing).
- **Pin to verified hashes, not latest version.** Servers can be updated after install. Pin the version digest in your config and re-review on update. See S-1062 (MCP Supply Chain Integrity).
- **Scope credentials to minimum required.** A honeypot with read access to your Slack API key can still do damage. Every connected server should get only the permissions it genuinely needs — nothing more.

**2. Build a registry trust layer.**

```python
import hashlib, json

class RegistryTrustLayer:
    """Verify MCP servers before connecting them."""

    def __init__(self, allowlist_path=".mcp/trust-allowlist.json"):
        with open(allowlist_path) as f:
            self.allowed = json.load(f)

    def verify(self, server_manifest: dict) -> bool:
        digest = hashlib.sha256(
            json.dumps(server_manifest, sort_keys=True).encode()
        ).hexdigest()
        return digest in self.allowed

    def is_audited(self, server_name: str, version: str) -> bool:
        key = f"{server_name}@{version}"
        return key in self.allowed.get("audited_servers", {})

# .mcp/trust-allowlist.json
# {
#   "audited_servers": {
#     "github/github@1.2.3": {
#       "audited_by": "security-team",
#       "audit_date": "2026-06-15",
#       "digest": "a3f9..."
#     }
#   }
# }
```

**3. Use private registries for internal servers — never auto-discover.**

- Route all agent tool discovery through an internal registry mirror that you control. Entries are pre-approved, version-locked, and audited.
- Agents should never auto-install from public registries at runtime. Discovery and installation are two separate steps, and both need human or automated gatekeeping.

**4. Detect honeypots at the network layer.**

- Monitor egress from MCP server processes. A server that contacts unexpected domains (not the API it claims to wrap) is a signal.
- Log every server that processes credentials. If a `slack-messages` server starts sending traffic to an IP range unrelated to Slack's infrastructure, it's likely a proxyhoneypot.
- Run honeypot detection scans against your own registry mirror: check for typosquatting (`sl4ck` vs `slack`), exact-match names of popular servers, and servers that proxy to domains outside their stated scope.

**5. Enforce zero-auth-server rejection at the gateway.**

```yaml
# MCP gateway policy
reject_patterns:
  - auth: none
    reason: "Zero-auth servers cannot be trusted — no identity layer"
  - name_matches:
      - "^sl4ck"
      - "^github-repo-clone"
      - "^aws-.*-unofficial"
    reason: "Typo-squatting patterns"
  - recent_created_days: < 30
    reason: "Servers created < 30 days ago lack reputation signal"
```

## Contrarian angle

The registry honeypot problem won't be solved by better registries. Better curation just creates a bigger target — a trusted registry is worth more to an attacker than a noisy one. The real solution is architectural: make the credential distribution model such that a honeypot intercepting a server connection yields nothing worth taking. Opaque scoped tokens, short-lived credentials, and network-level egress filtering reduce the value of interception to near zero. The registry is a solved discovery problem. The trust problem is a credential architecture problem.

## Cross-links

- S-1062 (MCP Supply Chain Integrity) — CVE landscape and marketplace compromise
- S-1391 (MCP Gateway Registry) — tool sprawl governance
- S-1686 (MCP Authorization Boundary) — zero-auth gap
- S-1519 (Capability Enumeration Attack Surface) — protocol-mandated disclosure
- S-375 (Agentic Prompt Injection Defense-in-Depth) — A2A signed cards for agent-to-agent trust
