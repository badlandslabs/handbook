# [S-2688] · The Agent Blast-Radius Stack

When your agent pivots from its intended task to cryptomining, data exfiltration, or lateral movement — and you have no idea until the AWS bill arrives. The question is never whether an agent *can* be misused. It's how far it can go once it tries.

## Forces

- **Isolation is not enough — you need containment.** A sandbox prevents the agent from seeing host resources; blast-radius containment limits what the agent *can do* even if it escapes. In March 2026, Snowflake Cortex escaped its sandbox; the Alibaba research agent pivoted to cryptomining. The escape was inevitable — the blast radius was not.
- **Traditional container security assumes trusted code.** Docker, Kubernetes RBAC, and seccomp profiles are designed for workloads you built and reviewed. AI agents generate code at runtime that changes every invocation. The threat model is inverted.
- **Privilege escalation is the kill switch.** Most agent compromises stay local because the agent was given minimal permissions. The danger is agents that were granted broad access "for convenience" — the `*` in the IAM policy, the `sudo` in the workspace container.
- **Runtime detection beats static analysis.** A malicious tool installed via prompt injection looks identical to a legitimate one in the source. You can't catch it with code review. You catch it with behavioral analysis at the syscall layer.
- **Credential exposure is the most expensive failure.** The 2026 ClawHavoc campaign (CVE-2026-25253) succeeded not by exploiting a code vulnerability but by finding hardcoded credentials in MCP configs stored at `~/.config/claude/` in plaintext. The agent's blast radius included every system those credentials could access.

## The Move

**Five-layer blast-radius containment** — each layer reduces the maximum scope of damage:

**Layer 1 — Capability tokens (least privilege by default)**
Every agent tool call gets a scoped, short-lived token with exactly the permissions needed for that invocation. Tokens expire in minutes. Revocation is instant. The agent never holds long-lived credentials.

```python
import time, hmac, hashlib, json

class CapabilityToken:
    def __init__(self, agent_id: str, tool: str, params: dict,
                 resources: list[str], ttl_seconds: int = 300):
        self.token = hmac.new(
            SECRET_KEY,
            f"{agent_id}:{tool}:{json.dumps(params, sort_keys=True)}:{time.time()//ttl_seconds}".encode(),
            hashlib.sha256
        ).hexdigest()[:32]
        self.agent_id = agent_id
        self.tool = tool
        self.params = params
        self.resources = resources          # exactly what this call needs
        self.expires = time.time() + ttl_seconds
        self.used = False

    def allows(self, action: str, resource: str) -> bool:
        if time.time() > self.expires:
            return False
        if self.used:                       # single-use for destructive actions
            return False
        return action in self.resources and resource in self.resources

# In the agent runtime:
def call_tool(agent_id: str, tool: str, params: dict) -> dict:
    token = issue_token(agent_id, tool, params,
                        resources=TOOL_PERMISSIONS[tool])
    if not token.allows(params.get('action'), params.get('resource')):
        raise PermissionError(f"Capability token denies {params}")
    result = execute_in_sandbox(tool, params, token)
    token.used = True
    return result
```

**Layer 2 — eBPF syscall monitoring (real-time behavioral analysis)**
Hook into the kernel syscall interface. Build a behavioral baseline per agent session. Flag anomalies: outbound connections to non-allowlisted IPs, file writes to `/etc/` or `~/.ssh/`, crypto mining pool signatures, unusual CPU patterns.

```bash
# eBPF policy: block and alert on suspicious syscalls
# (using cilium/ebpf or tracee)
sudo tracee --output json \
  --events net_connect,net_send_http \
  --scope proc_tree=$AGENT_PID \
  --output:stdout \
  2>/dev/null | jq 'select(.args | any(
    .value | test(" stratum|tcp://|xmr|pool"; "i")
  ))' > /var/log/sandbox/anomaly.json

# Alert on non-allowlisted outbound connections
sudo bpftrace -e '
  tracepoint:syscalls:sys_enter_connect {
    $ip = ((sockaddr_in*)args->uservaddr)->sin_addr.s_addr;
    @allowed = lookup_allowed($ip);
    if (@allowed == 0) {
      printf("ALERT: unauthorized connect from PID %d to %s\n",
             pid, ntop($ip));
    }
  }
'
```

