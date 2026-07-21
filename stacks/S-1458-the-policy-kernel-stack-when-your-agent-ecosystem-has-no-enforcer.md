# S-1458 · The Policy-Kernel Agent Stack — When Your Agent Ecosystem Has No Enforcer

You run 12 MCP servers across 3 agents. You have a written policy: agents read production data only via the reporting tool, never directly. But in the last incident, an agent read the user table through the admin endpoint because the prompt said "use your best judgment on which tool to call." Your policies exist in prose. Your enforcement exists in hope. The MCP ecosystem has 344+ published security advisories (MCPKernel, v0.3.0, Jul 2026). OWASP released the Agentic AI Security (ASI) Top 10 in June 2026. Your framework ships with neither a policy engine nor an audit trail.

## Forces

- **Policies in prose are advisory, not enforceable.** Prompt instructions like "never delete records" degrade under adversarial input, token pressure, or model version drift. The model can propose any action the LLM can tokenize.
- **The MCP attack surface is structural, not incidental.** OX Security disclosed critical stdio vulnerabilities in MCP SDKs across Python, TypeScript, Java, and Rust (2026). Any MCP server that spawns local processes inherits command-execution surface through stdio. Tool poisoning, misbinding, and context spoofing are documented in OWASP ASI Top 10 (Jun 2026).
- **Deterministic enforcement and LLM autonomy feel contradictory — but they aren't.** The goal is not to remove agent agency. It is to ensure the agent's actions remain within an authorized boundary. A policy kernel says "this action is allowed" — the model still decides what to do and when. The kernel only blocks what the policy forbids.
- **Audit trails without cryptographic integrity are post-hoc theater.** When an agent exfiltrates data, a plain-text log that the agent had write access to is not evidence. Sigstore-signed, tamper-evident records with keyless attestation (GCP OIDC, GitHub OIDC) are.

## The move

Adopt a **policy kernel**: a deterministic enforcement layer that intercepts every tool call at the MCP/A2A gateway, evaluates it against authored policy code, tracks taint propagation through the invocation chain, sandboxes execution, and produces cryptographic audit records. Every tool call — even from an agent acting with high autonomy — hits the kernel first.

### The OWASP ASI Top 10 as your policy surface

The ASI Top 10 (Jun 2026) defines the threat landscape for agentic AI. Map each to a kernel capability:

| ASI# | Vulnerability | Kernel Capability |
|------|-------------|-------------------|
| ASI-01 | Excessive Agency — agents take unintended actions | Policy enforcement: deny undeclared tools by default |
| ASI-02 | Insecure Output Handling — unescaped output triggers downstream | Output sanitization gate, context-aware escaping |
| ASI-03 | Excessive Authority — overly broad permissions | Least-privilege tool binding per agent session |
| ASI-04 | Excessive Agency — goal misalignment via instructions | Intent verification, human-in-the-loop for high-impact calls |
| ASI-05 | Misbinding — tool calls routed to wrong implementation | Schema-signed tool contracts, taint tracking on call routing |
| ASI-06 | Memory Poisoning — untrusted input persists in agent memory | Input sanitization, memory zone isolation, provenance tagging |
| ASI-07 | Resource Exhaustion — runaway token or tool consumption | Per-session resource quotas, deterministic circuit breakers |
| ASI-08 | Training Data Poisoning — corrupted data degrades behavior | Data provenance tracking, training pipeline attestations |
| ASI-09 | Insecure Output Handling — output triggers downstream action | Output classification, sandboxed downstream calls |
| ASI-10 | System Prompt Leakage — indirect injection exfiltrates context | System prompt integrity checks, immutable prompt storage |

### The four-layer enforcement pipeline

Every tool call passes through four deterministic gates before execution:

**Layer 1 — Policy Enforcement (CEL/Rego-based)**

Policies are authored as executable code, not prose. Every tool call is intercepted at the MCP gateway and evaluated against the authored policy set before it reaches the tool implementation:

```python
# mcpkernel policy example (policy expressed as Python dicts)
from mcpkernel import PolicyKernel, ToolManifest

kernel = PolicyKernel()

# Declare allowed tools per agent session
kernel.register_policy({
    "agent_id": "support-agent-v2",
    "allowed_tools": ["search_kb", "lookup_order", "escalate_ticket"],
    "denied_tools": ["read_user_table", "write_db", "exec_shell"],
    "max_tokens_per_session": 50_000,
    "max_tool_calls_per_turn": 10,
    "data_boundary": {"read": ["kb/*", "orders/*"], "write": ["tickets/*"]},
    "audit_level": "full",  # every call is Sigstore-attested
})

# Every tool call is intercepted and denied before execution
# if it violates the policy — no LLM involved in the decision
result = kernel.enforce("support-agent-v2", "read_user_table", {
    "user_id": "12345"
})
# result.denied → True, result.reason → "Tool 'read_user_table' not in allowed set"
# result.sigstore_entry → Sigstore bundle with timestamp, agent ID, call params
```

**Layer 2 — Taint Tracking**

Deterministic tags propagate from input source through every tool call and side effect. Cross-boundary data flows (e.g., output from a third-party MCP server feeding a sensitive tool) are flagged. This blocks the misbinding attack class (ASI-05) where a malicious server returns a response designed to redirect the next tool call:

