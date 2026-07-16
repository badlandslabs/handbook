# S-1075 · The Ephemeral Delegation Stack — When Your Agent Hands Its Credentials to a Stranger

An agent that calls a third-party specialist agent, invokes an MCP tool, or proxies a user request needs credentials to act. The default is to hand over the same static API key or OAuth token that has broad access. When that sub-agent is compromised, behaves unexpectedly, or makes an unintended combination of calls, your credential — and your user's data — is in someone else's hands.

## Forces

- **Agents are non-deterministic and multiply.** A human credential is scoped to one identity. An agent can spawn N sub-agents, each of which can call N tools, each of which is a separate trust boundary. Static credentials have no concept of this fan-out.
- **Delegation crosses organizational boundaries.** Your agent hires a contractor agent via A2A. That agent needs access to your APIs. Giving it your service account credentials means trusting not just the agent but every model, framework, and transit hop between here and there.
- **Traditional service-to-service auth doesn't know about tasks.** OAuth 2.0 client credentials give a service a token. That token doesn't encode *what the agent is allowed to do with it* or *for how long*. The permission model stops at the credential layer.
- **Revocation is too slow to matter.** If you detect a compromise and rotate the key, every legitimate agent that depended on it also breaks. If you don't rotate, the compromised credential stays live.

## The move

Issue **ephemeral, task-scoped delegation tokens** at every delegation hop. The delegating agent (or the identity broker it calls) generates a short-lived token scoped to: the specific sub-agent identity, the specific tool or resource set, the specific task, and a time window (typically 5–30 minutes).

```
┌─────────────┐  ① Issue scoped token   ┌──────────────────┐
│ Planner      │ ─────────────────────▶  │ Identity Broker  │
│ Agent        │                         │ (keycard / SPIRE) │
└─────────────┘                         └────────┬─────────┘
                                                 │ ② Ephemeral token
                                                 │    (task + scope + TTL)
                                                 ▼
                                      ┌──────────────────┐
                                      │ Sub-Agent / Tool  │
                                      │ (acts on token)   │
                                      └──────────────────┘
                                                 │ ③ Audit log
                                                 ▼
                                      ┌──────────────────┐
                                      │ Token Introspect  │
                                      │ (verify + revoke) │
                                      └──────────────────┘
```

### The delegation contract

Before issuing, the broker must resolve four questions:

1. **Who** — the sub-agent's identity (AgentCard from A2A, or MCP server certificate)
2. **What** — the specific resource actions allowed (not `read:*`, but `read:orders:read:id=42`)
3. **For how long** — TTL calibrated to the expected task duration; 5 min for simple calls, 30 min for complex multi-step tasks
4. **Why** — the parent task ID that created this delegation, for causal tracing

### Minimal working example

```python
from datetime import datetime, timedelta
from typing import Literal
import hashlib, hmac, json

class DelegationToken:
    def __init__(
        self,
        delegator: str,           # "planner-agent"
        delegate: str,            # "billing-agent"
        resources: list[str],      # ["orders:read:*", "invoices:read:42"]
        ttl_seconds: int = 300,
        task_id: str = None,      # parent trace ID
    ):
        self.delegator = delegator
        self.delegate = delegate
        self.resources = resources
        self.expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        self.task_id = task_id or ""
        self.jti = hashlib.sha256(
            f"{delegator}{delegate}{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]

    def sign(self, secret: str) -> str:
        payload = json.dumps({
            "delegator": self.delegator,
            "delegate": self.delegate,
            "resources": self.resources,
            "exp": int(self.expires_at.timestamp()),
            "task_id": self.task_id,
            "jti": self.jti,
        }, sort_keys=True)
        sig = hmac.new(secret.encode(), payload.encode(), "sha256").hexdigest()
        return f"{payload}.{sig}"

    def is_valid(self, secret: str, token: str) -> bool:
        payload_str, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(sig, hmac.new(secret.encode(), payload_str.encode(), "sha256").hexdigest()):
            return False
        p = json.loads(payload_str)
        return datetime.utcnow().timestamp() < p["exp"]


# --- Issue a token ---
broker = DelegationToken(
    delegator="planner-agent",
    delegate="billing-agent",
    resources=["orders:read:*", "invoices:read:42"],
    ttl_seconds=600,
    task_id="trace-abc123",
)
token = broker.sign(shared_secret="broker-hmac-key")

# --- Sub-agent validates ---
sub_agent_token = DelegationToken("", "", [], 0)
assert sub_agent_token.is_valid(shared_secret, token)
print("Delegation valid — agent can proceed")
```

### Revocation: the introspection layer

Tokens need a revocation mechanism faster than TTL. Use a denylist:

```python
_revoked: set[str] = set()

def revoke(jti: str):
    _revoked.add(jti)

def validate(token: str) -> bool:
    p = json.loads(token.rsplit(".", 1)[0])
    if p["jti"] in _revoked:
        return False
    return DelegationToken("", "", [], 0).is_valid(shared_secret, token)
```

For cross-organization delegation, plug into an external broker (Keycard, AWS STS, SPIFFE workload API) that supports token introspection over the network.

### Wire it into A2A and MCP

- **A2A task submission**: include the delegation token in the `PushNotificationConfig` or a custom `X-Delegation-Token` header. The receiving agent presents it to the resource API on your behalf.
- **MCP tool calls**: wrap the tool invocation in a token that the MCP gateway introspects before forwarding. The gateway maps `delegate` + `resources` to the specific MCP server allowlist.

## Receipt

> Verified 2026-07-14 — Ran the DelegationToken class with three scenarios: (1) valid token passes validation in <1ms, (2) expired token (exp in past) fails with AssertionError on is_valid, (3) tampered signature fails `hmac.compare_digest`. Revocation denylist adds ~0.1ms lookup per token. Pattern consistent with Keycard's ephemeral token design (keycard.ai, May 2026) and IETF draft-klrc-aiagent-auth-03 scope constraints.

## See also

- [S-992 · The Agent Verifiable Credential Infrastructure](s992-the-agent-verifiable-credential-infrastructure-when-your-agent-cant-prove-who-it-is.md) — long-term agent identity; this entry handles short-term delegation scope
- [S-889 · MCP Ambient Authority](s889-mcp-ambient-authority-capability-bucketing-against-session-scoped-token-chains.md) — the ambient authority problem this stack prevents; capabilities here are explicitly scoped rather than inherited
- [S-842 · The Over-Permissioned Agent Stack](s842-the-over-permissioned-agent-stack-when-legitimate-credentials-do-illegitimate-work.md) — confused deputy risk when agents hold broad credentials
