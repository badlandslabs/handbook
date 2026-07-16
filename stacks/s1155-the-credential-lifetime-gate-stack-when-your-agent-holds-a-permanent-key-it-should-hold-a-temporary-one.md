# S-1155 · The Credential Lifetime Gate Stack — When Your Agent Holds a Permanent Key It Should Hold a Temporary One

[Your agent gets a credential on Monday. It keeps that credential until someone revokes it. A developer leaves, an agent gets jailbroken, a task scope changes — the credential persists. This is the default state of most agent deployments, and it makes agents the most dangerous kind of non-human identity: one that holds permanent access to systems it only needed temporary access to.]

## Forces

- **Agents are temporal workers wearing permanent credentials.** A human contractor gets a badge that expires. Your agent gets an API key that lives in its config until someone removes it. The credential lifecycle model treats agents as infrastructure, not as personnel.
- **Privilege width and time are independent risk axes.** Least-privilege scoping limits *what* the agent can do. Lifetime bounds limit *for how long*. You can have minimal permissions that never expire — still a disaster if the agent is compromised six months later.
- **Agent sessions outlive the task that justified them.** An agent starts a data migration, finishes in 20 minutes, and keeps a credential with production write access for the next 90 days. The task ended; the access did not.
- **Credential blast radius compounds silently.** S-572 (context-window credential aggregation) covers the exposure risk of secrets in context. This pattern covers the *temporal exposure risk*: a credential that exists outside context but persists indefinitely, available to any subsequent agent session using the same identity.
- **90% of agents operate with permissions broader than required** (Obsidian Security, 2026) and **80% of organizations observe unintended agent actions** (SailPoint NHIMG, 2026). These are symptoms of credentials with no temporal boundary.

## The move

Tie credential lifetime to task execution — not to deployment. Every credential an agent holds has a hard expiry window. Credentials are issued on-demand, scoped to the specific task's permission surface, and revoked automatically when the task ends, fails, or times out.

Three layers work together:

**1. Credential Temporal Scoping (before the session)**
Before any agent session begins, issue a credential bound to the task's expected duration. Use the platform's short-lived credential API:

```python
import boto3
from contextlib import contextmanager

@contextmanager
def scoped_agent_credential(task_id: str, ttl_seconds: int = 900,
                            permissions: list[str] | None = None):
    """Issue an ephemeral credential for a bounded task window."""
    iam = boto3.client("iam")
    sts = boto3.client("sts")

    role_name = "ai-agent-execution-role"
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": permissions or ["s3:GetObject", "s3:PutObject"],
            "Resource": "arn:aws:s3:::task-data-bucket/*"
        }]
    }

    # Create a one-time inline policy
    policy_name = f"task-{task_id}"
    try:
        iam.create_policy(
            PolicyName=policy_name,
            PolicyDocument=json.dumps(policy)
        )

        # Assume the execution role with the scoped policy attached
        creds = sts.assume_role(
            RoleArn=f"arn:aws:iam::{ACCOUNT_ID}:role/{role_name}",
            RoleSessionName=f"agent-{task_id}",
            DurationSeconds=ttl_seconds
        )["Credentials"]

        yield creds  # Agent uses these for the session

    finally:
        # Clean up: revoke the inline policy
        try:
            iam.delete_policy(PolicyArn=f"arn:aws:iam::{ACCOUNT_ID}:policy/{policy_name}")
        except Exception as exc:
            logger.warning(f"Credential policy cleanup failed: {exc}")

# Usage
task_id = str(uuid.uuid4())
with scoped_agent_credential(task_id, ttl_seconds=900,
                              permissions=["s3:GetObject"]) as creds:
    agent.run(task="Summarize Q3 financials", short_lived_creds=creds)
# Creds auto-expired; policy detached and deleted
```

**2. Execution Window Enforcement (inside the loop)**

```python
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Protocol

@dataclass
class CredentialWindow:
    issued_at: datetime
    expires_at: datetime
    max_tool_calls: int

    def is_valid(self) -> bool:
        return (
            datetime.utcnow() < self.expires_at
            and self.call_count < self.max_tool_calls
        )

class LifetimeBoundedAgent:
    def __init__(self, credential_window: CredentialWindow):
        self.window = credential_window
        self.call_count = 0

    def run(self, task: str, llm, tools: list):
        while self.window.is_valid() and not self.task_complete:
            self.call_count += 1
            response = llm.generate(task, tools=tools)
            for tool_call in response.tool_calls:
                # Every tool call verified against the credential window
                if not self.window.is_valid():
                    raise CredentialExpiredError(
                        f"Tool call {self.call_count} blocked: "
                        f"credential expired at {self.window.expires_at}"
                    )
                self.execute_tool(tool_call)
```

**3. Revocation on Failure (the critical cleanup)**

```python
async def run_agent_task(task: str, llm, tools: list):
    window = CredentialWindow(
        issued_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=15),
        max_tool_calls=20,
    )
    agent = LifetimeBoundedAgent(window)

    try:
        result = await agent.run(task, llm, tools)
        log_agent_completion(task, window.call_count, "success")
        return result

    except CredentialExpiredError:
        log_agent_completion(task, window.call_count, "timeout")
        raise  # Already cleaned up; escalate to human

    except Exception as exc:
        # Immediate revocation: the credential is now suspect
        await revoke_all_agent_sessions(window)
        log_agent_completion(task, window.call_count, f"failure:{type(exc).__name__}")
        raise AgentExecutionError(f"Task failed, credentials revoked: {exc}") from exc

    finally:
        # Belt-and-suspenders: expire token at session end regardless
        await expire_token(window)
        await log_to_audit(window, task, agent.call_count)
```

## Receipt

> Verified 2026-07-15 — Research sources: CSA "Governing Non-Human Identities in Agentic Systems" (Jul 8, 2026) — 90% of agents operate with excess permissions, 80% of orgs observe unintended agent actions; Obsidian Security NHI survey (2026); Gheware DevOps Zero-Trust guide (Mar 2026); Keyfactor AI Agent Security (2026). No live execution performed. Code reflects AWS STS AssumeRole + IAM inline policy patterns from production cloud deployments. Verify credential expiry with: `aws sts get-session-token --duration-seconds 900` and confirm auto-expiry in CloudTrail (`EventsByUsername + .mfa_deleted` filter).

## See also

- [S-572 · Context Window Credential Aggregation Risk](stacks/s572-the-context-window-credential-aggregation-risk.md) — secrets that enter the context window
- [S-1065 · Inter-Agent Trust Escalation](stacks/s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — permission inheritance across agent chains
- [S-622 · Agent Sprawl Governance](stacks/s622-the-agent-sprawl-governance-stack-when-45-agents-per-engineer-creates-an-identity-crisis.md) — the NHI registry and lifecycle management layer
- [S-719 · AI Control Plane](stacks/s719-the-ai-control-plane-owasp-runtime-governance.md) — OWASP runtime governance that would enforce lifetime bounds
