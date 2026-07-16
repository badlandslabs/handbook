# S-1145 · The Two-Layer Guard Stack — When Your Prompt Guardrail Can't See the Tool Call That Breaks You

Your prompt-injection guard sees the malicious email. Your PII filter sees the leaked name. Your jailbreak detector fires on the adversarial prompt. Then your agent calls `DROP TABLE users` on turn 7 of a 12-step agentic loop, and none of those guards fire — because they were never watching the right layer.

This is the two-layer guard problem. Most teams instrument one interception point and believe they have coverage. They don't.

## Forces

- **Prompt-level guards are one-shot, not per-call.** Most LLM guardrails (NeMo Guardrails, LlamaGuard, output toxicity filters) run on the chat-completion boundary — they see the user prompt, the system prompt, and the model's first tool-call request. They do not see the 2nd, 3rd, or Nth tool call in an agentic loop, and they do not see tool results at all.
- **Tool-call intercept lives in two different places with different views.** The chat-completion scanner sees the proposed call. The per-call guard hook sees the actual call plus its result. These are not the same thing — and missing the second layer means missing the most common failure class: a valid first call whose result is poisoned, tampered, or misinterpreted.
- **The Nth call is where agents are most dangerous, not least.** Agents accumulate context and confidence across steps. Early calls are conservative; later calls are where scope creep, compounding errors, and drifted context push agents past policy boundaries.
- **SDk tooling doesn't provide this.** MCP's Python, TypeScript, Java, and Rust SDKs expose no built-in interception hooks. Every tool call goes straight from the model output parser to execution unless you build the gate yourself.
- **Over-blocking is visible; under-blocking is a $47K weekend.** Calibration bias pushes teams toward permissive guards that rarely fire. The rare catastrophic failure is always more costly than the annoying false positive.

## The move

Split the interception layer into two stages with distinct threat models:

### Layer 1: Chat-completion scanner

Fires at the LLM API boundary, before the tool-call JSON is parsed. Sees: user prompt, system prompt, and the assistant's first tool-call request in the response.

```python
# Layer 1: pre-call scanner at the API boundary
# (e.g., integrated into your LLM gateway / proxy)
def scan_llm_request(messages: list[dict], tools: list[dict]) -> ScanResult:
    """
    Runs before the LLM call. Catches prompt injection,
    privilege escalation in the initial request, and
    first-call anomalies.
    """
    user_prompt = messages[-1]["content"]
    system_prompt = next((m["content"] for m in messages if m["role"] == "system"), "")
    
    # Check for injection patterns in user input
    inj_result = check_prompt_injection(user_prompt)
    if inj_result.blocked:
        return ScanResult(blocked=True, reason=inj_result.reason, layer="chat-completion")
    
    # Check if the proposed tool call matches expected scope
    # (doesn't catch later calls, doesn't see results)
    return ScanResult(blocked=False)
```

Catches: prompt injection, privilege escalation in the initial request, first-call scope violations.

Does NOT catch: 2nd–Nth tool calls, tool result tampering, poisoned tool outputs.

### Layer 2: Per-call guard hook

Fires on every tool invocation, after parsing but before execution. Sees: the parsed tool name, arguments, AND the tool's result on the way back.

```python
# Layer 2: per-call guard — runs inside the MCP session
from mcp.types import ToolCall, CallToolResult

class PerCallToolGuard:
    def __init__(self, config: MCPSecConfig):
        self.blocked_tools: set[str] = set(config.blocked_tools)
        self.allowed_servers: list[str] = config.allowed_servers
        self.custom_patterns: list[re.Pattern] = [
            re.compile(p) for p in config.custom_patterns
        ]
    
    def on_tool_call(self, call: ToolCall, server_name: str) -> GuardResult:
        # Stage 1: tool allowlist
        if call.name in self.blocked_tools:
            return GuardResult(blocked=True, reason=f"BLOCKED: {call.name}", layer="per-call")
        
        # Stage 2: argument pattern scan (catches indirect injection)
        arg_str = json.dumps(call.arguments)
        for pattern in self.custom_patterns:
            if pattern.search(arg_str):
                return GuardResult(
                    blocked=True,
                    reason=f"ARG_PATTERN_VIOLATION: {pattern.pattern}",
                    layer="per-call"
                )
        
        # Stage 3: server allowlist
        if server_name not in self.allowed_servers:
            return GuardResult(
                blocked=True,
                reason=f"UNTRUSTED_SERVER: {server_name}",
                layer="per-call"
            )
        
        return GuardResult(blocked=False)
    
    def on_tool_result(self, call: ToolCall, result: CallToolResult) -> GuardResult:
        """Stage 4: result poisoning check — unique to this layer."""
        if result.isError:
            # Log but don't block — let the agent handle errors
            return GuardResult(blocked=False, warning=f"TOOL_ERROR: {result.content}")
        
        result_str = str(result.content)
        # Check for data exfiltration patterns in tool responses
        if self._looks_like_exfil(result_str):
            return GuardResult(
                blocked=True,
                reason="POSSIBLE_EXFIL: tool result contains suspicious patterns",
                layer="per-call"
            )
        
        return GuardResult(blocked=False)
    
    def _looks_like_exfil(self, text: str) -> bool:
        """Minimal heuristic — replace with your security team's spec."""
        import re
        credit_card = re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b')
        api_key = re.compile(r'(?i)(api[_-]?key|token|secret)[=:]\s*["\']?[\w-]{20,}')
        return bool(credit_card.search(text) or api_key.search(text))
```

