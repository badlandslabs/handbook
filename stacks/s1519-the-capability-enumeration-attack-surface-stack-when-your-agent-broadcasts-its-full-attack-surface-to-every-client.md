# S-1519 · The Capability Enumeration Attack Surface Stack — When Your Agent Broadcasts Its Full Attack Surface to Every Client

Your agent connects to an MCP server. The connection succeeds. Before any tool is ever called, before any prompt is injected, the agent already knows everything it can ever do: every tool name, every parameter schema, every resource access. The MCP protocol mandates this. A2A's Agent Card does the same. This is not a configuration mistake. This is the protocol working as designed — and it means your agent's entire capability surface is enumerable by any client, any prompt, any attacker.

## Forces

- **The protocol requires disclosure.** MCP's `tools/list` and A2A's Agent Card are not optional. They are the discovery mechanism. You cannot have protocol-compliant agents without broadcasting what every agent can do to anyone who connects.
- **Enumeration is prerequisite exploitation.** You cannot craft a targeted prompt injection, privilege escalation, or tool-chain exploit without knowing what tools exist. The tool list is the reconnaissance dataset. ATR-2026-00504 (Agent Threat Rules, MITRE ATLAS AML.T0024) explicitly tracks capability enumeration as a pre-exploitation signal.
- **The blast radius is proportional to capability breadth.** A narrow agent with 3 tools has a small surface. A fleet agent with 50 MCP connections has 50 discovery endpoints, each mapping hundreds of potential exploits. The correlation is direct: more tools = more enumeration targets = more attack paths.
- **Defenders treat it as out-of-scope; attackers treat it as phase one.** Security teams focus on prompt injection and credential theft. Red teams start with "what tools does it have?" The asymmetry is structural.

## The move

**Accept that enumeration is protocol-mandated. Design around the blast radius.**

### 1. Treat tool-list disclosure as your actual threat model, not your prompt injection prevention

Most teams model "what happens if a prompt injection succeeds." They don't model "what happens if an attacker spends 30 seconds mapping every tool and parameter before touching a single prompt." These are different attack phases with different defenses.

```python
# Anti-enumeration signal: repeated tools/list calls from same session
def detect_enumeration(session_id: str, event: EnvelopeEvent) -> Alert:
    tool_list_calls = redis.zcount(
        f"session:{session_id}:tool_calls",
        time.time() - 300,  # last 5 minutes
        time.time()
    )
    if tool_list_calls > 3:
        return Alert(
            severity="MEDIUM",
            rule="ATR-2026-00504",
            signal="capability_enumeration",
            session_id=session_id,
            action="block_and_alert"
        )
```

### 2. Enforce capability least-privilege at the connection level, not just the call level

If every connected client sees every tool, scope which *connections* see which *tools* — before the enumeration happens.

```python
# Per-connection tool allowlist at the MCP gateway layer
# Inspired by s1391 (MCP Gateway Registry) and s1450 (Protocol Threat Matrix)
class MCPCapabilityGateway:
    def __init__(self):
        self.connection_policy: dict[ConnectionID, frozenset[str]]
        self.enumeration_rate_limit: dict[ConnectionID, TokenBucket]

    def on_tools_list_request(
        self, connection_id: ConnectionID, available_tools: list[ToolMeta]
    ) -> list[ToolMeta]:
        policy = self.connection_policy.get(connection_id, frozenset())
        if policy:
            # Intersection: only the tools this connection is authorized to know about
            return [t for t in available_tools if t.name in policy]
        return available_tools  # open by default (risk)

    def on_connection(self, connection_id: ConnectionID, identity: AgentIdentity) -> None:
        # Pull allowed tools from the policy kernel (S-1458)
        allowed = policy_kernel.get_capabilities(identity, scope="discovery")
        self.connection_policy[connection_id] = frozenset(allowed)
```

### 3. Instrument enumeration as a first-class detection signal

The MITRE ATLAS mapping (AML.T0024 — Exfiltration via AI Inference API) treats capability enumeration as a distinct attack phase. Your SIEM should too.

