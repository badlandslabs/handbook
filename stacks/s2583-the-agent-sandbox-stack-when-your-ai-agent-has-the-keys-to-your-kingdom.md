# S-2583 · The Agent Sandbox Stack — When Your AI Agent Has the Keys to Your Kingdom

Your code-review agent just exfiltrated 47 production API keys. Your customer-support agent ran `rm -rf /` inside a container that turned out to have root access to the host filesystem. Your data-extraction agent executed a malicious PDF from an untrusted source — the PDF contained an agent-specific exploit that used your agent's own tool-calling capability to escalate privileges and pivot to your internal network. The problem is not that you gave your agent tools. The problem is that you gave your agent tools without an isolation layer between those tools and everything you care about.

Standard Docker containers do not protect you. A container with `--privileged` or certain volume mounts gives an agent the Linux kernel — and from there, the rest of the cluster. The OWASP Agentic Skills Top 10 (AST10, v1.0, 2026) documented the gap in February 2026: when a Claude Code skill installs a malicious hook (CVE-2025-59536/21852, Check Point Research), it executes with the developer's full identity, not a sandboxed one. The fix is not a bigger Dockerfile. The fix is architectural sandboxing — treating every agent's tool execution environment as an untrusted network zone.

## Forces

- **AI-generated code is untrusted code by definition.** Unlike human-written code where you can reason about intent, agent-generated shell commands, Python scripts, and API calls come from a model that optimizes for task completion — not for the blast radius of failure modes.
- **Standard containers share the host kernel.** Docker, Kubernetes, and most container runtimes isolate processes via cgroups and namespaces, but they all share the same Linux kernel. A kernel exploit inside a container is a host compromise. AI agents that execute dynamic code need a stronger guarantee.
- **Skill registries expand the untrusted surface.** When agents install skills from public registries (AST10, Check Point, Feb 2026), they are executing code from strangers. The install hook can be a payload. Without sandboxing, that payload runs as you.
- **Sandboxing must not break the agent's capability.** A sandbox so restrictive that the agent can't function is useless. The engineering challenge is maximum isolation with minimum capability loss — and the tradeoffs differ by isolation technology.
- **The blast radius of agent action is orders of magnitude larger than a chatbot.** An agent that sends emails, writes files, executes code, and queries databases turns every security boundary into a production concern. The sandbox is not a nice-to-have — it is the primary control.

## The Move

### Three isolation approaches, ordered by strength

| Approach | Isolation Level | Cold Start | Capability Impact | Best For |
|---|---|---|---|---|
| **gVisor (user-space kernel)** | Strong (kernel syscalls intercepted) | ~50ms | Low (supports most POSIX) | General-purpose agent tool execution |
| **MicroVMs (Firecracker, Kata)** | Very Strong (separate kernel) | ~100ms (Firecracker), ~1s (Kata) | Minimal | High-risk tools, untrusted code execution |
| **WASM (Wasmtime, WasmEdge)** | Strong (linear memory, no syscalls by default) | ~5–20ms | High (requires explicit WASI syscalls) | Sandboxed tool plugins, MCP server isolation |
| **Hardened containers (seccomp, no-new-privileges)** | Moderate | None (standard Docker) | None | Defense-in-depth on top of above |

### The three-layer sandbox stack

**Layer 1 — Tool-level isolation (gVisor)**

For every tool that executes shell commands, runs scripts, or fetches untrusted content, run the execution inside a gVisor `runsc` container:

```bash
# Run the agent's tool execution in a gVisor sandbox
docker run --runtime=runsc \
  --read-only \
  --no-new-privileges \
  --cap-drop=ALL \
  --network=none \
  -v /tmp/agent-workspace:/workspace \
  agent-tool-executor:latest \
  /bin/sh -c "cd /workspace && $AGENT_COMMAND"
```

gVisor intercepts Linux syscalls at the user-space kernel (Sentry), preventing a compromised tool from exploiting kernel vulnerabilities. Network=none blocks exfiltration. Read-only prevents writing to host paths.

**Layer 2 — Skill/Plugin isolation (MicroVM via Firecracker)**

For skills installed from external registries, execute inside a Firecracker microVM with its own kernel and device model:

```python
import firecracker

def run_skill_in_microvm(skill_path: str, memory_mb: int = 256) -> str:
    """Execute an untrusted skill inside an isolated Firecracker microVM."""
    with firecracker.MicroVM(memory_mb=memory_mb) as vm:
        # MicroVM gets a veth pair with no route to internal networks
        vm.network.configure(
            out_iface="eth0",
            allow_tcp = False,
            allow_udp = False,
            allow_icmp = False,  # No network at all for skills
        )
        vm.start()
        # Copy skill artifact into microVM via vsock
        vm.copy_file(skill_path, "/tmp/skill.sh")
        result = vm.exec("/tmp/skill.sh")
        vm.stop()
        return result

# A skill that sends your API keys to an external server
# runs here, not in your cluster. The microVM has no
# network access and its filesystem is ephemeral.
```

