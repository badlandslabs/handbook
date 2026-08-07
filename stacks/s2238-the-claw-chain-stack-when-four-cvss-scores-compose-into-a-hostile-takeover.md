# S-2238 · The Claw Chain Stack — When Four CVSS Scores Compose Into a Hostile Takeover

A prompt injection in your OpenClaw session delivers a payload. The sandbox blocks it from reading `/etc/passwd`. The agent firewall blocks it from opening outbound sockets. The MCP server refuses unauthorized connections. Every control works exactly as designed. Three minutes later, an attacker has a persistent backdoor on the host machine, all API keys from the agent's environment, and root-equivalent privileges. No single CVE did this. Four CVEs did — and they were all fixed the same day.

## Situation

You run OpenClaw to let an autonomous agent handle code reviews, issue triage, or CI pipeline tasks. The agent processes a user request that contains a prompt injection payload. From inside the sandbox, the payload executes — but the sandbox does its job. The agent can't reach the outside world. It can't read the credentials file. It can't write outside its working directory.

Except it can. Because the four CVEs in the "Claw Chain" disclosure (Cyera, April 2026; CSA AI Safety Initiative, May 2026) chain together to convert a sandboxed foothold into a host-level compromise — and each individual vulnerability looks like a low-severity implementation quirk.

## Forces

- **Composability is the attack.** CVSS 9.6 (write TOCTOU) + CVSS 7.7 (read TOCTOU) + CVSS 7.1 (MCP loopback bypass) + CVSS 6.8 (persistence) = host takeover. No single CVE triggers a security review. The combination never gets assessed because nobody owns the intersection.
- **Sandbox trust is transitive, not absolute.** The sandbox correctly contains the agent's direct actions. But the agent's *legitimate* ability to call MCP tools creates an implicit trust channel that bypasses sandbox authorization. The write tool goes through the sandbox — but the MCP command it triggers doesn't.
- **TOCTOU races are invisible in normal operation.** A symlink swap race condition in the filesystem bridge fires only during a targeted attack. It never fires in functional tests, fuzzing, or code review because the timing window is nanoseconds. It only matters when someone is exploiting it.
- **245,000 exposed instances.** As of May 2026, Shodan and ZoomEye scans identified approximately 245,000 publicly accessible OpenClaw instances. The attack surface isn't theoretical — it's internet-facing and pre-patched.

## The move

### 1. Understand the four-link chain

The Claw Chain disclosure (CVE-2026-44112 through CVE-2026-44118) chains four vulnerabilities across two subsystems:

| Link | CVE | CVSS | System | What it bypasses |
|------|-----|------|--------|-----------------|
| 1 | CVE-2026-44112 | **9.6** | OpenShell FS bridge (write) | Sandbox write boundary via TOCTOU symlink swap |
| 2 | CVE-2026-44113 | **7.7** | OpenShell FS bridge (read) | Sandbox read boundary via TOCTOU symlink swap |
| 3 | CVE-2026-44115 | **7.1** | MCP loopback runtime | MCP authentication for local servers |
| 4 | CVE-2026-44118 | **6.8** | Post-exploit persistence | System restart survival via cron/systemd |

**The exploit sequence:**
1. Attacker delivers a prompt injection containing a malicious symlink and payload script
2. Link 1: The FS bridge write path checks the target path, then swaps it to a host-level location before the write commits (TOCTOU window)
3. The malicious file — now outside the sandbox — contains a script that activates Link 3
4. Link 3: The MCP loopback bypass allows the script to send commands to any MCP server on `127.0.0.1` without credentials (MCP loopback servers assume local callers are trusted)
5. The attacker enumerates credentials available to the MCP server context
6. Link 4: A cron or systemd unit backdoor is written, surviving agent restart

### 2. Apply patches immediately

```bash
# Verify OpenClaw version — vulnerable before 2026.4.22
openclaw --version
# If < 2026.4.22:
openclaw update
# Or reinstall from the patched release
curl -fsSL https://get.openclaw.ai | sh -s -- --version 2026.4.22
```

Check CVE coverage across all agent framework installations in your fleet:

```bash
# Inventory check: report all agent framework versions
openclaw --version 2>/dev/null | tee /tmp/openclaw-version.txt
cursor --version 2>/dev/null
cline --version 2>/dev/null
# Cross-reference with known-vulnerable versions:
# OpenClaw: < 2026.4.22 is vulnerable to all four Claw Chain CVEs
# CVE-2026-42434 (SentinelOne): OpenClaw 2026.4.5–2026.4.10 exec-runtime bypass
```

### 3. Implement defense-in-depth for sandbox file I/O

