# S-709 · Agent Execution Isolation: The Five-Tier Sandbox Reference

Your agent writes Python at runtime and executes it. You never reviewed that code. Standard Docker shares the host kernel with every other workload — one container escape and the agent is in your production network. Five isolation tiers have converged in production; pick the one that matches what the code is actually doing.

## Forces

- Agents execute unreviewed code by design; the threat model is the inverse of traditional software development
- Docker/runc means shared kernel — every syscall routes to the same kernel that runs your databases, your secrets manager, your CI/CD agents
- Isolation strength trades against startup latency and cost; Firecracker microVMs cost 100–500ms and money per boot, while plain containers cost nothing
- The right tier depends on what the code *does*, not just how much you "trust" the model — a read-only formatter needs different protection than a network-capable code interpreter
- Cold-start overhead per call makes a secure sandbox unusable in latency-sensitive paths

## The move

### The five isolation tiers

Each tier covers a distinct slice of the threat surface. They are not interchangeable.

| Tier | Technology | Boot time | Isolation level | Appropriate use |
|------|-----------|-----------|-----------------|----------------|
| **T1** | Seatbelt (macOS), landlock (Linux 6.1+) | ~0ms | Syscall deny-listing via kernel APIs | Claude Code 1.3 default; internal code paths that are trusted but need damage containment |
| **T2** | gVisor (Sentry runtime + runsc) | ~50ms | Full syscall interception; user-space kernel | Moderate-untrusted code; interpreters without native syscall requirements |
| **T3** | Firecracker, Kata Containers | 100–500ms | Hardware-enforced kernel boundary per workload | Unreviewed agent-generated code; anything with filesystem or network access |
| **T4** | devcontainer spec + runtime | 1–5s | Full development environment | Coding agents needing compilers, package managers, shell access |
| **T5** | QEMU/KVM | 10–30s | Complete hardware virtualization | Third-party or adversarial workloads; compliance-required air-gapping |

**Firecracker wins the microVM tier** (T3) in practice: 125ms cold-boot vs. 500ms+ for Kata, 18MB vs. 50MB memory footprint, no legacy device emulation. E2B (375× YoY growth to 15M monthly executions, Mar 2024→2025; 88% Fortune 100 signed up by early 2026) and Vercel Sandbox (GA January 2026) both settled on Firecracker as their isolation engine.

### Why containers aren't enough

Docker containers using runc share the host Linux kernel. Every syscall goes directly to the host — filtered only by seccomp profiles and Linux capabilities, which are easy to misconfigure and easy for kernel CVEs to bypass. This was fine when the software inside containers was written, reviewed, and tested by engineers. It is not fine when an LLM generates the code at runtime and a prompt injection could steer it.

The failure mode is no longer theoretical:

| Incident | When | Mechanism |
|----------|------|-----------|
| Snowflake Cortex Code CLI escape | March 2026 | Unpatched runc CVE → container-to-host lateral movement |
| Alibaba research agent → cryptomining | 2025–2026 | Agent with network egress pivoted to crypto mining in cloud credits |
| Indirect prompt injection → tool call abuse | Ongoing | Malicious content in RAG documents, web pages, chat history changes what the agent calls |

### Two-layer threat model

Execution isolation (the sandbox) and agent-layer threats (prompt injection, tool poisoning) are independent problems:

```
Layer 1 — Agent behavior threats
  Prompt injection, capability over-granting, tool poisoning
         ↓ (the agent decides to call a tool)
Layer 2 — Execution threats
  Kernel CVE exploit, container escape, resource exhaustion
         ↓ (the code runs)
Containment boundary
  Sandboxing tier, egress filtering, resource caps
```

A clean prompt doesn't protect you from bad code. A strong sandbox doesn't protect you from a prompt injection that makes the agent call the wrong tool.

### WASM: the bounded-task exception

WebAssembly sits outside the five-tier ladder: near-zero microsecond startup, capability-based permissions (no syscall surface by default), and cross-platform portability. It handles **bounded, data-processing tasks** well. The tradeoff: no POSIX filesystem, no native library calls, no multi-process coordination without the component model.

