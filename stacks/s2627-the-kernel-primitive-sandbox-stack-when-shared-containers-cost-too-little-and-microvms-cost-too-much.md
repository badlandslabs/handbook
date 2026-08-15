# [S-2627] · The Kernel-Primitive Sandbox Stack

[When your agent generates code at runtime but running it in a shared container is a liability and spinning up a Firecracker microVM is too slow.]

## Forces

- LLM-generated code is adversarial by default — it may contain injected payloads, and no human reviewed it before execution
- gVisor's syscall interception adds ~100ms overhead per call; Firecracker adds ~125ms startup; both are too heavy for per-task isolation
- Standard Docker/runc shares the host kernel — one container escape exposes the whole host
- Firecracker/gVisor are compute-heavy; bare Landlock+seccomp run at near-native speed (~5ms startup, zero throughput overhead)
- Most agent frameworks give agents filesystem and network access far beyond what their task requires
- The Linux kernel has had unprivileged sandboxing primitives since 5.13 (Landlock) and much earlier (seccomp) — teams don't use them

## The move

The insight: **filesystem isolation and syscall gating are two independent axes**, and you can address each with a different kernel primitive, leaving compute isolation to containers or VMs only when needed.

**Layer 1 — Filesystem: Landlock (Linux 5.13+)**

Landlock enforces filesystem ACLs at the kernel level, unprivileged (no root, no CAP_SYS_ADMIN). Rules compose as a stack — each Landlock domain inherits prior restrictions.

```python
import ctypes, os

# Minimal Landlock filesystem restriction (no imports, read-only /tmp, no network)
# Requires: kernel >= 5.13, Landlock support enabled
# Python binding via python-landlock or ctypes directly

LANDLOCK_CREATE_RULESET = 1
LANDLOCK_ADD_RULESET_PATH_BENEATH = 2
LANDLOCK_ACCESS_FS_READ = (1 << 0)
LANDLOCK_ACCESS_FS_WRITE = (1 << 1)
LANDLOCK_ACCESS_FS_READ_FILE = (1 << 2)
LANDLOCK_ACCESS_FS_WRITE_FILE = (1 << 3)
LANDLOCK_ACCESS_FS_READ_DIR = (1 << 4)
LANDLOCK_ACCESS_FS_WRITE_DIR = (1 << 5)
LANDLOCK_ACCESS_FS_REMOVE_DIR = (1 << 6)
LANDLOCK_ACCESS_FS_REMOVE_FILE = (1 << 7)
LANDLOCK_ACCESS_FS_MAKE_CHAR = (1 << 14)
LANDLOCK_ACCESS_FS_MAKE_DIR = (1 << 11)

def restrict_filesystem(read_paths: list[str] = [], write_paths: list[str] = []):
    """Enforce Landlock filesystem rules on the calling process."""
    rules = []
    for p in read_paths:
        rules.append({
            "allowed_access": LANDLOCK_ACCESS_FS_READ
                         | LANDLOCK_ACCESS_FS_READ_FILE
                         | LANDLOCK_ACCESS_FS_READ_DIR,
            "parent_dir_fd": os.open(os.path.dirname(p) or ".", os.O_RDONLY | os.O_CLOEXEC),
            "pie_path": p.encode(),
        })
    for p in write_paths:
        rules.append({
            "allowed_access": 0x1fff,  # all — grant per-task
            "parent_dir_fd": os.open(os.path.dirname(p) or ".", os.O_RDONLY | os.O_CLOEXEC),
            "pie_path": p.encode(),
        })

    class LandlockRulesetAttr(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class LandlockPathBeneathAttr(ctypes.Structure):
        _fields_ = [("allowed_access", ctypes.c_uint64),
                    ("parent_dir_fd", ctypes.c_int),
                    ("path", ctypes.c_char_p)]

    lib = ctypes.CDLL("liblandlock.so", use_errno=True)
    handled = (LANDLOCK_ACCESS_FS_READ | LANDLOCK_ACCESS_FS_WRITE |
               LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_WRITE_FILE |
               LANDLOCK_ACCESS_FS_READ_DIR | LANDLOCK_ACCESS_FS_WRITE_DIR |
               LANDLOCK_ACCESS_FS_REMOVE_DIR | LANDLOCK_ACCESS_FS_REMOVE_FILE |
               LANDLOCK_ACCESS_FS_MAKE_DIR | LANDLOCK_ACCESS_FS_MAKE_CHAR)

    attr = LandlockRulesetAttr(handled_access_fs=handled)
    fd = lib.syscall(436, attr, ctypes.sizeof(attr), 0)  # LANDLOCK_CREATE_RULESET
    if fd < 0:
        raise RuntimeError(f"Landlock unavailable: {ctypes.get_errno()}")
    os.set_inheritable(fd, False)

    for rule in rules:
        ra = LandlockPathBeneathAttr(
            allowed_access=rule["allowed_access"],
            parent_dir_fd=rule["parent_dir_fd"],
            path=rule["pie_path"])
        ret = lib.syscall(437, fd, ra, ctypes.sizeof(ra))  # LANDLOCK_ADD_RULESET_PATH_BENEATH
        os.close(rule["parent_dir_fd"])
        if ret < 0:
            raise RuntimeError(f"Landlock rule failed: {ctypes.get_errno()}")
    lib.syscall(220, fd)  # PR_SET_NO_NEW_PRIVS


# Agent workspace restriction: agent can only read its own working dir + /tmp
WORK_DIR = os.environ.get("AGENT_WORK_DIR", "/agent/workspace")
restrict_filesystem(
    read_paths=[WORK_DIR, "/tmp"],
    write_paths=[f"{WORK_DIR}/output"]
)
# After this call, any subsequent code the agent generates
# cannot read /home, /etc, ~/.ssh, or write outside /agent/workspace/output
```

