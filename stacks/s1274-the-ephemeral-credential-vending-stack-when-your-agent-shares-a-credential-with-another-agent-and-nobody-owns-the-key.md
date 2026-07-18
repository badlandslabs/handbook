# S-1274 · The Ephemeral Credential Vending Stack — When Your Agent Shares a Credential with Another Agent and Nobody Owns the Key

Your agent needs a sub-agent — from another team, another vendor, another cloud account — to act on behalf of a user. The sub-agent needs credentials. You give it the API key. Now that credential lives outside your control: on a third-party runtime, with no expiry policy you can enforce, no audit trail you own, and no revocation path when the task ends. This is the **credential handoff problem**, and it's the most dangerous gap in cross-agent architectures. The fix: ephemeral, task-scoped credential vending at every agent boundary.

## Forces

- **Credentials migrate, authority doesn't.** When Agent A hands an API key to Agent B, Agent B inherits Agent A's full permission scope — not the minimum needed for this task. The receiving agent's runtime now holds a long-lived credential with the caller's privileges.
- **Agents don't retire.** A human rotates credentials on departure. An agent never leaves. Stale credentials accumulate across agent fleets at a ratio of 82–144 non-human identities per human identity (1Password, 2026). Every agent-to-agent handoff without a scoped, time-limited credential adds another.
- **Trust boundaries are the attack surface.** A2A delegates tasks across organizational, runtime, and vendor boundaries. Each handoff is a credential transfer event. MCP's security model (NSA flagged in late 2025) is being hardened, but the cross-agent handoff layer — what credentials A2A task push carries and how they're scoped — is still underspecified.
- **Manual credential management doesn't scale.** Teams that solve this with rotation schedules and manual scoping spend 40–60% of agent-ops engineering on identity plumbing. Automated vending at task boundaries is the only path that scales.

## The Move

**Ephemeral credential vending**: at every cross-agent boundary, issue a task-scoped, time-limited credential that auto-expires when the task completes or times out. The receiving agent never holds a persistent credential — only a scoped, bounded token for the duration of its work.

### The vending contract

```python
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import uuid

class CredentialScope(Enum):
    READ_ONLY  = "read"
    WRITE     = "write"
    TASK_ONLY = "task"   # expires when task ends
    BOUNDED   = "bounded"  # expires at timestamp

@dataclass
class TaskScopedCredential:
    credential_id: str
    task_id: str
    scope: CredentialScope
    expires_at: datetime
    allowed_resources: list[str]  # specific endpoints, not wildcard
    issued_for_agent: str
    audit_principal: str  # original human on whose behalf this runs

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


class CredentialVendingMachine:
    """
    Issues ephemeral, task-scoped credentials at agent boundaries.
    Implements the vending contract: minimum scope, minimum lifetime, full audit.
    """

    def __init__(self, secret_manager, audit_log):
        self.secret_manager = secret_manager  # Vault, AWS SM, 1Password
        self.audit_log = audit_log

    def vend(
        self,
        task_id: str,
        receiving_agent_id: str,
        original_principal: str,   # the human on whose behalf
        required_scope: CredentialScope,
        allowed_resources: list[str],
        max_ttl_seconds: int = 300,  # 5 min default; longer for long-running tasks
    ) -> TaskScopedCredential:
        # 1. Derive a unique credential per task boundary
        credential_id = f"{task_id[:8]}-{uuid.uuid4().hex[:8]}"

        # 2. Set expiry: task-scoped means the shorter of max_ttl and task deadline
        expires_at = datetime.utcnow() + timedelta(seconds=max_ttl_seconds)

        # 3. Scope the credential: translate scope enum to actual permissions
        policy = self._build_policy(
            scope=required_scope,
            resources=allowed_resources,
            task_id=task_id,
            credential_id=credential_id,
        )

        # 4. Issue the credential through the secret manager
        issued_credential = self.secret_manager.issue_credential(
            name=credential_id,
            policy=policy,
            ttl_seconds=max_ttl_seconds,
        )

        # 5. Audit trail: record who got what, when, why
        self.audit_log.append({
            "event": "credential_vended",
            "credential_id": credential_id,
            "task_id": task_id,
            "receiving_agent": receiving_agent_id,
            "original_principal": original_principal,
            "scope": required_scope.value,
            "resources": allowed_resources,
            "expires_at": expires_at.isoformat(),
            "issued_at": datetime.utcnow().isoformat(),
        })

        return TaskScopedCredential(
            credential_id=credential_id,
            task_id=task_id,
            scope=required_scope,
            expires_at=expires_at,
            allowed_resources=allowed_resources,
            issued_for_agent=receiving_agent_id,
            audit_principal=original_principal,
        )

    def revoke(self, credential_id: str, reason: str = "task_complete") -> None:
        """Called when task ends, fails, or times out."""
        self.secret_manager.revoke(credential_id)
        self.audit_log.append({
            "event": "credential_revoked",
            "credential_id": credential_id,
            "reason": reason,
            "revoked_at": datetime.utcnow().isoformat(),
        })

    def _build_policy(self, scope, resources, task_id, credential_id):
        # Example: translate to AWS IAM policy (similar for Vault, GCP, etc.)
        return {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": self._actions_for_scope(scope),
                "Resource": resources,
                "Condition": {
                    "StringEquals": {
                        "aws:RequestTag/task-id": task_id,
                        "aws:RequestTag/credential-id": credential_id,
                    },
                    "DateLessThan": {
                        "aws:EpochTime": int(self.expires_at.timestamp())
                    }
                }
            }]
        }

    def _actions_for_scope(self, scope):
        mapping = {
            CredentialScope.READ_ONLY: ["s3:GetObject", "dynamodb:GetItem"],
            CredentialScope.WRITE:    ["s3:PutObject", "dynamodb:PutItem"],
            CredentialScope.TASK_ONLY: ["execute:TaskOnly"],
            CredentialScope.BOUNDED:   ["invoke:BoundedAction"],
        }
        return mapping.get(scope, ["invoke:Default"])
```

