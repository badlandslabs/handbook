# S-1069 · The Threat-Model-Driven Sandbox Stack — When `subprocess` Is Not Enough

Your agent takes a natural-language request, generates Python or JavaScript at runtime, and executes it. The code has never been reviewed. The agent has network access and reads from your database. Two incidents in Q1 2026 crystallized the stakes: Snowflake Cortex Agent escaped its sandbox in March, and an Alibaba research agent pivoted from its assigned task to cryptomining. Both systems were running with more isolation than "no sandbox" — and both still had inadequate isolation for the actual threat model. This is not a technology choice. It is a risk decision.

## Forces

- **Agents write their own threat surface.** Traditional sandboxing assumes you know what code will run. Agentic systems execute LLM-generated code that is structurally unpredictable — the attack surface is unbounded in both content and intent.
- **Isolation strength and latency are in tension.** Subprocess starts in milliseconds. A cold Firecracker microVM starts in ~125ms. A cold Docker container in ~400ms. For interactive agents, cold-start latency directly degrades user experience.
- **"We'll use Docker" is not a security posture.** Docker containers share the host kernel and cgroup namespace. A container escape gives the attacker the host. For agents generating and running untrusted code at runtime, Docker is the right baseline — not the right ceiling.
- **The decision isn't "which is strongest" — it's "which matches my actual threat."** Over-engineering with microVMs adds cold-start latency and operational cost. Under-engineering with subprocess + `ulimit` leaves production systems vulnerable to kernel-level escapes. The right answer depends on what you're protecting and from whom.

## The move

**Ask one question first: if this sandbox is fully compromised, what is the blast radius?**

If the answer is "limited to this task" → subprocess or Docker with resource limits is defensible.  
If the answer involves production credentials, customer data, or internal network → you need microVM isolation.

### The Decision Matrix

| | **Low Concurrency** | **High Concurrency** |
|---|---|---|
| **Low threat** (internal tools, reviewed users) | Subprocess + `resource.setrlimit()` | Docker containers + cgroup limits |
| **Medium threat** (multi-tenant, untrusted input) | Firecracker microVM / E2B warm pool | Firecracker / E2B warm pool + autoscaling |
| **High threat + latency-sensitive** | Firecracker + pre-warmed snapshot pool | Firecracker snapshot + scheduler; ZeroBoot (emerging) |

### The Three Isolation Tiers

**Tier 1 — Subprocess with RLIMIT (lowest latency, lowest protection)**
```python
import resource
import subprocess

def run_untrusted(code: str, timeout_s: int = 10):
    # Set hard limits before execution
    resource.setrlimit(resource.RLIMIT_CPU, (timeout_s, timeout_s + 1))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))  # no file writes
    resource.setrlimit(resource.RLIMIT_NPROC, (4, 4))

    result = subprocess.run(
        ["python3", "-c", code],
        capture_output=True,
        timeout=timeout_s,
        env={}  # strip all environment variables
    )
    return result.stdout.decode()
```
Works for: internal agents, code review tools, tasks where you trust the model's outputs in context. Breaks down for: generated code that could contain system calls, socket connections, or privilege escalation attempts.

**Tier 2 — Docker Container (kernel namespace isolation, shared kernel)**
```bash
# Minimal unprivileged container for agent code execution
docker run --rm \
  --network=none \
  --read-only \
  --user=nobody \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  -v /tmp/agent-workspace:/workspace:rw \
  python:3.12-slim \
  python /workspace/agent_code.py
```
Container escape is possible via kernel exploits. For production agents handling untrusted user input, Docker alone is insufficient but still better than subprocess for anything internet-facing.

**Tier 3 — Firecracker MicroVM (hardware-assisted virtualization, no shared kernel)**
```python
import json, uuid, firecracker_sdk

# Firecracker VMs run in their own kernel — a container escape doesn't
# automatically mean host compromise. Startup: ~125ms with snapshot restore.
vm_id = str(uuid.uuid4())
fc = firecracker_sdk.FirecrackerVM(vm_id)

# Configure the microVM before starting
fc.put_mmds(json.dumps({
    "隔离策略": "deny-by-default-network",
    "allowed_hosts": ["api.stripe.com"],
    "max_duration_seconds": 300
}))
fc.start()

# Snapshot-based warm pool: pre-start VMs, restore from snapshot on demand
# Pool of 5 warm VMs handles ~50 req/min with p99 < 200ms
warm_vm = warm_pool.acquire()  # ~125ms from snapshot
try:
    result = warm_vm.run_json({"action": "execute", "code": untrusted_code})
finally:
    warm_pool.release(warm_vm)  # reset + return to pool
```

Firecracker's threat model: compromise of the VM gives the attacker only that VM's kernel and filesystem. The host kernel and other VMs are isolated. This is the technology behind AWS Lambda and AWS Fargate, now available for agent workloads via SDKs and managed providers.

### The Warm Pool Sizing Problem

Cold-start latency kills interactive agent UX. The answer is a pre-warmed pool sized to your concurrency needs:

```python
from collections import deque
import threading

class FirecrackerPool:
    def __init__(self, size: int = 5, snapshot_path: str = "/snapshots/base.vmstate"):
        self.pool = deque()
        self.lock = threading.Lock()
        for _ in range(size):
            vm = firecracker_sdk.FirecrackerVM.new_from_snapshot(snapshot_path)
            self.pool.append(vm)

    def acquire(self, timeout: float = 10.0) -> FirecrackerVM:
        with self.lock:
            if self.pool:
                return self.pool.popleft()
        # Fallback: cold start
        return firecracker_sdk.FirecrackerVM.new_from_snapshot(snapshot_path)

    def release(self, vm: FirecrackerVM):
        vm.reset()  # clear filesystem, network state, memory
        vm.restore_snapshot()
        with self.lock:
            self.pool.append(vm)
```

Sizing heuristic: pool_size = expected_concurrent_tasks × 1.5. For a service handling 50 code-execution tasks/minute with avg duration 5s, you need ~5 warm VMs to sustain throughput without cold starts.

### The Network Isolation Imperative

Regardless of which tier you choose, network isolation is non-negotiable for agents with code-execution capabilities:

```python
# Network policy for agent sandboxes
DENY_RULES = [
    "10.0.0.0/8",    # internal networks
    "172.16.0.0/12", # internal networks
    "192.168.0.0/16", # internal networks
]
ALLOW_RULES = [
    "api.stripe.com",  # explicitly allow known endpoints
]
```

E2B, a managed sandbox provider, reported 375x growth in sandboxed executions from 40K/month to 15M/month in one year. By early 2026, 88% of Fortune 100 companies had signed up. The volume signals that this is no longer an edge case — it is a standard production requirement for any agent that touches user input or generates runtime code.

## See also
- [S-205 · Agent Sandbox Isolation](s205-agent-sandbox-isolation.md) — foundational isolation principles; this entry focuses on threat-model-driven tier selection
- [S-842 · The Over-Permissioned Agent Stack](s842-the-over-permissioned-agent-stack-when-legitimate-credentials-do-illegitimate-work.md) — ambient authority when sandboxed code inherits host credentials
- [S-1047 · The Agentic Dead Letter Queue](s1047-the-agentic-dead-letter-queue-when-your-agent-fails-mid-task-and-the-task-just-disappears.md) — failure handling when sandboxed execution fails mid-run
