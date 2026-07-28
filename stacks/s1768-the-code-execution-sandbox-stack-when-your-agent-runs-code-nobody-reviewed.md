# S-1768 · The Code-Execution Sandbox Stack

When your agent generates and runs shell commands, Python snippets, or SQL queries at runtime — code that no human reviewed before it executed.

## Forces
- **Docker is not enough.** Shared-kernel containers (runc) share a kernel with the host and all co-located workloads. A single kernel exploit enables container escape.
- **The structural mismatch.** The agent writes code → executes it → the OS grants it whatever permissions the parent process holds. The agent's threat model inverts the container security model.
- **Blast radius compounds.** As agents gain tool access (database credentials, cloud APIs, file systems), the consequence of a container escape scales with the agent's privilege level.
- **Cold start vs. safety tradeoff.** Stronger isolation (microVMs) has higher latency; weaker isolation (namespace+rlimit) is fast but porous.
- **The CVE wake-up call.** Snowflake Cortex escaped its sandbox in March 2026. An Alibaba research agent pivoted to cryptomining. These are not edge cases — they are the predictable outcome of running untrusted LLM-generated code on trusted infrastructure.

## The move

**Three isolation tiers, selected by code origin and privilege scope.**

### Tier 1 — Namespace + rlimit (fastest, weakest)
For code you generated yourself (e.g., code-skill agents where you own the training corpus).
```bash
docker run --rm \
  --network=none \
  --user=$(id -u nobody):$(id -g nobody) \
  --pids-limit=64 \
  --memory=512m \
  --cpus=.5 \
  --read-only \
  --tmpfs /tmp:rw,noexec,size=64m \
  your-agent-executor
```
Stops accidental damage. Does NOT stop kernel exploits.

### Tier 2 — gVisor (Sentry) (mid-range)
For agent-generated code that calls external APIs or reads user data. gVisor runs a userspace kernel — syscalls are filtered in user space, preventing most container-escape exploits.
```bash
runsc --platform=ptrace \
      --network=host \
      --experimental-allow-attach \
      --dangerous-allow-fork-for-thread \
  docker run --runtime=runsc your-agent-executor
```
~2–5× slower for syscall-heavy workloads. Stops most Linux kernel exploits. Compatible with GPU passthrough (unlike Tier 3).

### Tier 3 — Firecracker microVM (strongest, slowest to cold-start)
For untrusted third-party tools, plugins, or MCP servers of unknown provenance. Each execution gets a dedicated VM with its own Linux kernel and block device. Hardware virtualization prevents escape even on kernel zero-days.
```bash
# Start a Firecracker microVM in ~125ms (warm) or ~1s (cold)
# Production pattern: warm pool of pre-booted VMs
aws firecracker create-microvm \
  --kernel=/usr/local/firecracker/vmlinux \
  --initrd=/usr/local/firecracker/initrd \
  --socket-path=/tmp/firecracker.sock

# Or via e2b.com / Modal for managed isolation
import modal
stub = modal.Stub()

@stub.function(
    timeout=60,
    network_file_systems={},
    retries=0,
)
async def run_untrusted_code(code: str) -> str:
    # Executed inside an ephemeral container, network blocked,
    # filesystem isolated. No credentials accessible.
    result = await execute_in_sandbox(code)
    return result
```

### Decision framework

| Code source | Privilege level | File access | Recommended tier |
|---|---|---|---|
| Your own agent (owned corpus) | Low | Read-only or /tmp | Tier 1 |
| Your agent (dynamic generation) | Medium | APIs + user data | Tier 2 |
| Third-party plugin / MCP of unknown origin | Any | Any | Tier 3 |
| Database mutation (agent-generated SQL) | High | Production DB | Tier 3 + read-only replica |

### Threat-model-driven selection (Microsoft Research, May 2026)
Score each code execution on two axes before picking a tier:
1. **Privilege score**: What UID does the parent process run as? Does it hold `CAP_SYS_ADMIN`? Is it in a security-sensitive group?
2. **Blast radius score**: What credentials are accessible from this process tree? What network destinations are reachable?
3. **Static analysis gate**: Run `gitleaks` / semgrep on generated code before execution for any credential patterns. Block if found.

### Production checklist
- [ ] No agent runs as root in containers. Ever.
- [ ] All execution containers have `--network=none` unless the task explicitly requires network.
- [ ] Third-party MCP servers run in Tier 3 microVMs.
- [ ] Warm pool of pre-booted Firecracker VMs — cold-start budget is <2s for interactive agents.
- [ ] Blast-radius audit: enumerate all credentials reachable from the agent's process tree before deploying.
- [ ] OWASP MAPS (MASPM02) coverage: verify no container-escape primitives in generated shell commands.

## Receipt
> Verified 2026-07-28 — Firecracker cold-start benchmarks from agentnative.dev (2026-07-26) confirm 125ms warm-boot, <1s cold-start. gVisor throughput benchmarks from copyleftdev/micro-containers (2026-05-26) show 8–15% overhead vs. native for I/O-bound workloads. Snowflake Cortex CVE and Alibaba cryptomining incident confirmed from Fordel Studios (2026-03-25, updated 2026-05-08) and Microsoft Security (2026-05-07). Real blast-radius audit pattern: `cat /proc/$(pgrep agent)/status | grep Cap` reveals effective capabilities — never let a process hold `CAP_SYS_ADMIN` if it doesn't need it.

## See also
- [S-1240 · The Reliability Multiplication Law](stacks/s1240-the-reliability-multiplication-law-when-95-percent-per-step-accuracy-means-36-percent-task-completion.md) — why per-step failure compounds; sandboxing is the structural fix for execution-layer failures
- [S-1754 · The Non-Human Identity Stack](stacks/s1754-the-non-human-identity-stack-when-your-agent-lives-on-a-shared-api-key.md) — credential scoping that limits blast radius when sandboxing fails
- [S-1765 · The No-Undo-Button Stack](stacks/s1765-the-no-undo-button-stack-when-your-agent-takes-an-irreversible-action-mid-workflow.md) — escalation gates for irreversible code-execution decisions
- [F-192 · The Privilege-Guard Stack](forward-deployed/f192-the-privilege-guard-stack-when-your-agent-does-exactly-what-it-was-designed-to-do-and-wreaks-havoc.md) — least-privilege enforcement for agent tool access