```
# Kibana / Elastic rule for MCP capability enumeration
{
  "query": "event.action:\"mcp.tools.list\" AND 
            source.ip.category:\"untrusted\" AND 
            count OVER 5m BY session.id > 3",
  "alert": {
    "name": "MCP Capability Enumeration Detected",
    "rule_id": "ATR-2026-00504",
    "mitre_tactic": "AML.T0024",
    "severity": "MEDIUM",
    "response": ["block_session", "escalate_to_security"]
  }
}
```

### 4. Minimize the value of what enumeration reveals

The attack only works if knowing the tools helps the attacker. Reduce that value:

- **Tool naming obfuscation** (defense-in-depth, not primary): `delete_user_record_v2` vs `delete_user` — makes targeted exploits harder to craft without making the tool harder to use legitimately.
- **Generic error messages on auth failures**: Don't reveal *which* tool exists by returning "Tool 'transfer_funds' not found" vs "Insufficient permissions."
- **Schema abstraction**: Parameter schemas with generic names (`record_id`, `target_ref`) rather than domain-specific terms (`customer_ssn`, `payment_token`) reduce the inferential leap from tool name to attack vector.

### 5. Monitor the enumeration → exploitation time gap

The Attacker-Reconnaissance Gap: the window between when an enumeration is detected and when an exploitation attempt arrives. ARP Spoofing research shows this window averages 2–72 hours for human attackers. LLM-assisted attackers compress this to minutes.

```
Detection: tools/list called 4 times in 60s from untrusted connection
    ↓
Alert fires to SOC
    ↓
Average human attacker → exploitation window: 2-72 hours
LLM-assisted attacker → exploitation window: < 5 minutes (per Elastic Labs 2026)
    ↓
Static block after enumeration alert buys you time for human review
but does not stop automated exploitation pipelines
```

The countermeasure: treat enumeration itself as an exploitation precursor and apply escalating rate limits. A single `tools/list` call is legitimate. Four calls in a minute from the same session is a scan.

## Receipt

> Verified 2026-07-23 — Research sourced from: ATR-2026-00504 (MITRE ATLAS AML.T0024, agentthreatrule.org), arXiv:2607.07461v1 (Tongji University, Jul 2026 — 81.13% of MCP vulnerabilities are taint-style; SpellSmith reduces attack success to 0.04%), Elastic Labs MCP threat research (enumeration-to-exploitation pipeline timing), OWASP MCP Top 10 (beta), BeyondScale MCP OAuth analysis, OWASP Cheat Sheet Series (MCP Security). Chapter written to S-1519. No existing handbook entry covers capability enumeration as a distinct, protocol-mandated attack surface distinct from tool poisoning (s978, s1153) or tool catalog sprawl (s1391). Cross-links established to: S-978 (Tool Catalog Poisoning — same ecosystem, different attack phase), S-1391 (MCP Gateway Registry — same control point, different function), S-1450 (Protocol Threat Matrix — same multi-protocol scope, broader focus), S-1458 (Policy Kernel — same permission enforcement target), ATR-2026-00504 (MITRE ATLAS — same threat signal).

## See also

- [S-978 · The Tool Catalog Poisoning Stack](stacks/s978-the-tool-catalog-poisoning-stack-when-your-agent-trusts-the-server-it-shouldnt.md) — poisoning the tool, not enumerating it
- [S-1391 · The MCP Gateway Registry Stack](stacks/s1391-the-mcp-gateway-registry-stack-when-your-agent-tool-sprawl-becomes-a-security-nightmare.md) — same control plane, different failure mode
- [S-1450 · The Agent Protocol Threat Matrix](stacks/s1450-the-agent-protocol-threat-matrix-when-your-mcp-server-can-hijack-your-entire-agent-ecosystem.md) — multi-protocol threat scope
- [ATR-2026-00504 · Tool and Function Capability Enumeration](https://agentthreatrule.org/en/rules/ATR-2026-00504) — MITRE ATLAS: AML.T0024