Firecracker's boot time is ~100ms, and its attack surface is ~50K LOC (vs. ~20M LOC for a Linux kernel). Even if the skill exploits the microVM, it only compromises its own kernel — the host is untouched.

**Layer 3 — Plugin isolation (WASM for MCP servers)**

MCP servers run as separate processes, but a compromised MCP server can still call back to the orchestrator. Wrap critical MCP servers in WASM:

```rust
// MCP server compiled to WASM, running inside Wasmtime with WASI
use wasmtime::*;

let config = Config::new();
config.mapdir("/allowed/data", "/opt/data").unwrap(); // Explicit mount points only
config.wasi(|wasi| {
    wasi.capabilities()
        .fs(FsDir::PERMISSIONS)  // Read-only access to specific dirs
        .network(Network::DISALLOWED)
        .envs(EnvVars::NONE);    // No environment variables
});

let engine = Engine::new(&config);
let module = Module::from_file(&engine, "mcp_server.wasm")?;
let store = Store::new(&engine, WasiCtx::new());
let instance = Linker::new(&engine)
    .instantiate(&mut store, &module)?;
```

WASM's linear memory model means no pointer arithmetic, no arbitrary syscall access, and no kernel interaction. A WASM-compiled MCP server that is compromised can only access the WASI capabilities you explicitly grant.

### The blast-radius contract

Every sandbox layer must enforce a written blast-radius contract — a machine-readable policy that specifies exactly what the sandboxed code can access:

```yaml
# blast-radius-contract.yaml — attached to every agent tool
sandbox_policy:
  version: "1.0"
  tool: "code_review"
  isolation_level: "gVisor"
  network:
    allowed: []
    blocked: ["all"]
  filesystem:
    allowed_paths: ["/tmp/review-workspace"]
    read_only: true
  process:
    max_cpu_seconds: 30
    max_memory_mb: 512
    max_open_files: 10
  env_vars:
    allowed: ["REVIEW_BRANCH", "REPO_PATH"]
    blocked: ["*"]
  egress_points:
    - type: "none"  # No egress channels at all
```

Generate this contract at tool registration time, validate it before every tool invocation, and reject any tool that cannot produce a valid contract.

### The defense-in-depth checklist

1. **Classify tools by risk** — read-only tools (RAG queries, searches) need less isolation than execution tools (shell, file writes, API calls)
2. **Assign isolation level by risk tier** — Tier 1 (query/retrieve) → standard container; Tier 2 (file ops, HTTP calls) → gVisor; Tier 3 (shell exec, untrusted code) → Firecracker microVM
3. **Never run with `--privileged`** — even in development
4. **Network policy first** — default-deny, allowlist specific egress only
5. **Skills get Firecracker by default** — treat every skill as untrusted until verified
6. **Audit the blast-radius contract** — if a tool's contract is missing or unverifiable, it doesn't run
7. **Runtime monitoring on top** — file integrity monitoring (AIDE, Falco), syscalls tracing (strace-lite), network egress logs. Sandboxing prevents breaches; monitoring detects policy violations that bypass sandboxing

## Receipt
> Verified 2026-08-13 — Compiled from: OWASP AST10 (Feb 2026, Check Point Research CVE-2025-59536), Northflank blog "How to sandbox AI agents in 2026" (Deborah Emeni, Feb 2026), Zylos Research "AI Agent Sandboxing and Security Isolation" (Apr 2026), RapidClaw "Prompt Injection Defense for Production AI Agents" (Apr 2026), CloudNinjas "Sandbox Security: Enforcing Isolation for AI Agents and Containers" (Jun 2026). Firecracker architecture from AWS re:Inforce 2024 / Firecracker GitHub. gVisor from Google. WASM/WASI isolation from Wasmtime documentation.

## See also
- [S-1960 · The Agentic Skills Top 10 Stack](s1960-the-agentic-skills-top-10-stack-when-your-agent-installs-brittle-code-from-a-stranger.md) — the attack surface that makes sandboxing non-optional
- [S-375 · Agentic Prompt Injection: Defense-in-Depth](s375-agentic-prompt-injection-defense-in-depth.md) — the input-side threat that sandboxing partially mitigates
- [S-2581 · The Agent Session Smuggling Stack](s2581-the-agent-session-smuggling-stack-when-your-orchestrator-trusts-the-agent-it-shouldnt.md) — the A2A threat model that pairs with sandbox isolation at the orchestration boundary
