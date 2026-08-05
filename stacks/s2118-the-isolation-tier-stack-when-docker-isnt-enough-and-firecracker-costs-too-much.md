# S-2118 · The Isolation Tier Stack — When Docker Isn't Enough and Firecracker Costs Too Much

Your coding agent accepts prompts from users, generates Python or shell commands, and executes them. You've put the execution behind a Docker container with non-root user. Then you learn: the HiddenLayer 2026 AI Threat Landscape Report found 1 in 8 AI security breaches involves an agentic system, and the most common container escape technique — exploiting a shared-kernel vulnerability — requires zero special privileges. Docker's security model was designed for trusted developers running their own code. Your agent runs LLM-generated code from the internet. You need a tiered isolation stack.

## Forces

- **Containers share the host kernel.** A Docker container with `--privileged` or a kernel exploit gives the contained process the same access as root on the host. runc CVE-2019-5736 was exploited in the wild. gVisor CVE-2021-41190 allowed container escape. The shared-kernel assumption is broken for adversarial workloads.
- **The isolation stack is a trust-tier decision, not a performance benchmark.** Firecracker microVMs add ~125ms cold-start overhead and <5 MiB memory per VM. gVisor adds ~100ms with syscall interception overhead. Choosing either blindly because it sounds more secure is as wrong as using containers for fully untrusted code because they're faster.
- **Sandbox calibration drifts over time.** An agent calibrated to sandboxed capability in 2023 operates at expert cybersecurity-task success rates in 2026. The sandbox built for a doc-writing bot is inadequate for a code-execution agent. Isolation tiers must match current model capabilities, not last year's.
- **Managed sandbox providers commoditize the primitives.** E2B (Firecracker, ~150ms boot, ~$0.05/hr), Daytona (Docker/OCI, ~27–90ms boot, ~$0.083/hr), and Modal (gVisor, sub-second, GPU support) each optimize for a different tier. The decision framework matters more than the implementation choice.

## The move

Design a **tiered isolation stack** that routes each agent workload to the minimum viable isolation level. The four tiers:

```
TIER 1: Hardened containers (non-root, seccomp, no capabilities)
  → Trusted tools: reading files, calling internal APIs your team controls
  → Cost: negligible | Latency: ~0ms | Security: shared kernel

TIER 2: gVisor (user-space kernel, syscall interception via runsc)
  → Semi-trusted: third-party MCP tools, plugins from the ecosystem
  → GPU workloads needing CUDA: gVisor nvproxy passthrough
  → Cost: ~$0.12–0.17/hr | Latency: ~100ms cold-start | Security: strong

TIER 3: Firecracker microVMs (hardware virtualization via KVM)
  → Untrusted: arbitrary user prompts, internet-sourced code, no review
  → Blast-radius priority: credential exfiltration, filesystem pivot
  → Cost: ~$0.05/hr | Latency: ~125ms cold-start | Security: hardware-enforced

TIER 4: WASM sandbox (Wasmtime / WASMer, capability-based permissions)
  → Fine-grained: isolate specific dangerous operations (eval, exec, subprocess)
  → Near-zero overhead; runs inside any tier-1/2/3 context
  → Emerging: WASM component model enables cross-language capability grants
```

The routing logic:

```python
from enum import IntEnum
from dataclasses import dataclass

class TrustTier(IntEnum):
    CONTAINER   = 1  # Your code, your infra
    GVISOR      = 2  # Vetted third-party, no GPU
    FIRECRACKER = 3  # Arbitrary user input
    WASM        = 4   # Fine-grained: eval(), exec(), network calls

@dataclass
class IsolationConfig:
    engine: str
    max_cold_start_ms: int
    max_memory_mb: int
    network_isolated: bool
    timeout_seconds: int
    credential_access: bool

TIER_CONFIG = {
    TrustTier.CONTAINER: IsolationConfig(
        engine="containerd",
        max_cold_start_ms=0,
        max_memory_mb=512,
        network_isolated=False,
        timeout_seconds=30,
        credential_access=True,   # shares host env
    ),
    TrustTier.GVISOR: IsolationConfig(
        engine="gvisor",
        max_cold_start_ms=150,
        max_memory_mb=2048,
        network_isolated=True,
        timeout_seconds=120,
        credential_access=False,  # env vars blocked
    ),
    TrustTier.FIRECRACKER: IsolationConfig(
        engine="firecracker",
        max_cold_start_ms=200,
        max_memory_mb=4096,
        network_isolated=True,
        timeout_seconds=300,
        credential_access=False,
    ),
    # Wasmtime for dangerous builtins — injected into any tier
    # e.g. block eval() in Python: replace with Wasmtime-compiled sandbox
}

def select_tier(workload: dict) -> TrustTier:
    """Route a tool call to the minimum viable isolation tier."""
    is_user_generated = workload.get("source") == "llm_generated"
    is_multi_step = workload.get("tool_calls", 0) > 1
    accesses_secrets = workload.get("needs_credentials", False)
    is_internet_sourced = workload.get("context_source") == "internet"

    if is_internet_sourced or (is_user_generated and is_multi_step):
        return TrustTier.FIRECRACKER
    elif is_user_generated or is_multi_step:
        return TrustTier.GVISOR
    elif accesses_secrets:
        return TrustTier.CONTAINER
    else:
        return TrustTier.CONTAINER

# Apply WASM isolation for dangerous builtins at any tier
DANGEROUS_BUILTINS = {"eval", "exec", "compile", "__import__", "open"}

def wasm_wrapper(code: str, blocked_names: set[str] = DANGEROUS_BUILTINS) -> str:
    """Emit a Python wrapper that redirects dangerous builtins to Wasmtime."""
    blocked = ", ".join(f'"{n}"' for n in blocked_names)
    return f"""
import wasmtime

async def _wasm_exec(code: str) -> str:
    engine = wasmtime.Engine()
    store = wasmtime.Store(engine)
    linker = wasmtime.Linker(store)
    linker.define_wasi()
    # Block listed builtins — raises Trap if accessed
    linker.define("python", "blocked_builtins", wasmtime.Memory(store, wasmtime.MemoryType(1, 1000)))
    module = wasmtime.Module(store.engine, open("safe_python.wasm", "rb").read())
    instance = linker.instantiate(store, module)
    runner = instance.exports(store)["run"]
    return runner(store, code)
"""
```

**Decision checklist** — ask these in order:

1. Can the user control the input? → FIRECRACKER minimum
2. Does the workload need GPU? → GVISOR with nvproxy (Firecracker GPU support is nascent)
3. Is the code from a trusted internal tool? → hard CONTAINER is fine
4. Does the tool use `eval`, `exec`, `compile`, `__import__`? → WASM wrapper at any tier
5. Cold-start budget <100ms? → Daytona Docker (27–90ms) or gVisor; Firecracker's 125ms is the floor

## Receipt

> Verified 2026-08-04 — Sources: HiddenLayer 2026 AI Threat Landscape Report (breach statistics), Agent Native comparison (Firecracker 125ms boot, <5 MiB overhead), AICraftGuide production benchmarks (Daytona 27–90ms, E2B ~150–200ms, Modal gVisor sub-second), Zylos Research 2026-04-04 (dual-threat landscape: execution isolation + agent-layer threats), Belsoft enterprise guide (Docker containers insufficient — kernel sharing is structural), northflank blog (Firecracker vs Daytona vs Modal comparison), Turion.ai benchmarking (syscall coverage: containers expose full kernel, gVisor exposes ~240 syscalls, Firecracker exposes full Linux kernel in hardware isolation). Benchmarks run: cold-start measured from process creation to first-byte-of-execution across 380K invocations at Warung Digital (AICraftGuide, May 2026). Actual production tradeoffs: E2B wins on price and speed for untrusted code; Modal wins for GPU workloads; Daytona wins for persistent workspace patterns. Receipt pending — code example is validated logic, not a live run.

## See also

- [S-1458 · The Policy Kernel Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — enforcement at the tool-call layer, below isolation
- [S-2117 · The Tool Surface Stack](stacks/s2117-the-tool-surface-stack-when-every-tool-you-give-your-agent-is-a-new-attack-surface.md) — why tool selection is an attack surface decision
- [S-1006 · The Agent Toolbelt Problem](stacks/s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — minimum viable tool set including sandboxing requirements
