# S-1930 · The Execution Sandbox Stack — When Your Agent Runs Untrusted Code With Root Access

Your AI agent generates a shell command at runtime, executes it, and the OS grants whatever permissions the host process already has. You never reviewed that command. You didn't approve its execution. It has network access, a shared kernel, and the same filesystem permissions as your production workloads. This is not a theoretical risk — Snowflake Cortex escaped its sandbox in March 2026. An Alibaba research agent pivoted to cryptomining. Microsoft published prompt-injection chains leading to remote code execution across agent frameworks in May 2026. CISA and allied agencies issued a joint advisory the same month flagging that most production deployments grant agents broad tool access without per-action logging or isolation boundaries. More than half of enterprise AI agents still run with no sandbox boundary between agent-generated code and the host. The question is not whether your agent will execute untrusted input — it will. The question is what happens after.

## Forces

- **Standard containers share the host kernel.** Docker's runc executes all syscalls directly on the host. Seccomp profiles and capabilities are the only gate — and they're routinely misconfigured for agent workloads where the command itself is unknown at deployment time.
- **The code is stochastic.** Unlike a traditional application, the same prompt produces different code each run. Static analysis can't guarantee safety because there is no static artifact. You cannot approve what you haven't seen.
- **Boot latency constrains when isolation is practical.** A 125ms Firecracker boot is acceptable for a task-level sandbox. It's not acceptable for every tool call in a fast agent loop. Isolation technology choice is a latency tradeoff.
- **Security and overhead trade in opposing directions.** The strongest isolation (hardware VMs) has the highest resource cost. The lightest (WASM) has the lowest overhead but limited syscall coverage. You cannot apply the same primitive everywhere.

## The move

**Four isolation primitives, each with a distinct fit:**

| Primitive | Boot time | Memory | Host kernel | Best for |
|---|---|---|---|---|
| gVisor (Sentry) | ~100ms | ~20MB | None intercepted | Task-level Python/code execution, general-purpose |
| Firecracker microVM | ~125ms | ~5MB | None (KVM) | Long-running agent tasks, stateful workloads |
| WASM (WASI) | <1ms | <1MB | None (capability model) | Fast tool calls, constrained operations |
| Kata Containers | ~1–2s | ~50–100MB | None (VM) | Legacy app compatibility, highest threat model |

**Decision tree:**

1. **Does the operation need POSIX syscalls?** → WASM (limited), gVisor (full), Firecracker (full)
2. **Is the operation under 1 second of expected duration?** → WASM or gVisor
3. **Does the operation need persistent state or network?** → Firecracker
4. **Is the threat model nation-state?** → Kata Containers

**The layered pattern for agent workloads:**

```
Host (no trust)
  └── MCP Gateway (policy enforcement — S-1458)
        ├── Fast tools (<1s) → WASM runtime (WASI)
        ├── General Python/shell → gVisor (Sentry)
        └── Long-running / network-facing → Firecracker microVM
```

**Key rule:** never run agent-generated code in the same process context as the agent controller. The sandbox is the trust boundary, not the agent itself.

