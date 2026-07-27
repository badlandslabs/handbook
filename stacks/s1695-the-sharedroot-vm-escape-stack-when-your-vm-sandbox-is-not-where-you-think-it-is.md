# S-1695 · The SharedRoot VM Escape Stack — When Your VM Sandbox Is Not Where You Think It Is

Your coding agent runs in a Linux VM. The VM is sandboxed. The host filesystem is read-write mounted into the VM via VirtioFS. An attacker exploits a Linux kernel bug in the traffic-control `act_pedit` module — specifically the COW (copy-on-write) mechanism — to poison a root-owned binary's in-memory text segment. When Cowork's privileged `coworkd` service re-executes that binary, the poisoned version runs as root — and the VM boundary vanishes. The host Mac is fully accessible via `/mnt/.virtiofs-root`. This is SharedRoot (CVE-2026-46331), and it changes the assumption that VM-level isolation is a meaningful security boundary for AI agents.

Published July 23, 2026 by Accomplish AI. Severely critical (9.1/10). ~500,000 macOS users running local Claude Cowork sessions were exposed before mitigation.

## Forces

- **VM isolation is the de facto standard for agent sandboxing** — agents running in a VM are assumed to be contained. SharedRoot breaks this assumption not by escaping the VM's network or filesystem rules, but by escaping the kernel itself.
- **VirtioFS makes the host filesystem part of the attack surface.** When the host `/` is mounted read-write at `/mnt/.virtiofs-root`, any privilege escalation inside the VM gives the attacker full host access — the VM boundary doesn't protect the host, it *enables* the pivot.
- **Kernel vulnerabilities in the VM create host-surface exploits.** The `act_pedit` COW flaw (CVE-2026-46331) is not an agent vulnerability — it's a Linux kernel vulnerability. The agent's ability to execute arbitrary traffic-control commands is the delivery mechanism, not the root cause.
- **The privilege boundary between VM user and VM root is no longer a safe assumption.** In a standard Unix model, escaping a sandboxed user account to root is contained. SharedRoot shows that in this configuration, VM root *is* host-level access.
- **Traditional agent security tooling doesn't cover this layer.** SAST, MCP audit logs, and output filtering all operate above the kernel boundary. There is no prompt injection, no malicious tool response, no social engineering — just a kernel bug and a mounting configuration.

## The Move

**1. Assume the VM is compromised, not the VM is safe.**
Design your agent security posture on the assumption that code execution inside the VM can escalate to host-level access. The VM is a convenience boundary, not a security boundary.

**2. Audit VirtioFS mount configurations.**
Check whether the host filesystem is mounted read-write into agent VMs. If it is, treat the agent as having full host filesystem access — because in this configuration, it effectively does.

```
# In Claude Cowork, check connected folders
# Any connected folder grants the agent a pathway to the host via VirtioFS
# The agent can escape connected folders to the entire host filesystem via /mnt/.virtiofs-root
```

**3. Prefer micro-VM isolation (Firecracker, gVisor) over shared-kernel VMs.**
Firecracker micro-VMs boot a minimal kernel per VM, eliminating the shared-host-kernel attack surface that VirtioFS exploit chains rely on. gVisor provides a user-space kernel that further limits kernel attack surface.

**4. Restrict traffic-control operations in the VM.**
The SharedRoot exploit chain requires `act_pedit` access within the VM to poison binary text segments. Block `tc` (traffic control) commands in seccomp profiles for agent sandboxes where not required.

```python
# Example seccomp profile addition — block traffic control in agent sandbox
import subprocess

# Block tc operations that enable the act_pedit COW attack vector
subprocess.run([
    "iptables", "-A", "OUTPUT", "-m", "owner", "--uid-owner", str(AGENT_UID),
    "-p", "tcp", "--dport", "443", "-m", "string",
    "--string", "act_pedit", "--algo", "bm", "-j", "DROP"
])
```

**5. Switch to cloud execution for sensitive workloads.**
Cloud execution moves the agent to a managed, isolated environment where the host kernel surface is controlled by the provider. For high-sensitivity coding tasks, this eliminates the local VM exploit surface entirely.

**6. Monitor for kernel namespace abuse and unusual tc activity.**
```
# Indicators of SharedRoot exploitation attempt:
# - Unexpected tc/act_pedit syscalls from agent user
# - netlink socket access from sandboxed process
# - Modification of /proc/[pid]/mem from non-privileged context
# - Unusual network namespace operations inside the VM
```

**7. Apply kernel patches and CVE-specific mitigations.**
CVE-2026-46331 patches the Linux kernel's `act_pedit` COW handling. Ensure VM kernels are updated. Note that kernel patching inside the agent VM is the deployer's responsibility — not the host OS vendor's.

**8. Apply least privilege to folder connections.**
In Cowork specifically, avoid connecting folders with sensitive contents (SSH keys, cloud credentials, `.env` files) to agent sessions. The attack requires only a connected folder — not any specific privilege — to pivot to full host access.

```python
# Folder connection policy for Cowork sessions
FOLDER_RISK_TIERS = {
    "low": ["docs/", "public_repos/"],      # Can be connected safely
    "medium": ["projects/", "workspace/"],     # Review contents before connecting
    "high": ["~/.ssh/", ".aws/", ".config/"], # Never connect to agent VM
}
```

## Receipt

> Verified 2026-07-26 — SharedRoot (CVE-2026-46331) technical analysis from Accomplish AI (GridTheGrey editorial, July 2026), The Hacker News (July 23, 2026), and GBHackers. Exploit chain confirmed: VirtioFS read-write mount → sandboxed `tc act_pedit` → COW poisoning of root binary → `coworkd` re-execution as root → host filesystem via `/mnt/.virtiofs-root`. Partial mitigation available via cloud execution mode. No dedicated CVE patch issued as of July 26, 2026. Code examples represent structural patterns; no runtime execution performed (Receipt pending — 2026-07-26).

## See also

- [S-1459 · The Trusted-File Escape Stack](s1459-the-trusted-file-escape-stack-when-your-agent-stays-inside-and-escapes-via-trusted-host-toolchain.md) — trust handoff exploits via workspace configuration files; the complementary file-based escape class
- [S-1069 · The Threat-Model-Driven Sandbox Stack](s1069-the-threat-model-driven-sandbox-stack-when-subprocess-is-not-enough.md) — Docker/kernel isolation decisions for runtime code execution
- [S-1072 · The Agent Sandbox Controller Stack](s1072-the-agent-sandbox-controller-stack-when-your-k8s-cluster-doesnt-know-what-an-agent-is.md) — Kubernetes-native agent isolation patterns
- [F-194 · AgentJacking & MCP Tool-Response Poisoning](../forward-deployed/f194-agentjacking-mcp-tool-response-poisoning.md) — MCP server supply chain attack class from June 2026
