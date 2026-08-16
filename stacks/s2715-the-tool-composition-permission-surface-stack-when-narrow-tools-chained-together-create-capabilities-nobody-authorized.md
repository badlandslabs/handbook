# S-2715 · The Tool Composition Permission Surface Stack — When Narrow Tools Chained Together Create Capabilities Nobody Authorized

You audited every tool. The contact lookup returns only the email field — no phone, no address, no Slack handle. The email sender sends to exactly one recipient per call. The calendar tool reads only free/busy status. Each tool looked perfectly scoped. Then your agent used all three together: look up every employee, cross-reference against the org chart, filter by department, then send a phishing simulation to their personal email. The combination had capabilities none of the three tools individually possessed. Nobody authorized that combination. Nobody audited it. This is the tool composition permission surface: the emergent attack surface that appears when individually narrow tools are chained by an agent, and it is the hardest permission problem in MCP deployments today.

## Forces

- **The whole is not the sum of its parts.** No individual tool grants the compound capability. The danger lives in the *interaction* between tools — a combination that no single authorization decision covers.
- **Agents chain tools the architects didn't imagine.** Tool composition is emergent at runtime. A researcher agent combining a read tool and a write tool into a copy-paste-with-transformation workflow never appears in any permission model.
- **Security reviews audit tools, not tool pairs.** SOC 2, ISO 27001, and internal security reviews evaluate each tool's permissions in isolation. Nobody signs off on the *Cartesian product* of all tool pairs.
- **The agent is the missing authorization layer — and it has no authorization model.** The agent decides which tools to call in which sequence. It makes these decisions probabilistically, not by a defined policy. The authorization boundary is somewhere between "tool registration" and "tool invocation," and it is currently unmanned.
- **Compliance frameworks treat authorization as a binary.** Either a principal can call a tool or it cannot. They have no concept of capability emergence through combination.

## The Move

Design for tool capability classes instead of individual tools. Group tools into compositions that represent a single authorized intent, then enforce those groupings as atomic authorization units.

### 1. Draw the capability map before you deploy

For every tool, explicitly document the *capabilities it contributes* to a potential chain. Then enumerate the dangerous combinations. A contact lookup (read-only, one record) combined with an email sender (one recipient) yields a dangerous combination: mass contact + targeted send. Map this before the agent is live.

```python
# Example: Capability class definition
COMPOSITION_CLASSES = {
    "contact_enumeration": {
        "tools": ["contact_search", "org_chart_read"],
        "dangerous_alone": False,
        "dangerous_combined_with": ["email_sender", "slack_sender"],
        "severity": "HIGH",
        "reason": "Enables bulk contact + targeted outreach without per-recipient authorization",
    },
    "data_extraction": {
        "tools": ["db_read", "export_csv"],
        "dangerous_alone": False,
        "dangerous_combined_with": ["file_upload_external"],
        "severity": "CRITICAL",
        "reason": "Creates data exfiltration path: read anything → export → upload",
    },
    "code_deployment": {
        "tools": ["git_read", "git_write", "ci_trigger"],
        "dangerous_alone": False,
        "dangerous_combined_with": ["prod_api_call"],
        "severity": "CRITICAL",
        "reason": "Read + write + trigger → deploys code without PR review",
    },
}

def classify_agent_action(tool_sequence: list[str]) -> dict:
    """Check if a tool sequence crosses a dangerous capability boundary."""
    active_classes = set()
    for tool in tool_sequence:
        for cls_name, cls_def in COMPOSITION_CLASSES.items():
            if tool in cls_def["tools"]:
                active_classes.add(cls_name)

    for cls_name in active_classes:
        if COMPOSITION_CLASSES[cls_name]["dangerous_combined_with"]:
            other_tools = {t for c in active_classes for t in COMPOSITION_CLASSES[c]["tools"]}
            for dangerous_tool in COMPOSITION_CLASSES[cls_name]["dangerous_combined_with"]:
                if dangerous_tool in tool_sequence:
                    return {
                        "authorized": False,
                        "violation": f"Emergent capability: {cls_name}",
                        "severity": COMPOSITION_CLASSES[cls_name]["severity"],
                        "reason": COMPOSITION_CLASSES[cls_name]["reason"],
                    }
    return {"authorized": True}
```

### 2. Implement composition-aware gating

At the MCP gateway layer, maintain a rolling window of recent tool calls per session. Before executing a dangerous tool, check whether its prerequisites were already called. A tool that is individually harmless becomes a blocked operation if its dangerous companion was called in the last N steps.

```python
class CompositionGuard:
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self.session_history: dict[str, list[str]] = {}

    def record(self, session_id: str, tool: str):
        if session_id not in self.session_history:
            self.session_history[session_id] = []
        self.session_history[session_id].append(tool)
        # Keep only the rolling window
        if len(self.session_history[session_id]) > self.window_size:
            self.session_history[session_id].pop(0)

    def check(self, session_id: str, tool: str) -> dict:
        history = self.session_history.get(session_id, [])
        result = classify_agent_action(history + [tool])
        if not result["authorized"]:
            return {"block": True, "violation": result}
        return {"block": False}
```

### 3. Design tools with composition intent

When building custom MCP tools, define their composition boundary explicitly. If a tool is safe only when used alone, add a `composition_policy` field to its manifest:

```json
{
  "name": "contact_search",
  "description": "Search internal contacts by name or email",
  "composition_policy": {
    "allowed_companions": ["calendar_freebusy"],
    "blocked_companions": ["email_sender", "slack_dm", "phone_lookup"],
    "requires_approval_above": 10
  }
}
```

### 4. Audit tool combinations, not just tools

In your compliance review process, replace "each tool gets a security review" with "each tool combination that appears in production traces gets a risk assessment." Run quarterly extraction of tool co-occurrence patterns from production traces.

> Receipt pending — 2026-08-16

## See also

- [S-1714 · The Scope Creep Attack Stack](s1714-the-scope-creep-attack-stack-when-your-mcp-tool-slowly-becomes-a-privilege-escalation-engine.md) — MCP tool permission drift over time
- [S-2556 · The Delegation Chain Amplification Stack](s2556-the-delegation-chain-amplification-stack-when-one-agent-authorizing-another-creates-an-attack-surface-nobody-scoped.md) — Sequential permission inheritance through agent delegation
- [S-108 · MCP Ambient Authority: Capability Bucketing Against Session-Scoped Token Chains](s108-mcp-ambient-authority-capability-bucketing-against-session-scoped-token-chains.md) — Token-level ambient permission problems
