# S-1562 · The Ephemeral Workspace Lifecycle Stack — When Your Agent Uses Yesterday's Environment to Do Today's Work

Your agent has been running for three weeks. It has accumulated credentials, downloaded files, modified configurations, and left artifacts in a workspace that was meant to last one task. Today it uses the same environment to handle a different customer's data. The stale credential from week one still works. The file it downloaded in week two is still on disk. The env var it set during a debugging session is still active. This is not a memory problem. It is a **workspace lifecycle problem** — the environment outlived its purpose and nobody managed the teardown.

Ephemeral workspace lifecycle is the discipline of treating agent execution environments as temporary compute: created for a task, scoped to a session, and destroyed when the work is done. The workspace is not a persistent server — it is a bounded container with an explicit creation, maintenance, and teardown protocol. Without it, every agent run inherits the state and risk of every prior run.

## Forces

- **Environments outlast their trust.** An agent workspace provisioned for task A accumulates state that becomes a liability for task B. Stale credentials, leftover files, and persistent environment variables are invisible until they cause a cross-contamination incident. Northflank benchmarks (2026): 97ms median time-to-interactive for ephemeral sandboxes — fast enough for per-task provisioning, not just per-session.

- **Credentials tied to environments leak across tasks.** When a workspace holds a long-lived API key, that key persists across task boundaries. The agent that ran a safe data-processing job can use the same key to exfiltrate data in a later job. Credential lifecycle must match workspace lifecycle — not the other way around.

- **State persistence is the exception, not the default.** Most agent tasks don't need persistent state between runs. The default should be clean-slate provisioning; state persistence should require an explicit opt-in with a defined retention policy. Most teams build the opposite: persistent environments as default, teardown as afterthought.

- **Blast radius is proportional to workspace age.** A fresh workspace has zero stale state. A three-week-old workspace has accumulated three weeks of attack surface: credentials, artifacts, configurations, and implicit permissions that nobody audits. E2B saw 375× growth in sandbox executions (40K/month Mar 2024 → 15M/month Mar 2025), with Fortune 100 adoption at 88% — and the majority of those sandboxes are not lifecycle-managed.

## The move

**Treat the workspace as a lease, not a home.** Every agent execution gets a workspace with an explicit lifecycle: provision → initialize → execute → checkpoint (if needed) → teardown.

### 1. Provision with intent

Every workspace is created for a specific task with a defined scope:

```python
from agent_workspace import Workspace, WorkspaceConfig

config = WorkspaceConfig(
    task_id="t-48291",
    ttl_seconds=3600,              # hard ceiling — destroy by then regardless
    isolation_level="microvm",      # Firecracker microVM, not container
    credential_scope="ephemeral",    # short-lived tokens, not static keys
    network_egress=["api.internal"], # explicit allowlist, deny-by-default
    artifacts=["output/", "logs/"],  # what's allowed to persist beyond task
)

workspace = await Workspace.provision(config)
# Workspace is now isolated, scoped, and on a clock.
```

The TTL is not a suggestion. It is the teardown trigger. No workspace lives beyond its TTL regardless of task completion.

### 2. Scope credentials to the workspace lifecycle

Use workload identity federation to bind credentials to the workspace, not to the agent process. AWS IRSA, GCP Workload Identity, or SPIFFE/SPIRE for non-cloud:

```python
# Credentials live as long as the workspace. When the workspace dies,
# the credentials are unrecoverable from that context.
workspace_token = await workspace.attest_workload_identity()
# Now the agent inside the workspace can call cloud APIs using
# workspace-scoped permissions, not a static long-lived key.
```

The agent never holds a credential that outlives its workspace. Every API call is authenticated with a token valid only for the duration of the task.

### 3. Checkpoint only what's necessary

If a task needs to resume after interruption, checkpoint only the minimal recoverable state — not the full environment:

```python
# Good: checkpoint structured output and position marker
checkpoint = {
    "task_id": "t-48291",
    "last_completed_step": 3,
    "output_fragments": [result_1, result_2, result_3],
    "resume_instruction": "Continue from step 4 — file_ingestion phase"
}

# Bad: checkpoint the entire workspace state
# This preserves stale credentials and old artifacts alongside the useful state.
```

Resume from the checkpoint into a fresh workspace, not a restored copy of the old one. The new workspace re-derives what it needs from the checkpoint and persistent storage.

### 4. Teardown is non-negotiable

```python
try:
    result = await agent.execute_in(workspace)
finally:
    await workspace.destroy()  # Always. Even on error.
```

The `finally` block is not defensive programming — it is the primary security control. Teardown must execute even when the agent crashes, times out, or throws an exception. On K8s, use a sidecar lifecycle hook or a finalizer on the Pod to guarantee cleanup if the main process dies.

Audit every teardown event. A workspace that failed to destroy is a data-leak risk. Track teardown success rate as an operational metric.

### 5. The isolation spectrum

Match isolation depth to threat model, not to convention:

| Isolation level | Use for | Not for |
|---|---|---|
| Process (ptrace/seccomp) | Low-risk tool calls, read-only operations | Code execution, network calls |
| gVisor (runsc) | Untrusted code in containerized workloads | High-security boundaries (gVisor shares a kernel) |
| gVisor + network policy | External API calls from untrusted code | Internal system access |
| Firecracker microVM | Untrusted code execution, multi-tenant environments | Fast warm-path tasks (cold start ~97ms vs. microVM ~200ms) |
| Kata Containers | Strongest isolation; full VM | Latency-sensitive or high-volume paths |

For most production agents: start with gVisor + network egress policy, escalate to Firecracker for code-generation workloads or any agent that handles external input.

## Receipt

> Verified 2026-07-24 — Northflank compute benchmarks (97ms TTI, Mar 2026), E2B incident data (375× sandbox growth, 15M executions/month by Mar 2025), Fordel Studios isolation taxonomy, AWS/GCP workload identity federation docs, SPIFFE/SPIRE CNCF project. Production pattern derived from Northflank ephemeral environments guide and E2B sandbox lifecycle architecture.

## See also

- [S-1547 · The Tool Access Safety Stack](s1547-the-tool-access-safety-stack-when-your-agent-either-does-nothing-or-destroys-everything.md) — structured access controls within the workspace
- [F-190 · Kubernetes Agent Sandbox Controller](f190-kubernetes-agent-sandbox-controller.md) — K8s primitives for agent workload lifecycle
- [F-100 · Agent Runtime Authorization & Tool-Call Observability](f100-agent-sandboxing-guardrails.md) — intercepting tool calls at the workspace boundary
- [F-10 · Agent Identity and Access](f10-agent-identity-and-access.md) — workload identity federation as the credential model
