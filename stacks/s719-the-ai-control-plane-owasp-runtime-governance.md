# S-719 · The AI Control Plane: OWASP Runtime Governance in Production

You wrote the policy. Your agent ignores it. The EU AI Act auditor wants the evidence in six weeks. This is not a prompt problem — it is a governance infrastructure problem.

## Forces

- **Policies are documents. Agents are actors.** Written acceptable-use policies, IAM roles, and audit requirements were designed for humans and deterministic services. Agents interpret intent, call tools across trust boundaries, and make consequential decisions autonomously. None of those mechanisms constrain an agent at runtime.
- **The OWASP Agentic Top 10 proves this is not theoretical.** Goal hijacking, tool misuse, memory poisoning, cascading failures, and rogue agents are documented real-world risks — not future concerns. The ATFX/ATF framework and Microsoft AGT are the industry's first deterministic enforcement responses.
- **AIs operate at 10–100× human speed with no natural friction.** A human sending 50 emails an hour triggers alert fatigue. An agent doing it silently is just throughput. The blast radius scales with autonomy.
- **96% enterprise adoption, <5% governance coverage.** IBM Institute for Business Value: 96% of enterprises use AI agents; almost none have runtime controls, cross-agent audit trails, or policy enforcement. The gap between agent deployment and governance coverage is structural, not a training problem.
- **The EU AI Act (August 2026) and Colorado AI Act (June 2026) make this legally urgent.** High-risk AI obligations now require audit trails, transparency, and conformity assessments. Agents in the wild cannot satisfy them without a control plane.

## The Move

An AI Control Plane is a runtime governance layer that sits between agents and their environment — enforcing what agents are allowed to do, logging what they did, and proving it to auditors. It is not a prompt guardrail or an LLM wrapper. It is infrastructure.

### Architecture: Three planes

```
┌─────────────────────────────────────────────────────────┐
│                  CONTROL PLANE                          │
│  Policy Store  │  Evaluator Chain  │  Audit Log         │
└────────────────────────┬────────────────────────────────┘
                         │ enforce / deny / log
┌────────────────────────▼────────────────────────────────┐
│                   DATA PLANE                             │
│  Agent  │  Tool calls  │  External systems  │  Other agents │
└─────────────────────────────────────────────────────────┘
```

**Control plane** (governance): What agents may do — policy decisions, permission checks, OWASP enforcement. **Data plane** (execution): Where agents run and interact.

### The five OWASP-runtime enforcement targets

| Risk | Control Mechanism |
|------|-------------------|
| A01: Goal hijacking | Policy gate on tool combinations; intent drift detection |
| A02: Tool misuse | Scoped OAuth token issuance per call; permission matrix |
| A03: Memory poisoning | Snapshot verification; anomaly scoring on memory writes |
| A04: Cascade failures | Circuit breaker at control plane; propagation blocking |
| A05: Rogue agents | Identity attestation; non-human identity audit trail |

### Policy Store pattern

Policies live in versioned, auditable artifacts — not scattered across prompts or application code.

```yaml
# policy_store/customer_onboarding_v2.yaml
version: "2.0"
scope:
  agent: customer-onboarding-agent
  environment: production
tools:
  allowed:
    - query_customer_db
    - update_crm
    - send_welcome_email
  denied:
    - delete_customer_record
    - transfer_funds
    - modify_pricing
rate_limits:
  send_welcome_email: 100/minute
  query_customer_db: 1000/minute
audit:
  log_level: full   # every call, every denial, every context window summary
escalation:
  denied_action: log + alert + human_review
  cascade_failure: suspend_agent + notify_ops
```

### Evaluator chain (pluggable)

Multiple evaluators run in sequence. Any `deny` short-circuits the call and writes to the audit log.

```python
from agent_governance import ControlPlane, PolicyStore

control_plane = ControlPlane(
    policy_store=PolicyStore("s3://policies/production/"),
    evaluators=[
        OWASPGoalHijackingEvaluator(),   # intent drift on multi-step calls
        ToolPermissionEvaluator(),        # OAuth scope per call
        RateLimitEvaluator(),             # per-agent, per-tool rate gates
        PIIClassifier(),                  # PII in outputs → redact + alert
        CustomBusinessLogicEvaluator(),   # domain-specific rules
    ],
    audit_sink=OpenTelemetrySink(),
)

result = control_plane.enforce(agent_id="onboarding-v3", tool_call=request)
# result: ALLOW | DENY | DENY_ESCALATE
```

### Non-human identity attestation

Every agent action is stamped with a cryptographic identity:

```json
{
  "agent_id": "customer-onboarding-v3",
  "non_human_identity_id": "nhi_01HX4K...",
  "policy_version": "v2.0",
  "action": "send_welcome_email",
  "timestamp": "2026-07-06T09:15:22Z",
  "evaluator_chain_result": "ALLOW",
  "trace_id": "abc123def456"
}
```

### The Microsoft Agent Governance Toolkit (AGT)

Microsoft's open-source [agent-governance-toolkit](https://github.com/microsoft/agent-governance-toolkit) (MIT, Apr 2026) is the reference implementation. It covers all 10 OWASP risks with deterministic enforcement, sub-millisecond p99 latency, and multi-framework support (LangChain, AutoGen, CrewAI, custom). One `pip install agt` gets a control plane into any agent stack.

```bash
pip install agt
agt init --policy-dir ./policies --framework langgraph
agt run --agent ./agent.py --enforce
```

## Receipt

> Verified 2026-07-06 — Microsoft Agent Governance Toolkit (`pip install agt`) released 2026-04-02 (MIT, microsoft/agent-governance-toolkit). OWASP Top 10 for Agentic AI published December 2025. EU AI Act high-risk obligations effective August 2026. IBM IBV: 96% enterprise adoption. Sub-millisecond enforcement latency confirmed in docs. Python 3.10+ required. S-718 (MCP security) and S-417 (failure modes) are complementary; this entry covers the cross-cutting policy/enforcement layer they require.

## See also

- [S-718 · MCP Won — Now Fix the Security Model](s718-mcp-standard-won-but-security-is-still-in-alpha.md) — MCP servers are the primary target surface for tool-misuse attacks AGT addresses
- [S-417 · Agent Failure Mode Taxonomy and Self-Healing Architecture](s417-agent-failure-mode-taxonomy-and-self-healing-architecture.md) — cascade failures (A04) and watchdog patterns complement control plane enforcement
- [S-417 · Agent Failure Mode Taxonomy](s417-agent-failure-mode-taxonomy-and-self-healing-architecture.md) — A01 goal hijacking detection builds on the loop detector / intent drift concepts
- [S-713 · Agent Eval Cost Governance](s713-agent-eval-cost-governance-the-unseen-liability.md) — governance and cost controls are co-deployed; policy store + audit trail covers both
