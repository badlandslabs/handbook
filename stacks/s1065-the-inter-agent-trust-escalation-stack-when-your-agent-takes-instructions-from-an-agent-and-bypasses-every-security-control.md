# S-1065 · The Inter-Agent Trust Escalation Stack — When Your Agent Takes Instructions from an Agent and Bypasses Every Security Control

In a multi-agent pipeline, Agent B receives a task from Agent A and executes it without independently verifying the request's legitimacy. Your network firewalls, your OAuth scopes, your MCP tool permissions — none of them fire because the second hop came from an internal agent, not an external actor. This is Inter-Agent Trust Escalation: the failure mode where agents treat instructions from other agents as inherently trusted, creating an internal attack surface that no perimeter control anticipates.

## Forces

- **Agents implement inter-process trust by default.** Unlike humans who authenticate at every boundary, agent-to-agent calls inherit a "trust because internal" assumption. When Agent A hands work to Agent B, Agent B's policy engine sees an authenticated principal — Agent A's token — and applies the full permission set associated with that identity, without evaluating whether Agent A was acting within its intended scope for this specific task.
- **Delegation chains multiply privileges without decay.** Each agent handoff in a pipeline adds capabilities: the orchestrator's permissions combine with the worker's, and the worker's combination with the specialist's. By the fifth hop, the terminal agent may hold credentials that none of the individual agents possessed alone. CSA research found that 97% of non-human identities (NHIs) carry permissions they never actively request — accumulated through delegation chains.
- **Internal prompts are not security boundaries.** An agent's system prompt, instruction hierarchy, or internal governance layer is invisible to the infrastructure enforcing network policy. If Agent A is compromised — or simply follows an instruction that drifts from its charter — Agent B has no mechanism to detect this at the enforcement layer. The request looks like any other authenticated call.
- **Legacy security frameworks predate agents.** RBAC, OAuth scopes, and network policy were designed for human-to-service and service-to-service communication. They do not carry task context, provenance chain, or original-user identity through multi-agent delegation hops.

## The move

**Treat inter-agent calls as untrusted by default, with cryptographic provenance and explicit scope narrowing.**

### 1. Add an append-only caveat chain to every agent delegation

Each agent that delegates work must attach a signed, scoped caveat that narrows what the downstream agent may do. Use a token format that supports attenuation: the original grant narrows at each hop, never widens.

```python
# Simplified delegation caveat construction
def build_delegation_token(
    original_token: dict,
    delegator_agent_id: str,
    target_agent_id: str,
    permitted_actions: list[str],
    resource_scope: list[str],
    expiry_seconds: int = 300,
) -> dict:
    """Each hop narrows scope. Downstream agents can ONLY act within the caveat."""
    return {
        "parent_token": original_token["jti"],
        "delegator": delegator_agent_id,
        "recipient": target_agent_id,
        "permitted_actions": permitted_actions,   # intersection, not union
        "resource_scope": resource_scope,         # specific resource IDs
        "issued_at": now_utc(),
        "expires_at": now_utc() + timedelta(seconds=expiry_seconds),
        "purpose": original_token.get("task_description"),  # anchors intent
    }

# Downstream agent verification at call time
def verify_delegation_token(token: dict, requested_action: str, target_resource: str) -> bool:
    in_scope_action = requested_action in token["permitted_actions"]
    in_scope_resource = target_resource in token["resource_scope"]
    not_expired = datetime.fromisoformat(token["expires_at"]) > now_utc()
    return in_scope_action and in_scope_resource and not_expired
```

### 2. Propagate original-user identity through every hop

The initiating user's identity and permissions must travel the full delegation chain so that every agent applies the user's actual authorization, not the delegating agent's elevated credentials.

```python
# Propagate original user context alongside agent context
DELEGATION_HEADERS = {
    "X-Original-User-Id": ...,      # end-user who initiated
    "X-Original-Permissions": ...,  # user's effective permission set at request time
    "X-Delegation-Path": ...,       # "orchestrator → writer → executor"
    "X-Task-Provenance": ...,       # original task description
    "X-Delegation-Signature": ..., # HMAC of full chain for tamper evidence
}

def delegate_to_worker(worker_id: str, task: dict, user_ctx: dict, delegation_chain: list[str]) -> dict:
    headers = {
        "X-Original-User-Id": user_ctx["user_id"],
        "X-Original-Permissions": json.dumps(user_ctx["effective_permissions"]),
        "X-Delegation-Path": " → ".join([*delegation_chain, worker_id]),
        "X-Task-Provenance": task.get("description", ""),
        "X-Delegation-Signature": hmac_sha256(
            SECRET, f"{user_ctx['user_id']}|{task['task_id']}|{worker_id}"
        ),
    }
    return agent_client.invoke(worker_id, task, headers=headers)
```

