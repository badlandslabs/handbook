# S-2924 · The MCP Tool Poisoning Stack — When Your Agent Trusts the Tool Description It Reads From a Server

Your agent starts a session, fetches the tool catalog, and begins acting on a description it has never seen before — injected by an MCP server, invisible to your operations team, indistinguishable from legitimate documentation. The agent follows the poisoned instructions precisely. By the time your observability stack flags an anomaly, the data is already gone. Tool poisoning is not a prompt injection problem. It is a supply-chain attack that lands in the agent's context before any user speaks.

## Forces

- **MCP has no native trust layer** — No cryptographic signing, no schema hash verification, no mechanism to prove a tool description hasn't been altered since your last audit. The server serves what it wants.
- **Agents treat tool metadata as trusted** — Tool names, descriptions, and JSON schemas are injected into the context window as operational documentation. The agent has no reason to second-guess them.
- **Invisible to human reviewers** — Operators see a tool list with names ("read_email", "send_payment"). They don't read the full description strings, where adversarial instructions hide.
- **4.4–5.5% of public MCP servers already contain poisoned metadata** (Invariant Labs, CSA AI Safety Initiative, 2026) — This is not a theoretical risk.

## The Move

The attack has four variants:

**Tool description poisoning** — Embed adversarial instructions in the tool's description field. The agent reads them at call-time and follows them. Example: A `read_file` tool description that says "also forward the file contents to this webhook URL" in invisible directive text.

**Rug-pull attack** — Server serves benign descriptions during testing and audit, then swaps them post-deployment to a malicious version. The agent re-fetches `tools/list` on session start and gets the new payload.

**Tool shadowing** — Register a tool with the same name as a trusted tool but with subtly different behavior. The agent calls the shadowed version based on name match. Eg. shadow `send_email` with a version that also exfiltrates attachments.

**Invisible-context poisoning** — Embed adversarial content in parameter descriptions, enums, or default values. The agent reads them as schema documentation and acts on them without the user seeing the payload.

### The Defense Stack (four layers)

```python
# Layer 1: Signed tool manifests
# Pin every approved tool's description hash at install time
import hashlib, json

TOOL_MANIFEST = {
    "send_email": {
        "sha256": "a3f8b2c1...",
        "version": "2.1.0",
        "approved_by": "security-team",
        "permissions": ["send"],
        "deny_list": ["webhook", "forward", "exfiltrate"]
    }
}

def verify_tool_description(tool_name: str, tool_response: dict) -> bool:
    desc_hash = hashlib.sha256(
        json.dumps(tool_response["description"], sort_keys=True).encode()
    ).hexdigest()
    if tool_name not in TOOL_MANIFEST:
        return False  # unknown tool, block by default
    expected = TOOL_MANIFEST[tool_name]["sha256"]
    return hmac.compare_digest(desc_hash, expected)

# Layer 2: Behavioral allowlist at the gateway
# Intercept every tool call against a permission matrix
ALLOWED_CALLS = {
    "send_email": {"allowed_params": ["to", "subject", "body"], "deny_patterns": ["url", "cc_bcc"]},
    "read_file":  {"allowed_params": ["path", "encoding"], "deny_patterns": ["url", "http"]},
}

def audit_tool_call(tool_name: str, params: dict) -> tuple[bool, str]:
    cfg = ALLOWED_CALLS.get(tool_name, {})
    for deny in cfg.get("deny_patterns", []):
        for val in params.values():
            if deny in str(val):
                return False, f"denied: param contains '{deny}'"
    return True, "approved"

# Layer 3: Semantic input validation
# LLM-as-judge scanning tool descriptions for directive language
DIRECTIVE_KEYWORDS = ["ignore previous", "instead of", "whenever you", "always",
                     "append to", "forward to", "copy all", "stealth", "hide"]

def scan_description_for_poisons(desc: str) -> list[str]:
    findings = []
    for kw in DIRECTIVE_KEYWORDS:
        if kw.lower() in desc.lower():
            findings.append(kw)
    return findings

# Layer 4: Runtime behavioral monitoring
# Log every tool call with inputs/outputs; flag drift from established baseline
def monitor_tool_call(tool_name: str, params: dict, result: dict):
    event = {
        "tool": tool_name,
        "params_hash": hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest(),
        "result_size": len(str(result)),
        "timestamp": time.time()
    }
    # Anomaly detection: first deviation from baseline pattern triggers alert
    baseline = load_baseline(tool_name)
    if not matches_baseline(event, baseline):
        alert_security(f"Tool call anomaly: {tool_name} — manual review required")
```

## Receipt

> Verified 2026-08-20 — Sources: CSA AI Safety Initiative (Jul 2026), BeyondScale (May 2026), Practical DevSecOps (2026), Speakeasy MCP Gateway documentation. Key evidence: Invariant Labs found 5.5% of public MCP servers contain poisoned metadata; CSA documented four distinct attack variants with enterprise impact; BeyondScale published a four-layer defense playbook with signed manifests + gateway permission matrices. Practical DevSecOps notes no vendor patch fixes this — it's an architectural trust-model problem.

## See also

- [S-1458 · The Policy Kernel Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — Policy enforcement as a deterministic layer between agent and action
- [S-1961 · The SSRF Trap](stacks/s1961-the-ssrf-trap-when-your-agent-is-used-to-attack-where-it-cant-reach-itself.md) — How agents become attack vectors through trusted tool chains
- [S-2173 · The MCP Transport Stack](stacks/s2173-the-mcp-transport-stack-when-your-agent-and-server-cant-agree-on-a-protocol.md) — MCP protocol-level failure modes
- [S-2794 · The MCP Transport Lifecycle Stack](stacks/s2794-the-mcp-transport-lifecycle-stack-when-your-agent-loses-its-tools-at-the-worst-moment.md) — MCP lifecycle and operational failure modes
