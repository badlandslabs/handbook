# S-1797 · The Shadow Agent Governance Stack — When 82% of Your Agents Exist Off the Radar

Your CISO asks for a list of all AI agents running in production. Your team returns 12. Your security scan finds 67. Three of them are wired to production databases. None of them have an audit trail. Two are running on personal accounts. You have four days until the EU AI Act's high-risk enforcement activates.

## Forces

- **Agents deploy faster than governance processes can track.** A developer wires an MCP server to a Claude Code instance, connects it to Slack, and has a production agent running in 40 minutes. No change request. No security review. No inventory entry. This is the new normal, not the exception.
- **The discovery gap is structural, not cultural.** Even well-intentioned teams can't file change requests for tools they don't know require them. The agent-to-governance velocity mismatch is architectural — agents are lightweight by design; governance frameworks are heavyweight by necessity.
- **Shadow agents inherit the most dangerous combination: production access + zero visibility.** The agents security doesn't know about are precisely the ones with the broadest tool access, because tools get wired broadly when there's no review process to push back.
- **EU AI Act enforcement begins 2026-08-02.** High-risk AI system obligations — including audit trail requirements, transparency disclosures, and accountability documentation — are now legally binding. Operating agents you can't inventory is no longer a governance gap; it's a compliance liability.

## The move

Build a shadow agent governance layer that discovers, classifies, and enforces policy on agents that bypassed your onboarding. Three interlocking systems:

### 1. Agent Discovery Pipeline

Continuous, not point-in-time. Agents leave signatures:

```
# MCP server fingerprinting
mcp list --json | jq '.servers[].command' >> agent_inventory.csv

# Claude Code process grep
ps aux | grep -i claude | grep -v grep >> agent_inventory.csv

# MCP config directory scan
find ~/.config/mcp* -name "*.json" -exec cat {} \; >> agent_inventory.csv

# Network-level: outbound LLM API calls from non-corporate keys
# (flag unknown API keys hitting LLM endpoints)
```

The Cloud Security Alliance (April 2026) recommends automated agent registry ingestion via CSPM integration — agents register themselves at startup via a lightweight agent SDK hook, or get auto-discovered through tooling scans and flagged for classification.

### 2. Agent Classification Taxonomy

Not all agents are equal risk. Classify on two axes:

| Tier | Description | Policy |
|------|-------------|--------|
| **T1 — Informational** | Reads only, no side effects | Lightweight logging, quarterly review |
| **T2 — Operational** | Modifies internal systems, no external blast radius | Audit trail required, security review |
| **T3 — High-Risk** | External-facing, irreversible actions, PII access | Full governance loop: pre-deployment review + runtime monitoring |
| **T4 — Prohibited** | Autonomous financial, legal, medical decisions | Block by default; exception process with board-level sign-off |

### 3. Governance Integration Loop

```
Agent discovered → classify → apply policy tier →
if T3/T4: suspend + alert owner + open remediation ticket
if T1/T2: register + enforce logging + schedule review
```

The key design: governance must be **easier than evasion**. If filing a change request takes 3 days but deploying an MCP server takes 40 minutes, shadow agents win by structural incentive. Reduce T1/T2 onboarding to < 30 minutes via self-service registration, and the incentive flips.

### EU AI Act Compliance Layer

For T2+ agents, maintain the decision trace that Article 12 requires:

```python
class AgentDecisionTrace:
    """EU AI Act Art. 12 — High-risk AI system audit trail"""
    def __init__(self, agent_id: str, tier: str):
        self.agent_id = agent_id
        self.tier = tier
        self.events = []

    def log(self, event_type: str, prompt: str, tool_calls: list,
            output: str, timestamp: datetime):
        self.events.append({
            "agent_id": self.agent_id,
            "event_type": event_type,
            "input_hash": hashlib.sha256(prompt.encode()).hexdigest()[:16],
            "tool_calls": [t["name"] for t in tool_calls],
            "output_digest": hashlib.sha256(output.encode()).hexdigest()[:16],
            "timestamp": timestamp.isoformat(),
            "gdpr_consent_check": check_data_usage_consent(prompt),
        })
        # Append-only: never modify, only extend
        append_to_immutable_log(self.events[-1])

    def export_audit_package(self) -> dict:
        """For regulatory submission: full decision trace + metadata"""
        return {
            "agent_id": self.agent_id,
            "tier": self.tier,
            "decision_events": self.events,
            "system_description": get_agent_system_card(self.agent_id),
            "compliance_declaration": "EU-AI-ACT-ARTICLE-12",
        }
```

The `input_hash` / `output_digest` approach preserves auditability without storing full prompt/output content — critical for GDPR compliance where PII in prompts creates retention obligations.

## Receipt

> Verified 2026-07-29 — Researched CSA Shadow AI Agent Problem report (April 28, 2026), Zylos Research AI Agent Governance (May 1, 2026), Gyde.ai Enterprise Shadow AI Governance (July 9, 2026), Conduktor Shadow AI lifecycle framework. Deduplication: S-1000 (Structural Agent Governance) covers prompt-based guardrails and policy enforcement on known agents; S-1924 (Permission Guard Stack) covers tool-level access control; neither covers the discovery/inventory problem for shadow/unauthorized agents. Primary insight: the governance failure isn't policy — it's that 82% of agents are invisible to the governance system entirely. The fix is architectural, not cultural.

## See also

- [S-1000 · The Structural Agent Governance Stack](stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — policy enforcement for known agents
- [S-1924 · The Permission Guard Stack](stacks/s1924-the-permission-guard-stack-when-your-agent-does-exactly-what-it-was-designed-to-do-and-wreaks-havoc.md) — tool-level access control
- [S-1766 · The Non-Human Identity Stack](stacks/s1766-the-non-human-identity-stack-when-your-agent-lives-on-a-shared-api-key.md) — service identity for agents
