# S-904 · The Claim Model for Agent Sandboxes — When Kubernetes Native Meets Agentic AI

Your Kubernetes YAML for a coding agent looks like a Rube Goldberg machine: a StatefulSet of size 1 for identity, a headless Service for DNS, a PersistentVolumeClaim for the scratch workspace, a separate ConfigMap for the system prompt, a Sidecar for observability, network policies, and a custom finalizer to handle graceful teardown. It works. Until you need 50 of them, or you need to pre-warm a pool so the first user request gets a sandbox in under 2 seconds, or you need to suspend and resume agents across idle periods. At that point, you are not doing platform engineering — you are duct-taping an alien workload onto primitives built for a different species.

The kubernetes-sigs/agent-sandbox project (March 2026, SIG Apps) solves this with a claim model: four CRDs that separate "I want an isolated agent workspace with this profile" from "here is the StatefulSet, Service, and PVC to make that happen." The cluster handles the stitching. You only write the intent.

## Forces

- **Agents are singleton stateful workloads.** Unlike microservices where Kubernetes ReplicaSets handle replication trivially, each agent has a persistent identity, a scratch filesystem, and session state that must survive across suspend/resume cycles. StatefulSet of size 1 is the correct primitive, but it is 20% of the solution.
- **Traditional Kubernetes primitives were not built for agent lifecycles.** StatefulSet + headless Service + PVC is the right foundation, but you also need warm pool pre-warming, graceful agent suspension (so idle agents don't burn budget), rapid resumption from suspension, and per-agent resource quota isolation. None of these are first-class StatefulSet concerns.
- **The blast radius of agent execution is unbounded.** Unlike traditional pods that run known, reviewed code, agents generate and execute untrusted code. Every agent needs its own isolated sandbox — not just container isolation, but potentially microVM isolation (Firecracker) for untrusted code execution. This is not a deployment topology concern; it is a security posture.
- **Provisioning latency is a UX cliff.** A coding agent that takes 8 seconds to warm up a new session loses the user. Pre-warmed sandboxes must be available within ~1 second of assignment. Without a standardized warm pool abstraction, every team re-invents this badly.

## The Move

### The Four CRDs

Agent Sandbox introduces four Kubernetes Custom Resource Definitions. Together they form a claim-based provisioning model:

```yaml
# 1. SandboxTemplate — the "flavor" of sandbox you want
apiVersion: sandbox.sigs.k8s.io/v1alpha1
kind: SandboxTemplate
metadata:
  name: coding-agent-default
spec:
  isolationLevel: firecracker        # firecracker | gvisor | container
  resources:
    requests:
      cpu: "2"
      memory: 4Gi
    limits:
      memory: 8Gi
  filesystem:
    scratchSize: 10Gi
  network: isolated                  # isolated | restricted | open
  lifetime: 72h                     # max lifetime before forced teardown
---
# 2. SandboxWarmPool — pre-warmed capacity
apiVersion: sandbox.sigs.k8s.io/v1alpha1
kind: SandboxWarmPool
metadata:
  name: coding-pool
spec:
  templateRef: coding-agent-default
  poolSize: 10                      # always maintain 10 warm sandboxes
  preWarming: true
---
# 3. SandboxClaim — the user's request ("I need a sandbox")
apiVersion: sandbox.sigs.k8s.io/v1alpha1
kind: SandboxClaim
metadata:
  generateName: agent-session-
spec:
  templateRef: coding-agent-default
  priority: high
  sessionTTL: 8h
---
# 4. Sandbox — the actual provisioned resource (controller-created)
# You don't create this; the controller creates it from a claim.
```

### The Provisioning Flow

When a user creates a `SandboxClaim`, the controller:

1. **Checks the warm pool first.** If a pre-warmed pod in `SandboxWarmPool` is available and unused, the controller assigns it to the claim in ~100ms. The user gets a warm sandbox immediately.

2. **Provisions on-demand if the pool is empty.** The controller creates the full StatefulSet + Service + PVC stack from the `SandboxTemplate`. This takes 5–15 seconds depending on the isolation level (Firecracker is slower to boot than gVisor).

3. **Tracks identity via the sandbox name.** The `Sandbox` resource name becomes the stable DNS name and persistent volume identity. An agent can be suspended (pod scaled to 0), then resumed, and reconnect to the same persistent filesystem and identity.

### Suspension and Resumption

Agents spend most of their time idle. A coding agent that handles 20 requests per hour has 19 hours of idle time at full compute cost. Agent Sandbox supports suspending idle agents:

```yaml
# Suspend: scale the agent workload to zero but preserve state
apiVersion: sandbox.sigs.k8s.io/v1alpha1
kind: Sandbox
metadata:
  name: agent-session-abc123
spec:
  state: Suspended

# Resume: controller restarts the pod, reattaches the PVC
apiVersion: sandbox.sigs.k8s.io/v1alpha1
kind: Sandbox
metadata:
  name: agent-session-abc123
spec:
  state: Active
```

On resumption, the agent reconnects to its persistent scratch workspace, retrieves its last session state from the filesystem, and resumes without a full re-initialization. The user experience is near-instantaneous for short idle periods.

### Isolation Levels

The `SandboxTemplate.spec.isolationLevel` field maps to the security boundary:

| Level | Technology | Boot Time | Security | Use Case |
|-------|-----------|-----------|----------|----------|
| `container` | standard runc | ~10ms | Weak (shared kernel) | Trusted agents, internal tools |
| `gvisor` | Google gVisor Sentry | ~100ms | Strong (syscall interception) | Semi-trusted, general purpose |
| `firecracker` | AWS Firecracker microVM | ~125ms | Hardest (VM boundary) | Untrusted code, computer use |

The container level is appropriate only inside an already-hardened outer boundary. For agents that execute user-provided code, browser-based computer use, or interact with untrusted documents, `firecracker` is the minimum defensible choice.

### Security Hardening Per Isolation Level

Regardless of the technology, a hardened `SandboxTemplate` should enforce:

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 65534        # nobody
    seccompProfile:
      type: RuntimeDefault
    capabilities:
      drop: [ALL]
    readOnlyRootFilesystem: true
  tmpfsMounts:
    - /tmp
    - /run
  resources:
    limits:
      memory: 4Gi
      cpu: "2"
  networkPolicy:
    egress: DenyAll           # start with no network, open selectively
```

Never mount the Docker socket into an agent sandbox. If agents need to spawn sub-agents or containers, use the orchestration API, not shared socket access. This is the most common container escape path for AI agents.

## Receipt

> Verified 2026-07-10 — Research synthesis from: kubernetes-sigs/agent-sandbox GitHub (Apache 2.0, SIG Apps, Janet Kuo & Justin Santa Barbara, March 2026); kubernetes.io blog post "Running Agents on Kubernetes with Agent Sandbox" (March 20, 2026); agent-sandbox.sigs.k8s.io documentation site; Kubernetes Slack SIG Apps channels (Q1–Q2 2026); OpenLegion AI Agent Sandboxing guide; Zylos Research AI Agent Sandboxing (April 2026). CRD examples derived from official API spec and documentation.

## See also

- [S-205 · Agent Sandbox Isolation](s205-agent-sandbox-isolation.md) — the conceptual layer: why agents need isolation, what isolation means, and how it compares across technologies
- [S-198 · Agent Tool Call Guardrails](s198-agent-tool-call-guardrails.md) — content-layer security that complements sandbox isolation
- [S-902 · The Scaffold Supply Chain Stack](s902-the-scaffold-supply-chain-stack-when-your-agent-builds-a-backdoor-into-your-own-infra.md) — supply chain threats that a sandbox does not stop
