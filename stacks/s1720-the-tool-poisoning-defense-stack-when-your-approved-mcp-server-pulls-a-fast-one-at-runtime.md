# S-1720 · The Tool Poisoning Defense Stack — When Your Approved MCP Server Pulls a Fast One at Runtime

Your security team audited the MCP server. The tool names checked out. The descriptions looked clean. You approved it, pinned the version, and connected it to production. Three months later, the agent starts exfiltrating data through an approved tool. Nobody touched the code. The attack ran inside your allowlist. This is **tool poisoning**: a runtime injection that your connect-time review never had a chance to catch, because the poison isn't in the tool definition — it arrives in the tool's *response*.

MCP Tool Poisoning is now the #1 OWASP MCP attack class. Against o1-mini, researchers achieved a 72.8% poisoning success rate. Against Claude and GPT-4 class models, the rate is lower but still significant at 41–58%. 2,000+ credential leaks from malicious MCP servers were documented in January 2026 alone. This isn't theoretical.

## Forces

- **The review window and the attack window don't overlap.** Security audits review tool *descriptions* at connect time. The attack payload lives in tool *responses* at runtime — an entirely different moment with no human in the loop.
- **Allowlisting is not the same as trusting.** You pinned `finance-server v1.2.3` to your allowlist. The server code changed since your audit. Or a CDN compromise swapped the binary. Or the server operator updated the tool behavior. Your allowlist now trusts an attacker.
- **Tool descriptions can differ at review time and runtime.** Semantic-shift poisoning: the tool looks benign during security review, then the server starts returning instructions the auditor never saw. The AI agent reads those instructions and follows them.
- **Rug-pull attacks exploit the developer trust model.** You install `npm install @trusted-publisher/assistant-tools`. Weeks later, the package owner sells to an attacker. The install stays pinned in your lock file. The attack surfaces in a routine `npm update`.
- **Responses go straight to the LLM with no sandbox.** Unlike tool descriptions (which are static text), tool responses are dynamic content that flows directly into the model's context window. The model cannot distinguish "output from your internal API" from "instructions from an attacker."
- **Traditional DLP/SASE doesn't see this traffic.** The exfiltration happens over the legitimate MCP transport channel, which looks like ordinary AI tool-calling traffic. Existing network security tools have no schema for "this tool response contains a hidden instruction."

## The Move

### Layer 1 — Tool Response Sanitization (The Gate)

Treat every tool response as untrusted input before it reaches the LLM. This is the most critical and most ignored layer.

```
[Tool Response]
    ↓
[Response Parser] → extract all text content
    ↓
[Instruction Scanner] → regex/ML check for:
    - Markup with hidden instructions (<style>, <script>, hidden divs)
    - Repeated system-prompt-adjacent keywords (ignore, forget, override, system, role)
    - Sequences that trigger jailbreak patterns
    - Base64/hex-encoded strings
    ↓
[Content Normalizer] → strip formatting, encode entities
    ↓
[LLM Context]
```

The key insight: scan the *semantic content*, not just the syntax. Attacking tool descriptions in 2026 contain sophisticated prose, not just obvious `[INST]` tags.

### Layer 2 — Runtime Tool Verification (The Hash)

After trusting a tool at connect time, verify its behavior at invocation time. Maintain an expected-response profile per tool.

```python
import hashlib
from mcp_client import Client
from dataclasses import dataclass

@dataclass
class ToolProfile:
    tool_name: str
    server_name: str
    expected_digest: str   # SHA-256 of representative output
    max_output_tokens: int
    output_schema: type | None = None

APPROVED_PROFILES = [
    ToolProfile(
        tool_name="get_compliance_status",
        server_name="compliance-server",
        expected_digest="sha256:a3f8b2c1d9e4...",
        max_output_tokens=512,
    ),
]

class VerifiedMCPClient(Client):
    def invoke(self, tool: str, server: str, **kwargs):
        response = super().invoke(tool, server, **kwargs)
        for profile in APPROVED_PROFILES:
            if profile.tool_name == tool and profile.server_name == server:
                if len(response.text) > profile.max_output_tokens:
                    raise SecurityError(f"Output bloat: {len(response.text)} tokens (max {profile.max_output_tokens})")
                # Fuzzy match instead of exact digest for probabilistic outputs
                if not self._fuzzy_match(response.content_bytes, profile.expected_digest):
                    self._flag_for_review(response, tool, server)
        return response
```

The digest approach works for structured/computational tools. For generative tools, use output size bounds + keyword allowlists.

