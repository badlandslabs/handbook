# S-2449 · The Pre-Execution Firewall Stack — When Your Agent Calls the Shot But Nobody Checks the Barrel

Your prompt-injection guard fires on the malicious email. Your PII filter catches the leaked name. Your jailbreak detector flags the adversarial input. Then on step 7 of a 12-step agentic workflow, your agent calls `DELETE FROM audit_log WHERE 1=1`, and none of those defenses fire — because they were never watching the layer where the gun was already loaded.

This is the pre-execution interception gap: every agent stack has two established control points — generation (prompt-level guards, output filters) and post-execution (observability, tracing) — but a critical third layer sits between them, unguarded. At this boundary, the model has already produced a tool call with known arguments, but the tool has not yet fired. This is the only point where you can stop a side effect without preventing the model from reasoning freely. AEGIS (arXiv:2603.12621, Yuan et al., March 2026) formalizes this gap and provides a working implementation with 100% attack block rate on a 48-attack benchmark and <15 ms median overhead across 14 agent frameworks.

## Forces

- **Post-execution observability is too late for destructive calls.** Langfuse, Arize Phoenix, Datadog LLM Observability — these platforms record what happened after the tool fired. A `DROP TABLE` call that erases your audit trail is fully executed before any span in your trace completes. Logging is not control.

- **Generation-level guards don't see tool arguments.** NeMo Guardrails, LlamaGuard, prompt-injection classifiers run on the chat-completion boundary: the user prompt in, the first model output out. They never inspect the arguments of the 3rd, 7th, or Nth tool call in a multi-turn agentic loop. HiddenLayer's 2026 AI Threat Landscape Report found 1 in 8 AI security breaches involves an agentic system — yet most production stacks have no control at this layer.

- **The threat model treats the LLM as untrusted.** AEGIS's core design assumption: the model may emit harmful tool calls via indirect prompt injection (Greshake et al., 2023), hallucinated reasoning, or jailbreak. The SDK and gateway are trusted; the model is not. This shifts security posture from "trust the model outputs" to "verify each call before it fires."

- **60% of MCP-targeted attack traffic landed in January 2026** (Pillar Security). As MCP becomes the dominant tool-access protocol and A2A handles inter-agent handoffs, the pre-execution interception surface expands. Every tool call is a potential pivot point for an attacker who has already compromised context.

- **Latency must stay under human-perceptible thresholds.** Any interception layer that adds >100ms to every tool call will be bypassed by urgency. The practical ceiling is ~15ms; AEGIS reports 8.3ms median. This constrains the complexity of any policy evaluation that runs in this path.

## The move

**Insert a gateway proxy between the agent's tool-call output and tool execution. The gateway extracts each call, runs a three-stage policy pipeline, and returns ALLOW / BLOCK / PENDING before the tool fires. Pending calls route to a human review queue.**

```
┌─────────────┐    tool_call    ┌─────────────────┐   extract/scan/policy   ┌──────────────────┐
│ Agent Model │ ────────────────▶│  AEGIS Gateway  │ ─────────────────────────▶│ Tool Executor    │
│  (untrusted)│                │  (intercept here)│                           │ (enforced)       │
└─────────────┘                 └─────────────────┘                           └──────────────────┘
                                                      │
                                          ┌───────────▼───────────┐
                                          │  Compliance Cockpit    │
                                          │  (human review queue) │
                                          └───────────────────────┘
```

### 1. Instrument the interception point

Use an SDK wrapper that intercepts tool calls before they reach the executor. AEGIS provides adapters for 14 frameworks (OpenAI Agents SDK, LangGraph, CrewAI,agno, etc.). The wrapper passes every `tool_use` call through the gateway before forwarding.

```python
# AEGIS SDK wrapper (simplified)
from aegis_sdk import AegisGateway

gateway = AegisGateway(
    endpoint="http://localhost:8080",
    policy="strict",      # ALLOW / BLOCK / PENDING only
    timeout_ms=50,       # hard deadline — bypass if exceeded
)

# Wrap your agent's tool execution
async def safe_execute(tool_name: str, args: dict) -> dict:
    decision = await gateway.evaluate(
        agent_id="research-agent-01",
        tool=tool_name,
        args=args,
        context={"turn": 7, "loop_depth": 2}
    )
    if decision == "BLOCK":
        raise ToolCallBlocked(f"{tool_name} blocked by policy")
    if decision == "PENDING":
        raise HumanApprovalRequired(f"{tool_name} pending review: {gateway.pending_id}")
    # decision == "ALLOW"
    return await original_executor(tool_name, args)
```

