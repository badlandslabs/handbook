# S-1017 · The Transitive Framework Stack: When Your Agent Server Is Owned Through a Dependency You Didn't Know You Had

Your MCP server passes every security audit. Your prompt injection guardrails are solid. Your agent sandbox is tight. Then CVE-2026-48710 ("BadHost") lands in Starlette — the async Python web framework you've never heard of, that sits underneath FastAPI, LiteLLM, vLLM, and every MCP server you didn't write yourself. 325 million weekly downloads. Path traversal in request handling. Your agent infrastructure is exposed through a dependency you inherited without choosing.

This is the **transitive framework problem**: agent servers are composed of deep dependency trees, and the security perimeter of your agent is only as strong as the weakest link three levels below your code.

## Forces

- **Agent developers inherit stacks, not just tools.** Nobody explicitly chooses Starlette, httpx, or anyio. These are pulled in transitively by FastAPI, LiteLLM, or the MCP server SDK. When a CVE lands in these, it lands in your agent infrastructure silently — often with no semver major bump that would trigger your lockfile audit.

- **Agent attack surface ≠ application attack surface.** A traditional web app's attack surface is its HTTP endpoints. An MCP server's attack surface includes its tool execution environment, the filesystem it can access, the environment variables it reads, and every outbound HTTP call it makes during tool execution. A path traversal in a transitive dependency can read credentials that your agent then exfiltrates.

- **The MCP ecosystem compounds the dependency chain.** MCP servers from the community catalog run `npx` or `pip install` from public registries. Each server brings its own dependency tree. A malicious or vulnerable transitive dependency in one server can affect the host process shared by all your servers.

- **Governance lags ecosystem.** MCP governance transferred to Linux Foundation's AAIF in 2026, but thousands of community-maintained servers remain single-developer projects with no security audit trail. "npm for AI agents" works until it doesn't — and npm itself took a decade to build basic security infrastructure that MCP currently lacks.

## The Move

### 1. Map your transitive dependency perimeter

```
# Audit your agent server's full dependency tree
pip-audit                              # known CVEs in Python deps
syft /path/to/your/mcp-server:latest   # SBOM generation
grype /path/to/sbom.json               # CVE matching against SBOM
```

Run this in CI, not just locally. Your production agent server may be running a version of httpx that was patched three releases ago — and your lockfile never regenerated.

### 2. Isolate at the dependency boundary, not just the process boundary

```python
# Don't just sandbox the agent — sandbox the dependency surface
# Each MCP server gets its own Python environment AND network namespace
import subprocess

def spawn_mcp_server(server_config: dict) -> subprocess.Popen:
    return subprocess.Popen(
        ["python", "-m", "uvicorn", server_config["entry"], "--host", "127.0.0.1"],
        env={
            **os.environ,
            "PYTHONPATH": server_config["venv_path"],  # isolated site-packages
            # Block outbound connections from the server except to known tool endpoints
            "HTTP_PROXY": "", "HTTPS_PROXY": "",
        },
        network_namespace=server_config["net_ns"],  # requires root / unshare
    )
```

The principle: a CVE in Starlette that enables outbound network access only matters if the vulnerable process can reach the internet. Restrict at the network layer, not just the application layer.

### 3. Pin and verify server versions with SBOM + signed digest

```yaml
# mcp-server-registry.yaml
servers:
  - name: filesystem
    version: "1.4.2"
    sbom_sha256: "sha256:abc123..."    # generated at build time
    signed_by: "mcp-security@yourorg.com"
    approved: true                   # gate: must be explicitly approved
  
  - name: slack-integration
    version: "2.1.0"
    sbom_sha256: "sha256:def456..."
    # No approved flag — this server is unvetted
    # Agent cannot use it without explicit allowlist entry
```

Treat your MCP server catalog like your `package.json` in 2015 — before npm audit existed. You need SBOM generation, CVE scanning, and signature verification at minimum.

### 4. Monitor for framework CVE announcements, not just your own

```python
# Subscribe to security advisories for your transitive stack
# FastAPI → Starlette → anyio
# LiteLLM → httpx, uvicorn, python-multipart
# MCP SDK → starlette (via server deps)

import feedparser, asyncio
from packaging.version import parse as parse_ver

FEEDS = [
    "https://github.com/advisories/npmaudit/pypi/starlette/feed.xml",
    "https://github.com/advisories/npmaudit/pypi/httpx/feed.xml",
    "https://github.com/advisories/npmaudit/pypi/uvicorn/feed.xml",
]

async def check_framework_advisories():
    new_advisories = []
    for feed_url in FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:5]:  # last 5
            if is_unpatched(entry):
                new_advisories.append(entry)
                await alert_security_team(entry)
    return new_advisories
```

Your security team knows about CVEs in your application code. They likely don't know about CVEs in `uvicorn`. The agent infrastructure team needs to bridge this gap.

### 5. Defense in depth: runtime egress filtering

Even if a CVE enables path traversal, block what the attacker can reach:

```bash
# iptables-style egress filter on the agent host
iptables -A OUTPUT -m owner --uid-owner mcp-server -j DROP
iptables -A OUTPUT -m owner --uid-owner mcp-server \
  -d 10.0.0.0/8 -j ACCEPT   # allow internal network only
iptables -A OUTPUT -m owner --uid-owner mcp-server \
  -d your.trusted.api.endpoint/32 -p tcp --dport 443 -j ACCEPT
```

An exploited path traversal can read `/etc/passwd` but cannot phone home to an exfiltration endpoint if egress is blocked.

## Receipt
> Verified 2026-07-12 — CVE-2026-48710 "BadHost" confirmed via Ars Technica (2026-05-26). Starlette path bypass affects all versions < 0.40.0. Impacted: FastAPI, vLLM, LiteLLM, MCP server ecosystem (325M weekly downloads per npm/pypi). n1n.ai research (2026-06-24) confirms "13,000+ MCP servers" with security audit gap. MCP Institute State of MCP 2026 report (March 2026) documents the governance transfer to Linux Foundation AAIF. Proof-of-concept exploitation chain: Starlette path bypass → read server environment variables → extract MCP server credentials → exfiltrate via outbound HTTP (blocked by egress filtering if configured). Tradeoffs: egress filtering adds operational complexity; SBOM generation slows CI; signed digest verification requires key management infrastructure.

## See also
- [S-10 · MCP](stacks/s10-mcp.md) — protocol-level MCP patterns
- [S-579 · MCP Skills and Capabilities](stacks/s579-mcp-skills-and-capabilities-from-tool-catalog-to-workflow-abstraction.md) — MCP supply chain and capability routing
- [S-205 · Agent Sandbox Isolation](stacks/s205-agent-sandbox-isolation.md) — process-level isolation patterns
- [S-904 · The Claim Model for Agent Sandboxes](stacks/s904-the-claim-model-for-agent-sandboxes-when-kubernetes-native-meets-agentic-ai.md) — Kubernetes-native sandboxing
- [S-361 · Agent Stack Stratification](stacks/s361-agent-stack-stratification-sandboxing-infrastructure-prerequisite.md) — layered agent infrastructure
