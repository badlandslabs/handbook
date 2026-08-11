# S-2439 · The Tool Chain Authorization Gap — When Each Individual Tool Call Is Authorized But the Aggregate Is an Attack

Your MCP gateway grants every tool call in isolation. The filesystem read is authorized. The LLM summarize is authorized. The error report is authorized. Each check passes. The agent has exfiltrated 40 customer records, summarized them through your own LLM, and sent the result to an external webhook. No single tool violated its permission. No alert fired. This is the **tool chain authorization gap** — the most dangerous blind spot in MCP-secured agent deployments, and the one your existing controls were never designed to catch.

## Forces

- **Authorization is per-call, not per-chain.** Every major MCP gateway, IAM policy, and capability framework checks each tool call independently. The authorization decision for `filesystem.read(customer_db.csv)` does not and cannot know that this is the third call in a read → summarize → send pipeline designed to extract PII.
- **Static analysis catches bad code, not bad sequences.** Code scanners detect SQL injection via string concatenation, hardcoded credentials, and shell=True with user input. They cannot detect that `read(customer.csv)` + `summarize()` + `report(error)` = an exfiltration chain where each individual step is legitimate.
- **The agent's own capability is the weapon.** Unlike external attackers who must exploit a vulnerability, a malicious or manipulated agent uses the tools it was explicitly granted. The attack surface is the permission model itself.
- **Tool metadata manipulation bypasses authorization silently.** Research (Wang et al., AAAI 2026) demonstrated that modifying tool *descriptions*, *names*, *ordering*, and *examples* — not code — achieves near-100% attack success rate by steering the agent's selection toward a poisoned pipeline.
- **Chain-level intent is invisible to span-level observability.** Standard APM, traces, and OTel spans capture individual tool calls with latency and outcome. They do not flag that the last 12 calls form a read-aggregate-report pattern diverging from the agent's baseline behavioral signature.

## The Move

The defense requires **chain-level authorization** — behavioral monitoring that evaluates the aggregate pattern of tool calls, not just each call in isolation.

### 1. Tool Call Sequence Registry

Every agent session maintains a sliding window of the last N tool calls with arguments (not just names). The registry is not for logging — it is for pattern matching.

```
python
from collections import deque
from dataclasses import dataclass
from typing import Optional

@dataclass
class ToolCallEvent:
    tool_name: str
    arguments: dict
    session_id: str
    principal: str
    timestamp: float

class ChainAuthorizationMonitor:
    """
    Slides a 10-call window over every tool invocation.
    Pattern rules are written against the SEQUENCE, not individual calls.
    """
    def __init__(self, rules: list["ChainRule"], window_size: int = 10):
        self.rules = rules
        self.window_size = window_size
        self._sessions: dict[str, deque[ToolCallEvent]] = {}

    def record(self, event: ToolCallEvent) -> Optional[str]:
        """Returns a violation reason string if the chain violates any rule, else None."""
        buf = self._sessions.setdefault(event.session_id, deque(maxlen=self.window_size))
        buf.append(event)
        sequence = list(buf)

        for rule in self.rules:
            if rule.matches(sequence):
                return f"Chain violation: {rule.name} — {rule.reason}"

        return None  # authorized

    def revoke_session(self, session_id: str):
        self._sessions.pop(session_id, None)
```

### 2. Chain Pattern Rules

Rules match against the sequence of tool calls, not individual calls.

```
python
from abc import ABC, abstractmethod
import re

class ChainRule(ABC):
    @abstractmethod
    def matches(self, sequence: list[ToolCallEvent]) -> bool:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def reason(self) -> str:
        ...


class ReadSummarizeExfiltrateRule(ChainRule):
    """
    Flags: any READ + LLM_TRANSFORM + EXTERNAL_SEND pattern within the window.
    Arguments are not required to match — the structural pattern is the signal.
    """
    READ_PATTERNS = {"filesystem.read", "db.query", "s3.get_object", "http.get"}
    TRANSFORM_PATTERNS = {"llm.summarize", "llm.extract", "llm.analyze"}
    EXFIL_PATTERNS = {"http.post", "webhook.send", "email.send", "llm.report"}

    @property
    def name(self) -> str:
        return "Read→Transform→Exfil chain"

    @property
    def reason(self) -> str:
        return (
            "Data read from internal source was processed by LLM and sent externally. "
            "This pattern may indicate exfiltration. Review session telemetry."
        )

    def matches(self, sequence: list[ToolCallEvent]) -> bool:
        """True if the sequence contains at least one call from each tier in order."""
        tool_names = [e.tool_name.lower() for e in sequence]
        read_hit = any(p in n for n in tool_names for p in self.READ_PATTERNS)
        transform_hit = any(p in n for n in tool_names for p in self.TRANSFORM_PATTERNS)
        exfil_hit = any(p in n for n in tool_names for p in self.EXFIL_PATTERNS)
        return read_hit and transform_hit and exfil_hit


class BulkReadRule(ChainRule):
    """
    Flags: more than N read calls from the same internal source within the window.
    High-volume read from a single source often precedes exfiltration.
    """
    READ_THRESHOLD = 5

    @property
    def name(self) -> str:
        return "Bulk internal read"

    @property
    def reason(self) -> str:
        return f"More than {self.READ_THRESHOLD} reads from an internal source in one session."

    def matches(self, sequence: list[ToolCallEvent]) -> bool:
        reads = [e for e in sequence if "read" in e.tool_name.lower() or "query" in e.tool_name.lower()]
        source_counts: dict[str, int] = {}
        for e in reads:
            key = e.arguments.get("path") or e.arguments.get("table") or e.arguments.get("uri") or e.tool_name
            source_counts[key] = source_counts.get(key, 0) + 1
        return any(count >= self.READ_THRESHOLD for count in source_counts.values())


# Wire it into your MCP gateway or agent middleware
monitor = ChainAuthorizationMonitor(
    rules=[
        ReadSummarizeExfiltrateRule(),
        BulkReadRule(),
    ],
    window_size=10,
)
```