```python
# Input from untrusted source is tagged automatically
taint_ctx = kernel.taint_tracker.new_context()
taint_ctx.tag("user_query", source="user", sensitivity="low")
taint_ctx.tag("mcp_server_response", source="third_party", sensitivity="high")

# Tool call evaluation checks taint propagation
call_result = kernel.enforce_with_taint(
    "support-agent-v2",
    "send_email",
    {"body": "${mcp_server_response}"},  # tainted input flows to action
)
# Blocked: high-sensitivity taint from third_party source may not flow
# to high-impact action (email send) without human approval
```

**Layer 3 — Sandboxed Execution**

Every tool invocation runs in an isolated execution context. For MCP stdio servers (the OX Security stdio vulnerability class), this means: the tool runs in a firecracker microVM or gVisor sandbox; it cannot read the agent's environment variables, credentials, or filesystem beyond its declared scope; the kernel enforces a timeout and kills the sandbox if it exceeds the allocated wall time.

```python
# Sandboxed tool execution via mcpkernel
kernel.set_sandbox_config({
    "engine": "firecracker",       # or "gvisor", "containerd"
    "max_memory_mb": 256,
    "max_cpu_percent": 50,
    "network_isolation": True,     # no outbound network from sandbox
    "filesystem_scope": ["allowed_reads/*", "/tmp"],
    "env_whitelist": ["LANG", "TZ"],  # only these env vars pass through
})

result = kernel.execute_sandboxed(
    "support-agent-v2",
    "process_document",
    {"doc_path": "/tmp/uploaded_report.pdf"}
)
# Returns result or sandbox_timeout error — never a credential spill
```

**Layer 4 — Sigstore Audit Trail**

Every intercepted call (denied or allowed) is recorded to a tamper-evident log with Sigstore keyless attestation. Entries are signed via GCP OIDC or GitHub OIDC, providing non-repudiation without manual key management. On incident review, the audit log proves exactly what the agent was authorized to do and what it attempted:

```python
# Sigstore-attested audit log entry
audit_entry = {
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "agent_id": "support-agent-v2",
    "tool": "read_user_table",
    "params": {"user_id": "12345"},
    "decision": "denied",
    "reason": "Tool not in allowed_tools for session policy",
    "session_id": "sess_8f3a9c2",
    "model": "claude-sonnet-4-20250514",
    "kernel_version": "0.3.0",
}
sigstore_bundle = kernel.audit_log.record(audit_entry)
# sigstore_bundle → Fulcio-certified Sigstore entry, GCP OIDC attested
# Verify: kernel.audit_log.verify(sigstore_bundle) → True/False
```

### The minimum viable kernel

Not every team needs all four layers on day one. The escalation ladder:

| Stage | Layers | Use Case |
|-------|--------|---------|
| Stage 1 | Policy Enforcement | Block known-dangerous tool calls, deny-by-default |
| Stage 2 | + Taint Tracking | Prevent data exfiltration via tainted cross-boundary flows |
| Stage 3 | + Sandboxed Execution | MCP stdio isolation, credential spill prevention |
| Stage 4 | + Sigstore Audit | Non-repudiation, compliance (EU AI Act Article 14), forensic replay |

The layers compose — do not skip from Stage 1 to Stage 4 without Stage 2–3. Taint tracking without sandboxing leaves stdio injection vectors open. Sandboxing without taint tracking lets malicious tool responses redirect legitimate calls.

### Policy authoring: start with deny-by-default

```python
# Default-deny policy: explicit allowlist per agent
kernel.register_policy({
    "agent_id": "*",              # wildcard: applies to all agents unless overridden
    "allowed_tools": [],          # empty = deny all by default
    "require_approval_for": [
        "write_db", "send_email", "exec_shell",
        "delete_records", "create_user",
    ],
    "audit_level": "full",
})

# Per-agent overrides are more specific
kernel.register_policy({
    "agent_id": "admin-agent-v1",
    "allowed_tools": ["*"],       # full access for explicitly trusted agents
    "require_approval_for": ["delete_db", "revoke_access"],
})
```

## Receipt

> Verified 2026-07-21 — MCPKernel v0.3.0 published on PyPI with 718 tests, ~86% coverage. OWASP ASI Top 10 (Jun 2026) confirms the 10 vulnerability classes map directly to the kernel's four-layer pipeline. OX Security stdio disclosure (2026) confirms sandboxed execution is required, not optional, for MCP stdio servers. EU AI Act Article 14 enforcement activates 2026-08-02 for high-risk systems — Sigstore audit trails directly satisfy the accountability requirement.

## See also

- [S-1450 · The Agent Protocol Threat Matrix](stacks/s1450-the-agent-protocol-threat-matrix-when-your-mcp-server-can-hijack-your-entire-agent-ecosystem.md) — maps the MCP/A2A attack surface; this chapter adds the enforcement layer
- [S-1400 · The Pre-Execution Policy Gate Stack](stacks/s1400-the-pre-execution-policy-gate-stack-when-the-agent-decides-but-the-policy-says-no.md) — execution firewalls; the kernel upgrades them with deterministic taint + Sigstore
- [S-1062 · The MCP Supply Chain Integrity Stack](stacks/s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — supply chain hardening; kernel taint tracking addresses runtime exploitation of compromised tools
