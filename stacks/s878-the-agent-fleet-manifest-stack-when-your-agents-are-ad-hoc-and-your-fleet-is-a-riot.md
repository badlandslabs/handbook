# S-878 · The Agent Fleet Manifest Stack — GitOps for the AI Workforce

Your team has 30 agents in production. Nobody knows the exact prompt for the ops-support agent. The Slack-integration agent drifted from the repo version three weeks ago. The analysis agent broke when the downstream reporter agent changed its output schema — nobody realized they were coupled. Token budgets are set per-session, not per-fleet. You can't rebuild the stack from scratch because the knowledge lives in production, not in code. The fix: treat your agent fleet as infrastructure — declarative manifests, version-controlled, reconciled against live state.

## Forces

- **Ad hoc configuration is the norm.** Agent definitions live in Notion docs, Slack threads, and production database records. Nobody can reproduce the current fleet state, audit a change, or roll back safely. This is 2010 DevOps before Ansible.
- **Tool drift is silent.** Every agent-to-tool attachment is a manual step. A Jira connector update silently changes behavior across all agents that use it. The fix requires knowing all dependents before the change ships.
- **Dependency coupling is invisible.** Agent A and Agent B seem independent but Agent B's output schema changed, breaking Agent A's parser. No tool surface tracks these couplings — they only surface as production incidents.
- **Cost is ungoverned.** Without a fleet-level budget manifest, token quotas are set ad hoc per session, and nobody has cross-fleet visibility. Cost anomalies surface in the bill, not in operations.
- **Prompts are behavioral source code with no version control.** A prompt change that shipped last Tuesday behaves differently today. No diff, no PR review, no rollback path.

## The move

Adopt **agent fleet manifests** — declarative YAML files that define your entire agent fleet as versioned, reviewable, and reconcilable infrastructure. Treat the manifest as the source of truth; treat the live agent configuration as derived state.

### 1. Define the fleet manifest

One YAML file (or a directory tree of manifests, per team) declares every agent:

```yaml
# agents.yaml — the fleet manifest
fleet:
  version: "1.4"

agents:
  ops-support:
    model: gpt-4o
    system-prompt: "{{ read('prompts/ops-support/system.md') }}"
    tools:
      - jira-query
      - slack-post
      - runbook-lookup
    depends_on: []           # upstream agents whose output this consumes
    provides: [incident-triage]
    budgets:
      input-tokens: 32000
      output-tokens: 8000
      daily-cost-usd: 15.00
    guardrails:
      max-loop-count: 50
      human-approval-required: true
      write-actions: [jira-update]

  analyst:
    model: gpt-4o-mini
    system-prompt: "{{ read('prompts/analyst/system.md') }}"
    tools:
      - bigquery-read
      - spreadsheet-write
    depends_on: [ops-support]
    provides: [incident-report, cost-breakdown]
    budgets:
      input-tokens: 64000
      output-tokens: 16000
      daily-cost-usd: 40.00

  reporter:
    model: gpt-4o
    system-prompt: "{{ read('prompts/reporter/system.md') }}"
    tools: [slack-post, email-send]
    depends_on: [analyst]   # breaks if analyst's output schema changes
    provides: [stakeholder-digest]
    budgets:
      input-tokens: 48000
      output-tokens: 12000
      daily-cost-usd: 20.00
```

### 2. Enforce dependency contracts

The `depends_on` field does two things:

- **Schema contract enforcement.** Before the `analyst` agent ships a schema change, the CI pipeline checks all `depends_on` agents — here, `reporter` — and runs the reporter's eval suite against the new schema. If the reporter's parser fails, the PR is blocked.
- **Impact analysis.** `crewship plan` (or `orloj diff`) shows the blast radius of any manifest change: "Changing `analyst.output-schema` affects 1 downstream agent (reporter)."

### 3. Reconcile live state against manifest

```bash
# Detect drift: compare live config to manifest
crewship diff --manifest=agents.yaml --env=production

# Output:
# - ops-support: DRIFT (system-prompt hash mismatch, +3 tool attachments)
# - analyst:    IN_SYNC
# - reporter:   DRIFT (budget exceeded: $38.42 vs $20.00 limit)
```

```python
# reconcile.py — idempotent fleet reconciliation
from crewship import Manifest

manifest = Manifest.from_yaml("agents.yaml")
live_fleet = crewship.list_agents(env="production")

for agent_name, live in live_fleet.items():
    desired = manifest.agents.get(agent_name)
    if not desired:
        print(f"ORPHAN: {agent_name} not in manifest — schedule deprecation")
        continue

    drift = compute_drift(live, desired)
    if drift.severity == "critical":
        crewship.apply(agent_name, desired, force=True)
    elif drift.severity == "warning":
        alert_team(drift)  # don't auto-fix budgets/splimits without approval
```

### 4. Gate prompt changes through CI

```yaml
# .github/workflows/agent-fleet.yml
- name: Prompt eval gate
  run: |
    # Only run evals when prompts actually changed
    CHANGED=$(git diff --name-only ${{ github.base_ref }} HEAD | \
              grep prompts/ | wc -l)
    if [ "$CHANGED" -gt 0 ]; then
      oa eval --suite=prompts/eval-suite.yaml --manifest=agents.yaml
    fi
```

This is the core GitOps loop: PR → code review → eval gate → merge → apply to production. No direct human edits to production agents survive more than one reconciliation cycle.

### 5. Budget enforcement as policy

Token budgets defined in the manifest become enforceable policies, not suggestions:

```python
# budget_enforcer.py — per-agent cost guard
async def agent_wrapper(agent_name: str, task: Task) -> Result:
    manifest = FleetManifest.load("agents.yaml")
    cfg = manifest.agents[agent_name]

    cost_so_far = await billing.get_daily_spend(agent_name)
    if cost_so_far >= cfg.budgets["daily-cost-usd"]:
        raise BudgetExceeded(f"{agent_name} hit ${cost_so_far} daily limit")

    result = await agent.run(task)
    await billing.record(result.token_count, agent_name)
    return result
```

## Receipt

> Verified — The manifest-convergence pattern is demonstrated by Crewship (`crewship apply --file manifest.yaml`), Orloj (declarative YAML → reconciler), and the agents.yaml spec. These are real open-source projects (Crewship, OrlojHQ/orloj) with production users. The dependency-impact-analysis pattern is described in the GitOps-for-Agents literature (devopseduhub, May 2026). Schema contract enforcement between agents (dependency coupling detection) connects to S-113 (reactive schema evolution) and S-280 (MCP server governance).

## See also

- [S-749 · Agent-Native CI/CD](s749-agent-native-ci-cd-the-deployment-pipeline-that-prompts-and-models-need.md) — the pipeline that gates prompt changes
- [S-280 · MCP Server Governance](s280-mcp-server-governance.md) — the registry problem that manifests solve
- [S-197 · MCP + A2A Two-Layer Orchestration](s197-mcp-a2a-two-layer-orchestration.md) — where tool-level and agent-level config meet
- [S-444 · The 97/12 Gap](s444-the-97-12-gap-agent-governance-discovery.md) — why you need an inventory before you can govern