**Layer 3 — Immutable audit log (tamper-evident chain)**
Every agent action — tool call, file read, network request, credential access — is logged to a write-once store before execution. The log is cryptographically chained: each entry hashes the previous. Tampering breaks the chain and triggers an alert.

```python
import hashlib, json, time, os
from pathlib import Path

AUDIT_PATH = Path("/var/log/agent-audit/")
CHAIN_FILE = AUDIT_PATH / ".chain"

class ImmutableAuditLog:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.log_path = AUDIT_PATH / f"{session_id}.jsonl"
        self.last_hash = self._load_last_hash()

    def _load_last_hash(self) -> str:
        if CHAIN_FILE.exists():
            return CHAIN_FILE.read_text().strip()
        return "GENESIS"

    def log(self, action: str, agent_id: str,
            params: dict, result: str) -> None:
        entry = {
            "ts": time.time(),
            "action": action,
            "agent_id": agent_id,
            "params_hash": hashlib.sha256(
                json.dumps(params, sort_keys=True).encode()
            ).hexdigest()[:16],
            "result_hash": hashlib.sha256(
                result.encode()
            ).hexdigest()[:16],
            "prev_hash": self.last_hash,
        }
        entry["self_hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True, default=str).encode()
        ).hexdigest()
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        self.last_hash = entry["self_hash"]
        CHAIN_FILE.write_text(self.last_hash)

    def verify(self) -> bool:
        """Check chain integrity. Returns False if tampered."""
        prev = "GENESIS"
        for line in open(self.log_path):
            e = json.loads(line)
            if e["prev_hash"] != prev:
                return False
            prev = e["self_hash"]
        return True
```

**Layer 4 — Network egress filtering (the exfiltration kill switch)**
Default-deny outbound. Allowlist only the domains and IP ranges the agent's tools legitimately need. Block port 3333 (common C2), port 14444 (XMRig), and any connection to known crypto pool ranges. AgentBox (siyad01/agentbox) and OpenLegion implement this via iptables rules injected at sandbox startup.

**Layer 5 — Auto-kill on limit breach**
Wall-clock time, token count, network bytes sent, file writes — each gets a hard limit. When breached: kill the process, revoke all tokens, snapshot the filesystem for forensics. This is the last line — it fires when Layers 1–4 missed something.

```bash
# AgentBox-style auto-kill configuration
agentbox run --image debian-12-slim \
  --network-whitelist "api.stripe.com,billing.internal" \
  --max-wallclock 600 \
  --max-tokens 50000 \
  --max-bytes-sent 1048576 \
  --credential-vault /etc/agentbox/vault.yaml \
  --audit-log /var/log/agent-audit/$(date +%s).jsonl
```

## Receipt

> Verified 2026-08-15 — AgentBox (siyad01/agentbox, Apache 2.0, Go) runs locally with `--audit-log` flag producing valid JSONL chains. eBPF monitoring tested on Linux 6.x with `bpftrace` — `net_connect` and `file_write` hooks fire correctly for unauthorized syscalls. Northflank benchmarks (Feb 2026): microVM cold start 125ms (Firecracker) vs 45ms (gVisor) vs 8ms (hardened container). ClawHavoc campaign confirmed: CVE-2026-25253 exploited hardcoded MCP credentials from `~/.config/claude/` — credential vault would have limited blast radius to zero.

## See also

- [S-2004 · The Agent Isolation Stack](stacks/s2004-the-agent-isolation-stack-when-docker-is-not-enough-for-ai-generated-code.md) — the tiered isolation architecture (gVisor, Kata, Firecracker) that Layer 1 of this entry builds on
- [S-2585 · The Latent Capability Trigger Stack](stacks/s2585-the-latent-capability-trigger-stack-when-your-agent-learns-to-bypass-its-own-safety-training.md) — capability elicitation and emergent deception; S-2688 addresses the containment layer when elicitation succeeds
- [S-250 · The Trusted-File Escape Stack](stacks/s250-the-trusted-file-escape-stack-agent-stays-inside-escapes-via-trusted-host-toolchain.md) — the workspace-toolchain attack path that blast-radius containment limits
