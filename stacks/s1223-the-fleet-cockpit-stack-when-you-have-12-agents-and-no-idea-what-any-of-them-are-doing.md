# S-1223 · The Fleet Cockpit Stack — When You Have 12 Agents and No Idea What Any of Them Are Doing

You deployed your first agent six months ago. Now you have 12 agents across the org — customer support, code review, data extraction, research, procurement approval — and nobody has a single view of the fleet. One agent is looping on a sensitive task. Another ran for 47 minutes and nobody noticed it failed. A third is costing $3,200/month and nobody can explain why. Your security team just discovered three agents they didn't know existed. This is the fleet management gap: having a workforce without a control room.

## Forces

- **Agents proliferate faster than governance.** The pattern is consistent: individual teams spin up agents to solve immediate problems, with no fleet-level visibility. By the time central teams notice, there are a dozen agents across five teams, each with different auth contexts, tool access, and failure modes.
- **Fleet behavior is not the sum of individual agent views.** Single-agent dashboards show you what one agent is doing. Nobody can tell you: which agents are currently running, what the aggregate cost trajectory is, which tasks are blocked on approval, and which agents have hit an error in the last hour — all at once.
- **The management plane lags the execution plane by 6-12 months.** Every team can deploy an agent in a day. The org-wide fleet management infrastructure takes months to design and build. Teams ship agents before the governance layer exists.

## The move

The fleet cockpit is the single operational interface that surfaces the entire agent workforce as one governed system. It is not a monitoring dashboard — it is a management plane. Six capabilities define a minimum viable fleet cockpit:

### 1. Cockpit View — Fleet-Wide State

A single pane showing every agent's status without context-switching.

**Must display:**
- Running agents: current task, tool in use, elapsed time, estimated cost to date
- Queued: tasks waiting for agent availability or human approval
- Blocked: tasks suspended on a dependency, gate, or rate limit
- Completed: recent completions with success/failure and cost
- Health signals: error rate, avg session duration, tokens/task

```
Fleet Overview — Last 60s
─────────────────────────────────────────────
Running:  7 agents   Avg cost/task: $0.43
Queued:   3 tasks   Error rate:      1.2%
Blocked:  2 (1 awaiting approval, 1 rate-limited)
─────────────────────────────────────────────
```

### 2. Identity Registry — What Each Agent Is and Who Owns It

Every agent must have a structured identity record in the registry before it is provisioned:

- **Owner team** and **business owner** (human accountable)
- **Purpose statement** — what the agent is allowed to do (not allowed is separate)
- **Tool scope** — exactly which tools, APIs, and data sources the agent can access
- **Auth context** — which identity/service account it runs under
- **Risk tier** — low (read-only, no external calls), medium (writes within sandbox), high (external calls, financial actions, PII access)
- **Approval chain** — who must approve high-risk actions before execution

```
Agent: customer-support-v3
Owner: CX Platform Team / Maria Santos
Purpose: Answer FAQ, route escalations, update ticket status
Tool scope: [zendesk_read, zendesk_write, knowledge_base_search, faq_lookup]
Auth context: svc-cx-platform@company.com (least-privilege)
Risk tier: MEDIUM
Approval chain: None for FAQ; Maria Santos for escalations
```

### 3. Provisioning Gate — No Agent Deploys Without Registry Entry

Agents that skip the registry are shadow agents. The provisioning gate enforces the catalog-first sequence:

1. Agent developer submits registry entry for review
2. Security reviews tool scope and auth context
3. Risk tier assigned
4. If HIGH risk: approval gate configured before deployment
5. Agent provisioned with credentials scoped to its registry entry
6. Fleet cockpit begins receiving telemetry

This is the only way to close the "82% of agents discovered without security's knowledge" gap.

### 4. Intervention Surface — Act Across the Fleet

Visibility without actionability is a dashboard, not a cockpit. The fleet management plane must support:

- **Suspend**: pause an agent mid-task cleanly (state preserved, not killed)
- **Kill**: hard terminate with mandatory reason code
- **Throttle**: reduce concurrency limit or rate for a specific agent
- **Escalate**: promote a blocked task to human review queue
- **Inspect**: pull full session trace for any running or recent agent
- **Scope-revoke**: remove a specific tool or data source from an agent without redeploying

### 5. Cost Attribution — Per-Agent, Per-Task, Per-Team

Token costs are not evenly distributed. A single multi-turn agent task can cost 50x a simple lookup. Fleet-level cost management requires:

- **Per-agent spend tracking**: cumulative cost per agent per billing period
- **Per-task cost breakdown**: what drove the cost (model tier, token volume, tool calls)
- **Per-team chargeback**: aggregate cost by owning team for budget attribution
- **Anomaly detection**: alert when an agent's cost/task deviates >2σ from its baseline
- **Budget caps**: hard stop or approval required when an agent or team hits its monthly AI budget

### 6. Drift Detection — Fleet Configuration as Code

Agent configurations drift. A developer updates an agent's prompt without a registry update. A new tool gets added to an agent's toolkit but the security review never runs. Fleet configuration must be treated as code:

- Registry entries live in versioned config (GitOps)
- Agent configs compared against registry on every startup
- Drift flagged as a security event: "Agent customer-support-v3 has tool scope drift: zendesk_admin added without registry update"
- Automated remediation: revert to last-known-good config or suspend agent pending re-approval

### The Full Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    FLEET COCKPIT                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │ Cockpit  │ │ Identity │ │ Provision│ │Intervene │      │
│  │  View    │ │ Registry │ │   Gate   │ │ Surface  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│  ┌──────────┐ ┌──────────┐                               │
│  │  Cost    │ │  Config  │                               │
│  │Attribution│ │  Drift   │                               │
│  └──────────┘ └──────────┘                               │
├─────────────────────────────────────────────────────────────┤
│                 AGENT FLEET (12-100s of agents)            │
│  [customer-support] [code-review] [research] [procurement]   │
│  [data-extraction] [ticket-triage] [financial-approval]     │
├─────────────────────────────────────────────────────────────┤
│              CONTROL PLANE (Registry · Policy · Audit)      │
└─────────────────────────────────────────────────────────────┘
```

### What This Prevents

Without the fleet cockpit, the failure mode is always the same: agents proliferate → incidents accumulate → security discovers them → scramble to govern retroactively → more incidents → regulatory exposure. The EU AI Act Article 12 logging requirements, the Singapore MII framework's human accountability mandate, and internal audit obligations all require a fleet-level management plane. You cannot satisfy any of them with individual agent dashboards.

### Getting Started

1. **Week 1**: Inventory every agent currently running. If it's not in a spreadsheet, it doesn't exist yet — but it exists.
2. **Week 2-3**: Assign every discovered agent a risk tier and an owner. Register the high-risk ones first.
3. **Month 2**: Instrument all agents with fleet telemetry (agent_status, task_start, task_end, token_count, error_code).
4. **Month 3**: Build the cockpit view. Start with status + cost. Add drift detection once the registry is populated.
5. **Month 4+**: Wire in the provisioning gate for new agents. Make registry entry a hard prerequisite.

```python
# Minimal fleet agent record schema
class AgentRecord(BaseModel):
    agent_id: str                      # unique identifier
    name: str                          # human-readable name
    owner_team: str                    # team accountable
    business_owner: str                 # human owner email
    purpose: str                       # one-sentence description
    tool_scope: list[str]              # permitted tools
    auth_context: str                  # service account
    risk_tier: Literal["LOW", "MEDIUM", "HIGH"]
    approval_chain: list[str]           # approver emails for HIGH actions
    registry_version: str              # git SHA of last approved config
    status: Literal["active", "suspended", "deprovisioned"]

    def is_compliant(self, running_config: dict) -> bool:
        return (
            set(running_config.get("tool_scope", []))
            .difference(self.tool_scope) == set()
            and running_config.get("registry_version") == self.registry_version
        )
```
