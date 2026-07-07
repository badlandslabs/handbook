# S-758 · The Sandbox Is Now a First-Class Layer: Agent Code Execution Isolation

When agents generate and execute code on shared infrastructure, you have a trust problem that containers cannot solve. Docker namespaces and cgroups isolate visibility and resource consumption — but they do not interpose on syscalls. The agent's code runs with the host kernel's full permission surface. The fix is architectural: treat sandboxing as a dedicated infrastructure layer, not an afterthought.

## Forces

- **Agents generate untrusted code at runtime.** Unlike a developer who ships reviewed code, an agent produces and executes code without per-command human review. The threat model is fundamentally different from traditional containerized workloads — [Turion.ai, "Agent Sandboxing: Firecracker, gVisor & Production Isolation," May 22, 2026](https://turion.ai/blog/agent-sandboxing-firecracker-gvisor-microvm-architecture)
- **Docker shares the host kernel.** Namespaces and cgroups provide process isolation, not syscall isolation. A malicious or buggy agent command can interact with kernel interfaces directly — [Turion.ai, same source](https://turion.ai/blog/agent-sandboxing-firecracker-gvisor-microvm-architecture)
- **The agent stack is stratifying.** Specialized layers are emerging with different defensibility profiles. Sandboxing is clearly becoming its own distinct infrastructure tier, alongside orchestration and memory — [Philipp D. Dubach, "Don't Go Monolithic; The Agent Stack Is Stratifying," Hacker News discussion, February 2026](https://news.ycombinator.com/item?id=47114201), [HN comment by 7777777phil](https://news.ycombinator.com/item?id=47114201)
- **Managed platforms abstract the choice away.** E2B, Daytona, and Modal offer managed sandbox environments with pre-built tooling, but introduce vendor dependency and cost at scale — [CallSphere, "Agentic Sandboxing 2026: E2B, Daytona, and Modal Patterns," April 23, 2026](https://callsphere.ai/blog/agentic-sandboxing-2026-e2b-daytona-modal-patterns)

## The Move

Treat the sandbox as a separate deployment tier with its own decision framework:

- **Match isolation tier to threat model.** gVisor for dev/CI/CD (fast cold starts, sufficient isolation), Firecracker or Kata Containers for production (hardware-virtualized, minimal attack surface). Docker is not production-safe for untrusted agent code — [Turion.ai, same source](https://turion.ai/blog/agent-sandboxing-firecracker-gvisor-microvm-architecture)
- **Use managed platforms for speed, build custom for control.** E2B and Daytona handle pre-warmed environments, internet access, and tooling setup — useful for teams that want to ship without maintaining sandbox infrastructure. Modal provides serverless compute with sandboxed execution built in — [CallSphere, same source](https://callsphere.ai/blog/agentic-sandboxing-2026-e2b-daytona-modal-patterns)
- **Pre-warm sandboxes aggressively.** Cold start latency for Firecracker microVMs can exceed 100ms; pre-warmed pools eliminate this. This is not optional for interactive agent use cases.
- **Restrict filesystem and network scope within the sandbox.** Even inside an isolated VM, agents should operate with minimal filesystem visibility and controlled outbound network access.
- **Log and audit every execution.** Sandboxing without observability is theater. Capture what was executed, for how long, and what it produced.
- **Treat sandbox cost as a first-class budget line.** Sandboxes are billed per-second of execution. A multi-agent system where each agent maintains its own sandbox pool can easily rack up 10x the inference cost in execution infrastructure.

## Evidence

- **HN engineering discussion (2026):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." — 7777777phil, HN comment on stack stratification post — [HN thread](https://news.ycombinator.com/item?id=47114201)
- **Technical deep-dive:** Turion.ai benchmarked isolation tiers: gVisor adds ~5ms syscall overhead vs native, Firecracker microVMs add ~1ms with full hardware virtualization. Microsoft Security published research on prompt injection via generated code executables on May 7, 2026, raising the stakes — [Turion.ai article](https://turion.ai/blog/agent-sandboxing-firecracker-gvisor-microvm-architecture)
- **Enterprise platform analysis:** E2B targets deep research agents and coding agents with pre-built environments. Daytona positions itself for enterprise-grade isolation with audit trails. Modal integrates sandboxed execution with its serverless compute model — [CallSphere blog](https://callsphere.ai/blog/agentic-sandboxing-2026-e2b-daytona-modal-patterns)

## Gotchas

- **Pre-warming is load-bearing, not optional.** Without warm pools, your latency SLA collapses under concurrency. Each cold-start Firecracker microVM takes 100ms+ — unacceptable for interactive agents.
- **Managed platforms hide cost until you scale.** E2B and Daytona charge per sandbox-second. A system running 10 concurrent agents, each holding a sandbox, looks cheap at 1x concurrency and catastrophic at 100x.
- **Isolation without observability is theater.** A sandbox that silently executes malicious code is worse than no sandbox — it creates false confidence. Instrument every execution.
- **gVisor is not Kata/Firecracker.** gVisor interposes syscalls in userspace (Sentry) but still shares the host kernel. For production against a real threat model (prompt injection, adversarial agent output), hardware virtualization (Firecracker, Kata) is the correct tier.
