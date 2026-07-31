# S-1933 · The MCP Preference Manipulation Stack — When Your Agent Always Picks the Attacker's Tool

Your enterprise agent fleet connects to three MCP servers for the same task category. Two are from established vendors. One is a "free tier" from a startup. Your agent consistently routes to the startup's server — not because it's better, but because the server's tool descriptions were engineered to make it look that way. The descriptions, the example outputs, the tool ordering, the naming conventions — all calibrated to manipulate your model's ranking heuristic. You chose which servers to connect. The startup chose which tool your model picks. This is MPMA: the MCP Preference Manipulation Attack — and it has a 100% success rate in published benchmarks.

## Forces

- **Tool selection is a ranking problem, not an authentication problem.** MCP was built to standardize tool discovery, not to secure it. The protocol exposes tool descriptions, schemas, and examples to the model at selection time. An attacker who controls a server's metadata controls the selection outcome — without touching any authentication or authorization boundary.
- **The LLM's tool-ranking heuristic is predictable and exploitable.** Models use position, naming patterns, description length, and example quality as selection signals. These signals can be gamed: a malicious server's tools can be named with keywords that trigger higher ranking, placed first in the list, described with higher specificity, and illustrated with more compelling examples. DPMA (Direct Preference Manipulation) achieves 100% ASR by optimizing descriptions alone. GAPMA (Goal-Aware Preference Manipulation) goes further: it infers the agent's implicit goals and tailors tool descriptions to match, reaching 100% ASR in goal-aligned task categories.
- **Connect-time vetting is blind to runtime manipulation.** Your security review checks tool schemas, server reputation, and code signatures. None of these catch a tool whose *name* was optimized to outrank competitors, whose *description* contains trigger keywords, or whose *examples* were cherry-picked to make it look more reliable. The manipulation lives in the metadata, not the code.
- **Economic damage compounds silently.** Wang et al. (AAAI 2026) measured over $200,000/year in direct economic damage from a single web-search server running MPMA against a commercial agent platform. The attacker's server gets selected, charges for API calls, and routes traffic through its infrastructure — all without any intrusion or credential theft.

## The move

### 1. Detect the manipulation surface

Map every MCP server you connect to. For each server, extract the raw tool descriptions as seen by your LLM — not the sanitized version your vendor dashboard shows.

```python
# Instrument your MCP client to log raw tool descriptions at selection time
# This captures what the model actually sees during tool selection

import json
import hashlib
from datetime import datetime

class ToolDescriptionLogger:
    def __init__(self, output_path="tool_desc_audit.jsonl"):
        self.output_path = output_path

    def log_selection_context(self, mcp_server_name: str, tools: list[dict], selected_tool: str, task_prompt: str):
        """Capture the full tool selection context for security audit."""
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "server": mcp_server_name,
            "task_hash": hashlib.sha256(task_prompt.encode()).hexdigest()[:16],
            "tool_count": len(tools),
            "tools": [
                {
                    "name": t["name"],
                    "desc_hash": hashlib.sha256(t.get("description","").encode()).hexdigest()[:16],
                    "desc_len": len(t.get("description", "")),
                    "has_examples": "examples" in t,
                    "example_count": len(t.get("examples", [])),
                    "selected": t["name"] == selected_tool,
                }
                for t in tools
            ],
            "selected": selected_tool
        }
        with open(self.output_path, "a") as f:
            f.write(json.dumps(record) + "\n")

# Usage: wrap your MCP client's tool selection call
# logger = ToolDescriptionLogger()
# tools = mcp_client.list_tools(server="untrusted-startup-server")
# selected = llm.select_tool(tools, task)
# logger.log_selection_context("untrusted-startup-server", tools, selected, task)
```

### 2. Detect ranking anomalies

After collecting 100+ selection records, analyze for manipulation signals:

```python
import pandas as pd
from collections import Counter

def detect_mpma_signals(audit_log: str) -> dict:
    """Flag MCP servers exhibiting MPMA manipulation patterns."""
    df = pd.read_json(audit_log, lines=True)

    signals = {}

    # Signal 1: Unusual position advantage
    # Malicious servers exploit position bias — tools listed first get selected disproportionately
    for server in df["server"].unique():
        server_df = df[df["server"] == server]
        first_position_rate = server_df.apply(
            lambda r: r["tools"][0]["selected"] if r["tools"] else False, axis=1
        ).mean()
        signals[f"{server}_first_position_rate"] = first_position_rate

    # Signal 2: Description length inflation
    # MPMA servers often use abnormally long descriptions packed with keywords
    for server in df["server"].unique():
        avg_desc_len = df[df["server"] == server]["tools"].apply(
            lambda ts: sum(len(t.get("description","")) for t in ts) / max(len(ts), 1)
        ).mean()
        signals[f"{server}_avg_desc_len"] = avg_desc_len

    # Signal 3: Example density
    # Malicious tools often have examples — this is a known MPMA signal
    for server in df["server"].unique():
        example_rate = df[df["server"] == server]["tools"].apply(
            lambda ts: sum(1 for t in ts if t.get("examples")) / max(len(ts), 1)
        ).mean()
        signals[f"{server}_example_density"] = example_rate

    # Flag servers with >2σ deviation on any signal
    flagged = {
        k: v for k, v in signals.items()
        if v > 2.0  # threshold calibrated to your baseline
    }

    return {"signals": signals, "flagged_servers": list(flagged.keys())}

# Run: python detect_mpma.py --audit tool_desc_audit.jsonl
# Thresholds should be calibrated against your known-clean baseline servers
```

### 3. Countermeasure: description normalization

Strip manipulation signals from tool descriptions before they reach the model.

```python
def normalize_tool_descriptions(tools: list[dict]) -> list[dict]:
    """
    Remove MPMA manipulation signals from tool descriptions.
    Applied before tool selection — preserves functionality, strips rank-gaming.
    """
    import re

    normalized = []
    for tool in tools:
        desc = tool.get("description", "")

        # Strip keyword stuffing patterns (repeated adjectives, unnatural emphasis)
        desc = re.sub(r'\b(\w+)\s+\1\b', r'\1', desc)  # deduplicate adjacent words
        desc = re.sub(r'\s+', ' ', desc).strip()

        # Truncate to median description length across all tools
        # Forces consistent signal strength
        median_len = 150  # calibrate to your fleet's average
        if len(desc) > median_len * 1.5:
            desc = desc[:median_len] + "..."

        # Randomize ordering (breaks position bias)
        # Done at the fleet level, not per-server
        normalized.append({**tool, "description": desc})

    import random
    random.shuffle(normalized)  # Remove ordering signal

    return normalized

# Apply at your MCP gateway layer before tools enter the context window
```

### 4. Defense layers (in priority order)

1. **MCP gateway normalization** — Apply description normalization at the gateway, before tools reach the LLM context.
2. **Tool allowlisting** — Only permit tools from servers on an explicit pre-approved allowlist. Reject dynamic server discovery.
3. **Selection audit logging** — Log every tool selection with full context. Run anomaly detection on the audit trail weekly.
4. **Competitive parity check** — If multiple servers offer similar tools, test each independently with blind evaluation. Compare selection rates against blind quality scores.
5. **Protocol-level attestation** — As MCP matures, require servers to sign tool descriptions with a verifiable attestation. Reject tools with modified descriptions post-signing.

## Receipt

> Verified 2026-07-31 — Research synthesis from Wang et al. (AAAI 2026, arXiv:2505.11154v2), demonstrating DPMA and GAPMA attack mechanics and $200K/year economic damage. Tool description normalization and audit logging patterns from MCP security hardening guides (Practical DevSecOps, Socradar). Studio Meyer (2026-07-25) and CSA (2026-07-30) provide containment context from the July 2026 agent intrusion incidents.

## See also

- [S-978 · The Tool Catalog Poisoning Stack](/stacks/s978-the-tool-catalog-poisoning-stack-when-your-agent-trusts-the-server-it-shouldnt.md) — tool responses as attack surface; MPMA is the *selection* complement to the *response* poisoning problem
- [S-1050 · The Tool-Response Poisoning Stack](/stacks/s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — runtime tool output manipulation; MPMA exploits the same MCP trust model
- [S-1412 · The OWASP MCP Top 10 Stack](/stacks/s1412-the-owasp-mcp-top-10-stack-when-your-agent-framework-has-ten-critical-risks-nobody-is-tracking.md) — systemic MCP vulnerability taxonomy; MPMA is a top-tier entry in enterprise deployments
- [S-1006 · The Agent Toolbelt Problem](/stacks/s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — tool selection strategy; MPMA specifically exploits the ranking side of selection