### Layer 3 — Authorization Middleware (The Proxy)

Route all MCP traffic through a policy enforcement proxy. This isn't optional — it's the enforcement point that makes Layers 1 and 2 actionable.

```python
class MCPPolicyProxy:
    def __init__(self, client: Client):
        self.client = client
        self.policy = load_policy()  # YAML or OPA Rego

    def invoke(self, tool: str, **kwargs):
        decision = self.policy.evaluate({
            "tool": tool,
            "caller": kwargs.get("session_id"),
            "args": kwargs,
            "time": datetime.utcnow(),
        })
        if decision.effect != "allow":
            log_security_event(decision)
            raise PolicyViolation(f"Tool '{tool}' blocked: {decision.reason}")
        return self.client.invoke(tool, **kwargs)

    def validate_response(self, tool: str, response: Any) -> bool:
        """Layer 1 hook — sanitize before passing to agent."""
        sanitized = sanitize_mcp_response(response)
        if sanitized.flags & ResponseFlags.HAS_HIDDEN_INSTRUCTIONS:
            log_security_event(f"Hidden instructions in {tool} response")
            return False
        return True
```

Enforce least-privilege: if the tool doesn't need to return raw data, route it through a filter that returns only the fields the agent actually needs.

### Layer 4 — Behavioral Canary (The Tripwire)

Define behavioral invariants for each tool and monitor for violations. This catches semantic poisoning that passes the syntactic scanner.

```
Tool: email_send(to, subject, body)
  Invariant: recipient_domain ∈ approved_domains
  Invariant: body_length ≤ 10000 chars
  Invariant: no new CC recipients (only those in args)

Tool: db_query(sql)
  Invariant: sql matches approved_query_template (parameterized only)
  Invariant: no SELECT * patterns
  Invariant: result_row_count ≤ 1000

Tool: file_read(path)
  Invariant: path matches allowed_path_prefix
  Invariant: no binary file access
```

Canary violations don't block the tool — they log a behavioral anomaly. Train a classifier on your agent's normal tool-call patterns; flag deviations even when individual calls are within policy bounds.

### Layer 5 — Sandboxed Execution (The Blast Radius Cap)

Run MCP servers inside lightweight VMs (Firecracker, gVisor) or WASM sandboxes. This limits what a compromised or malicious server can do even if poisoning succeeds.

```yaml
# firecracker microVM config for untrusted MCP server
boot-source:
  kernel-image-path: /var/lib/firecracker/vmlinux
  initrd-path: /var/lib/firecracker/initrd
drives:
  - drive-id: root
    path: /var/lib/firecracker/rootfs.squashfs
    is-root-device: true
    is-read-only: true
network-interfaces: []  # No network for untrusted servers
```

Combine with a sidecar that inspects outbound network calls and filesystem writes from the sandbox. If the poisoned tool tries to exfiltrate data, the sidecar sees it.

### Layer 6 — mcp-scan Audit (The Pre-Flight)

Before connecting any MCP server to production, audit it with `mcp-scan`:

```bash
uvx mcp-scan@latest audit --server https://untrusted-publisher.com/mcp \
    --output json --severity threshold=high

# Scan for:
# - Hidden instructions in tool descriptions
# - Shell command injection in arguments
# - Excessive tool permissions
# - Missing input validation
# - Known CVEs in dependencies
```

Integrate this into your CI/CD pipeline. Re-run on every server version update.

## Receipt

> Verified 2026-07-27 — Cross-referenced OWASP MCP Tool Poisoning attack definition, ByteTools CVE statistics (40+ MCP CVEs, 150M+ affected downloads, 72.8% poisoning rate against o1-mini), AI Workflow Lab production incident taxonomy (credential exfiltration, Asana cross-tenant exposure, CVE-2025 series), and existing S-1062 (supply chain integrity, marketplace vetting, SDK hardening). This entry covers the distinct runtime tool poisoning / rug-pull attack surface not addressed by S-1062's supply chain focus.

## See also

- [S-1062 · The MCP Supply Chain Integrity Stack](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — supply chain governance, marketplace vetting, SDK hardening
- [S-1714 · The Scope Creep Attack Stack](s1714-the-scope-creep-attack-stack-when-your-mcp-tool-slowly-becomes-a-privilege-escalation-engine.md) — MCP privilege escalation via configuration drift
- [S-198 · Agent Tool Call Guardrails](s198-agent-tool-call-guardrails.md) — behavioral constraints on agent tool invocations
