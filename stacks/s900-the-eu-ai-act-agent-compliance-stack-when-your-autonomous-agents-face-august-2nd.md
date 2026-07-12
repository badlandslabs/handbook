# S-900 · The EU AI Act Agent Compliance Stack — When Your Autonomous Agents Face August 2nd

The EU AI Act's high-risk obligations took effect on August 2, 2026. Your agents write contracts, approve expenses, triage healthcare data, and make credit decisions — all autonomously. The Act does not use the word "agent" once across its 113 articles, yet every one of those decisions now falls under legal obligation. Most engineering teams have no idea what that means technically. This entry maps it.

## Forces

- **The Act treats autonomy as a risk amplifier.** The more consequential the decisions your agent makes without human review, the higher its classification burden and the stricter its controls must be.
- **Multi-agent systems are one system.** The May 2026 Digital Omnibus clarified: a fleet of agents coordinating to produce a single outcome is a single regulated AI system. One agent's output feeds another's input — the entire pipeline is what gets audited.
- **"We have a policy document" is not compliance.** Article 9 requires a real-time risk management system. Article 12 requires machine-readable, immutable audit logs per decision. Article 14 requires a functional stop mechanism — not a memo about one.
- **82% of enterprises have agents their security teams don't know exist** (Zylos Research, May 2026). The compliance gap is also a discovery problem.

## The move

### 1. Classify your agents against the risk tier

Not all agents face the same obligations. Map every deployed agent to a tier before designing anything:

| Tier | Triggers | Examples | Core Obligations |
|------|----------|----------|----------------|
| **Unacceptable** | Deceptive manipulation, social scoring | — | Banned outright |
| **High-Risk** (Annex III) | Education, employment, credit, healthcare, critical infrastructure, law enforcement | Loan approval agent, CV screening agent, medical triage agent | Articles 9–15: full risk management, data governance, transparency, human oversight, accuracy, security, conformity assessment |
| **Limited Risk** | chatbots, content generation | Customer support agent, draft writer | Article 50: transparency obligations only (disclose AI interaction) |
| **Minimal Risk** | Spam filter, internal tooling | Log analysis agent, code reviewer | No mandatory obligations (voluntary codes apply) |

**The autonomy amplifier:** An agent that makes consequential decisions autonomously (no human in the loop) is more likely to land in high-risk territory than the same agent with mandatory human review gates. This means the autonomy level (S-355) and the compliance tier are the same design decision, not separate ones.

### 2. Build the Article 12 Audit Trail — per decision, immutable, machine-readable

Article 12 requires logging that enables traceability of every AI-generated decision. For agentic systems this means:

```python
# Structured audit log schema per agent decision cycle
@dataclass
class AgentAuditEntry:
    task_id: str                      # stable across retries
    agent_id: str                     # which agent
    autonomy_level: int               # S-355 L0–L5
    system_version: str               # prompt + model + tool versions (S-584)
    input_hash: str                   # SHA-256 of task input (GDPR: no PII in logs)
    decision_rationale: dict          # structured reason, not free text
    tools_invoked: list[ToolCall]     # every tool, every attempt
    output_hash: str                  # SHA-256 of agent output
    human_override: bool              # did a human intervene?
    override_rationale: str | None    # if so, why
    timestamp_utc: datetime
    trace_id: str                     # cross-agent correlation (S-799)
    session_id: str                   # MCP session (S-870)
    nhi_credentials_used: list[str]    # non-human identities (S-572)

    def to_immutable_record(self) -> bytes:
        """Write once — append-only, no in-place mutation."""
        import json
        return json.dumps(asdict(self), default=str).encode()
```

Storage requirements: append-only (WORM/imm不可篡改), minimum 5-year retention, exportable in standard format for regulator access. Cloud object storage with bucket immutability + S3 Object Lock is the minimum viable implementation.

### 3. Implement Article 14 Human Oversight — the functional stop button

Article 14 requires that high-risk agents include "effective human oversight measures." For agentic systems, this means at minimum:

**Runtime halt capability** — a kill switch that stops the agent loop mid-execution, not just at session end. This requires the orchestration layer to support interruption signals that drain the pending task queue and persist current state for review.

```python
async def halt_agent(agent_id: str, task_id: str, reason: str) -> HaltReceipt:
    # 1. Send interrupt signal to orchestration layer
    await orchestrator.interrupt(task_id)
    # 2. Persist current state snapshot
    state_snapshot = await agent_store.snapshot(task_id)
    # 3. Log halt event to audit trail
    await audit.log(HaltEvent(agent_id, task_id, reason, state_snapshot.hash))
    # 4. Notify human reviewer
    await notify_supervisor(agent_id, task_id, state_snapshot.summary)
    return HaltReceipt(task_id, state_snapshot.id, halt_time=utcnow())
```

