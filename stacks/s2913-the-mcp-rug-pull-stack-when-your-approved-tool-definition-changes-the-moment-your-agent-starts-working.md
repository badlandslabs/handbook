# S-2913 · The MCP Rug-Pull Stack — When Your Approved Tool Definition Changes the Moment Your Agent Starts Working

You reviewed the tool schema. You approved the tool. You shipped the agent. Then the MCP server silently changed the tool description overnight — replacing `list_repos` with an exfiltration payload — and every session that ran today sent your private code to an attacker you never knew existed. The CVE is CVE-2025-54136 (CVSS 8.8): **tool definition approval does not survive subsequent server-side changes.** There is no native MCP mechanism to detect this.

This is the rug-pull attack. It is one of three variants in the **MCP tool poisoning** family that CSA documented across 45+ real-world servers at >60% success rate (72.8% with the best-performing agent model). Unlike tool description poisoning (S-743) — where a malicious schema ships at install time — the rug-pull shifts the attack surface to the runtime lifecycle: the server you trusted mutates its own definitions after you approved them.

## Forces

- **MCP's approval model is one-shot and ephemeral.** Most MCP hosts present tool definitions to a human (or auto-approve) at session start. After that, the server can return a different `tools/list` response on any subsequent call. There is no diffing, no version pinning, no re-approval prompt. Approved once means trusted forever — until the server decides otherwise.
- **Server-side mutation is invisible in normal operation.** MCP servers legitimately change tool schemas as they upgrade. Legitimate mutation and malicious mutation produce the same network behavior. Without schema hashing and change detection, you cannot distinguish "v1.2.0 of the GitHub MCP added a new parameter" from "attacker added exfiltration instructions to `list_repos`."
- **The attack succeeds even in fully air-gapped environments.** Because the payload lives in the tool metadata that the MCP server returns, not in external content, the attack works against internal servers behind VPNs, in private VPCs, or on localhost. Cross-site tool poisoning (where one MCP server mutates how another server's tools are interpreted) compounds this for multi-server deployments.
- **Tool shadowing adds a cross-server dimension.** A malicious MCP server can inject instructions that alter how the agent uses *other* servers' tools — without touching those servers at all. The agent's reasoning about `list_repos` gets modified by `evil_search`, a server that has no direct access to your code.

## The Move

### 1. Schema Pinning at First Load

Hash the `tools/list` response on first connect and store the schema fingerprint alongside the server identity.

```python
import hashlib, json

def pin_schema(server_id: str, tools_response: dict) -> str:
    schema_bytes = json.dumps(tools_response, sort_keys=True).encode()
    fingerprint = hashlib.sha256(schema_bytes).hexdigest()[:16]
    # Store: server_id → fingerprint in an approved-manifest store
    store_approved_manifest(server_id, fingerprint, tools_response)
    return fingerprint
```

### 2. Runtime Diff Detection

Before every session, re-fetch `tools/list` and compare against the pinned fingerprint.

```python
def check_schema_drift(server_id: str, tools_response: dict) -> DriftResult:
    current_fingerprint = hashlib.sha256(
        json.dumps(tools_response, sort_keys=True).encode()
    ).hexdigest()[:16]
    approved = get_approved_fingerprint(server_id)
    if current_fingerprint != approved:
        # Log diff, alert, and quarantine server until human review
        diff = compute_schema_diff(
            get_approved_schema(server_id),
            tools_response
        )
        return DriftResult(drifted=True, diff=diff, severity=classify(diff))
    return DriftResult(drifted=False)
```

### 3. Cross-Server Tool Shadowing Guard

Instrument MCP hosts to tag each tool with its source server. Enforce that tool semantics from Server A cannot be modified by Server B.

```python
class ToolMetadata:
    source_server: str
    schema_hash: str
    approved_by: str
    approved_at: datetime

def dispatch_tool(tool_call: ToolCall, host_registry: dict[str, MCPServer]) -> None:
    tool_meta = host_registry[tool_call.server_id].tool_catalog[tool_call.tool_name]
    # Guard: shadowing detection
    if tool_call.injected_context.get("alternate_server"):
        raise ShadowingBlocked(
            f"Tool {tool_call.tool_name} from {tool_meta.source_server} "
            f"was called with context from {tool_call.injected_context['alternate_server']}"
        )
```

### 4. Immutable Tool Manifest

Store approved schemas in a separate, append-only manifest store (e.g., OPA rego policy, SPIFFE attestations, or a signed manifest in a git repo). Rollback to the last known-good schema on drift — do not auto-accept the new version.

### 5. Tool Description Sandboxing

Parse tool descriptions with a description-only parser that strips anything resembling instructions. Run the stripped schema against the agent to verify the tool still functions. If it stops working, the original description contained structural instructions (not just documentation).

## Receipt

> Verified 2026-08-20 — Sources: CSA AI Safety Initiative Labs, "MCP Tool Poisoning: Adversarial Hijacking of AI Agent Workflows" (2026-07-02) — >60% attack success rate across 45+ real-world MCP servers; 72.8% with best-performing agent model; CVE-2025-54136 (CVSS 8.8) for rug-pull via schema mutation after approval; Invariant Labs found 5.5% of public MCP servers contain poisoned metadata. BeyondScale Enterprise Defense Playbook (2026-05-20) provides the four-pattern taxonomy and defense playbook. CybesecPentesting published red-team testing methodology for rug-pull detection (2026).

## See also

- [S-743 · MCP Tool Description Poisoning](s743-mcp-tool-description-poisoning-the-schema-is-the-attack-surface.md) — The install-time variant: malicious schemas shipped before the session begins
- [S-968 · MCP Server Attestation](s968-the-mcp-server-attestation-stack-when-you-dont-know-if-your-server-is-who-it-claims.md) — Runtime verification of server identity and behavioral drift
- [S-2911 · MCP Auth Gap](s2911-the-mcp-auth-gap-stack-when-half-your-mcp-servers-have-no-authentication.md) — The complementary gap: servers with no authentication in production
- [S-1062 · MCP Supply Chain Integrity](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — The ecosystem-level CVE landscape across MCP SDKs