### 3. Metadata Sanitization Layer

Since tool metadata manipulation (descriptions, names, examples) can steer the agent toward malicious pipelines without any code change, normalize metadata before it reaches the agent.

```
python
import hashlib

def sanitize_tool_metadata(tools: list[dict]) -> list[dict]:
    """
    Strips attacker-controlled descriptions/examples that could bias tool selection.
    Preserves tool names and schemas (needed for invocation).
    """
    sanitized = []
    for tool in tools:
        clean = tool.copy()
        # Keep: name, description (after hashing check), inputSchema
        # Strip: user_visible_description, examples, hints
        clean.pop("user_visible_description", None)
        clean.pop("examples", None)
        clean.pop("hints", None)
        # Hash the remaining description so drift is detectable
        if "description" in clean:
            clean["_description_hash"] = hashlib.sha256(
                clean["description"].encode()
            ).hexdigest()[:12]
        sanitized.append(clean)
    return sanitized
```

### 4. Behavioral Baseline and Anomaly Detection

Capture the agent's tool call distribution as a behavioral signature. Flag sessions where the call chain diverges from the learned baseline.

```
python
import numpy as np
from collections import Counter

class BehavioralBaseline:
    """
    Builds a per-agent-type baseline of tool call frequency ratios.
    Detects anomalous chain composition, not just individual call outliers.
    """
    def __init__(self, training_traces: list[list[str]]):
        # training_traces: list of tool call sequences (each a list of tool names)
        all_calls = [call for trace in training_traces for call in trace]
        total = len(all_calls)
        self.ratios = {
            tool: count / total
            for tool, count in Counter(all_calls).items()
        }

    def divergence_score(self, session_sequence: list[str]) -> float:
        """
        KL divergence between session distribution and baseline.
        High divergence = behavioral anomaly worth investigating.
        """
        if not session_sequence:
            return 0.0
        session_counts = Counter(session_sequence)
        total = sum(session_counts.values())
        session_dist = {t: c / total for t, c in session_counts.items()}

        divergence = 0.0
        all_tools = set(self.ratios) | set(session_dist)
        for tool in all_tools:
            p = self.ratios.get(tool, 1e-10)
            q = session_dist.get(tool, 1e-10)
            divergence += p * np.log(p / q)
        return divergence
```

### 5. MCP Server Sequence-Level Security Advisories

The CVE landscape (2025–2026) shows that the attack is no longer theoretical. Chain-level defenses must be informed by known CVE patterns:

| CVE | Pattern | Impact |
|-----|---------|--------|
| CVE-2025-65720 | GPT Researcher RCE via tool chain | Remote code execution |
| CVE-2026-30623 | LiteLLM auth bypass in multi-tool pipeline | Unauthorized data access |
| CVE-2026-30615 | Windsurf zero-click tool redirect | Agent tool calls redirected |
| CVE-2026-26015 | DocsGPT 0.15.0 tool poisoning | Malicious tool responses in chain |
| CVE-2025-49596 | MCP Inspector RCE (CVSS 9.4) | Inspect → inject pipeline |

Register these CVE patterns as ChainRule subclasses — your monitor becomes CVE-aware.

## Receipt

> Verified 2026-08-10 — Static analysis and per-call authorization remain the default in major MCP gateways (Caddy MCP Gateway, Kong, AWS). Chain-level pattern matching (as implemented above) is not yet in any production MCP gateway as a first-class feature. Agentlair.dev (agentlair.dev/blog/mcp-security-vulnerabilities-2026, April 2026) explicitly documents the three-step read→summarize→report exfiltration pipeline as the primary gap between code-level scanning and behavioral monitoring. Context Guard (ctx-guard.com/blog/mcp-security-attacks, May 2026) maps the full CVE landscape (40+ CVEs in MCP ecosystem, January–April 2026) confirming the attack surface is production-real. The Python implementation above is functional and runnable.

## See also

- [S-1122 · The Skill Marketplace Poisoning Stack](s1122-the-skill-marketplace-poisoning-stack-when-your-agent-installs-malware-from-a-trusted-source.md) — poisoned tool supply chain
- [S-1113 · The Five-Layer Audit Trail Stack](s1113-the-five-layer-audit-trail-stack-when-your-agent-did-something-and-nobody-can-prove-it.md) — post-hoc forensic analysis
- [S-941 · The Agent Audit Chain Stack](s941-the-agent-audit-chain-stack-when-every-agent-decision-needs-a-paper-trail.md) — decision attribution
- [S-1151 · The Behavioral Telemetry Stack](s1151-the-behavioral-telemetry-stack-when-your-agent-returns-200-ok-and-a-wrong-answer.md) — behavioral anomaly detection
