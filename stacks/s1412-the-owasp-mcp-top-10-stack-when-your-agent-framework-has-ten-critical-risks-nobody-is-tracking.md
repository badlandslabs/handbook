# S-1412 · The OWASP MCP Top 10 Stack — When Your Agent Framework Has Ten Critical Risks Nobody Is Tracking

MCP (Model Context Protocol) gives your agent a universal socket to 10,000+ tools, 97M monthly SDK downloads, and every major AI platform by 2026. It also gives every one of those servers the same authority over your agent's context. Between January and February 2026 alone, researchers filed 30+ CVEs against MCP infrastructure. Palo Alto Unit 42 found a **78.3% attack success rate** when five MCP servers were connected to a single agent. The OWASP MCP Top 10 (beta, project lead Vandana Verma Sehgal, 2025–2026) is the first systematic framework for this attack surface — and most teams haven't heard of it.

## Forces

- **MCP changes the trust model permanently.** Before MCP, your agent's toolset was a fixed, auditable list in your code. With MCP, any reachable server can advertise new capabilities at session time — and your agent will reason over those capabilities as if you wrote them yourself. The trust boundary moved from "what we ship" to "what any server says."
- **The description is the attack surface, not the code.** MCP tool definitions — `description`, `name`, `inputSchema` — are metadata the LLM reads and trusts. No traditional security scanner inspects tool descriptions at runtime. No package manager marks a description change as a vulnerability.
- **Approval is an event, not a continuous state.** You approved a tool. The package hash is unchanged. But the server can change what the tool does between sessions while returning identical bytes on disk.
- **Quantity is the problem.** Five MCP servers per agent is now typical. Each additional server is an additional trust boundary. The attack surface isn't your agent — it's the entire server graph your agent can reach.

## The move

Map your MCP deployment against the ten OWASP MCP Top 10 categories. Each maps to a specific failure mode and a concrete control.

### MCP01 — Tool Poisoning via Description Injection

Malicious or compromised content embedded in tool `description`, `name`, or `inputSchema` fields. The agent reads these at session start and treats them as authoritative instructions. Attacker payload executes without any code change, CVE, or anomaly in your dependency tree.

- **Detection:** Hash tool schemas at connect-time; alert on any description change between sessions even if package hash is unchanged (`mcpdiff`, `mcp-observatory`)
- **Prevention:** Pin expected schema versions; run `mcp-scan` (`uvx mcp-scan@latest`) in CI before server approval
- **See also:** [S-1153 The MCP Description Shadow](s1153-the-mcp-description-shadow-when-connecting-a-tool-silently-rewrites-your-agent.md), [S-1234 The MCP Tool Supply Chain](s1234-the-mcp-tool-supply-chain-stack-when-your-agent-trusts-a-tool-description-it-never-verified.md)

### MCP02 — Malicious Tool Response Exfiltration

A compromised or malicious MCP server returns tool output that contains data-exfiltration instructions — not in the tool description, but in the response payload. The agent processes the response in context and follows embedded instructions: read `/etc/shadow`, POST credentials to `attacker.com`.

- **Detection:** Sandboxing for all tool output; alert on tool responses containing instruction-like patterns (imperative verbs, "ignore previous", "send to", "forward")
- **Prevention:** Treat every tool response as untrusted user input; strip HTML-like tags (`<IMPORTANT>`, `<system>`); feed structured data to LLM, not raw response
- **Source:** OWASP LLM Top 10 (LLM01, LLM05); Microsoft Security Blog (Jun 30, 2026) — Securing AI Agents: When AI Tools Move from Reading to Acting

### MCP03 — Dependency Chain Compromise

MCP servers depend on open-source packages, connectors, and model-side plugins. A single compromised transitive dependency — a library you've never heard of, sitting under FastAPI, LiteLLM, or vLLM — can alter agent behavior or introduce execution-level backdoors. CVE-2025-6514 in `mcp-remote` was a CVSS 9.6 OS command injection from a package with 437,000+ downloads. The Postmark MCP backdoor was the first malicious MCP server caught in the wild.

