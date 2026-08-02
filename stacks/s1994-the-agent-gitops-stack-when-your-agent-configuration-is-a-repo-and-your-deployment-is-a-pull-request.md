# S-1994 · The Agent GitOps Stack — When Your Agent Configuration Is a Repo and Your Deployment Is a Pull Request

*When you have 12 agents running in production, nobody knows which version of the triage prompt is live, the compliance team's policy change requires a developer to manually edit a JSON file in production, and "did we roll back the code analysis agent's new system prompt before the regression started?" has no answer. You need GitOps for agents: treat agent configs — prompts, tool definitions, memory schemas, budgets, policies — as declarative infrastructure managed through Git with automated reconciliation loops.*

## Forces

- **Agent behavior lives in strings, not binaries.** Unlike a microservice where a deployment means a new container image, an agent's behavior is largely determined by its system prompt, tool definitions, and configuration — text that lives in files, databases, or feature flags. Without infrastructure-style discipline, these strings drift silently across environments.

- **Configuration changes to agents are high-stakes and silent.** A prompt edit can change what an agent approves, what data it accesses, what tools it calls, and what policies it enforces. Unlike a config map change in Kubernetes (which restarts a pod), an agent config change can apply mid-conversation with no restart signal.

- **Manual deployments of agent config are un-auditable and unreproducible.** Teams that manage agent configs in UI dashboards, feature flags, or spreadsheet-tracked prompts have no rollback story, no diff, no approval workflow, and no blast-radius assessment.

- **Agent fleets amplify the problem.** When one prompt change affects 47 agents (as documented in fleet-management failures), a manual update workflow becomes a single point of catastrophic failure.

## The Move

Treat your agent configuration as a Git repository with the same discipline you apply to application code.

### 1. Define Agents as Declarative Specs

Structure your agent repo like infrastructure-as-code:

```
agents/
├── triage-agent/
│   ├── prompt.md          # system prompt as markdown
│   ├── tools.yaml          # tool definitions
│   ├── memory-schema.json  # memory tier config
│   ├── policy.yaml         # budget, guardrails, escalation
│   └── _versions/
│       ├── v1.2.0/
│       └── v1.3.0/
├── code-review-agent/
│   └── ...
└── fleet-config.yaml       # shared budget, model routing
```

Every agent is a versioned directory. No ad-hoc string management.

### 2. Enforce Code Review for Prompt Changes

Prompts are code. A system prompt change that removes a safety instruction deserves the same review as a security-relevant code change. Require:

- **Diff review** — PR shows before/after prompt diff
- **Behavioral test** — prompt PR includes a golden-dataset test that validates the expected behavior change
- **Blast-radius label** — does this affect data access, financial operations, or policy enforcement?

### 3. Deploy via Reconciliation Loop

Use an operator (or workflow) that continuously reconciles desired state (Git) with observed state (running agents):

```python
# AgentGitOps operator (pseudocode)
class AgentReconciler:
    def reconcile(self, agent_name: str):
        desired = self.load_spec(f"agents/{agent_name}")
        observed = self.fetch_running_config(agent_name)

        if desired != observed:
            diff = self.compute_diff(desired, observed)
            if self.automatic_rollback_enabled(diff):
                self.rollback_to_previous(agent_name)
            else:
                self.alert_and_wait(diff)
            self.apply_spec(agent_name, desired)

        self.record_audit_trail(agent_name, desired, observed)
```

The reconciliation loop should detect drift: if a running agent's behavior doesn't match its declared spec (detectable via trace sampling and eval), trigger an alert or auto-remediation.

### 4. Environment Promotion Pipeline

Agent configs flow through environments the same way code does:

```
feature-branch → PR review → staging eval → canary (5% of agents) → full fleet
```

Canary promotion means: run the new prompt against 5% of agent instances, measure correctness SLOs against baseline, auto-promote if metrics are green, auto-rollback if they degrade.

```yaml
# .agent-ci.yaml — agent-specific CI config
agents:
  triage-agent:
    canary_fraction: 0.05
    eval_gate:
      task_completion_rate: "> 0.92"
      policy_violation_rate: "< 0.01"
      hallucination_rate: "< 0.05"
    rollback_on_regression: true
    promotion_delay_seconds: 300
```

### 5. Prompt Version as First-Class Artifact

Tag every agent config with a content-addressable hash. The hash becomes the deployment identity:

```
triage-agent @ a3f9c2b  (prompt hash)
triage-agent @ v1.4.0   (semantic version, references the hash)
```

When an agent crashes or regresses, you roll back to a known hash — not a guessed version number. This is the same pattern as container image SHAs.

## Receipt

> Verified 2026-08-02 — Pattern synthesized from KubeAgenticOperator (GitHub, declarative agent Kubernetes deployment), Microsoft KARS/Agent Reference Stack (GitOps-native agent operations on AKS), Fast.io "AI Agent GitOps" guide (declarative agent pipeline patterns), and DevOpsEduHub "GitOps for Agents" (2026-05-08 enterprise case study). The operator reconciliation pattern, canary promotion with eval gates, and content-addressable prompt versioning are documented in these sources. Code examples are synthetic constructions grounded in the documented patterns.

## See also

- [S-1160 · The Agent-Native CI/CD Stack](s1160-the-agent-native-cicd-stack-when-your-deployment-pipeline-cant-tell-if-your-agent-got-worse.md) — eval-gated deployment pipelines that this GitOps stack builds on
- [S-1223 · The Fleet Cockpit Stack](s1223-the-fleet-cockpit-stack-when-your-agent-fleet-is-an-unknowable-chaos.md) — fleet-wide observability that pairs with declarative management
- [S-1650 · The Tool Interface Stack](s1650-the-tool-interface-stack-when-your-tool-description-works-for-humans-but-not-for-agents.md) — tool definitions that belong in the agent spec directory
