# S-1072 · The Agent Sandbox Controller Stack — When Your K8s Cluster Doesn't Know What an Agent Is

Your agentic system runs on Kubernetes. Your agent needs a sandboxed execution environment — ephemeral, isolated, with network controls and a clean teardown path. But Kubernetes knows about Deployments, Pods, and Services. It does not know about AgentProfiles, sandbox lifetimes, capability allowlists, or the difference between a session that completed and one that was interrupted. You build one-off bash scripts and Helm hooks to paper over the gap. They don't scale. You need a controller that speaks the agent's language.

## Forces

- **Agent workloads are stateful and long-running — Pods are not.** A single agent session may run for hours, survive across multiple LLM calls, and need to persist state (memory, scratch files, partial results) between sandbox invocations. Standard Kubernetes pods assume either stateless short-lived work or long-running services with fixed interfaces — neither matches the agent's session model.
- **Lifecycle management and isolation technology are separate concerns.** S-205 covers isolation choices (Firecracker, gVisor, WASM). S-1069 covers threat-model-driven sandbox selection. Neither addresses the controller problem: how Kubernetes manages the lifecycle of agent workloads — provisioning, teardown, resource negotiation, crash recovery — independently of which isolation technology is chosen.
- **The 375x growth gap.** E2B (the leading agent sandboxing platform) went from 40K to 15M executions/month in one year. 88% of Fortune 100 companies are experimenting with sandboxed agent execution. Kubernetes is the standard workload orchestrator — and it has no native concept of an agent session.

## The move

**Adopt the Kubernetes SIG Apps `kubernetes-sigs/agent-sandbox` controller** (launched November 2025). It decouples agent workload lifecycle management from isolation technology selection — the controller handles *when* and *how* to create/destroy sandboxed environments; you choose *which* isolation primitive (Firecracker, gVisor, WASM, Docker) independently.

The controller introduces three Kubernetes CustomResourceDefinitions:

**`Sandbox`** — the core resource. Represents an isolated execution environment for a single agent session.
```yaml
apiVersion: agent.sigs.k8s.io/v1alpha1
kind: Sandbox
metadata:
  name: agent-session-abc123
  namespace: agent-workloads
spec:
  agentProfileRef: coding-agent-v2
  ttl: 3600        # destroy after 1 hour (even if running)
  idleTimeout: 300 # destroy after 5 min of no activity
  resources:
    memory: "512Mi"
    cpu: "500m"
  networkPolicy:
    egress:
      - to: "api.github.com:443"
      - to: "pypi.org:443"
    ingress: []     # no inbound connections
  isolationRuntime: firecracker  # swappable: gvisor, wasm, docker
status:
  phase: Running
  podRef: "pod/sandbox-agent-session-abc123-x7k2p"
```

**`AgentProfile`** — defines what capabilities a class of agents can use.
```yaml
apiVersion: agent.sigs.k8s.io/v1alpha1
kind: AgentProfile
metadata:
  name: coding-agent-v2
spec:
  allowedTools:
    - exec_python
    - read_file
    - search_web
    - write_file  # restricted to /workspace/ only
  maxConcurrentSandboxes: 10
  defaultResources:
    memory: "512Mi"
    cpu: "500m"
  isolationDefaults:
    runtime: firecracker
    networkEgressAllowlist:
      - "api.github.com:443"
      - "pypi.org:443"
```

**`ExecutionPolicy`** — controls how the controller provisions and manages sandbox resources.
```yaml
apiVersion: agent.sigs.k8s.io/v1alpha1
kind: ExecutionPolicy
metadata:
  name: session-expiry-policy
spec:
  maxSessionDuration: 7200       # hard limit
  gracefulShutdownGracePeriod: 30 # seconds to drain
  onExpiry: rollback             # rollback | archive | fail
  onCrash: destroy               # destroy | snapshot | alert
```

**The controller loop:**
```
Agent requests session
  → Controller reads AgentProfile
  → Controller creates Sandbox CR (not a Pod directly)
  → Provisioner plugin creates the actual isolation environment
      (Firecracker VM / gVisor container / WASM module)
  → Controller updates Sandbox.status with podRef + endpoint
  → Agent uses sandbox
  → On TTL/idle/crash → ExecutionPolicy triggers graceful teardown
  → Provisioner destroys isolation environment
  → Controller deletes Sandbox CR
  → Pod is deleted
```

**Key architectural insight:** The Sandbox CR is the reconciliation handle. Whether the underlying isolation is a Firecracker MicroVM, a gVisor container, or a WASM module — the Kubernetes API sees the same resource. You can swap isolation technologies by changing `isolationRuntime` without rewriting your agent's Kubernetes integration.

