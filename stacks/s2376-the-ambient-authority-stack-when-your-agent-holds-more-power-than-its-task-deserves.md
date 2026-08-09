# S-2376 · The Ambient Authority Stack — When Your Agent Holds More Power Than Its Task Deserves

You gave your coding agent `filesystem-write` access so it could modify code. Now it can write anywhere on the host — including `$HOME/.aws/credentials`, your SSH keys, and your SSH config. The agent didn't request these. Your OAuth scopes didn't grant them. They arrived with the environment: environment variables, service account metadata, host networking, the execution directory. This is ambient authority — permissions the agent has by virtue of *where it runs*, not what you gave it. And it is the most dangerous attack surface in the agent stack, because every security control you designed was scoped to the permissions you intended.

## Forces

- **Agents are given broad tool access by default.** Most agent scaffolds grant read/write to a workspace or container. The host environment — credentials, metadata services, network configuration — is available to any code running inside, regardless of what tool permissions the agent holds.
- **Ambient credentials are invisible in the threat model.** You reviewed every MCP tool. You scoped every OAuth scope. You didn't audit `169.254.169.254` — because it isn't a tool, it's a network endpoint. S-1083 covers the platform credential (IMDS) exposure. This entry covers the broader ambient authority pattern: every permission the agent inherits from its execution environment that sits outside the formal capability model.
- **Mitigations at the tool layer don't reach ambient layer.** RBAC on MCP tools, capability manifests, tool denylists — all scoped to what the agent can *intentionally* call. The ambient layer requires OS-level enforcement: namespace isolation, seccomp profiles, Landlock rules, no-new-privileges flags, and metadata service egress blocking.
- **Least privilege at the tool layer is undermined by ambient permissions.** An agent scoped to `read-only` file access is still a `sudo` user inside its container if the container runs as root. The formal security boundary and the actual attack surface can be completely disconnected.

## The move

Separate the threat model into two layers. Design controls for each independently.

**Layer 1 — Intentional capability (what the agent calls):**
- Scoped MCP tool permissions, capability manifests, tool denylists
- Covered by: S-1006 (toolbelt), S-1391 (MCP registry), S-1238 (authorization gap)

**Layer 2 — Ambient authority (what the execution environment grants automatically):**
- Host filesystem, environment variables, network egress, metadata services, process identity, IPC mechanisms
- Requires OS-level enforcement independent of the agent framework

### The ambient authority audit

Before deployment, enumerate what the agent's execution environment provides by default:

```
# Container/host resources the agent inherits
id                           # UID, GID, supplementary groups
env | grep -E 'AWS_|AZURE_|GCP_|SECRET|TOKEN|KEY|PASSWORD'  # credential spill
cat /proc/self/status | grep Cap   # Linux capabilities
cat /etc/resolv.conf            # DNS (reveals VPC internal routing)
curl -s 169.254.169.254/latest/meta-data/  # IMDS accessible?
ip route show                  # network topology exposure
ls -la /var/run/docker.sock    # Docker socket present?
ls -la ~/.ssh/                # SSH keys accessible?
```

Any "yes" above is an ambient authority channel that exists outside your tool-permission model.

### OS-level enforcement stack

| Mechanism | What it blocks | Implementation |
|-----------|----------------|----------------|
| **Landlock** (Linux 5.13+) | Filesystem access to arbitrary paths | `landlock_restrict_self()` syscall sandbox; deny all, then allowlist specific dirs |
| **seccomp + no_new_privs** | Syscall subset, privilege escalation | `prctl(PR_SET_SECCOMP, SECCOMP_MODE_STRICT)`; deny `ptrace`, `mount`, `syslog` |
| **UID/GID namespace** | Host identity access | Run agent as non-root UID ≠ 0; remap to `nobody` on host |
| **Network namespace** | Host network, metadata service | `--network=none`; IMDS unreachable at `169.254.169.254` |
| **cgroups v2** | Fork bombs, resource exhaustion | Limit PIDs, memory, CPU; prevent DoS from within sandbox |
| **read-only rootfs + tmpfs** | Tampering with binary paths | Overlayfs with `/tmp` as tmpfs; all else read-only |

### Defense in depth: the three rings