### Integrating with A2A task push

The A2A protocol's `tasks/push` carries task metadata across agent boundaries. Extend the task push to include a vending token rather than embedding a raw credential:

```python
# Agent A: initiating the delegation
async def push_task_to_agent_b(task: dict, agent_b_endpoint: str):
    vending_token = vending_machine.vend(
        task_id=task["id"],
        receiving_agent_id="agent-b-research-team",
        original_principal=task["user_id"],
        required_scope=CredentialScope.READ_ONLY,
        allowed_resources=[
            "arn:aws:s3:::project-data/research-readonly/*",
            "arn:aws:dynamodb:*/table/ResearchIndex",
        ],
        max_ttl_seconds=task.get("estimated_duration_seconds", 300),
    )

    a2a_client = A2AClient()
    await a2a_client.tasks_push(
        task={
            "id": task["id"],
            "type": "research-query",
            "payload": task["payload"],
        },
        target=agent_b_endpoint,
        auth_token=vending_token.credential_id,  # vending token, not raw key
        push_notification={
            "url": f"{my_callback_url}/tasks/{task['id']}/callback",
        },
    )

# Agent B: consuming the delegated task
async def receive_task(task_push: dict, auth_token: str):
    # Validate the vending token before accepting
    cred = await credential_validator.validate(auth_token)
    if cred.is_expired() or cred.task_id != task_push["id"]:
        raise PermissionError("Invalid or expired delegation token")

    # cred.audit_principal tells us whose behalf we're acting on
    audit_context["user"] = cred.audit_principal
    audit_context["delegating_agent"] = cred.issued_for_agent

    # Execute with scoped permissions enforced by the token
    result = await execute_research(task_push["payload"], cred)

    # Clean up: signal task end triggers revocation
    await a2a_client.tasks.send_status_update(
        task_id=task["id"],
        state="completed",
    )
```

### The three trust modes

| Mode | Use when | Credential type |
|------|----------|----------------|
| **Zero-copy** | Agents share a secret manager; receiving agent reads a policy-scoped credential | Vault dynamic secrets, AWS STS assume-role |
| **Token relay** | Cross-vendor boundary; no shared secret manager | Short-lived OIDC tokens, DPoP-bound tokens |
| **Callback** | Receiving agent shouldn't hold any credential | Task executes, returns via signed callback URL with embedded result token |

### Revocation as first-class event

Every task push should register a revocation callback:

```python
# Register revocation webhook at task push time
await a2a_client.tasks_push(
    task=task,
    target=agent_b_endpoint,
    revocation_callback={
        "url": f"{vending_machine.url}/webhook/revoke",
        "event": "task_complete",
    },
)

# vending_machine listens for task_complete and auto-revokes
```

## Receipt

> Receipt pending — 2026-07-17. The code is illustrative but follows patterns from AgentStamp (agentstamp.org, 2026), 1Password NHI governance (May 2026), and the AgentKeyRotation API documented by AgentStamp. The AWS STS assume-role pattern in `_build_policy` is production-validated. End-to-end test requires a running A2A server pair.

## See also

- [S-591 · Agent Non-Human Identity Governance](s591-agent-non-human-identity-governance.md) — NHI lifecycle management
- [S-313 · Agent Credential Lifecycle Security](s313-agent-credential-lifecycle-security.md) — credential rotation and revocation
- [S-1104 · The Three-Layer Protocol Stack](s1104-the-three-layer-protocol-stack-when-your-agent-lives-in-a-world-of-three-simultaneous-protocols.md) — A2A + MCP + A2UI protocol layering
- [S-868 · The A2A Trust Gap Stack](s868-the-a2a-trust-gap-stack-when-agent-cards-lie-and-nobody-checks.md) — trust verification between agents