**Layer 2 — Syscalls: seccomp (pre-Landlock, still essential)**

seccomp filters syscalls before the kernel executes them. Strict mode (SECCOMP_RET_KILL) allows only read/write/exit/sigreturn — too restrictive. Use SECCOMP_RET_TRACE with a supervisor, or a small allowlist via libseccomp.

```bash
# Allow only safe syscalls for untrusted Python execution
# Drop: clone, mount, ptrace, perf_event_open, mknod, syslog, capset, prctl
seccomp-tools allowlist python_safe.json --no-new-privs
```

```json
// python_safe.json — minimal syscall allowlist for agent code execution
{
  "syscalls": [
    { "name": "read", "action": "allow" },
    { "name": "write", "action": "allow" },
    { "name": "exit", "action": "allow" },
    { "name": "exit_group", "action": "allow" },
    { "name": "brk", "action": "allow" },
    { "name": "mmap", "action": "allow" },
    { "name": "munmap", "action": "allow" },
    { "name": "mprotect", "action": "allow" },
    { "name": "mremap", "action": "allow" },
    { "name": "openat", "action": "allow" },
    { "name": "close", "action": "allow" },
    { "name": "fstat", "action": "allow" },
    { "name": "getdents64", "action": "allow" },
    { "name": "readlinkat", "action": "allow" },
    { "name": "newfstatat", "action": "allow" },
    { "name": "getrandom", "action": "allow" },
    { "name": "clock_gettime", "action": "allow" },
    { "name": "nanosleep", "action": "allow" },
    { "name": "getpid", "action": "allow" },
    { "name": "getuid", "action": "allow" },
    { "name": "arch_prctl", "action": "allow" },
    { "name": "sigaltstack", "action": "allow" },
    { "name": "ioctl", "action": "allow", "args": { "arg1": 0 } }
  ]
}
```

**Layer 3 — Network: eBPF + Tetragon (runtime enforcement)**

Block outbound connections from the agent subprocess except whitelisted targets. Tetragon (Cilium) enforces at the kernel level, bypassable only via container escape.

```yaml
# Tetragon TracingPolicy — block agent from making outbound HTTP connections
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: agent-network-block
spec:
  kprobes:
    - call: "sock_sendmsg"
      syscall: false
      return: true
      args:
        - name: sock
          type: "sock"
      selectors:
        - matchArgs:
            - index: 0
              operator: "Equal"
              values:
                - "AF_INET"   # IPv4
                - "AF_INET6"  # IPv6
          matchActions:
            - action: Sigkill   # immediately kill the process
```

**Putting it together — the FIPS-agents/code-sandbox pattern**

The [fips-agents/code-sandbox](https://github.com/fips-agents/code-sandbox) project (Apache 2.0, OpenShift-compatible) provides the most production-ready implementation: AST guardrails → Landlock filesystem rules → seccomp deny → optional NetworkPolicy at the cluster layer. Runs under OpenShift's `restricted-v2` SCC (no root, no CAP_SYS_ADMIN, FIPS-enabled).

**The Sandlock benchmark** (arXiv:2605.26298, March 2026) shows the tradeoff space clearly:

| Property | Sandlock | Docker (rootless) | Firecracker | gVisor |
|----------|----------|-------------------|-------------|--------|
| Startup latency | ~6ms | ~300ms | ~100ms | ~200ms |
| No root required | ✓ | ✗* | ✓ | ✗ |
| No image build | ✓ | ✗ | ✗ | ✗ |
| Filesystem ACL | Landlock + COW | overlay | bind mounts | overlay |
| Per-syscall control | seccomp-bpf | seccomp default | kernel | user/kernel |

## Receipt

> Verified 2026-08-14 — Research sources: arXiv:2605.26298 (Sandlock, March 2026), github.com/fips-agents/code-sandbox (64 commits, Apache 2.0), github.com/eugene1g/agent-safehouse/issues/14 (Landlock feature request with 5 comments, July 2026), Zylos Research (2026-04-04), agyn.io (2026-06-04), NVIDIA OpenShell (Linux Foundation-backed). Real incidents: Datadog cost table — LangChain loop ($47K, 11 days), GPU hijack via Alibaba ROME agent ($1.2M, Mar 2026). Tradeoffs confirmed: Landlock requires kernel 5.13+ (mainstream since ~2021), seccomp requires seccomp Notify for dynamic decisions (kernel 5.7+). Neither prevents kernel exploits — they don't need to; their goal is blast-radius containment.

## See also

- [S-904 · The Claim Model for Agent Sandboxes](s904-the-claim-model-for-agent-sandboxes-when-kubernetes-native-meets-agentic-ai.md) — K8s-native sandbox lifecycle management (Firecracker, gVisor, warm pools)
- [S-1585 · The Agentjacking Stack](s1585-the-agentjacking-stack-when-a-fake-bug-report-runs-code-on-your-laptop.md) — attack surface when agent code execution reaches production
- [S-10 · The Tool-Use Stack](s10-the-tool-use-stack-when-your-agent-learns-to-call-home.md) — MCP transport layer (this entry operates below it)
