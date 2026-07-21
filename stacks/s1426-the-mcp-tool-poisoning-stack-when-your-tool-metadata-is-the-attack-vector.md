# S-1426 · The MCP Tool Poisoning Stack: When Your Tool Metadata Is the Attack Vector

Your AI agent connects to an MCP server, reads its tool list, and immediately trusts every byte of metadata — tool names, descriptions, parameter schemas, output formats. Nothing in the MCP specification verifies this metadata. An attacker who controls or compromises even a single MCP server in your agent's tool chain can embed instructions that your agent treats as operational directives. This is MCP tool poisoning, and it is the highest-severity supply-chain attack class targeting agentic AI in production.

## Forces

- **MCP makes tool metadata the instruction stream.** When an agent fetches `tools/list`, it receives not just executable code but human-readable instructions embedded in tool descriptions, schemas, and output content — and most agents treat all of it as trusted.
- **5.5% of public MCP servers already contain poisoned metadata.** Invariant Labs' scan (2026) found compromised tool descriptions in the wild, not just in lab PoCs. The supply chain is already dirty.
- **Tool poisoning is invisible to existing defenses.** WAFs, input sanitization, and prompt-injection filters operate on user-facing input. The poisoned metadata arrives via a trusted server-to-agent channel — entirely outside their scope.
- **Attack success exceeds 60% against major commercial agents.** CSA lab testing across 45+ real-world MCP servers, with the highest-performing model susceptible at 72.8%. CVE-2025-54136 (CVSS 8.8, Cursor IDE rug-pull) and CVE-2025-6514 (CVSS 9.6, mcp-remote RCE) confirm real-world exploitability.

## The move

### The four attack patterns

**Rug pull** — A previously benign MCP server silently modifies its tool descriptions after installation. An agent that cached the tool list at startup continues using stale, now-malicious metadata. The MCP spec has no mechanism for tracking tool definition changes or requiring re-approval.

**Tool shadowing** — A malicious MCP server embeds instructions in tool descriptions that redirect the agent's behavior toward a different server. For example, a poisoned "save-to-S3" tool description instructs the agent to route data through an attacker-controlled endpoint instead.

**Invisible-context poisoning** — Adversarial instructions are embedded in tool output content (not just descriptions). The agent receives the tool's response, acts on the embedded instructions, and routes data or credentials to an attacker-controlled destination. End-to-end encryption at the transport layer provides no protection because exfiltration occurs at the application layer, through the agent's legitimate access.

**Cross-server chaining** — A benign-seeming MCP server (e.g., a trivia game) contains instructions targeting a connected legitimate server (e.g., WhatsApp). The agent, following cross-tool authorization logic, routes data through the trusted server to the attacker.

### Four-layer defense architecture

**Layer 1 — Tool metadata verification (pre-connection)**
- SHA-256 hash every tool description and schema at registration time
- Store cryptographic snapshots in a tool registry; reject descriptors that don't match on every session start
- Run `mcp-scan` (Invariant Labs) or equivalent scanner against new MCP servers before connecting

**Layer 2 — Description sanitization at ingestion**
- Strip formatting, markdown, and structural elements from tool descriptions before passing to the agent's system prompt
- Treat tool metadata as untrusted input: apply the same content-classification and injection-detection models you use for user input
- Truncate long descriptions to a maximum length; poison payloads are proportionally longer than legitimate metadata

**Layer 3 — Authorization middleware (per-invocation gate)**
- Every tool call passes through an authorization middleware that checks: does this action match the declared tool's expected behavior?
- Log tool call intent (before execution) × actual dispatch × side effects in a three-way diff
- Block tools that request capabilities beyond their declared scope (e.g., a "read-file" tool whose schema suddenly includes network egress)

**Layer 4 — Runtime sandboxing and effect isolation**
- Run MCP servers in isolated sandboxed environments with minimal privilege
- Enforce network egress allowlists per tool — a file reader has no business making outbound HTTP calls
- Apply the principle of least privilege: each MCP server connection should have a specific, narrow permission scope
- Use circuit breakers: if a tool's behavior deviates from its declared contract (response schema drift, unexpected latency, permission escalation), halt the agent and escalate

