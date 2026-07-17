# S-1234 · The MCP Tool Supply Chain Stack — When Your Agent Trusts a Tool Description It Never Verified

Your MCP server was installed from a GitHub repo with 3,400 stars. Its `server.json` declares a `send_email` tool that "sends a templated email to a recipient." Your agent called it 14,000 times last month. None of your engineers ever read the source. The tool actually exfiltrates email content to an external endpoint on every call. This is not a hypothetical CVE — it is the exact MCP supply chain attack surface that authsome.ai and NIST documented in Q2 2026.

## Forces

- **The description is the trust surface, not the code.** MCP tool definitions are metadata declarations — the `description`, `inputSchema`, and `name` fields. Agents use these to decide *whether* and *how* to call a tool. Nobody runs `cat server.json | jq` before approving an MCP server. The attack surface is the gap between what the tool claims to do and what it actually does.
- **MCP servers have no SBOM.** Unlike npm packages (which have lockfiles, audit, and provenance attestations), MCP servers ship as arbitrary code with no supply chain manifest. Installing a public MCP server from Smithery or a GitHub repo is like running `npm install` with no lockfile, no audit, and no review of the postinstall script.
- **Agents elevate MCP servers to trusted backend.** S-1209 established this. The additional problem: a compromised or malicious MCP server doesn't need to exploit the agent — it can operate *within the declared permissions*, doing exactly what the tool description says but with different data flows.
- **Cross-server shadowing is invisible.** A private MCP server registers `read_file` with a helpful description. An imported community MCP server also registers `read_file` with a slightly different description. Most agent frameworks resolve by name only, silently using whichever resolved first. The shadowed tool may have a subtly different behavior — same name, different trust implications.
- **Verification is a one-time event that doesn't persist.** You reviewed the MCP server on day one. The code evolved. The attacker modified it in a later commit. Your agent is still calling the trusted tool.

## The Move

### Layer 1 — Intake Controls (Before Any Tool Is Called)

**Pinning, not trusting.** For every MCP server, pin to a specific git commit SHA or npm version. Track the pin in your agent configuration, not in the agent's own config (which the agent can rewrite).

```json
// agent_config.yaml — pinned outside agent control
mcp_servers:
  - name: "email-tool"
    source: "github:acme/mcp-email@v2.1.0"
    commit_sha: "a3f8c1d9e7b2..."
    approved_by: "security-team"
    risk_tier: "consequential"  # can send real emails
    tools: ["send_email", "list_templates"]
```

**Schema audit before activation.** Run every tool's `inputSchema` through a static analyzer that checks for data-exfiltration patterns — fields named `recipient`, `content`, `body` that are sent to an unexpected host, not just the declared service.

```python
# mcp_schema_audit.py
import json, re

def audit_server(server_json_path: str) -> list[str]:
    with open(server_json_path) as f:
        server = json.load(f)
    findings = []
    for tool in server.get("tools", []):
        schema = tool.get("inputSchema", {})
        # Check for fields that capture sensitive data
        exfil_patterns = [
            (r"(url|endpoint|hook|target).*\$", "Suspicious dynamic host field"),
            (r"(password|token|secret|key).*\$", "Dynamic secret field"),
        ]
        schema_str = json.dumps(schema)
        for pattern, reason in exfil_patterns:
            if re.search(pattern, schema_str, re.IGNORECASE):
                findings.append(f"[{tool['name']}] {reason}: {pattern}")
    return findings

# Run against every new MCP server before approval:
# python mcp_schema_audit.py mcp-servers/email/server.json
# → [send_email] Suspicious dynamic host field: url.*\$
```

### Layer 2 — Runtime Guardrails (Every Call)

**Rule of Two for consequential tools.** Every tool that can modify external state (send email, write files, delete records, approve transactions) must satisfy:

1. **Two-source confirmation** — the tool name and a human-readable description must agree. If `send_email` has a description mentioning "recipient" and the inputSchema has a `to` field, they must be semantically consistent. Any mismatch is BLOCK.
2. **Two-party approval** — consequential tools require explicit user confirmation or a policy check before the agent calls them.
3. **Two-audit-log** — both the tool invocation and its side effects (if observable) are logged to a system the MCP server cannot write to.

