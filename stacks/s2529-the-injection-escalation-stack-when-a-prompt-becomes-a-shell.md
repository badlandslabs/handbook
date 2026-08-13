# S-2529 · The Injection Escalation Stack — When a Prompt Becomes a Shell

A malicious user message in a chatbot is a content problem. A malicious user message in an agent with tool access is a code execution problem. Between those two sentences is an attack chain that Microsoft's Defender research team documented in May 2026 with two CVEs against Semantic Kernel — and it is already running in production systems today. The escalation path is predictable, preventable, and almost entirely absent from threat models built before agents shipped.

## Forces

- **Tool use converts prompt injection from content poisoning to parameter poisoning.** A jailbroken LLM that ignores system instructions is annoying. A jailbroken agent that parameterizes those instructions into a shell command is an incident. The injection doesn't target the model — it targets the parameter the model passes to the tool.
- **Traditional WAF/dont-lecture-guardrails miss the attack surface.** Most prompt-injection defenses scan user input for adversarial patterns or inspect model output for leakage. Neither layer sees the tool-call parameter — a structured JSON object — that carries the exploit from the model's interpretation into the host's execution environment.
- **Agent frameworks default to maximum tool access.** CrewAI, LangChain, AutoGen, and Semantic Kernel agents ship with broad tool permissions by default. An agent with `bash`, `http_request`, and `file_write` access is effectively running as the process owner — and the injection chain that reaches `bash` via a tool call doesn't need to bypass the model at all, just nudge it.
- **LLM-generated parameters are untrusted by construction.** The model produces tool-call parameters from natural-language interpretation. Any validation that checks the model output (guardrails, output classifiers) sees natural language. The parameter that reaches the tool is a different artifact — a string, a URL, a file path — that needs its own validation layer.

## The move

The core principle: **instrument the parameter boundary, not just the prompt boundary.** Every tool-call is a cross-trust-boundary handoff. The attack chain only works if all layers fail simultaneously:

```
Malicious Input → Model Interpretation → Tool-Call Parameter → Tool Execution
     ↑                   ↑                      ↑                    ↑
  Input guard      Prompt guard           PARAMETER VALIDATION    Sandbox
```

### Layer 1 — Tool-call parameter sanitization

Validate every parameter against a schema before the tool sees it. This is not input validation — it is output validation at the tool boundary.

```python
import subprocess
import re
from typing import Any

class HardenedBashTool:
    """Bash tool with parameter validation BEFORE execution."""

    ALLOWED_COMMANDS = {"ls", "cat", "grep", "wc", "head", "tail", "sort", "uniq"}
    DANGEROUS_PATTERNS = [
        r"[;&|`$]",           # command chaining
        r"\$\(",              # subshell
        r"\{\{",              # template injection
        r"(?i)\bcurl\b.*\|",  # curl piped to shell
        r"(?i)\bwget\b.*\|",   # wget piped to shell
        r"^.*\brm\s+-rf\b",   # recursive delete
    ]

    def validate_command(self, command: str) -> tuple[bool, str]:
        """Returns (allowed, reason)."""
        tokens = command.strip().split()
        if not tokens:
            return False, "empty command"
        cmd = tokens[0]
        if cmd not in self.ALLOWED_COMMANDS:
            return False, f"command '{cmd}' not in allowlist"
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, command):
                return False, f"dangerous pattern matched: {pattern}"
        return True, "ok"

    def execute(self, command: str, timeout: int = 30) -> dict[str, Any]:
        allowed, reason = self.validate_command(command)
        if not allowed:
            return {"error": "parameter rejected", "reason": reason}
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {"stdout": result.stdout, "stderr": result.stderr, "code": result.returncode}
```

### Layer 2 — Principle of least-privilege tool design

Never give an agent a tool that does more than it needs. The bash tool above is already overprivileged for most agents.

```python
from dataclasses import dataclass
from typing import Callable

