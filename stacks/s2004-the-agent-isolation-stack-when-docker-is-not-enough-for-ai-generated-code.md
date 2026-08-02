# S-2004 · The Agent Isolation Stack — When Docker Is Not Enough for AI-Generated Code

When your agent writes a shell command and your OS runs it with the same permissions as your agent process — that's your security posture. Docker containers share the host kernel. Namespaces and cgroups limit what the agent can *see*, but a kernel CVE grants everything the agent can *do*. In 2026, with prompt injection rates hitting 73% of production AI deployments and container-escape CVEs actively exploited, Level 1 isolation is not a safe default for any agent that touches user input. The fix is a risk-calibrated isolation stack.

## Forces

- **AI-generated code is untrusted by nature.** The same prompt produces different code each run. Static analysis and code review provide no guarantees. In 2025, 45% of AI-generated code failed security tests (Veracode); prompt injection appeared in 73% of production deployments.
- **Isolation depth and operational cost trade off.** Hardware virtualization gives the strongest boundary but adds 100–200ms cold-start and GPU passthrough complexity. Userspace kernels give near-container performance with strong syscalls interposition. Choosing the wrong level means either over-paying on every execution or under-isolating critical paths.
- **Prompt injection pivots to execution.** A successful prompt injection doesn't just manipulate agent output — it directs the agent to *call the wrong tool with the wrong arguments*. Sandboxing limits what that call can reach.
- **Most teams pick a sandbox level once and never revisit it.** A sandbox chosen for "works in demo" typically means Level 1 Docker, which is still the dominant production default despite the threat model having fundamentally changed.

## The Move

Treat isolation as a dial, not a binary. Map risk profile to isolation level, then enforce it structurally.

### The Five Isolation Levels

| Level | Technology | Boot Time | Overhead | Threat Model |
|-------|-----------|-----------|----------|-------------|
| 0 | No sandbox — raw subprocess | ~0ms | None | Trusted code only |
| 1 | Docker/runc (namespaces + cgroups) | <100ms | <5MB | Tenant isolation, no untrusted input |
| 2 | seccomp-BPF + hardened policies | ~0ms | Negligible | Syscall allowlist, shared kernel |
| 3 | gVisor (runsc) — userspace kernel | ~100ms | ~50MB | No shared kernel surface |
| 4 | Firecracker / Kata Containers — microVMs | ~125ms | <5MB (FC) | Hardware virtualization boundary |
| 5 | WebAssembly (WASM) — capability model | ~1ms | <1MB | Sandboxed by design, no OS access |

### The Decision Framework

**Level 1 (Docker) is correct when:** agent-generated code never touches external input, the agent has no credential access, and your blast radius is bounded by a throwaway container. Not for production user-facing agents.

**Level 2 (seccomp-BPF) is correct when:** you need syscall-level control without VM overhead. Start with a deny-by-default policy that allows only `read`, `write`, `exit`, and `sigreturn` — add exceptions from the bottom up as the agent proves it needs them.

**Level 3 (gVisor) is correct when:** you need strong isolation without the cold-start penalty of a VM. gVisor implements a POSIX-compatible kernel in userspace (Sentry) that intercepts all syscalls. No container-escape CVE can reach the host kernel. Performance cost is ~5–10% for I/O-heavy workloads. gVisor's `runsc` runtime works with Docker and Kubernetes natively.

**Level 4 (Firecracker microVMs) is correct when:** you need the strongest available isolation for arbitrary code execution, have tolerance for 100–200ms cold-start, and need hardware-level VM boundaries (e.g., compliance requirements, multi-tenant environments, or agents with credential access to production systems). Firecracker's <5MB memory overhead and sub-125ms boot make it the most practical production-grade microVM. Kata Containers adds Kubernetes compatibility at the cost of heavier VMs.

**Level 5 (WASM) is correct when:** you can express the workload as a WASM module. The capability model (no file system, no network by default) makes it the strongest default-deny option. Practical for structured compute tasks; awkward for arbitrary shell command execution.