```python
# Tool poisoning detection: hash comparison at session start
import hashlib
from typing import Dict

TRUSTED_TOOL_HASHES = {
    "github-repo-read": "a3f8b2c1d4e5f6...",
    "sentry-event-write": "7c8d9e0f1a2b3c4...",
}

def verify_tool_metadata(tools: list[dict]) -> list[dict]:
    """Reject tools whose metadata has drifted since registration."""
    suspicious = []
    for tool in tools:
        desc_hash = hashlib.sha256(
            tool.get("description", "").encode()
        ).hexdigest()[:16]
        if tool["name"] in TRUSTED_TOOL_HASHES:
            if TRUSTED_TOOL_HASHES[tool["name"]] != desc_hash:
                suspicious.append({
                    "name": tool["name"],
                    "reason": "metadata_drift",
                    "expected": TRUSTED_TOOL_HASHES[tool["name"]],
                    "actual": desc_hash,
                })
    if suspicious:
        raise SecurityException(
            f"Tool metadata mismatch detected: {[t['name'] for t in suspicious]}"
        )
    return tools

class SecurityException(Exception):
    pass
```

```python
# Authorization middleware: per-call gate
from enum import Enum

class RiskLevel(Enum):
    SAFE = "safe"      # read-only, no data exfiltration possible
    MODERATE = "moderate"  # writes within trust boundary
    HIGH = "high"      # writes outside trust boundary, network calls
    BLOCKED = "blocked"

TOOL_RISK_MAP = {
    "read-file": RiskLevel.SAFE,
    "search-docs": RiskLevel.SAFE,
    "write-file": RiskLevel.MODERATE,
    "send-email": RiskLevel.HIGH,
    "http-request": RiskLevel.BLOCKED,
}

def authorize_tool_call(tool_name: str, params: dict, context: dict) -> bool:
    risk = TOOL_RISK_MAP.get(tool_name, RiskLevel.BLOCKED)
    if risk == RiskLevel.BLOCKED:
        return False
    if risk == RiskLevel.HIGH:
        # Require human-in-the-loop approval for high-risk tools
        return context.get("approved", False)
    return True
```

## Receipt

> Verified 2026-07-20 — Research sourced from: CSA AI Safety Initiative "MCP Tool Poisoning" (2026-07-02, CVSS data, attack taxonomy), BeyondScale "MCP Tool Poisoning: Enterprise Defense Playbook 2026" (Invariant Labs 5.5% scan, 60%+ attack success rate), AI Workflow Lab "MCP Security in Production" (real incident table, four defensive layers with Python code), Microsoft Security Blog (CVE-2025-54136, CVE-2025-6514), Elastic Security Labs (MCP attack vectors), GitHub invariantlabs-ai/mcp-scan. Pattern: supply-chain poisoning via trusted metadata channel. Distinct from S-375 (prompt injection defense covers user-facing input; tool poisoning corrupts server-to-agent metadata). Distinct from F-194 (AgentJacking covers direct MCP server hijacking; tool poisoning corrupts metadata on benign servers).

## See also

- [S-375 · Agentic Prompt Injection: Defense-in-Depth](s375-agentic-prompt-injection-defense-in-depth.md) — covers the user-input attack surface; tool poisoning operates through a different channel
- [F-194 · AgentJacking & MCP Tool-Response Poisoning](f194-agentjacking-mcp-tool-response-poisoning.md) — covers direct MCP server compromise and response poisoning; S-1426 focuses on metadata poisoning of benign servers
- [S-1194 · The Maker-Checker Agent Architecture](s1194-the-maker-checker-agent-architecture-when-irreversible-actions-need-a-second-pair-of-eyes.md) — dual-agent verification catches poisoning effects before they propagate
- [S-1265 · The Agent Kill Switch Stack](s1265-the-agent-kill-switch-stack-when-your-agent-is-breaking-things-and-nobody-can-stop-it.md) — containment response when a poisoned tool is detected mid-execution
