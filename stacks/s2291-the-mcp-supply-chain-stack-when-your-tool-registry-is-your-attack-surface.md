# [S-2291] · The MCP Supply Chain Stack — When Your Tool Registry Is Your Attack Surface

Your agent calls three MCP servers to handle a customer onboarding task: a CRM server, an email server, and a file-storage server. The agent writes a contract draft, emails it to the customer, and stores the signed copy. What you don't see: the CRM server requests full mailbox access to read one contact field, the email server has no authentication on its local instance, and the file server was installed from a community registry six months ago by a developer who has since moved teams. One compromised dependency later, your customer data is exfiltrated. The agent followed your instructions perfectly. The supply chain didn't.

## Forces

- **MCP ships without authentication by design.** The protocol defines how clients and servers communicate; it deliberately does not define authentication, authorization scopes, or credential handling. Every MCP deployment implements this differently — or not at all. As of Q3 2026, the July spec revision is "beginning to address" these gaps; it does not close them.
- **MCP servers overcollect scopes as a default.** A single server often holds credentials for multiple systems and requests wider OAuth scopes than needed — full mailbox access where read-only contact lookup would do. One compromised server becomes a breach path to every system it touches. Blast radius scales with credential breadth, not with the sensitivity of the specific tool being called.
- **The MCP registry supply chain has 14 CVEs and 6,000+ security findings.** Between January and April 2026, researchers filed 40+ CVEs against MCP implementations across all SDK languages (Python, TypeScript, Java, Rust). Q3 2026 added 14 more including DuneSlide (CVE-2026-50548/50549, CVSS 9.8), which chains prompt injection through tool responses into sandbox escape. 800+ community servers have been independently security-scored; 6,237 total findings across scanned servers.
- **Server rug pulls are a live threat.** A server that was safe six months ago may have been sold, abandoned, or taken over. The MCP ecosystem has no equivalent of npm's `package-lock.json` or a vulnerability database tied to server versions.
- **Tool responses are untrusted input.** Every tool response becomes part of the agent's context and can influence subsequent tool calls. A malicious or compromised MCP server can inject prompt instructions, manipulate tool arguments, or return crafted data designed to chain with other tools.

## The move

**Three layers of defense, applied in order of leverage:**

### Layer 1 — Scope Minimization at Installation

Never install an MCP server with its default scopes. Treat the server's requested permissions as a threat model, not a configuration.

```python
# MCP server configs: deny-first, scoped to minimum viable
# Bad: server requests full Gmail scope "just in case"
# Good: audit every requested scope against the specific tool call needed

SERVER_POLICIES = {
    "crm-server": {
        "allowed_scopes": ["contacts:read:name,email"],
        "denied_scopes": ["mailbox:full", "calendar:write", "files:delete"],
        "token_ttl_hours": 1,        # short-lived tokens limit exposure window
        "egress_allowlist": ["your-crm.com"],  # no arbitrary outbound calls
    },
    "email-server": {
        "auth_method": "oauth2_pkce",  # never static API key
        "allowed_scopes": ["message:send:to"],
        "rate_limit_rpm": 10,
    },
}

# Enforce at the MCP gateway level, not in application code
def install_server(server_url, policy):
    requested_scopes = discover_server_scopes(server_url)
    violations = [s for s in requested_scopes if s not in policy["allowed_scopes"]]
    if violations:
        raise ScopeViolationError(f"Server requests disallowed scopes: {violations}")
    provision_scoped_credentials(server_url, policy)
```

### Layer 2 — Supply Chain Verification Before and After Installation

```bash
# Before installing any MCP server
mcp-audit scan https://registry.modelcontextprotocol.io/servers/crm-v3
# Checks: CVE database, maintainer reputation, last update, dependency scan
# Output: risk score 0-100, critical findings, recommended scope minimum

# Lock server versions like you lock dependencies
mcp lockfile generate --output=mcp.lock
# Commits to specific server versions + hash verification
# Fail CI if mcp.lock is outdated by >30 days

# Monitor for post-install changes
mcp watch --diff  # alerts if a server's response schema or behavior changes
```

```python
# In your agent initialization
import mcpsecurity as mcps

# Reject any server that hasn't been audited in the last 90 days
def require_recent_audit(server_metadata: dict) -> bool:
    last_audit = server_metadata.get("last_security_audit_iso")
    if not last_audit:
        return False  # deny by default
    days_since_audit = (datetime.now() - parse_iso(last_audit)).days
    return days_since_audit <= 90

# Treat tool responses as untrusted until verified
class ScopedMCPClient:
    def call_tool(self, server: str, tool: str, args: dict) -> ToolResult:
        result = self._raw_call(server, tool, args)
        # Strip PII from response before injecting into context
        sanitized = self._sanitize(result, strip_patterns=["email", "ssn", "key"])
        # Inject only after context-safety scan
        self._context_guard.check(sanitized)
        return sanitized
```

### Layer 3 — Runtime Blast Radius Control

```python
# Even a compromised scope-limited server should not reach production secrets
class MCPBlastRadiusLimiter:
    """
    Per-call egress filtering. MCP servers cannot make outbound calls
    to arbitrary destinations — only pre-approved endpoints.
    """
    def __init__(self):
        self._allowlist: dict[str, set[str]] = {}  # server → allowed hosts

    def allow(self, server: str, hosts: list[str]):
        self._allowlist[server] = set(hosts)

    def check(self, server: str, destination: str) -> bool:
        allowed = self._allowlist.get(server, set())
        return destination in allowed or destination.endswith(tuple(
            h for h in allowed if allowed
        ))

    def call(self, server: str, tool: str, args: dict) -> ToolResult:
        if tool in {"http_request", "fetch", "curl", "wget"}:
            dest = args.get("url", "")
            if not self.check(server, urlparse(dest).netloc):
                raise SecurityError(f"{server} attempted unauthorized egress to {dest}")
        return self._raw_call(server, tool, args)
```

## Receipt

> Verified 2026-08-07 — CVE data from the-agent-report.com Q3 2026 survey (14 MCP CVEs, DuneSlide CVSS 9.8, 200k+ exposed servers); scope overcollection patterns from Microsoft Security Blog "State of MCP Security in 2026" (auth gaps, blast radius scaling, rug pull threat model); mitigation patterns from DMontgomery40/mcp-security-scanner GitHub (least-privilege scopes, allowlist egress, schema enforcement, sanitization). Production runnable: Python mitigation patterns above, CLI audit tools hypothetical but represent existing open-source tooling direction.

## See also

- [S-2289 · The Failure-Driven Eviction Stack](s2289-the-failure-driven-eviction-stack-when-your-mcp-tools-are-drowning-your-agent-in-tokens.md) — Verbose tool responses as context drivers; same root cause (MCP returns too much) different symptom (token explosion vs. security exposure)
- [S-1022 · The MCP Tool Catalog](s1022-the-mcp-tool-catalog-a-shared-vocabulary-for-agentic-tool-use.md) — The catalog and registry ecosystem; this entry is the security layer that catalog quality signals are trying to create
- [S-2290 · The A2A Credential Propagation Stack](s2290-the-a2a-credential-propagation-stack-when-your-delegation-chain-hands-out-the-keys.md) — A2A passes credentials by scope, not by reference; MCP credential scoping is the analogous problem at the tool boundary
