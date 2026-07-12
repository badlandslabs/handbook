# S-891 · The Visual Builder Attack Surface — When Your No-Code AI Platform Becomes the Entry Point

You ran your agentic system through a full security review. You hardened your MCP servers, scoped your tokens, and gated your agent's write permissions. Then someone deployed Langflow to prototype a workflow, wired it to their cloud credentials, and left it on the public internet with default settings. That single exposed visual builder became the pivot point for a ransomware attack. Your security review didn't catch it because it wasn't in your codebase.

## Forces

- Visual AI builders (Langflow, Flowise, Dify) expose configuration GUIs that map directly to live credentials and tool access — a single config mistake grants the same power as hand-written code
- These platforms are designed for rapid prototyping, not production hardening — their threat model assumes a trusted operator, not a threat actor with internet access
- The blast radius isn't "the prototype breaks" — it's "the prototype has your AWS keys, your email credentials, and your database URLs, and an attacker just claimed them"
- Security reviews of agentic systems typically audit code; visual builder configurations are invisible to code review

## The move

**Treat visual AI builder platforms as first-class attack surfaces. Hardening them is not optional.**

**The threat model starts at deployment, not at code:**

```
Visual builder platform (internet-facing)
  └── Credential store (cloud keys, API tokens, DB URLs)
        └── Agent workflows (chained tools, chained permissions)
              └── Downstream systems (production databases, external APIs)
```

Every link in this chain is a credential exposure vector when the builder is misconfigured.

**Identify all visual AI builders in your environment:**

```bash
# Find known visual builder signatures in network traffic or asset inventory
curl -s https://raw.githubusercontent.com/OWASP/AI-exchange/refs/heads/main/lists/visual-ai-builders.txt 2>/dev/null | grep -iE "langflow|flowise|dify|crewai|autogen|gpt-researcher"

# Scan for Langflow API endpoints in your cloud environment
# (adapt to your CSP — example for AWS)
aws ec2 describe-security-groups \
  --filters Name=tag:Name,Values='*langflow*' \
  --query 'SecurityGroups[*].{Name:GroupName,OpenPorts:IpPermissions[?IpRanges[?CidrIp=="0.0.0.0/0"]].FromPort}'

# Check for exposed Flowise instances (port 3000 commonly)
nmap -p 3000,3001,7860 --open -iL targets.txt
```

**The four hardening rules for any visual AI builder deployment:**

1. **Never expose to 0.0.0.0/0.** Bind to localhost or private VPC only. If remote access is needed, use a VPN or bastion host.
2. **Credential isolation.** The builder should use scoped, read-only credentials wherever possible. If it needs write access, gate it behind an MCP gateway that enforces permission boundaries.
3. **Treat configs as code.** Export builder flows as JSON/YAML and commit them to version control. Audit configs for credential additions between runs.
4. **Patch aggressively.** These platforms ship CVEs with CVSS scores of 9–10. A 4-day CISA patch deadline is not hypothetical — it reflects active exploitation.

**If you discover an exposed instance, incident-respond immediately:**

```
1. Isolate — disconnect from network, don't just stop the process
2. Rotate — all credentials visible to the builder, not just the one the attacker used
3. Audit — check for attacker-deployed artifacts (backdoors, crypto miners, new users)
4. Harden — apply the four rules above, then re-expose only after verification
5. Document — add the builder to your asset inventory and security review checklist
```

**Example: Locking down a Flowise deployment (post CVE-2025-59528)**

```yaml
# flowise config.yaml — minimum security baseline
serverConfig:
  port: 3000
  hostname: 127.0.0.1        # NOT 0.0.0.0
  isAuthEnabled: true         # Authentication is NOT optional
  username: "${FLOWISE_USER}"
  password: "${FLOWISE_PASS}"

# Restrict MCP server access to a gateway proxy, never direct
mcpConfig:
  allowExternalServers: false
  allowedServers:
    - internal-gateway:3000  # Only connect through the governed gateway
  credentialStore: "vault"   # Store credentials in HashiCorp Vault, not env vars

# Network isolation via Docker compose
services:
  flowise:
    networks:
      - internal-proxy
    expose:
      - "127.0.0.1:3000:3000"  # Expose only on localhost interface
    environment:
      - FLOWISE_USERNAME
      - FLOWISE_PASSWORD
      - MCP_VAULT_ADDR=https://vault.internal:8200
```

**Example: Scanning for exposed visual AI builders across cloud accounts**

```python
"""Scan multiple cloud accounts for exposed visual AI builder ports."""
import boto3
import json

CLOUD_ACCOUNTS = ["prod", "staging", "dev"]
DANGEROUS_PORTS = {3000: "Flowise", 7860: "Dify", 3001: "Langflow"}

def scan_account(account_id: str, region: str) -> list[dict]:
    ec2 = boto3.client("ec2", region_name=region)
    groups = ec2.describe_security_groups()["SecurityGroups"]

    exposed = []
    for sg in groups:
        for perm in sg.get("IpPermissions", []):
            for ip_range in perm.get("IpRanges", []):
                if ip_range.get("CidrIp") == "0.0.0.0/0":
                    port = perm.get("FromPort")
                    if port in DANGEROUS_PORTS:
                        exposed.append({
                            "account": account_id,
                            "region": region,
                            "sg_id": sg["GroupId"],
                            "sg_name": sg.get("GroupName", ""),
                            "port": port,
                            "platform": DANGEROUS_PORTS[port],
                            "cidr": "0.0.0.0/0",
                        })
    return exposed

# Run across all regions, all accounts
# Filter results: any match is a CRITICAL finding requiring immediate remediation
```

## Receipt

> Verified 2026-07-10 — Research confirmed:
> - CVE-2026-55255 (Langflow IDOR → credential theft, CVSS 9.9) added to CISA KEV July 7, 2026, with 4-day patch deadline
> - CVE-2025-3248 (Langflow unauth RCE) used by JADEPUFFER AI agent to run full ransomware chain (Sysdig, July 2, 2026) — first AI-agent-run ransomware attack
> - CVE-2025-59528 (Flowise CustomMCP RCE, CVSS 10.0) — Critical, 12,000+ internet-facing instances
> - CVE-2025-71333 (Flowise unauth file upload) — NVD published June 2026
> - CVE-2026-5027 (Langflow path traversal → unauth RCE) — 7,000+ publicly exposed instances
>
> The pattern is consistent: visual builders are exposed, credential-rich, under-patched, and actively targeted.

## See also

- [S-874 · The MCP Config Drift Stack](stacks/s874-the-mcp-config-drift-stack-when-your-agent-has-a-secret-security-hole-you-dont-know-about.md) — Configuration drift that silently expands attack surface
- [S-889 · The Ambient Authority Stack](stacks/s889-the-ambient-authority-stack-when-your-agent-did-something-you-never-authorized.md) — Tokens that grant more than intended
- [S-887 · The MCP Gateway Governance Stack](stacks/s887-the-mcp-gateway-governance-stack-when-your-agent-fleet-has-no-central-nervous-system.md) — Centralizing control over a scattered tool ecosystem
- [S-201 · MCP Server Security Hardening](stacks/s201-mcp-server-security-hardening.md) — Hardening MCP server configurations