```python
import asyncio
import subprocess
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class IsolationTier(Enum):
    WASM = "wasm"       # <1ms boot, capability-gated, no filesystem
    GVISOR = "gvisor"   # ~100ms boot, full POSIX, user-space kernel
    FIRECRACKER = "fc"  # ~125ms boot, hardware VM, full isolation


@dataclass
class SandboxConfig:
    tier: IsolationTier
    max_memory_mb: int = 256
    timeout_seconds: int = 30
    network_allowed: bool = False
    read_only_fs: bool = True


class IsolationRuntime(Protocol):
    async def spawn(self, config: SandboxConfig) -> str: ...
    async def run(self, sandbox_id: str, command: str, input_data: bytes) -> bytes: ...
    async def destroy(self, sandbox_id: str) -> None: ...


class FirecrackerRuntime:
    """Firecracker microVM — ~125ms boot, full VM isolation via KVM."""

    def __init__(self, kernel_path: str, rootfs_path: str):
        self.kernel_path = kernel_path
        self.rootfs_path = rootfs_path
        self._running: dict[str, subprocess.Popen] = {}

    async def spawn(self, config: SandboxConfig) -> str:
        sid = str(uuid.uuid4())[:8]
        # Firecracker starts a microVM with a jailed fs and limited memory
        cmd = [
            "firecracker",
            "--api-sock", f"/tmp/fc-{sid}.sock",
            "--config-json", "-",
        ]
        fc_cfg = {
            "boot-source": {"kernel_image_path": self.kernel_path, "initrd_path": ""},
            "drives": [{"drive_id": "root", "path_on_host": self.rootfs_path, "is_root_device": True}],
            "machine-config": {"vcpu_count": 1, "mem_size_mb": config.max_memory_mb},
            "network-interfaces": [],
        }
        import json
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        proc.stdin.write(json.dumps(fc_cfg).encode())
        await proc.stdin.drain()
        proc.stdin.close()
        self._running[sid] = proc
        return sid

    async def run(self, sandbox_id: str, command: str, input_data: bytes) -> bytes:
        sock = f"/tmp/fc-{sandbox_id}.sock"
        # Send command via Firecracker FCIOCTL
        proc = await asyncio.create_subprocess_exec(
            "nc", "-U", sock,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(
            proc.communicate(input=command.encode() + b"\n" + input_data),
            timeout=30,
        )
        return out

    async def destroy(self, sandbox_id: str) -> None:
        if sandbox_id in self._running:
            self._running[sandbox_id].terminate()
            del self._running[sandbox_id]


class AgentToolExecutor:
    """Routes each tool call to the appropriate isolation tier."""

    def __init__(self):
        self.gvisor = None       # initialized on first use
        self.firecracker: FirecrackerRuntime | None = None
        self.wasm = None         # initialized on first use

    def _select_tier(self, tool_name: str, estimated_duration_s: float) -> IsolationTier:
        # Fast read-only tools → WASM
        if estimated_duration_s < 1 and tool_name in {"grep", "wc", "head", "tail"}:
            return IsolationTier.WASM
        # Long-running or network-required → Firecracker
        if estimated_duration_s > 10 or "http" in tool_name or "network" in tool_name:
            return IsolationTier.FIRECRACKER
        # Everything else → gVisor
        return IsolationTier.GVISOR

    async def execute(self, tool_name: str, command: str,
                      estimated_duration_s: float = 5) -> bytes:
        tier = self._select_tier(tool_name, estimated_duration_s)
        config = SandboxConfig(
            tier=tier,
            max_memory_mb=256,
            timeout_seconds=max(estimated_duration_s * 2, 30),
            network_allowed=tier == IsolationTier.FIRECRACKER,
        )

        # Lazy-init the runtime for the selected tier
        if tier == IsolationTier.FIRECRACKER:
            if not self.firecracker:
                self.firecracker = FirecrackerRuntime("/opt/fc/vmlinux", "/opt/fc/rootfs.ext4")
            runtime: IsolationRuntime = self.firecracker
        # gVisor and WASM runtimes initialized similarly
        # ...

        sandbox_id = await runtime.spawn(config)
        try:
            return await runtime.run(sandbox_id, command, b"")
        finally:
            await runtime.destroy(sandbox_id)
```

## Receipt

> Verified 2026-07-31 — Sandboxing taxonomy confirmed against production practitioner consensus (Fordel Studios, Zylos Research, TURION.AI, Paperclipped, arXiv 2603.02277). Isolation tier decision table matches the four-primitive framework from Zylos 2026-04-04. Firecracker boot time (~125ms, 5MB) confirmed against Amazon Firecracker public benchmarks. Snowflake Cortex sandbox escape (March 2026) and Alibaba cryptomining incident (March 2026) cited in Fordel Studios research. Microsoft research (May 7, 2026) on prompt injection → RCE confirmed via TURION.AI citing. CISA joint advisory (May 1, 2026) confirmed via TURION.AI citing. E2B platform growth (40K → 15M executions/month, 375× in one year) from Fordel Studios. Fortune 100 on E2B: 88% — Cisco RSA 2026 reference. Code example is structural pseudocode illustrating the pattern — Firecracker socket API calls use simplified `nc` illustration; production use should call the Firecracker HTTP API directly.

## See also

- [S-1458 · The Policy-Kernel Agent Stack](s1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — Policy enforcement at the MCP/A2A gateway; sandboxing is Layer 3 of the policy kernel
- [S-1927 · The MCP Token Wall Stack](s1927-the-mcp-token-wall-stack-when-three-servers-consume-71-percent-of-your-context-before-your-agent-does-anything.md) — MCP server overhead that compounds when every server also spins up a sandbox
- [S-1929 · The Fallback Ladder Stack](s1929-the-fallback-ladder-stack-when-your-agent-can-recover-but-doesnt-know-how.md) — Recovery when sandbox execution itself fails (OOM, timeout, kernel panic)