**The provisioner plugin interface:**
```python
from abc import ABC, abstractmethod

class SandboxProvisioner(ABC):
    @abstractmethod
    async def provision(self, sandbox: Sandbox) -> SandboxStatus:
        """Create the isolated environment. Returns status with endpoint."""
        ...

    @abstractmethod
    async def destroy(self, sandbox: Sandbox) -> None:
        """Tear down the isolated environment."""
        ...

    @abstractmethod
    async def health_check(self, sandbox: Sandbox) -> bool:
        """Return True if the sandbox is still alive."""
        ...

# Built-in provisioners:
# - FirecrackerProvisioner   (MicroVM — strongest isolation)
# - GVisorProvisioner         (user-space kernel — fast startup)
# - WasmProvisioner           (WASM isolate — minimal footprint)
# - DockerProvisioner         (fallback — shares kernel, quick for low-risk)
```

**Minimal end-to-end example using the controller's client SDK:**
```python
from kubernetes import client, config
from kubernetes.client import CustomObjectsApi
from datetime import datetime

# Load in-cluster config (works inside the operator Pod)
config.load_incluster_config()
custom_api = CustomObjectsApi()

namespace = "agent-workloads"
profile = "coding-agent-v2"

# 1. Agent requests a new sandboxed session
sandbox_manifest = {
    "apiVersion": "agent.sigs.k8s.io/v1alpha1",
    "kind": "Sandbox",
    "metadata": {
        "name": f"session-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "namespace": namespace,
    },
    "spec": {
        "agentProfileRef": profile,
        "ttl": 3600,
        "idleTimeout": 300,
        "resources": {"memory": "512Mi", "cpu": "500m"},
        "isolationRuntime": "firecracker",
    },
}

custom_api.create_namespaced_custom_object(
    group="agent.sigs.k8s.io",
    version="v1alpha1",
    plural="sandboxes",
    namespace=namespace,
    body=sandbox_manifest,
)

# 2. Wait for the controller to provision it
def wait_for_sandbox_ready(name: str, timeout: int = 30) -> dict:
    for _ in range(timeout):
        sb = custom_api.get_namespaced_custom_object(
            "agent.sigs.k8s.io", "v1alpha1",
            namespace, "sandboxes", name
        )
        if sb.get("status", {}).get("phase") == "Running":
            return sb["status"]
        import time; time.sleep(1)
    raise TimeoutError(f"Sandbox {name} did not become ready in {timeout}s")

status = wait_for_sandbox_ready(sandbox_manifest["metadata"]["name"])
print(f"Sandbox ready at: {status['endpoint']}")
# Agent connects to status['endpoint'], runs code, gets results

# 3. Agent completes — controller handles teardown per ExecutionPolicy
# No manual Pod management needed. TTL or idle timer triggers destroy.
```

## Receipt

> Verified 2026-07-13 — Researched `kubernetes-sigs/agent-sandbox` (SIG Apps, launched November 2025), Zylos agent sandboxing security research (April 2026), Fordel Studios production agent isolation report (March 2026), E2B 375x growth metric, Northflank Kubernetes sandboxing guide (February 2026).

Key tradeoffs:
- **Firecracker vs gVisor vs WASM**: Firecracker gives strongest isolation at ~125ms startup cost; gVisor gives good isolation at ~50ms; WASM gives minimal footprint but limited to bounded compute. The controller lets you choose per-risk-level without changing the operator.
- **Controller overhead**: The reconciliation loop adds ~1-2 seconds to session provisioning on top of the isolation runtime's own startup time. For long-running agent sessions (minutes to hours), this is negligible. For high-frequency short tasks (<10s), it may not be the right pattern.
- **Not a security panacea**: The controller manages lifecycle, not isolation guarantees. If you choose Docker as the isolation runtime, you still share the host kernel. The threat model from S-1069 applies.

## See also

- [S-1069 · The Threat-Model-Driven Sandbox Stack](stacks/s1069-the-threat-model-driven-sandbox-stack-when-subprocess-is-not-enough.md) — threat modeling for which isolation technology to use
- [S-205 · Agent Sandbox Isolation](stacks/s205-agent-sandbox-isolation.md) — isolation technology deep-dive (Firecracker, gVisor, WASM)
- [S-1047 · The Agentic Dead Letter Queue](stacks/s1047-the-agentic-dead-letter-queue-when-your-agent-fails-mid-task-and-the-task-just-disappears.md) — crash recovery patterns for interrupted agent sessions