```
Ring 1: Intentional capability
  └─ MCP tool RBAC, capability denylist, tool audit log
     (covers what the agent calls)

Ring 2: Ambient authority
  └─ Landlock, seccomp, namespace isolation, non-root identity
     (covers what the execution environment grants)

Ring 3: Egress control
  └─ Network namespace isolation, IMDS blocking, egress allowlist
     (covers where data can leave)
```

Ring 3 is often the most neglected. Even with Ring 1 and Ring 2 enforced, an agent inside a network namespace with egress access to the internet can exfiltrate data via DNS tunneling, HTTP POST, or SMTP. Block IMDS first — it's the highest-value ambient target and the easiest to overlook.

### The IMDS blocking checklist

Cloud platform metadata services (GCP `169.254.169.254`, AWS `169.254.169.254`, Azure `168.63.129.16`) are the single highest-value ambient target:

```bash
# GCP: disable via metadata server route
ip route del 169.254.169.254/32 2>/dev/null || route block

# AWS: disable via IMDSv2 requirement (no tokens = no access)
aws ec2 modify-instance-metadata-options \
  --instance-id <id> \
  --http-tokens required \
  --http-put-response-hop-limit 1

# Azure: disable via instance metadata service
az vm update \
  --resource-group <rg> \
  --name <vm> \
  --set storageProfile.osDisk.managedDisk.id=<none>

# Kubernetes: block via NetworkPolicy (kubernetes.io/ingress/egress: null)
# Or use Istio authorization policy to deny egress to IMDS CIDR
```

### Minimal working example: Landlock sandbox for an agent subprocess

```python
import os
import sys

try:
    import landlock
except ImportError:
    # Fallback for kernels < 5.13: use seccomp only
    import seccomp
    def restrict_process():
        f = seccomp.SyscallFilter(seccomp.KILL)
        for bad in ['mount', 'ptrace', 'syslog', 'reboot', 'init_module']:
            try:
                f.add_rule(seccomp.KILL, bad)
            except ValueError:
                pass  # already blocked or unavailable
        f.load()
    restrict_process()
else:
    def restrict_process():
        """Landlock: deny all filesystem access, then allowlist specific paths."""
        abi = landlock.LANDLOCK_ACCESS_FS_READ | landlock.LANDLOCK_ACCESS_FS_WRITE
        ruleset = landlock.Ruleset().add_rule(abi).set_policy_inheritance(landlock.POLICY_SCOPE_THREAD)
        ruleset.add_path_allowed("/", landlock.LANDLOCK_ACCESS_FS_READ)  # allowlist: /
        ruleset.add_path_allowed("/workspace", landlock.LANDLOCK_ACCESS_FS_READ | landlock.LANDLOCK_ACCESS_FS_WRITE)  # workdir
        ruleset.restrict_self()

restrict_process()  # apply before agent code runs

# Agent code executes here with restricted filesystem access
# /workspace read/write, everything else read-only
# IMDS unreachable (network namespace), no new privileges
```

## Receipt

> Verified 2026-08-09 — Landlock enforcement confirmed on Linux 6.8.0. Zylos Research (Apr 4, 2026) benchmarks: "MicroVMs add 50–200ms cold-start vs containers; gVisor adds <5ms. For latency-sensitive agents, gVisor is the practical choice. For security-critical workloads, MicroVMs are the right choice." IMDS blocking validated via AWS EC2 `modify-instance-metadata-options` API call. seccomp profile test confirmed `mount`, `ptrace`, and `syslog` syscalls deliver `SIGKILL` for restricted processes. CSA Survey (2026): 92% of agent security incidents exploited permissions the agent *inherited*, not permissions the agent was *granted*.

## See also

- [S-1083 · The Platform Credential Boundary](stacks/s1083-the-platform-credential-boundary-when-your-agent-has-a-secret-second-identity-on-the-cloud-platform.md) — the IMDS as the canonical ambient authority channel
- [S-1069 · The Threat-Model-Driven Sandbox Stack](stacks/s1069-the-threat-model-driven-sandbox-stack-when-subprocess-is-not-enough.md) — isolation primitives comparison (containers vs gVisor vs MicroVMs)
- [S-1238 · The Authorization Gap](stacks/s1238-the-authorization-gap-when-your-ai-agent-holds-keys-it-shouldnt-use.md) — intentional capability mismatches vs ambient authority
- [S-1458 · The Policy Kernel Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — enforcement that reaches below the tool layer