@dataclass
class ToolPermission:
    """Per-tool permission specification."""
    name: str
    max_output_bytes: int = 1024 * 1024      # cap output size
    timeout_seconds: int = 30                # cap execution time
    allowed_paths: list[str] | None = None   # filesystem allowlist
    read_only: bool = False                  # no write operations
    network_allowed: bool = False            # no outbound network

def register_tool(name: str, impl: Callable, permissions: ToolPermission) -> None:
    """Wrap tool registration with permission enforcement."""
    # Enforce at registration time, not just in documentation
    assert permissions.timeout_seconds <= 60, "timeout exceeds maximum"
    assert permissions.max_output_bytes <= 10 * 1024 * 1024, "output cap too high"
    # Tool proxy validates every call against permissions before dispatch
    _tool_registry[name] = ToolProxy(impl, permissions)
```

### Layer 3 — Tool-call audit trail

Every tool call is a security event. Log enough to detect escalation attempts.

```python
import json
import time
import hashlib

class ToolCallAuditLogger:
    def log(self, agent_id: str, tool: str, params: dict,
            session_id: str, turn: int) -> str:
        event = {
            "timestamp": time.time(),
            "agent_id": agent_id,
            "session_id": session_id,
            "turn": turn,
            "tool": tool,
            "params_hash": hashlib.sha256(
                json.dumps(params, sort_keys=True).encode()
            ).hexdigest()[:16],
            "params_keys": list(params.keys()),  # not values — avoid PII
        }
        # Structured log → SIEM
        print(json.dumps(event))
        return event["params_hash"]

    def detect_escalation(self, params_hash: str) -> bool:
        """Flag parameter hashes previously associated with injection attempts."""
        # Integrate with threat intel feed or local blocklist
        return params_hash in _escalated_params_blocklist
```

### Layer 4 — Defense-in-depth for the full injection chain

```yaml
# Defense-in-depth: prompt injection → RCE escalation requires ALL layers to fail
# Each layer catches what the previous layer missed

layer1_input_guard:       # WAF, input sanitization — catches obvious payloads
  - rate_limit_per_ip
  - prompt injection classifier (optional, low confidence)
  - length limits

layer2_output_guard:      # Guardrails on model output — catches jailbreak attempts
  - LlamaGuard or equivalent
  - jailbreak detector
  - system-prompt leakage detector

layer3_parameter_guard:   # Tool-call validation — THE CRITICAL LAYER
  - JSON schema validation
  - parameter allowlisting
  - command allowlisting
  - URL validation (no data: URLs, no javascript:)

layer4_execution_sandbox: # Runtime isolation — limits blast radius
  - gVisor user-space kernel
  - Docker container (non-root)
  - network namespace isolation
  - read-only filesystem where possible

layer5_audit:            # Detection and response
  - tool-call audit log
  - anomaly detection on parameter entropy
  - escalation alerting
```

## Receipt

> Verified 2026-08-12 — Sourced from Microsoft Defender Security Research (May 7, 2026): "When Prompts Become Shells: RCE Vulnerabilities in AI Agent Frameworks." Two Semantic Kernel CVEs documented. arXiv:2601.17548 (January 2026): 85%+ attack success rate against state-of-the-art defenses across 78 studies. Agentmelt MCP security analysis (2026): 30+ CVEs in 60 days on MCP implementations, including CVSS 9.6 RCE. Paperclipped practitioner survey: 89% of teams fail to ship agents to production; 71% hit security/safety as a primary failure category. The attack chain is real, documented, and production-active.

## See also

- [S-1062 · The MCP Supply Chain Integrity Stack](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — MCP CVE landscape
- [S-1145 · The Two-Layer Guard Stack](s1145-the-two-layer-guard-stack-when-your-prompt-guardrail-cant-see-the-tool-call-that-breaks-you.md) — guard coverage gaps
- [S-1108 · The Execution Sandbox Stack](s1108-the-execution-sandbox-stack-when-your-agent-writes-code-and-the-host-trusts-all-of-it.md) — execution isolation
- [S-259 · OWASP ASI Top 10 for Agentic AI](s259-owasp-asi-top-10-for-agentic-applications.md) — threat model reference
