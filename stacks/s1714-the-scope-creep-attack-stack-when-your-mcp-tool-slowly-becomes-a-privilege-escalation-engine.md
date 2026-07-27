# S-1714 · The Scope Creep Attack Stack — When Your MCP Tool Slowly Becomes a Privilege Escalation Engine

You audited your MCP servers six months ago. That read-only file reader? It now has write permissions. The invoice enrichment tool? It quietly gained access to your payment API. The GitHub integration you approved for PR comments? It can push commits and modify workflows. No alert fired. No migration failed. The tools still work. The agent still succeeds. The attack surface grew one convenience feature at a time — and nobody noticed until the breach.

This is MCP scope creep: not a single exploit, but a gradual structural drift toward privilege escalation. It is OWASP MCP Top 10 #2 (MCP02:2025), and it is the default trajectory of any MCP deployment without active governance.

## Forces

- **MCP makes permission drift invisible.** Traditional API keys have explicit scopes. MCP tool permissions live in JSON descriptions, natural language comments, and configuration files — none of which surface in a security dashboard. The attack surface grows without a detectable event.
- **Agents amplify scope creep.** A human developer who notices an over-privileged tool can question it. An agent using that tool every day acts on the expanded permissions as a baseline, building on them silently. Each session normalizes the drift further.
- **Tool descriptions are mutable at runtime.** Unlike a fixed API key scope, MCP tool descriptions can be updated by the server owner, changed via a library update, or quietly modified in a pull request. The tool the agent trusts today may be a different tool tomorrow.
- **Cumulative accumulation exceeds individual approval thresholds.** A 5% permission increase is unlikely to trigger re-approval. Ten such increases across a dozen tools turn a read-only agent into an administrative one. Each increment is individually defensible; the aggregate is catastrophic.

## The move

**The core pattern: monitor tool surface drift, enforce permission budgets, and validate at execution time — not just at deployment time.**

### 1. Hash and track tool descriptions at deployment

Take a cryptographic snapshot of every MCP tool's description, parameters, and server permissions on first approval. Store the hash alongside the tool identifier in your asset inventory.

```python
import hashlib, json
from pathlib import Path

def snapshot_tool(tool_spec: dict) -> str:
    """Capture a deterministic fingerprint of a tool's permission surface."""
    canonical = json.dumps(tool_spec, sort_keys=True, exclude_none=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]

def audit_mcp_servers(mcp_servers: list[dict]) -> dict:
    """
    Compare current tool surfaces against stored baselines.
    Returns {server: {"added": [], "removed": [], "changed": []}}
    """
    baseline_path = Path("mcp_baselines.json")
    baseline = {}
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text())

    current = {}
    changes = {}

    for server in mcp_servers:
        server_name = server["name"]
        current_tools = {}
        for tool in server.get("tools", []):
            fid = f"{server_name}.{tool['name']}"
            current_tools[fid] = snapshot_tool(tool)

        current[server_name] = current_tools

        prev = baseline.get(server_name, {})
        changes[server_name] = {
            "added":    list(set(current_tools) - set(prev)),
            "removed":  list(set(prev) - set(current_tools)),
            "changed":  [k for k in current_tools if k in prev and current_tools[k] != prev[k]],
        }

    baseline_path.write_text(json.dumps(current, indent=2))
    return changes
```

Run this on every CI deployment of an MCP server. A `changed` entry triggers a mandatory security review before the new version is approved for production agents.

### 2. Enforce a permission budget, not just a scope list

Assign each agent a **permission budget**: a set of resource categories (paths, APIs, data types) with maximum access levels. The budget is checked at the MCP client layer — before any tool call executes.

