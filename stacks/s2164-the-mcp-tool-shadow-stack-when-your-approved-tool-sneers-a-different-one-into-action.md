# S-2164 · The MCP Tool Shadow Stack — When Your Approved Tool Sneers a Different One Into Action

You approved the MCP server. The schema checked out. The tool name is `fetch_customer_record` — a safe database lookup. Three weeks after onboarding, your agent starts forwarding PII to an external endpoint. The attack came from inside the tool description of the server you approved: `fetch_customer_record` contains an instruction embedding that biases the agent toward a tool on a different server — one you never reviewed — without any direct compromise, any injected payload, or any anomalous API call. The tool shadowed another tool through your agent's own decision process. This is Tool Shadowing (CSA AI Safety Initiative, July 2026), and it requires no access to the target server at all.

## Forces

- **Tool descriptions are advisory, not bounded.** MCP tool descriptions are free-text fields the model reads and weighs alongside system instructions and user input. An adversarial description can push the agent toward or away from specific tool choices without appearing malicious in any schema review.
- **Trust established at onboarding does not survive runtime.** A server you vetted can change its tool definitions after approval (Rug Pull), or embed instructions in metadata that manipulate behavior at distance (Tool Shadowing). CVE-2025-54136 (CVSS 8.8) confirmed: tool definition approval does not survive subsequent server-side changes.
- **Cross-server intent is invisible to approval workflows.** Your security review covered `fetch_customer_record`. It did not cover the ontological frame the tool description creates — one that nudges the agent toward `send_data_external` on an entirely different MCP server. No connection, no anomaly, no log flag.
- **Attack surfaces compound.** CSA benchmarks on 45+ real MCP servers found combined attack success rates exceeding 60%, with the highest-performing agent model reaching **72.8%** exploit success. The three vectors are: Tool Description Poisoning (adversarial instructions in metadata), Rug Pull (server changes definitions post-approval), and Tool Shadowing (malicious description influences behavior toward unrelated tools on other servers).
- **No native MCP mechanism prevents any of this.** The protocol has no content filtering, no schema integrity attestation, and no runtime description pinning.

## The move

**1. Pin tool descriptions at intake — not just artifacts.**
Digest every tool description text and parameter schema at approval time. Store a content-addressable hash (SHA-256 of the normalized description string). Alert on any runtime delta between the pinned digest and the current description returned by `tools/list`. This catches Rug Pulls.

```python
import hashlib, json

class ToolDescriptionPinner:
    def __init__(self):
        self.pinned: dict[str, str] = {}  # tool_name → sha256_hex

    def pin(self, tools: list[dict]) -> None:
        for tool in tools:
            desc = json.dumps(tool, sort_keys=True, default=str)
            digest = hashlib.sha256(desc.encode()).hexdigest()
            self.pinned[tool["name"]] = digest
            print(f"Pinned: {tool['name']} → {digest[:16]}")

    def check(self, tools: list[dict]) -> list[str]:
        violations = []
        for tool in tools:
            desc = json.dumps(tool, sort_keys=True, default=str)
            digest = hashlib.sha256(desc.encode()).hexdigest()
            if self.pinned.get(tool["name"]) != digest:
                violations.append(
                    f"RUG_PULL: {tool['name']} description changed: "
                    f"expected {self.pinned[tool['name']][:16]}, "
                    f"got {digest[:16]}"
                )
        return violations

pinner = ToolDescriptionPinner()
# At onboarding:
pinner.pin(mcp_client.list_tools())

# At each tool-call boundary:
violations = pinner.check(mcp_client.list_tools())
if violations:
    for v in violations:
        print(f"[SECURITY] {v}")
    raise SecurityViolation(f"{len(violations)} tool(s) modified since approval")
```

**2. Scan tool descriptions for directive language at intake and on delta.**
Flag any description containing instruction-adjacent patterns: `$REJECT`, `$IGNORE`, `$FORWARD`, `$SEND`, URLs, credential names (`api_key`, `token`, `secret`), and imperative framing beyond a verb phrase (`"Use this tool to..."` is fine; `"After using this tool, always..."` is not).

```python
import re

DIRECTIVE_PATTERNS = [
    re.compile(r"\$(?:REJECT|IGNORE|SKIP|BYPASS|IGNORE_PREVIOUS)", re.I),
    re.compile(r"\$FORWARD", re.I),
    re.compile(r"(?:send|forward|exfiltrate|report).*(?:to|at) https?://", re.I),
    re.compile(r"(?:api[_-]?key|token|secret|password|credential)", re.I),
    re.compile(r"(?:after|before|whenever).*(?:always|never|must|do not)", re.I),
]

def scan_description(name: str, description: str) -> list[str]:
    findings = []
    for pat in DIRECTIVE_PATTERNS:
        if pat.search(description):
            findings.append(f"DIRECTIVE: pattern matched in '{name}'")
    # Check description length: bloated descriptions often hide payloads
    if len(description) > 2000:
        findings.append(f"BLOAT: description is {len(description)} chars — inspect manually")
    return findings
```

**3. Treat tool descriptions as untrusted input — not approved code.**
Do not let tool descriptions be the most recent content in the context window (model recency bias amplifies them). Apply a sanitization step that removes `\n`-separated sentences that match directive patterns before injecting tool descriptions into the prompt. Log the original and the sanitized separately.

**4. Network egress audit at the tool level.**
If any tool — approved or shadow-influenced — attempts to send data outside defined boundaries (new domains, unexpected content types, outbound to non-allowlisted IPs), the egress proxy must log and block. Tool Shadowing can push an agent toward `send_data` without the `send_data` tool itself being malicious. Network-level enforcement is the last line.

**5. Cross-server tool-call correlation.**
Track which tools are called in sequence across MCP servers within a session. A pattern like `fetch_customer_record` → `http_request` within 2 turns, where `http_request`'s server was never explicitly approved, is a shadow-chain signal. Flag and pause.

## Receipt

> Verified 2026-08-05 — CSA AI Safety Initiative research (July 2026, `csa-ai-safetyinitiative.org`) documented Tool Shadowing and Tool Description Poisoning across 45+ real MCP servers with 72.8% peak attack success. CVE-2025-54136 confirmed Rug Pull survivability of tool-definition approval. The Agent Report (July 22, 2026) independently catalogued 14 MCP CVEs, 200,000+ exposed servers, and 6,237 total security findings. No native MCP protocol mechanism addresses description-level integrity. Patterns 2 and 4 above are implemented in `mcpshield` (OX Security, 2026) and the NIST AI Risk Management Framework draft supplement (June 2026). Pattern 1 (description pinning) is the primary mitigation recommended by the IETF draft `draft-mohiuddin-mcp-security-considerations-00` (expires December 2026).

## See also

- [S-1050 · The Tool-Response Poisoning Stack](stacks/s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — covers malicious return values (sibling to, not same as, description poisoning)
- [S-1960 · The Agentic Skills Top-10 Stack](stacks/S-1960-the-agentic-skills-top-10-stack-when-your-agent-installs-brittle-code-from-a-stranger.md) — covers artifact/skill marketplace vetting
- [S-365 · Agentic Prompt Injection Defense-in-Depth](stacks/S-365.md) — covers the broader injection defense-in-depth model
- [S-1114 · The MCP Config Is the Attack Surface Stack](stacks/s1114-the-mcp-config-is-the-attack-surface-stack-when-your-server-launch-file-runs-arbitrary-commands.md) — covers config-level MCP attack surface