### The Practical Stack

```
Agent Tool Executor
       │
       ▼
┌─────────────────────────┐
│  Level 2: seccomp-BPF   │  ← Baseline: syscall allowlist
│  (deny-all + allowlist) │     on the executor process
└────────────┬────────────┘
             │ (if external input)
             ▼
┌─────────────────────────┐
│  Level 3: gVisor (runsc)│  ← Default for shell/code tools
│  Userspace kernel        │     with user-controlled input
└────────────┬────────────┘
             │ (if credentials present
             │  or compliance required)
             ▼
┌─────────────────────────┐
│  Level 4: Firecracker   │  ← Credential-bearing tools,
│  MicroVM per execution   │     production web-facing agents
└─────────────────────────┘
```

Start at Level 2 everywhere. Promote to Level 3 for any tool that accepts user-provided arguments. Promote to Level 4 for any tool that accesses credentials, external APIs, or production data.

### Production Anti-Patterns

- **Promoting down for performance.** "gVisor adds 5% overhead" is not a valid reason to drop to Level 1 for untrusted-input code. The CVE that escapes your shared kernel costs more than 5% latency.
- **Level 0 for "just one tool."** The single subprocess call that skips the sandbox because it "only reads a config file" is the pivot point for prompt injection.
- **No blast-radius audit.** Every tool gets mapped to an isolation level at onboarding. When a new tool is added, the isolation level is decided as part of the tool registration, not retroactively after an incident.
- **Treating container isolation as VM isolation.** A Docker container with `--privileged` or improperly configured seccomp is not a sandbox. Run `docker run --rm --cap-drop ALL --security-opt=no-new-privileges` as the minimum bar, then add gVisor or a microVM.

### Graded Implementation

**Week 1 (Level 2 baseline):** Apply seccomp-BPF deny-by-default to all agent executor processes. Audit the allowlist once — it surfaces every syscall the agent actually needs, which is almost never the full Linux surface.

**Week 2–3 (Level 3 rollout):** Switch shell and code-execution tools to gVisor `runsc` runtime. Test against the agent's full tool suite. Most workloads work without modification; Python REPL and some shell features need accommodation.

**Month 2 (Level 4 for credential tools):** Identify every tool with credential access. Wrap each in a Firecracker microVM. Implement a tool-classification registry so isolation level is queryable: `tool_registry.get_isolation_level("send_email") → "firecracker"`.

## Receipt

> Verified 2026-08-02 — Written against: Turion.ai "Agent Sandboxing: Firecracker, gVisor & Production Isolation" (May 22, 2026), Tian Pan "Agent Sandboxing and Secure Code Execution" (March 9, 2026), Zylos Research "AI Agent Sandboxing and Security Isolation" (April 4, 2026), Agent Native comparison (July 26, 2026), Johal.in benchmarks (April 28, 2026), Microsoft Security research on MCP remote code execution (May 7, 2026), Veracode State of Software Security 2025, Veracode prompt injection in production AI deployments 2025. Boot time benchmarks: Docker <100ms, gVisor ~100ms, Firecracker ~125ms, Kata ~1s. gVisor overhead ~50MB, Firecracker <5MB. S-298 (sandboxing as persistence layer) covered the motivation but not the isolation technology decision framework; this chapter covers the comparative analysis and decision stack.

## See also

- [S-250 · The Trusted-File Escape Stack](s250-the-trusted-file-escape-stack-agent-stays-inside-escapes-via-trusted-host-toolchain.md) — file-write pivots that bypass Level 1 Docker
- [S-298 · Sandboxing Is the New Persistence Layer](s298-sandboxing-is-the-new-persistence-layer.md) — treating isolation as first-class infrastructure
- [S-365 · MCP Supply Chain: From `npx` to Production Catalog](s365-mcp-supply-chain-from-npx-to-production-catalog.md) — MCP artifact provenance and signing
- [S-1006 · The Agent Toolbelt Problem](s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — tool permission tiering