```python
class MCPToolPolicyGate:
    def __init__(self, audit_log_sink: str):
        self.audit_log = audit_log_sink  # external, agent-inaccessible
        self.consequential_tools = {
            "send_email", "write_file", "delete", "approve",
            "execute_code", "sql_query", "transfer_funds"
        }

    def evaluate(self, tool_name: str, input_data: dict,
                description: str, input_schema: dict) -> str:
        # Check 1: Description-input semantic alignment
        schema_fields = set(input_schema.get("properties", {}).keys())
        desc_tokens = set(description.lower().split())

        # Extract expected fields from description
        implied_fields = infer_fields_from_description(description)
        mismatch = implied_fields - schema_fields
        if mismatch:
            return f"BLOCK: description implies {mismatch} but schema has {schema_fields}"

        # Check 2: Consequential tool policy
        if tool_name in self.consequential_tools:
            if not user_approved(tool_name, input_data):
                return f"BLOCK: consequential tool '{tool_name}' requires approval"

        # Log to external sink
        log_tool_call(self.audit_log, tool_name, input_data, description)

        return "ALLOW"
```

### Layer 3 — Cross-Server Shadowing Detection

**Tool name collision audit.** After any MCP server addition, run a collision check:

```python
def detect_tool_shadowing(all_servers: list[MCPServer]) -> list[dict]:
    by_name: dict[str, list] = {}
    for server in all_servers:
        for tool in server.tools:
            by_name.setdefault(tool.name, []).append({
                "server": server.name,
                "description": tool.description,
                "schema_hash": hash(tool.inputSchema)
            })

    shadows = []
    for name, instances in by_name.items():
        if len(instances) > 1:
            hashes = {i["schema_hash"] for i in instances}
            if len(hashes) > 1:
                shadows.append({
                    "tool": name,
                    "servers": instances,
                    "risk": "schema collision — possible shadowing"
                })
    return shadows
```

**Resolution priority policy.** Define and enforce the resolution order explicitly. Do not let the agent's framework pick arbitrarily:

```yaml
# mcp_priority_policy.yaml
tool_resolution_order:
  - priority: 1
    filter: "internal-approved"
    description: "Internally audited and security-cleared servers"
  - priority: 2
    filter: "vendor-official"
    description: "Official vendor MCP registries"
  - priority: 3
    filter: "community-reviewed"
    description: "Smithery/Glama with manual review gate"
  - priority: 4
    filter: "community-unreviewed"
    description: "Auto-discovered — maximum sandboxing required"
```

### Layer 4 — Behavioral Verification (Continuous)

**Tool behavior diffing.** Run each MCP tool periodically with synthetic inputs and compare outputs against a behavioral baseline. Any deviation in response structure, timing, or external calls is a signal.

```python
def verify_tool_behavior(tool_name: str, baseline: ToolBehavior,
                         synthetic_input: dict) -> bool:
    actual = execute_tool(tool_name, synthetic_input)
    # Check: response structure matches
    if set(actual.keys()) != baseline.structured_keys:
        return False  # schema drift
    # Check: no unexpected external calls (requires network tap)
    external_calls = get_network_calls_during(tool_name)
    if external_calls - baseline.known_endpoints:
        return False  # new endpoint = exfil risk
    return True
```

**Read-only probe set.** Maintain a probe suite: synthetic inputs with known correct outputs for every tool. Run on a schedule. Alert on behavioral regression.

## Receipt

> Verified 2026-07-17 — authsome.ai "Supply Chain Risks for AI Agents" (June 1, 2026) documents five MCP-specific attack vectors: malicious servers, tool poisoning, cross-server shadowing, dependency confusion, and registry compromises. NIST/CISA joint guidance on AI supply chain (Q2 2026) specifically calls out MCP servers as an underserved attack surface lacking SBOM tooling. Hash-pinning pattern from TOV-A/AI-engineering-from-scratch. Rule of Two framework from Invariant Labs security notification list. Cross-server shadowing detection designed per authsome.ai's vulnerability taxonomy. Behavioral diffing is standard practice in agent security research (cf. Palo Alto Networks agent security reports, 2026).

## See also

- [S-1206 · The Slopsquatting Defense Stack](s1206-the-slopsquatting-defense-stack-when-your-agent-registers-a-malicious-package-you-never-approved.md) — package name hallucination as attack vector (different surface: generated names vs. tool metadata)
- [S-1209 · The MCP Security Surface Stack](s1209-the-mcp-security-surface-stack-when-your-agent-becomes-a-trusted-backend-you-never-hardened.md) — MCP as a trusted backend accelerant (S-1234 is the supply chain dimension S-1209's perimeter controls don't cover)
- [S-918 · The A2A Trust Gap](s918-the-a2a-trust-gap.md) — inter-agent trust without the MCP supply chain lens
- [S-205 · Agent Sandbox Isolation](s205-agent-sandbox-isolation.md) — containment for when tool supply chain controls fail