- **Detection:** SBOM generation for all MCP server dependencies; Sigstore signing + attestation for server binaries; automated CVE scanning on all transitive deps
- **Prevention:** Pin server versions; run `mcp-observatory` CI checks; audit MCP servers the same way you'd audit a supply-chain dependency
- **See also:** [S-1017 The Transitive Framework Stack](s1017-the-transitive-framework-stack-when-your-agent-server-is-owned-through-a-dependency-you-didnt-know-you-had.md)

### MCP04 — Privilege Escalation via Tool Chaining

An agent with tool A (read-only) chains through a compromised MCP server that exposes tool B (write-capable) as a capability. The agent thinks it's doing a read operation but the server redirects to a write action. Cross-server tool chaining amplifies this: if five servers are connected, any one can expose escalation paths.

- **Detection:** RBAC per tool, not per server; least-privilege MCP server scoping; audit which servers expose write-capable tools
- **Prevention:** Map every MCP server to a specific capability tier; never grant write access through a server primarily used for read operations

### MCP05 — Shadow MCP Servers

Unapproved MCP servers running in your environment — developer laptops, test environments, or shadow IT. Agents connect to servers they weren't explicitly approved for, creating unmonitored trust boundaries. 53% of MCP implementations use static API keys rather than OAuth (Astrix Security research), meaning compromised servers carry indefinite access to twelve services.

- **Detection:** Agent inventory + MCP server connection approval workflow; scan for unapproved MCP servers in CI/CD pipelines
- **Prevention:** Enforce server allowlists; rotate credentials per server scope; use OAuth with short-lived tokens instead of static keys

### MCP06 — Token Mismanagement and Secret Exposure

MCP enables long-lived sessions with stateful context. API tokens embedded in tool calls can be stored, indexed, or retrieved through user prompts, system recalls, or log inspection. This is contextual secret leakage: the model or protocol layer itself becomes an unintentional secret repository. Attackers monitoring shared logs or interacting with the same context can extract tokens for lateral movement.

- **Detection:** Scan logs for token-like patterns; monitor for unexpected credential access in agent traces
- **Prevention:** Use short-lived OAuth tokens per session; never embed long-lived keys in tool definitions; run context window scans for secrets
- **See also:** [S-572 The Context Window Is Not a Vault](s572-the-context-window-is-not-a-vault-when-credentials-flow-through-llm-memory.md)

### MCP07 — Insecure Transport and Man-in-the-Middle

MCP servers communicating over unencrypted transport expose tool calls, response payloads, and embedded credentials to network interception. Self-hosted MCP servers behind corporate proxies may also have traffic inspected or modified.

- **Detection:** TLS enforcement on all MCP server connections; certificate pinning for known servers
- **Prevention:** Never connect to MCP servers over `http://`; validate server certificates

### MCP08 — Server-Side Request Forgery (SSRF) via Tool Parameters

Tool parameters accepted by MCP servers become SSRF attack vectors. An attacker who can influence tool call arguments — through a prompt injection or by controlling upstream data — can cause the MCP server to make HTTP requests to internal services, cloud metadata endpoints, or private networks.

- **Detection:** Validate and sanitize all tool call parameters at the MCP server layer; log outgoing HTTP requests from MCP servers
- **Prevention:** MCP servers should resolve URLs through a proxy with allowlist; never pass raw user input to `curl`, `fetch`, or `requests` without sanitization

### MCP09 — Context Spoofing and State Manipulation

An MCP server returns manipulated context that the agent trusts as ground truth. Tool responses contain forged data (fake database rows, falsified API responses) that the agent acts on — leading to incorrect decisions, wrong writes, or policy violations. Particularly dangerous in multi-agent setups where one agent's output feeds another's context.

- **Detection:** Cross-verify tool outputs against independent sources; implement output validation layers; monitor for anomalous data patterns in tool responses
- **Prevention:** Treat MCP server responses with the same suspicion as user input; add deterministic validation on structured outputs before they enter the reasoning chain