### 3. Require out-of-band confirmation for sensitive cross-domain actions

Any agent action that crosses a trust boundary (e.g., a research agent attempting a write, a code agent accessing financial data, a planning agent calling external APIs) must require a human confirmation through a channel the agent cannot access.

```python
# Flag cross-domain or high-sensitivity actions
SENSITIVE_ACTION_THRESHOLDS = {
    "write": ["external_api", "database", "filesystem"],
    "read": ["credentials", "keys", "PII"],
    "delegate": ["escalate_scope", "add_permission"],
}

def flag_cross_boundary_action(agent_id: str, action: str, resource: str, delegation_token: dict) -> bool:
    # Check if action is in sensitive categories
    for category, patterns in SENSITIVE_ACTION_THRESHOLDS.items():
        if action == category and any(p in resource for p in patterns):
            # Verify the delegation token explicitly covers this
            if not verify_delegation_token(delegation_token, action, resource):
                raise SecurityException(
                    f"Agent {agent_id} attempted {action} on {resource} "
                    f"without scope. Delegation path: {delegation_token['delegation_path']}"
                )
            # Require human confirmation for cross-domain sensitive actions
            return True  # Signal: surface to human for out-of-band approval
    return False
```

### 4. Detect semantic drift between delegation purpose and actual action

Log the declared task purpose from the delegation token. At execution time, compare the actual action against the purpose. Drift triggers an alert or abort.

```python
def detect_intent_drift(declared_purpose: str, actual_action: str, tool_args: dict) -> DriftResult:
    """Use a lightweight classifier or rule engine to flag semantic misalignment."""
    purpose_embedding = embed(declared_purpose)
    action_embedding = embed(f"{actual_action} {tool_args}")
    cosine_sim = dot(purpose_embedding, action_embedding) / (
        norm(purpose_embedding) * norm(action_embedding)
    )
    if cosine_sim < DRIFT_THRESHOLD:  # typically 0.7–0.8
        return DriftResult(drifted=True, confidence=cosine_sim, action=actual_action)
    return DriftResult(drifted=False)
```

### 5. Apply network-level microsegmentation between agents

Even with application-layer controls, isolate agents by capability tier. Agents that handle external data get a different network segment from agents that handle internal computation. No agent reaches across tiers without going through a verified proxy.

## Receipt

> Verified 2026-07-13 — Research sources: Microsoft AI Red Team Taxonomy v2.0 (June 2026, 7 new failure categories, empirical from 12 months of red team engagements); CSA "Control the Chain, Secure the System" (March 2026, delegation attack taxonomy, Macaroon/Biscuit pattern, 4 defensive requirements); OWASP ASI Top 10 for Agentic Applications (ASI02: Inter-Agent Trust Escalation); arXiv:2506.03053 "MAEBE" (peer pressure in multi-agent ensembles, inter-agent bias transfer); CSA/Okta NHI research (97% NHIs carry unneeded permissions, 144:1 NHI-to-human ratio). Code reflects the Macaroon-style attenuation pattern from the CSA paper, adapted to standard OAuth infrastructure. No live execution — pattern is structural, not library-dependent.

## See also

- **[S-574 · The Agent Per-Principal, Per-Endpoint Least Privilege at NHI Scale Stack](s574-the-agent-per-principal-per-endpoint-least-privilege-at-nhi-scale-stack-when-your-agent-is-the-principal-but-nobody-owns-the-key.md)** — NHI-as-first-class-principal, brokered credentials, endpoint allowlists. The authorization architecture that Inter-Agent Trust Escalation exploits.
- **[S-1052 · The Cascade Stack](s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md)** — Cross-agent error propagation. When one agent's wrong output silently poisons the next agent's reasoning.
- **[S-1000 · The Structural Agent Governance Stack](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md)** — Enforcement that doesn't live or die with the model's attention. Governance-to-agent typed wire as the complement to delegation-layer controls.
- **[S-1034 · The Role Fence Stack](s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md)** — Preventing agents from overstepping their charter within a pipeline. Complementary to the cross-hop trust controls here.