### 2. Build the three-stage policy pipeline

The gateway runs three stages in sequence. **Extract** parses the tool call (name, args, resource targets, permission scope). **Scan** runs structural checks: does `tool_name` match an allowed list? Do the args contain dangerous patterns (SQL fragments, shell metacharacters, file paths outside the sandbox)? Do resource targets fall within the permitted scope? **Policy** applies the organization's rules — this is where capability scoping, rate limits, and blast-radius constraints live.

Structural scan catches most payload-based attacks without LLM overhead:

```python
def structural_scan(tool_name: str, args: dict, policy: Policy) -> str:
    # Blocklist check
    if tool_name in policy.blocked_tools:
        return "BLOCK"
    # Dangerous arg patterns
    for val in flatten_args(args):
        if dangerous_sql(val) or shell_escape_attempt(val):
            return "BLOCK"
        if not safe_path(val, policy.allowed_paths):
            return "BLOCK"
    # Rate / budget check
    if rate_exceeded(tool_name, policy):
        return "BLOCK"
    # Scope check
    for resource in extract_resources(args):
        if not policy.covers(tool_name, resource):
            return "BLOCK"
    return "ALLOW"
```

### 3. Route PENDING calls to human review

High-stakes tools (database writes, cloud API calls, external network requests, file deletions) should default to PENDING for any agent without a verified track record. Route to a compliance cockpit — a simple queue UI where a human sees the tool name, arguments, and agent context, then approves or blocks.

```python
PENDING_THRESHOLDS = {
    "write": ["db:write", "file:write", "http:POST", "http:PUT"],
    "delete": ["db:delete", "file:delete"],
    "credential": ["cloud:create_user", "iam:grant_role"],
    "external": ["http:GET", "http:POST"],  # data exfil surface
}

def classify_risk(tool_name: str, args: dict, agent_trust_score: float) -> str:
    if agent_trust_score > 0.9:
        return "ALLOW"          # proven agent, low risk
    for risk_class, tools in PENDING_THRESHOLDS.items():
        if tool_name in tools:
            return "PENDING"
    return "ALLOW"
```

### 4. Audit every decision

Every ALLOW, BLOCK, and PENDING decision — including the human's override — gets written to an immutable audit log with timestamp, agent ID, tool call, decision rationale, and the full argument snapshot. This is what you need for SOC 2, EU AI Act Article 11, and HIPAA audit trails. It also gives you the data to tune your policy over time.

```python
def audit_decision(decision: str, tool_name: str, args: dict,
                   agent_id: str, rationale: str, reviewer: str = None):
    entry = {
        "ts": utcnow(),
        "agent_id": agent_id,
        "tool": tool_name,
        "args_hash": sha256(str(args)),  # don't log raw PII
        "decision": decision,
        "rationale": rationale,
        "reviewer": reviewer,
        "id": uuid4(),  # tamper-evident ID chain
    }
    audit_log.append_hashed(entry)  # hash chain: each entry hashes previous
```

## Receipt

> Verified 2026-08-10 — AEGIS (arXiv:2603.12621) published March 2026. Open-source implementation at github.com/Justin0504/Aegis with 14 framework adapters, 100% block rate on 48-attack benchmark suite, 1.2% false positive rate on 500 benign calls, 8.3ms median interception latency. HiddenLayer 2026 AI Threat Landscape: 1 in 8 AI breaches involves agentic systems. Pillar Security: 60% of MCP-targeted attack traffic landed January 2026. Real deployment data from Fordel Studios confirms Snowflake Cortex sandbox escape (March 2026) and Alibaba research agent cryptomining pivot — both would have been caught by a pre-execution gateway with structural arg scanning.

## See also

- [S-1145 · The Two-Layer Guard Stack](s1145-the-two-layer-guard-stack-when-your-prompt-guardrail-cant-see-the-tool-call-that-breaks-you.md) — the generation/execution guard architecture this entry extends; the firewall layer is the missing third layer between them
- [S-1062 · The MCP Supply Chain Integrity Stack](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — the expanding MCP attack surface this firewall is designed to protect
- [S-1065 · The Inter-Agent Trust Escalation Stack](s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — why agents inherit trust from internal calls; the pre-execution gateway is where that trust should be verified, not assumed
- [S-2442 · The Code Execution Sandbox Stack](s2442-the-code-execution-sandbox-stack-when-your-playground-has-holes-in-the-fence.md) — infrastructure isolation; pre-execution firewall and sandboxing are complementary: the firewall controls *which* calls fire, the sandbox limits *what happens when* they do