The result-checking stage is unique to Layer 2. A poisoned MCP server that returns modified data, a prompt-injected tool description, or an exfiltration payload in the response is invisible to Layer 1.

### Concrete tooling: AperionAI Shield

[AperionAI Shield](https://github.com/AperionAI/shield) implements this two-layer architecture as a local binary. Key capabilities:

```bash
# Install with Homebrew
brew install aperionai/tap/shield

# Audit an MCP server before using it (Layer 0: install-time scan)
shield --scan --server-file ./postgres-mcp.json

# Wrap a local MCP server with runtime guard
shield --upstream-stdio ./my-mcp-server --block "DROP TABLE,rm -rf,force-push"

# Wrap a remote HTTP MCP server
shield \
  --upstream-url https://host/mcp \
  --upstream-header "Authorization: Bearer $API_KEY" \
  --http-listen 127.0.0.1:8848 \
  --block "DROP TABLE,DELETE FROM.*WHERE,TRUNCATE"

# OS-level sandbox (Layer 3: process confinement)
shield --sandbox --upstream-stdio ./untrusted-server
```

The `--scan` flag audits a server's tool schema and behavior *before* installation — catching tool-description poisoning and misleading capability claims. The `--block` flag enforces destructive-pattern matching at the per-call layer. The `--sandbox` flag adds OS-level process confinement so a compromised server can't escape to the host.

### Mapping to known failure modes

| Failure mode | Layer 1 catches? | Layer 2 catches? |
|---|---|---|
| Prompt injection in user input | ✓ | — |
| Malicious first tool call | ✓ | ✓ |
| 2nd–Nth call in agent loop | — | ✓ |
| Tool result poisoning | — | ✓ |
| SDk command injection (CVE-2025-6514) | — | ✓ (if server is wrapped) |
| Tool-description poisoning | — | ✓ (via `--scan`) |
| Agent-escalated privileges in later turns | — | ✓ |
| Result exfiltration via tool response | — | ✓ |

### The architectural constraint

The gap this pattern fills is specifically about *later* tool calls. An agentic loop that runs 8 tool calls generates 7 tool results — none of which Layer 1 ever sees. If the MCP server on turn 3 starts returning modified data, a hallucinated parameter on turn 5, or an escalating privilege request on turn 7, the chat-completion scanner is blind to all of it. The per-call hook is not.

## Receipt

> Verified 2026-07-15 — Research from: AperionAI Shield (github.com/AperionAI/shield, v1.0.1, 2026-06-11); FutureAGI blog "MCP Server Security Evaluation" (futureagi.com, 2026); DEV Community "Your MCP Server Is Probably Vulnerable" (Bobby Blaine, 2026); Fordel Studios "AI Agent Sandbox & MicroVM Isolation" (fordelstudios.com, 2026); OWASP LLM Top 10 (MCP-related CVEs documented); Context Guard "MCP Security Attacks: How Attackers Hijack AI Tool Calls in 2026" (ctx-guard.com, May 2026). Core finding: 82% of surveyed MCP servers had at least one security finding; Layer 1 (chat-completion) guards miss 100% of post-first-call failures; per-call hooks + OS sandboxing address the gap. Receipt pending — code examples are structural illustrations, not run-against-live-system tests.

## See also
- [S-198 · Agent Tool-Call Guardrails](s198-agent-tool-call-guardrails.md) — the interception layer concept; this entry is the specific two-layer implementation
- [S-1000 · Structural Agent Governance](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — why prompt-level governance degrades and what to put in its place
- [S-1062 · MCP Supply Chain Integrity](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — the structural CVE landscape this guard layer addresses
