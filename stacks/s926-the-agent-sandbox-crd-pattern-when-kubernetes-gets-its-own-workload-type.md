# S-926 · The Agent Sandbox CRD Pattern: When Kubernetes Gets Its Own Workload Type

Kubernetes had Deployments for stateless apps, StatefulSets for ordered persistence, and Jobs for batch. Then it got agents — long-running, stateful, singleton workloads that fit none of those models cleanly. The `kubernetes-sigs/agent-sandbox` project (SIG Apps, November 2025) answers the question: what if agent isolation was a first-class Kubernetes resource type, with its own CRD, controller, and declarative API?

## Forces

- Kubernetes' three native workload types assume either replication or statelessness — agent runtimes need exactly-one-pod, stable identity, pause/resume lifecycle, and per-agent persistent storage, none of which map cleanly to Deployment or StatefulSet
- Sandboxing decisions were historically baked into agent frameworks or scattered across Helm charts and init scripts — the lifecycle of the sandbox and the lifecycle of the agent were coupled, making them hard to reason about independently
- Cold-start latency kills agent UX: starting a new microVM for every agent interaction adds 100–500ms of overhead; teams need warm pools that can be handed off to agents on demand
- Isolation technology choices (gVisor vs Kata Containers vs Firecracker) should be swappable without rewriting orchestration code — the management plane and the isolation plane should be decoupled
- GKE shipped native Agent Sandbox CRDs (Sandbox, SandboxTemplate, SandboxClaim, SandboxWarmPool) as of 2026, making this a production-ready capability, not a science project

## The move

The core insight: **agent sandboxing is an infrastructure workload problem, not a framework problem.** The `agent-sandbox` project decouples three concerns that were previously tangled:

1. **Sandbox lifecycle** (create, pause, resume, delete) — handled by the `Sandbox` CRD controller
2. **Sandbox policy** (isolation backend, resource limits, network egress) — declared in `SandboxTemplate`
3. **Sandbox allocation** (which agent gets which sandbox) — managed via `SandboxClaim`

### The four CRDs

```yaml
# 1. SandboxTemplate: the isolation policy declaration
apiVersion: extensions.agents.x-k8s.io/v1beta1
kind: SandboxTemplate
metadata:
  name: untrusted-code-executor
spec:
  isolationBackend: gVisor          # or KataContainers, Firecracker
  resources:
    limits:
      cpu: "2"
      memory: 1Gi
  networkEgress:
    allow:
      - dest: "api.stripe.com"
        ports: [443]
  readOnlyRootFilesystem: true
  capDrop: ["ALL"]
  maxDuration: "30m"               # auto-shutdown guard
---
# 2. Sandbox: a live instance of a template
apiVersion: agents.x-k8s.io/v1beta1
kind: Sandbox
metadata:
  name: agent-42-sandbox
spec:
  templateRef: untrusted-code-executor
  operatingMode: Running            # or Suspended (pause/resume)
---
# 3. SandboxClaim: a scheduling request (agent side)
apiVersion: extensions.agents.x-k8s.io/v1beta1
kind: SandboxClaim
metadata:
  name: agent-42-claim
spec:
  templateRef: untrusted-code-executor
  # Controller finds or creates a matching Sandbox and binds it
---
# 4. SandboxWarmPool: pre-started instances
apiVersion: extensions.agents.x-k8s.io/v1beta1
kind: SandboxWarmPool
metadata:
  name: warm-pool-1
spec:
  templateRef: untrusted-code-executor
  poolSize: 5                      # 5 pre-warmed sandboxes ready
  preStartCommand: "cd /workspace"  # warmup script
```

### The claim model: separating allocation from orchestration

The claim model is the architectural key. The agent (or the agent orchestrator) creates a `SandboxClaim`. The controller handles the rest: finding an available warm sandbox, instantiating a cold one if needed, binding the claim, and returning a stable endpoint. The agent never directly creates pods — it requests an isolated environment declaratively, the same way it requests a PersistentVolumeClaim.

This means your agent orchestrator can be written as a pure declarative controller: it creates `SandboxClaim` objects and watches for bound `Sandbox` objects, without caring whether the controller used a warm pool or cold-started a microVM.

### Warm pools: sub-second agent response

Cold-start benchmarks for isolation technologies:

| Backend | Cold start | Warm resume | Memory overhead |
|---------|-----------|-------------|----------------|
| gVisor (runsc) | ~50ms | <5ms | ~100MB |
| Kata Containers | ~1–2s | <10ms | ~200MB |
| Firecracker | ~100–500ms | <5ms | ~5MB (minimal) |

With `SandboxWarmPool`, you pay the cold-start cost once during pool initialization. Agents requesting a sandbox get a pre-warmed instance in under 10ms. The pool controller monitors utilization and scales the pool up or down — more agents requesting sandboxes triggers pool expansion, idle sandboxes trigger hibernation.

### Integration with agent frameworks

The `agent-sandbox` controller watches `SandboxClaim` objects and updates their `.status` with the sandbox endpoint. Agent SDKs can watch claims and receive the sandbox connection details:

```python
# Agent requests a sandbox (SDK pattern)
claim = api.create_sandbox_claim(
    template="untrusted-code-executor",
    labels={"agent-id": "agent-42"}
)

# SDK watches for binding
sandbox = wait_for_sandbox_bound(claim)
exec_endpoint = sandbox.status.endpoint  # e.g., unix socket or TCP

# Agent executes code inside the sandbox
run_in_sandbox(exec_endpoint, user_code)
```

The orchestrator (CrewAI, LangGraph, AutoGen, custom) never talks to Kubernetes directly — it uses the claim abstraction, keeping the orchestration layer isolated from the infrastructure layer.

## Receipt

> Receipt pending — Kubernetes SIG Apps `agent-sandbox` v0.5.0 was verified functional as a released project (latest at 2026-07-10) with GKE native CRD support confirmed. Exact warm pool benchmarks are from vendor documentation (Northflank, Firecracker project) — run `kubectl apply` + `kubectl get sandboxclaim` in a GKE Autopilot cluster to confirm end-to-end.

## See also

- [S-709 · Agent Execution Isolation: The Five-Tier Sandbox Reference](stacks/s709-agent-sandboxing-tiers-and-execution-isolation-in-production.md) — isolation technology taxonomy (gVisor, Kata, Firecracker, etc.); S-926 covers the *management plane* for those technologies
- [S-315 · Agent Sandboxing as a First-Class Infrastructure Layer](stacks/s315-agent-sandboxing-stratification.md) — the original observation that sandboxing is its own stack layer; S-926 shows what that layer looks like as a K8s-native CRD
- [S-213 · The Stratified Agent Stack](stacks/s213-stratified-agent-stack.md) — the broader stratification model; sandbox CRDs are the concrete instantiation of the isolation stratum