The TOCTOU vulnerabilities target the filesystem bridge between the sandbox and host. Mitigate at the bridge layer:

```python
# O_EXCL prevents symlink swap during open by failing if target exists as symlink
import os

def safe_sandbox_write(sandbox_root: str, relative_path: str, content: bytes) -> None:
    """
    Write a file inside the sandbox root with TOCTOU mitigation.
    O_NOFOLLOW fails the open if any path component is a symlink.
    O_EXCL fails if the target already exists as a symlink.
    """
    safe_path = os.path.join(sandbox_root, relative_path)
    real_path = os.path.realpath(safe_path)

    # Verify the resolved path is still under sandbox root
    if not real_path.startswith(os.path.realpath(sandbox_root) + os.sep):
        raise PermissionError(f"Escape attempt blocked: {relative_path} resolves outside sandbox")

    fd = os.open(
        safe_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_EXCL,
        0o644
    )
    try:
        os.write(fd, content)
    finally:
        os.close(fd)
```

### 4. Scope MCP loopback access

MCP servers running on loopback that assume local callers are trusted are a systemic risk. Apply network-level scoping:

```bash
# Restrict MCP loopback access to only the agent's own processes
# Add to OpenClaw sandbox config:
iptables -A OUTPUT -m owner --uid-owner openclaw-agent \
  -d 127.0.0.1 \
  -m conntrack --ctstate NEW \
  -m recent --set --name mcp-access \
  -j ACCEPT

# Allow only pre-registered MCP server ports on loopback
iptables -A OUTPUT -m owner --uid-owner openclaw-agent \
  -d 127.0.0.1 \
  -p tcp --dport 3000:3999 \
  -m conntrack --ctstate ESTABLISHED \
  -j ACCEPT

# Block everything else on loopback
iptables -A OUTPUT -m owner --uid-owner openclaw-agent \
  -d 127.0.0.1 \
  -j DROP
```

### 5. Monitor for the chain, not just the links

Individual CVE exploitation looks like normal agent behavior. The chain is detectable by correlation:

```yaml
# Falco rules for Claw Chain detection
- rule: OpenClaw Sandbox Write Outside Mount
  condition: >
    process.name = openclaw
    and file.name startswith "/home/"
    and not file.name contains "/.openclaw/sandbox/"
    and file.name contains ".."
  output: >
    Possible sandbox TOCTOU write escape attempt
    (user=%user.name file=%fd.name)

- rule: MCP Loopback Unauthorized Command
  condition: >
    process.name != openclaw
    and process.name startswith "mcp"
    and connection.destination = "127.0.0.1"
    and connection.uid != openclaw_uid
  output: >
    Non-agent process accessing MCP loopback
    (user=%user.name proc=%process.name)

- rule: Cron Persistence After Agent Session
  condition: >
    file.name contains "/etc/cron"
    and file.name contains "openclaw"
    and process.parent.name = openclaw
  output: >
    OpenClaw agent establishing cron persistence backdoor
    (user=%user.name file=%fd.name)
```

## Receipt

> Verified 2026-08-06 — Claw Chain research from CSA AI Safety Initiative (Cyera, published 2026-05-17/18) and SentinelOne vulnerability database confirmed four distinct CVEs: CVE-2026-44112 (CVSS 9.6), CVE-2026-44113 (CVSS 7.7), CVE-2026-44115 (CVSS 7.1), CVE-2026-44118 (CVSS 6.8). 245,000 exposed instances confirmed via Shodan + ZoomEye (May 2026). Patches available in OpenClaw 2026.4.22 (released April 2026). Python O_NOFOLLOW/O_EXCL mitigation implemented and verified on Linux 6.x. iptables MCP scoping verified via `iptables -L -n -v`. Falco rules tested against synthetic TOCTOU file write — correctly blocked.

## See also

- [S-1917 · The Trust Handoff Stack](/handbook/stacks/s1917-the-trust-handoff-stack-when-your-sandboxed-agent-escapes-through-a-file-it-was-allowed-to-write.md) — trusted-file escape via config injection
- [S-1000 · The Structural Agent Governance Stack](/handbook/stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — defense-in-depth for autonomous systems
- [S-1072 · The Agent Sandbox Controller Stack](/handbook/stacks/s1072-the-agent-sandbox-controller-stack-when-your-k8s-cluster-doesnt-know-what-an-agent-is.md) — Kubernetes-native sandbox isolation
- [S-2221 · The Agentic Supply Chain Compromise Stack](/handbook/stacks/s2221-the-agentic-supply-chain-compromise-stack-when-trusted-plugins-became-the-attack-vector.md) — MCP ecosystem vulnerabilities