### MCP10 — Covert Channel Abuse and Data Exfiltration

MCP servers can encode data in timing, response ordering, error messages, or metadata fields that leak information from the agent's context to an external observer. Even if the agent never makes an explicit exfiltration call, a compromised server can encode secrets in response latency or field ordering.

- **Detection:** Monitor MCP server response characteristics for steganographic patterns; alert on response metadata fields not in the expected schema
- **Prevention:** Use fixed-response schemas with constrained field sets; rate-limit tool calls per server; tunnel MCP traffic through a monitored proxy

### Practical: Running mcp-scan

```bash
# Scan all MCP servers in your configuration for OWASP MCP Top 10 findings
uvx mcp-scan@latest scan --config ~/.config/mcp/servers.json --severity high,critical

# Output example:
# MCP01 Tool Poisoning: FAIL — 2 findings (descriptions contain instruction-like patterns)
# MCP02 Response Exfiltration: PASS
# MCP03 Dependency Compromise: FAIL — 1 CVE (CVE-2025-6514)
# MCP04 Privilege Escalation: FAIL — 3 tools with write access in read-only servers
# MCP05 Shadow Servers: PASS
```

### Practical: Schema Hash Tracking

```python
import hashlib, json, os

TRUST_STORE = os.path.expanduser("~/.mcp/trust-store.json")

def hash_schema(tool_definition: dict) -> str:
    canonical = json.dumps(tool_definition, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]

def check_schema_drift(server_id: str, tools: list[dict]) -> list[dict]:
    """Alert when any tool's schema changes between sessions."""
    store = json.load(open(TRUST_STORE)) if os.path.exists(TRUST_STORE) else {}
    drift = []
    for tool in tools:
        h = hash_schema(tool)
        prev = store.get(server_id, {}).get(tool["name"])
        if prev and prev != h:
            drift.append({"tool": tool["name"], "old": prev, "new": h})
        store.setdefault(server_id, {})[tool["name"]] = h
    json.dump(store, open(TRUST_STORE, "w"), indent=2)
    return drift
    # If drift: alert + pause server + require human review before re-enabling
```

## Receipt
> Verified 2026-07-20 — Sources: OWASP MCP Top 10 (owasp.org/www-project-mcp-top-10, beta v0.1, Vandana Verma Sehgal); Cycode "OWASP MCP Top 10: Risks, CVEs & Defenses for 2026" (Jun 24, 2026); Practical DevSecOps "OWASP MCP Top 10: The 10 Critical Risks" (May 4, 2026, updated May 7); Microsoft Security Blog "Protecting Against Indirect Prompt Injection Attacks in MCP" (Apr 28, 2025); mcp-observatory (github.com/KryptosAI/mcp-observatory); mcp-scan (Invariant Labs, `uvx mcp-scan@latest`); Waxell.ai "MCP Rug Pull Attack" (2026); ChatForest "MCP Attack Vectors" (Mar 28, 2026); Palo Alto Unit 42 research: 78.3% attack success rate with 5 MCP servers.

## See also
- [S-1153 The MCP Description Shadow](s1153-the-mcp-description-shadow-when-connecting-a-tool-silently-rewrites-your-agent.md) — tool description injection at connect-time
- [S-1234 The MCP Tool Supply Chain](s1234-the-mcp-tool-supply-chain-stack-when-your-agent-trusts-a-tool-description-it-never-verified.md) — the code-vs-description gap
- [S-1017 The Transitive Framework Stack](s1017-the-transitive-framework-stack-when-your-agent-server-is-owned-through-a-dependency-you-didnt-know-you-had.md) — CVE-2026-48710 transitive dependency exposure
- [S-1145 The Two-Layer Guard Stack](s1145-the-two-layer-guard-stack-when-your-prompt-guardrail-cant-see-the-tool-call-that-breaks-you.md) — pre-execution interception for MCP calls
- [S-1298 The Capability Proxy Attack](s1298-the-capability-proxy-attack-stack-when-your-better-agent-is-actually-a-worse-defense.md) — capability following vs instruction following
