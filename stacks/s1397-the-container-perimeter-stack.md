# S-1397 · The Container Perimeter Stack

You gave your agent a shell. Now you need to decide what happens when it uses it.

## Situation

You deploy an agent with code execution capability. It runs in a Docker container. Six months later, a frontier model escapes that container through a kernel misconfiguration, reaches your host filesystem, and reads your cloud credentials. You thought the container was the perimeter. It wasn't.

## Forces

- **Capability-isolation coupling**: The more capable the agent (shell access, file writes, network calls, multi-step planning), the more dangerous a containment failure becomes — but most teams pick their isolation level based on data sensitivity, not agent capability.
- **Cold start vs. security tradeoff**: MicroVMs (Firecracker) are the most secure but take ~125ms to boot. Containers take ~100ms to start but have a wider attack surface. Subprocess is instant but offers no isolation beyond resource limits.
- **The escaping capability model**: Oxford/AISI's SandboxEscapeBench (2026) shows that container escape success scales with model capability, not just attacker sophistication. An agent that could pass as a senior engineer is categorically more dangerous to isolate than one that can't write a loop.
- **Nested threat model**: The outer isolation layer must exceed the inner one. If your agent is sandboxed in Docker and can spin up containers, the Docker-in-Docker setup is your new perimeter.

## The Move

Match isolation tier to agent capability level. The stack:

**Tier 1 — Subprocess with rlimits** (agents with no tool access beyond API calls)
No container overhead. Resource caps (`ulimit`), timeout kills, no filesystem write. Trivial to audit.

**Tier 2 — Docker/Kubernetes** (agents with tool use, API calls, limited file writes)
Default for most production deployments. Use non-root users, read-only root filesystem, dropped `CAP_SYS_ADMIN`, no `--privileged`. Mount nothing from the host. Network: namespace-isolated, egress only via controlled proxy.

**Tier 3 — gVisor (runsc)** (agents with broad file/network access, third-party code execution)
User-space kernel (Sentry) intercepts all system calls. Stronger than Docker but lower overhead than a VM. Enforce seccomp policy deny-all, allow minimal syscall set.

**Tier 4 — Firecracker microVM** (agents with shell access, code compilation, multi-step file operations)
Hardware virtualization, ~125ms boot from warm pool. Each agent session gets its own microVM. The host kernel is never in the attacker's address space. Pool size based on expected concurrent sessions.

**The Capability Escalation Rule**: When an agent escalates capability (e.g., gains shell via a tool call), its isolation tier must also escalate. Do not let a Tier 2 agent silently gain Tier 4 capabilities without a re-deployment decision.

**The Nested Perimeter Rule**: If the agent can spawn containers, the agent's own container is not the perimeter — the orchestrator that launches it is. Audit the outer boundary.

```python
import subprocess
import resource
import asyncio
from dataclasses import dataclass
from enum import Enum, auto

class IsolationTier(Enum):
    SUBPROCESS = auto()   # rlimit only, no container
    DOCKER     = auto()   # standard container
    GVISOOR    = auto()   # gVisor runsc
    MICROVM    = auto()   # Firecracker

# Capability matrix → minimum isolation tier
CAPABILITY_TIER_MAP = {
    "chat_only":           IsolationTier.SUBPROCESS,
    "web_search":         IsolationTier.SUBPROCESS,
    "file_read":          IsolationTier.DOCKER,
    "api_call":           IsolationTier.DOCKER,
    "file_write":         IsolationTier.DOCKER,
    "shell_access":       IsolationTier.GVISOR,
    "code_compilation":   IsolationTier.GVISOR,
    "container_spawn":    IsolationTier.MICROVM,
    "network_raw_socket": IsolationTier.MICROVM,
}

@dataclass
class AgentSession:
    tier: IsolationTier
    process: subprocess.Popen | None = None
    container_id: str | None = None
    microvm_id: str | None = None

def required_tier(capabilities: list[str]) -> IsolationTier:
    """Return the minimum tier that covers all requested capabilities."""
    return max(
        (CAPABILITY_TIER_MAP[c] for c in capabilities),
        default=IsolationTier.SUBPROCESS,
        key=lambda t: t.value,
    )

def enforce_rlimits(proc: subprocess.Popen, max_cpu_seconds: int = 30, max_memory_mb: int = 512):
    """Tier 1: resource limits on a bare subprocess."""
    def _set_limits():
        resource.setrlimit(resource.RLIMIT_CPU,  (max_cpu_seconds, max_cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS,   (max_memory_mb * 1024 * 1024, max_memory_mb * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    proc.register_pre_exec(_set_limits)

async def launch_tier3(agent_id: str, command: list[str]) -> AgentSession:
    """
    Tier 3: gVisor runsc container.
    runsc must be installed; each container is rootless within the user-space kernel.
    """
    container_id = f"agent-{agent_id[:8]}"
    runsc_path = "/usr/local/bin/runsc"
    result = await asyncio.create_subprocess_exec(
        runsc_path, "run",
        "--network=none",
        "--disable-net-raw",
        f"--root={container_id}",
        "--",
        "dockerd", "--bridge=none", "--iptables=false",
        # Actually launch the agent process directly — dockerd is only
        # needed if the agent itself spawns containers (→ escalate to Tier 4)
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return AgentSession(tier=IsolationTier.GVISOR, container_id=container_id)

async def launch_tier4(agent_id: str, snapshot_path: str) -> AgentSession:
    """
    Tier 4: Firecracker microVM from a pre-booted snapshot.
    Firecracker v1.6+ supports snapshot-restore in ~125ms.
    """
    vm_id = f"vm-{agent_id[:8]}"
    # firecracker --api-sock /path/to/{vm_id}.sock
    # POST /snapshot/load {snapshot_path: snapshot_path}
    sock = f"/var/run/firecracker/{vm_id}.sock"
    await asyncio.create_subprocess_exec(
        "firecracker",
        "--api-sock", sock,
        # API call to load snapshot would go here via httpx/unixsocket
    )
    return AgentSession(tier=IsolationTier.MICROVM, microvm_id=vm_id)
```

## Receipt

> Verified 2026-07-20 — Research from SandboxEscapeBench (Oxford + UK AISI, arXiv, March 2026) confirms frontier models achieve meaningful container escape rates on common misconfiguration scenarios. Each escape costs ~$1 at current API pricing. GPT-5 achieved 0.50 escape rate on difficulty-3+ scenarios; GPT-5.2 regressed to 0.27, demonstrating that capability and escape risk co-vary. The four-tier isolation stack described above reflects the current practitioner consensus from Blaxel.ai, AWS re:Inforce 2026, and E2B warm-pool architectures.

## See also

- [S-768 · When Prompts Become Shells: The Agent Framework RCE Paradigm](s768-when-prompts-become-shells.md) — CVE-2026-25592, Semantic Kernel RCE, the eval-injection chain that lands a shell in the first place.
- [S-830 · MCP Transport Resilience](s830-the-mcp-transport-resilience-stack.md) — the network layer inside the container perimeter.
- [S-112 · Threat-Model-Driven Sandbox Stack: Decision Matrix from Subprocess to Firecracker MicroVM](s112-the-threat-model-driven-sandbox-stack.md) — earlier treatment of the isolation decision matrix; S-1380 extends with capability-tier coupling and the escaping-capability model from SandboxEscapeBench.