Use WASM when: the task is a pure computation (parse JSON, transform data, run a regex engine). Use Firecracker (T3) when: the agent needs a shell, a real filesystem, compilers, or network access.

### Kubernetes-native isolation: kubernetes-sigs/agent-sandbox

SIG Apps launched `kubernetes-sigs/agent-sandbox` in November 2025. The core insight: **workload lifecycle management is orthogonal to isolation technology**. Sandboxes need lifecycle management (create, pause on idle, TTL-based deletion, pool sizing) that should not be entangled with the choice of Firecracker vs. gVisor vs. WASM.

The controller provides three CRDs:

```yaml
# Sandbox — isolated execution environment for one agent session
apiVersion: sandbox.sigs.k8s.io/v1
kind: Sandbox
metadata:
  name: code-interpreter-session-abc123
spec:
  runtime: firecracker        # firecracker | gvisor | wasm | kata
  timeout: 30m
  resources:
    cpu: "2"
    memory: "4Gi"
  egressPolicy: denied        # deny | allow(cidrs: [...])
---
# SandboxTemplate — versioned, reusable isolation profile
apiVersion: sandbox.sigs.k8s.io/v1
kind: SandboxTemplate
metadata:
  name: untrusted-code-interpreter
spec:
  runtime: firecracker
  resources:
    cpu: "1"
    memory: "2Gi"
  egressPolicy: denied
  maxConcurrent: 50
---
# SandboxPool — pre-warmed instance pool for zero cold-start
apiVersion: sandbox.sigs.k8s.io/v1
kind: SandboxPool
metadata:
  name: interpreter-pool
spec:
  templateRef: untrusted-code-interpreter
  size: 20
  prewarm: true    # fill pool at controller startup
```

Pre-warming is the operational linchpin. A pool of 20 pre-warmed Firecracker instances means the first 20 concurrent code executions hit zero cold-start latency. The controller manages pool sizing, TTL-based teardown, and pause-on-idle — you write the template once, the controller handles the lifecycle.

### Decision tree

```
Does the agent execute code it wrote or received at runtime?
│
├── No  → No sandbox needed; standard container with minimal perms
│
└── Yes → Is the code from a trusted source (your own pipeline)?
          │
          ├── Yes → gVisor (T2): intercept syscalls, 50ms boot
          │
          └── No (unreviewed) → Does it need POSIX FS, network, or shell?
              │
              ├── No  → WASM: microsecond boot, capability-denied by default
              │
              └── Yes → Firecracker microVM (T3):
                          • pre-warmed pool for latency tolerance
                          • egress deny-by-default
                          • session-level TTL (30m default)
                          → See [S-690 · Execution Tier Routing](stacks/s690-execution-tier-routing.md) for
                            runtime routing when one agent calls multiple tools at different tiers
```

## Receipt

> Verified 2026-07-06 — kubernetes-sigs/agent-sandbox (Nov 2025, SIG Apps), Fordel Studios (Mar 2026): Snowflake + Alibaba incidents, E2B 375× growth + 88% Fortune 100 stat, Zylos Research (Apr 2026): five-tier taxonomy and syscall interception model, Digital Applied (May 2026): Vercel Sandbox GA January 2026, Firecracker 125ms boot / 18MB spec, WASM capability model tradeoffs.

## See also

- [S-690 · Execution Tier Routing](stacks/s690-execution-tier-routing.md) — runtime router that classifies each tool call and routes to the matching tier from this reference; S-709 is the isolation technology companion
- [F-06 · Agent Sandboxing](forward-deployed/f06-agent-sandboxing.md) — field note intro; S-709 is the production engineering deep-dive
- [S-679 · MCP: The Interoperability Standard with a 92% Exploit Surface](stacks/s679-mcp-tool-schema-standard-with-security-warnings.md) — agent-layer threats (tool poisoning, prompt injection) that compound execution-layer risk
- [S-352 · Agentic Compensation Keys](stacks/s352-agentic-compensation-keys.md) — retry and idempotency for sandbox calls that fail mid-execution
