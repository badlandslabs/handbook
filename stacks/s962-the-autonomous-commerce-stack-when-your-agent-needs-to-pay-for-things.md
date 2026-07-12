# S-962 · The Autonomous Commerce Stack: When Your Agent Needs to Pay for Things

MCP connects agents to tools. A2A connects agents to agents. AP2 connects agents to money. The first two layers were hard. This one is harder — because money introduces accountability, fraud, and regulatory obligations that tooling and delegation never did. If your agent can call a paid API, hire a peer agent, or settle a dispute autonomously, you have an autonomous commerce system. The engineering decisions that make it safe are the subject of this entry.

## Forces

- **Agents as economic principals is no longer hypothetical.** Locus, Stripe Agent SDK, and emerging AP2 implementations are live in 2026. Agents can now hold balances, authorize charges, and complete financial transactions without human co-signature. The compliance and security implications arrive before most teams have thought through the governance model.
- **The four-layer stack is the 2026 reference architecture.** MCP (vertical: agent→tool), A2A (horizontal: agent↔agent), AP2 (financial: agent→money), and ANP (discovery: agent→network). S-414 introduced this thesis; this entry covers the AP2 layer specifically — the hardest and least-documented one.
- **Payment authorization in autonomous systems breaks every fraud model built for humans.** Human payment fraud detection looks for anomalies relative to human behavior. An agent spending $3,000 in one minute on API calls isn't fraud — it might be a legitimate automated pipeline. Traditional fraud controls generate false positives that halt legitimate agent workloads.
- **"Receipt pending" is not an acceptable state for a financial transaction.** Unlike a tool call that returns a wrong answer (correctable), a financial transaction that completes without fulfillment is a real money event. The compensation model for agents (S-352) must now include a payment reversal layer.

## The move

### The four-layer stack in production

```
User Intent
    ↓
Agent (LLM + Harness)
    ├── MCP Layer → Paid Tools / Data APIs
    ├── A2A Layer → Peer Agent Delegation
    └── AP2 Layer → Wallet / Payment / Settlement
                    ↑
              ANP Discovery ← Agent Registry
```

Each layer has its own protocol, its own auth model, and its own blast radius on failure.

### Permissioned wallet per agent

Never give an agent a shared corporate account. Each agent gets a dedicated wallet with scoped permissions:

```python
from locus import AgentWallet, PaymentPermission, SpendLimit

wallet = AgentWallet(
    agent_id="customer-researcher-v3",
    owner_hierarchy="acme-corp.eng.team",
)

# Scope: only the tools this agent is authorized to pay for
wallet.add_permission(PaymentPermission(
    recipient="data-provider-api",
    max_per_transaction=50.00,
    max_daily=500.00,
    requires_receipt=True,        # must verify outcome before settlement
    escrow_enabled=True,          # hold funds until task completion
))

wallet.add_permission(PaymentPermission(
    recipient="peer-agent-registry",
    max_per_transaction=25.00,
    max_daily=150.00,
    requires_receipt=True,
    escrow_enabled=True,
))

# Emergency brake
wallet.set_global_spend_limit(1000.00)  # hard cap per billing period
wallet.set_suspension_policy(
    alert_at_pct=0.8,
    auto_suspend=True,
    notify=["acme-security@company.com", "acme-eng-oncall"]
)
```

### Escrow for multi-step tasks

For tasks where payment must follow verified fulfillment (e.g., a research agent pays a data-retrieval agent):

```python
from locus import EscrowPayment, ReleaseCondition

escrow = wallet.escrow(
    amount=15.00,
    recipient="data-fetcher-agent",
    release_conditions=[
        ReleaseCondition(
            type="tool_result_verified",
            tool="final_report_delivery",
            check="content_hash_matches",
            timeout_seconds=300,
        ),
        ReleaseCondition(
            type="llm_judge_approved",
            judge_prompt="Did the data fetcher deliver the requested dataset "
                         "matching the query parameters? Reply only 'yes' or 'no'.",
            threshold=0.9,
        ),
    ],
    on_timeout="release_funds_back",
)
# Funds are held. If neither release condition fires in 5 minutes,
# funds return to the agent wallet automatically.
```

### Payment authorization gate

Financial actions require a separate authorization decision from the execution decision. The agent decides *what to do*; the wallet decides *whether it can pay*:

```python
# Agent wants to call a paid API
plan = agent.plan(task)
estimated_cost = wallet.estimate(plan)  # looks up vendor pricing

if wallet.can_afford(estimated_cost):
    auth_token = wallet.authorize(plan, estimated_cost)
    result = agent.execute(plan, payment_token=auth_token)
    wallet.settle(result, escrow=escrow)
else:
    # Fall back to cheaper alternative or escalate
    wallet.flag_for_review(plan, estimated_cost)
    fallback_plan = agent.plan(task, budget_constraint=wallet.balance)
```

This is the payment equivalent of the read/write gate in S-355. The financial gate is orthogonal to the autonomy level — an L5 fully autonomous agent still needs a funded, authorized wallet.

### SLA-backed payment for agent-to-agent work

When one agent hires another, AP2 enables payment conditioned on outcome:

```python
from locus import SLAPayment, SLAVebalTerms

sla_payment = wallet.create_sla_payment(
    provider="specialist-agent-firm",
    task_description="Extract contact info for 500 companies from LinkedIn",
    payment_amount=75.00,
    sla_terms=SLAVebalTerms(
        delivery_deadline_minutes=120,
        accuracy_threshold=0.95,
        refund_pct_perViolation=0.25,
        arbitration="llm-judge:accuracy",
    ),
)

# Payment released only if SLA conditions are met.
# Disputes go to LLM-as-judge arbitration with human appeal path.
```

### Monitoring: financial observability for agents

Agent payment monitoring is distinct from cost monitoring (S-103, S-311):

```python
from locus import PaymentAlert

# Alert when spend pattern changes (potential prompt injection or bug)
wallet.monitor(PaymentAlert(
    condition="dau_spend_stddev > 3",  # flag if daily spend exceeds 3σ
    action="slack: #agent-finance-alerts",
))

wallet.monitor(PaymentAlert(
    condition="new_recipient_authorized",
    action="email: acme-security + human_approval_required",
))

wallet.monitor(PaymentAlert(
    condition="refund_rate > 0.05",
    action="pause_all_payments + incident_ticket",
))
```

### Compliance: agent financial identity

Autonomous financial transactions require the agent to have a financial identity that satisfies AML/KYC requirements. This is where agent identity governance (S-420) meets agent payments:

```python
# Agent financial identity must be linked to a corporate identity
wallet.register_financial_identity(
    agent_id="customer-researcher-v3",
    corporate_owner="acme-corp",
    kyc_reference="kyc-2026-00789-acme",
    jurisdiction="US",
    transaction_limits={
        "daily": 5000.00,
        "monthly": 50000.00,
    },
    regulatory_flags=["aml_screened", "sar_eligible"],
)
```

EU AI Act Article 16 and Colorado SB-205 (effective August 2026) both require audit trails for automated decision-making that affects financial outcomes. AP2 transactions must be logged with the same immutable audit chain as S-941's agent audit log.

## Receipt

> Receipt pending — 2026-07-11. Core concepts synthesized from Locus agent payment infrastructure docs (2026), Stripe Agent SDK (2025-2026 GA), Zylos Research protocol convergence notes (2026), CSA NHI governance framework (2026), and AP2 protocol spec (agent-network-protocol.com, 2026). Locus and Stripe Agent SDK patterns are live in production at enterprise adopters. AP2 spec is available at agent-network-protocol.com/specs/ but the payment layer spec itself is early-stage (v0.9 as of July 2026). Escrow and SLA-backed patterns are derived from financial services best practices applied to agent contexts. The code examples are realistic architectural patterns — not from a runnable open-source library yet, as no canonical AP2 implementation library exists. Monitor agent-network-protocol.com for spec maturation and AP2 library releases.

## See also

- [S-352 · Agentic Compensation Keys](s352-the-compensation-key-stack-when-your-agent-must-survive-restarts.md) — idempotency and compensation patterns that underpin safe autonomous transactions
- [S-355 · Bounded Autonomy Levels](s355-bounded-autonomy-stack-the-safer-agentic-architecture.md) — the autonomy model that should govern financial decision thresholds
- [S-414 · The Protocol Convergence Thesis](s414-the-protocol-convergence-thesis.md) — the four-layer stack (MCP + A2A + AP2 + ANP) that this entry completes
- [S-420 · Agent Identity Governance](s420-the-agent-identity-governance-stack-the-ai-principal-paradigm.md) — financial identity and compliance requirements for autonomous agents
- [S-941 · Agent Audit Chain](s941-the-agent-audit-chain-eu-ai-act-logging-for-multi-agent-systems.md) — immutable logging for financial audit trails under EU AI Act and Colorado SB-205