**Override logging** — every human override is itself a record that must be auditable. The override rationale feeds back into the risk management loop (Article 9 continuous improvement cycle).

**Escalation thresholds** — define what triggers a human review gate. Common patterns:
- Confidence score below threshold (requires calibrated scoring — S-857)
- Dollar value exceeds cap (financial agents)
- Action targets a high-risk data category (health, biometric, financial)
- Agent loops more than N times without progress (S-880 circuit breaker)

### 4. Run the Article 9 Risk Management Cycle — continuous, not annual

Article 9 requires an ongoing risk management process, not a one-time compliance checkbox:

1. **Identify** — map every agent to its risk tier; identify novel risks from agent combinations (architectural debt of composition — S-893)
2. **Evaluate** — for high-risk agents: what is the worst outcome per failure mode? Likelihood × severity
3. **Mitigate** — implement controls: autonomy gates (S-355), compensation keys (S-352), capability bucketing (S-889), ambient authority controls
4. **Monitor** — continuous behavioral drift detection (S-885), MCP security scanning, eval stamps (S-882)
5. **Update** — risk management system must adapt as agents evolve. A low-risk agent promoted to high-risk triggers re-classification.

### 5. Handle the multi-agent pipeline as one regulated system

When multiple agents coordinate, the May 2026 Omnibus means the compliance obligation flows through the entire pipeline. Design for this:

- **Shared audit context** — propagate `trace_id` (S-799) and `task_id` across every agent handoff so regulators can reconstruct the full decision chain from a single entry point
- **Upstream accountability** — the deploying organization bears responsibility for all agents in the pipeline, including third-party agents called via A2A (S-14) or MCP (S-10)
- **Conformity assessment** — document the full pipeline, not individual agents. A single non-compliant node in a chain makes the chain non-compliant

## Receipt

> Verified 2026-07-10 — Chapter written from:
> - EU AI Act full text (Articles 9, 12, 13, 14, 16, 17, 50, 99)
> - The Agent Report (2026-06-24): EU AI Act regulatory reckoning analysis
> - Kakunin EU AI Act compliance guide for autonomous agents
> - Zylos Research (2026-05-01): AI Agent Governance and Compliance in 2026
> - Tigera (2026-04-17): Accountability — the bottleneck for enterprise agents
> - Gheware DevOps Guide: EU AI Act Audit Trails & Kill Switches (2026)
> - Cordum EU AI Act for AI Agents (2026)
> - Thinking Inc: AI Agent Governance Framework for Enterprise (2026-03-12)
> - 80% of orgs encountered risky agent behavior (McKinsey, cited by Tigera); only ~33% report governance maturity
> - 82% of enterprises have agents security teams don't know exist (Zylos, May 2026)
> - EU AI Act Article 99 penalties: €35M or 7% global turnover for prohibited practices; €15M or 3% for high-risk obligations violations
> - May 2026 Digital Omnibus: multi-agent systems treated as single regulated system
> - Fines have not yet been issued under the new obligations — the enforcement infrastructure is still being built — but the obligations are in force

## See also

- [S-355 · Agent Autonomy Levels: The Bounded Autonomy Pattern](s355-agent-autonomy-levels-bounded-autonomy.md) — maps to compliance tier; autonomy level IS the risk classification decision
- [S-572 · The Context Window Credential Leak Stack](s572-the-context-window-credential-leak-stack-when-the-context-window-becomes-the-credential-store.md) — NHI blast-radius control, required for Article 17 data governance
- [S-584 · Agent Versioned Release Bundles](s584-agent-versioned-release-bundles-the-release-engineering-discipline-ai-never-had.md) — system version tracking required for Article 12 traceability
- [S-889 · The Ambient Authority Stack](s889-the-ambient-authority-stack-when-your-agent-did-something-you-never-authorized.md) — least-privilege tooling for Article 14 human oversight
- [S-799 · Cross-Agent Trace Correlation](s799-the-error-taxonomy-stack-failure-classification-before-recovery.md) — audit trail construction across delegation boundaries
- [S-799 · Cross-Agent Trace Correlation](s799-the-error-taxonomy-stack-failure-classification-before-recovery.md) — trace_id propagation across multi-agent pipelines
- [S-870 · MCP Session Architecture](s870-the-mcp-session-architecture-stack-when-the-protocol-was-built-for-demos-and-youre-in-production.md) — session-scoped logging for Article 12 compliance
- [F-42 · AI Incident Response](forward-deployed/f42-ai-incident-response.md) — post-incident response procedure for compliance breaches