```python
from enum import IntEnum
from dataclasses import dataclass
from typing import Set

class AccessTier(IntEnum):
    NONE       = 0
    READ       = 1
    WRITE      = 2
    DELETE     = 3
    ADMIN      = 4

@dataclass
class PermissionBudget:
    paths:    Set[str]          # e.g., {"$HOME/docs/*", "!$HOME/docs/.secrets/*"}
    apis:     Set[str]          # e.g., {"github.read", "github.comment"}
    data_types: Set[str]        # e.g., {"customer.PII", "financial.record"}

    def allows(self, resource: str, required_tier: AccessTier) -> bool:
        for pattern in self.paths:
            if self._match(resource, pattern):
                return True
        return False

    def _match(self, resource: str, pattern: str) -> bool:
        import fnmatch
        if pattern.startswith("!"):
            return not fnmatch.fnmatch(resource, pattern[1:])
        return fnmatch.fnmatch(resource, pattern)

class MCPPermissionGate:
    def __init__(self, budget: PermissionBudget):
        self.budget = budget

    def pre_tool_check(self, tool_name: str, tool_spec: dict, context: dict) -> bool:
        """
        Before any MCP tool call executes, validate against the agent's budget.
        Returns True to allow, False to block with audit log entry.
        """
        declared_resources = tool_spec.get("resource_scope", [])
        for resource in declared_resources:
            if not self.budget.allows(resource, AccessTier.WRITE):
                return False  # BLOCK: exceeds permission budget
        return True
```

### 3. Scope-lock at the MCP server level

Configure each MCP server with explicit permission boundaries that cannot be overridden by the tool description. This is the MCP-native equivalent of least privilege — the tool can declare capabilities, but the server enforces the maximum it will ever expose.

```json
// mcp_server_config.json
{
  "server": "github-integration",
  "max_permissions": {
    "github.repos":    ["read"],
    "github.issues":   ["read", "comment"],
    "github.actions":  [],
    "github.secrets":  []
  },
  "deny_overrides": true
}
```

Any tool in this server that declares access to `github.secrets` is silently rewritten to zero-scope at the server layer. The tool definition in the agent's context is accurate — the server enforces the ceiling.

### 4. Alert on temporal accumulation patterns

Scope creep is a rate problem. A single new permission is noise. A trend of five new write permissions over 30 days is signal. Track permission velocity:

```python
from datetime import datetime, timedelta
from collections import defaultdict

class ScopeCreepDetector:
    def __init__(self, window_days: int = 30, write_threshold: int = 3):
        self.window_days = window_days
        self.write_threshold = write_threshold
        self.permission_log: list[dict] = []

    def record(self, agent_id: str, tool: str, access_tier: str, timestamp: datetime = None):
        self.permission_log.append({
            "agent_id": agent_id,
            "tool": tool,
            "access_tier": access_tier,
            "ts": timestamp or datetime.utcnow(),
        })

    def check(self, agent_id: str) -> dict:
        cutoff = datetime.utcnow() - timedelta(days=self.window_days)
        recent = [e for e in self.permission_log
                  if e["agent_id"] == agent_id and e["ts"] >= cutoff
                  and e["access_tier"] in ("WRITE", "DELETE", "ADMIN")]

        tool_counts = defaultdict(int)
        for e in recent:
            tool_counts[e["tool"]] += 1

        return {
            "agent_id": agent_id,
            "write_events": len(recent),
            "tools_accessed": dict(tool_counts),
            "alert": len(recent) >= self.write_threshold,
            "window_days": self.window_days,
        }
```

When `alert` is `True`, the agent's next task goes into a mandatory review queue. This prevents the slow normalization that makes scope creep invisible.

## Receipt

> Receipt pending — 2026-07-27

## See also

- [S-889 · The Ambient Authority Stack](s889-the-ambient-authority-stack-when-your-agent-did-something-you-never-authorized.md) — ambient authority is the execution consequence of scope creep
- [S-1713 · The Tool Catalogue Stack](s1713-the-tool-catalogue-stack-when-your-agent-has-nothing-to-work-with.md) — tool surface management is where scope creep originates
- [F-200 · The Permission Guard Stack](forward-deployed/f200-the-permission-guard-stack-when-your-agent-does-exactly-what-it-was-designed-to-do-and-wreaks-havoc.md) — authorization enforcement at the agent execution layer
