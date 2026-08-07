# S-2274 · The Isolation Spectrum Stack — When Your Agent Runs Code and Nobody Drew the Fence

You give your agent a code execution tool. It writes a shell command, a Python snippet, or a SQL query — and the runtime fires it. Nobody reviewed the code. Nobody isolated the environment. The agent has the privileges of the process that spawned it. This is the isolation spectrum problem: most teams treat sandboxing as binary (none vs. Docker), but it is a dial with five distinct stops, and the wrong setting costs you either safety or latency.

## Forces

- **Agent-generated code is untrusted by definition.** No human reviews it before execution. Every code-execution tool call is a trust boundary, and the agent crosses it autonomously.
- **Isolation depth and latency are in tension.** Stronger isolation costs more startup time and memory. For short-lived agent tasks, a 125ms microVM boot can dominate execution time.
- **Standard containers are weaker than they look.** Docker/runc uses Linux namespaces — all containers on a host share the same kernel. One unpatched CVE compromises every container simultaneously.
- **The blast radius grows with tool access.** An agent with file write + shell + network access, running in a shared-kernel container, is one kernel exploit from full host compromise.
- **Teams migrate up the spectrum reactively.** They add gVisor after an incident. They switch to microVMs when cost analysis reveals the container compromise cost exceeded the isolation overhead. Proactive spectrum-based design is rare.

## The move

Treat sandboxing as a dial with five defined stops. Match each tool call to its appropriate isolation level, not to a default.

### The five-level isolation spectrum

| Level | Mechanism | Startup | Security | When to use |
|-------|-----------|---------|---------|-------------|
| **L0** | No sandbox (`exec()`, bare subprocess) | 0ms | None | Static developer scripts, offline tooling, single-tenant with full trust |
| **L1** | Docker/LXC (Linux namespaces + cgroups) | ~50ms | Weak — shared kernel | Internal trusted workloads, read-only tool access |
| **L2** | seccomp-BPF + hardened policies | ~5ms | Moderate — syscall allowlist | General-purpose agent tools, moderate risk |
| **L3** | gVisor (user-space kernel, runsc) | ~100ms | Strong — syscall interception in user space | Production agents with broad tool access, file I/O, network |
| **L4** | Firecracker microVM (hardware virtualization) | ~125ms | Near-VM — hardware isolation | Untrusted external tools, third-party code, high-risk execution |
| **L5** | Confidential Computing (SEV-SNP, TDX) | ~1s+ | Strongest — memory encryption, attestation | High-assurance workloads, compliance-mandated isolation |

### Practical implementation

```
python
# Tag each tool with its isolation requirement
TOOL_ISOLATION = {
    "read_file":    "L1",   # container is sufficient
    "write_file":  "L3",   # needs gVisor — writes can corrupt
    "shell_exec":  "L4",   # arbitrary commands → microVM
    "http_request": "L3",  # network egress → gVisor minimum
    "sql_query":   "L2",   # structured input, moderate risk
    "mcp_tool":    "L4",   # untrusted third-party code
}
```

```
python
def execute_tool(tool_name, args, isolation_level):
    match isolation_level:
        case "L1": return docker_container.run(cmd, timeout=30)
        case "L2": return seccomp_policy.run(cmd, syscalls=allowlist)
        case "L3": return gvisor_runsc.run(cmd, timeout=60)
        case "L4": return firecracker_vm.spawn(timeout=120)
        case _:
            raise ValueError(f"Unknown isolation level {isolation_level}")
```

### The critical insight: L1 is not safe enough for agents

Docker containers were designed to isolate multi-tenant workloads written by different teams. They were not designed to isolate code written by an LLM that an attacker can influence through prompt injection. The shared kernel is the failure point: CVE-2024-1086 (container escape via netfilter) and CVE-2022-0847 (Dirty Pipe) both allow container-to-host escalation. A production agent running L1 with a shell tool is one unpatched CVE from host root.

```
[Agent generates code]
        ↓
[Code executed in Docker container]
        ↓
[Container escape via kernel CVE]
        ↓
[Attacker gains host access]
        ↓
[All other agents on host compromised]
```

### Tool-specific isolation routing

Not every tool needs L4. Route by risk:

```
python
HIGH_RISK_TOOLS   = {"shell_exec", "eval", "exec", "subprocess"}
MODERATE_TOOLS    = {"write_file", "http_request", "sql_write", "browser"}
LOW_RISK_TOOLS    = {"read_file", "search", "http_get", "sql_read"}

def isolation_for(tool_name):
    if tool_name in HIGH_RISK_TOOLS:    return "L4"
    if tool_name in MODERATE_TOOLS:     return "L3"
    return "L2"
```

### Egress filtering at every level

Regardless of isolation level, apply network egress allowlisting at the host or sidecar level:

```
python
EGRESS_ALLOWLIST = {
    "read_file":    [],
    "write_file":  [],
    "shell_exec":  ["api.stripe.com:443", "api.github.com:443"],
    "http_request": ["${ALLOWED_DOMAINS}"],
}

def check_egress(tool_name, destination):
    allowed = EGRESS_ALLOWLIST.get(tool_name, [])
    if "${" in " ".join(allowed):  # template expansion
        allowed = expand_from_config(allowed)
    if destination not in allowed:
        raise EgressViolation(f"{tool_name} → {destination} not in allowlist")
```

### Rollback as a complement to isolation

Even with L4 isolation, agents can corrupt their own state. Pair isolation with checkpoint/rollback:

- **Filesystem snapshots**: `btrfs` or `overlayfs` snapshots before each agent task, rollback on failure signal.
- **Database branching**: Agent writes go to an ephemeral branch; merge only after human review or automated validation.
- **Crab runtime** (arXiv 2604.28138): Semantics-aware checkpoint/restore that captures agent-facing state and enables proactive rollback via API — the agent can request a restore to a known-good checkpoint.

```
python
def agent_task_with_rollback(task_id, tool_calls):
    snapshot_id = filesystem_snapshot_create()
    try:
        result = run_agent_task(tool_calls, isolation="L4")
        validate_output(result)
        return result
    except AgentFailure as e:
        filesystem_snapshot_rollback(snapshot_id)
        raise RetryableError(f"Task {task_id} failed, rolled back: {e}")
```

## Receipt

> Verified 2026-08-07 — Written from: Tian Pan, tianpan.co/blog/2026-03-09-agent-sandboxing-secure-code-execution (March 2026, 5-level isolation spectrum with boot times); Zylos Research, zylos.ai/research/2026-04-04 (February 2026 consensus that Docker is insufficient, Firecracker vs. gVisor comparison); arXiv 2604.28138, "Crab: A Semantics-Aware Checkpoint/Restore Runtime for Agent Sandboxes" (checkpoint/rollback pattern); Microsoft Security Blog, microsoft.com/security/blog/2026/07/16 (least-privilege tool binding). Distinct from S-812 (ephemeral workspace isolation — L1 focus) and S-1017 (transitive framework vulnerabilities — dependency focus). No duplicate: S-812 covers workspace-level isolation; this entry covers the full isolation spectrum with explicit mechanism-to-risk mapping and tool-specific routing.

## See also

- [S-812 · The Ephemeral Workspace Isolation Stack](stacks/s812-ephemeral-workspace-isolation.md) — L1/L2 workspace isolation pattern
- [S-1017 · The Transitive Framework Stack](stacks/s1017-the-transitive-framework-stack-when-your-agent-server-is-owned-through-a-dependency-you-didnt-know-you-had.md) — dependency-layer threat model
- [S-1000 · The Structural Agent Governance Stack](stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — policy-layer containment
