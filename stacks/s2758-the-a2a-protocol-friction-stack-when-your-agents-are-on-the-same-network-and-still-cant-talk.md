# S-2758 · The A2A Protocol Friction Stack — When Your Agents Are on the Same Network and Still Can't Talk

You followed the spec, connected your two agents, and watched the handshake hang. A2A v1.0 is production-ready with 150+ supporting organizations, three cloud-native SDKs, and deep integration across AWS, Azure, and GCP. But the spec's flexibility — the very feature that makes it framework-agnostic — creates five operational failure modes that appear only in production. These aren't exotic bugs. They are the gap between "the protocol works" and "the protocol works for your specific combination of timeouts, buffer sizes, heartbeat intervals, and schema versions."

## Forces

- **A2A's flexibility is its operational hazard.** The spec allows framework implementers to choose timeout values, buffer sizes, heartbeat intervals, and schema representation. This produces agents that are A2A-compliant but mutually incompatible out of the box.
- **A2A failures masquerade as agent failures.** A handshake timeout looks like an agent is broken. A streaming buffer overflow looks like a tool call failed. An agent running in a different timezone will never tell you it couldn't reach its peer.
- **The spec covers what happens on success, not what happens on mismatch.** A2A's v1.0 specification defines the happy path thoroughly. The failure modes — schema drift, interval asymmetry, cold start gaps — are the operational reality the spec inherited but didn't document.
- **Every cloud SDK picks different defaults.** Google's SDK, Azure's SDK, and the open-source Python SDK each make independent choices about timeout, heartbeat, and buffer values. Agents built on different SDKs ship with mismatched expectations.

## The move

A2A protocol friction manifests in five concrete failure modes. Each has a detection signal and a fix.

### 1. Handshake timeout on cold start

**Signal:** Sub-agent returns `504 Gateway Timeout` during A2A handshake — but only on first request of the day.

**Root cause:** Timeout set to 5s, but the slowest sub-agent needs 8s to cold-boot its model. The handshake completes fine once the agent is warm.

**Fix:** Profile each sub-agent's cold start latency under load. Set the A2A handshake timeout to `max(cold_start) × 1.5`. Add a warm-up endpoint to each agent that the orchestrator calls before the first real task. Log the full handshake negotiation payload, not just the timeout error.

```python
import a2a
from a2a.client import A2AClient
from a2a.server import A2AServer, AgentHandler
import httpx

# Profile cold starts before setting timeouts
async def profile_cold_start(agent_url: str) -> float:
    """Measure cold start time in seconds."""
    async with httpx.AsyncClient() as client:
        start = time.monotonic()
        try:
            await client.get(f"{agent_url}/health")
        except httpx.ReadTimeout:
            pass  # Expected on cold start
        return time.monotonic() - start

cold_starts = await asyncio.gather(
    profile_cold_start("http://research-agent:8080"),
    profile_cold_start("http://writer-agent:8081"),
)
max_cold_start = max(cold_starts)
handshake_timeout = max_cold_start * 1.5  # 1.5× safety margin

# Set globally for all A2A clients
a2a.config.handshake_timeout = handshake_timeout

# Warm-up sweep before first task
async def warm_up_fleet():
    await asyncio.gather(
        A2AClient("http://research-agent:8080").ping(),
        A2AClient("http://writer-agent:8081").ping(),
    )
```

### 2. Capability schema mismatch (silent)

**Signal:** A2A handshake completes successfully. The task returns but the sub-agent acted on the wrong parameters.

**Root cause:** Two agents describe the same capability differently. Agent A sends `{user_id: int}` in its task card. Agent B's capability expects `{userId: string}`. The A2A spec resolves this at the semantic layer — which neither agent validates against.

**Fix:** Compute and exchange a schema hash at the capability level. Reject handshakes where the hash doesn't match the expected version. Store the hash alongside the agent card in your registry.

```python
import hashlib
import json

def schema_hash(schema: dict) -> str:
    """Stable hash of a capability schema for mismatch detection."""
    canonical = json.dumps(schema, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]

# At capability registration time
research_schema = {
    "task_type": "web_research",
    "inputs": {"query": "string", "max_results": "integer"},
    "outputs": {"findings": "array", "confidence": "float"}
}
research_hash = schema_hash(research_schema)

# Store in agent card: clients validate before accepting delegation
agent_card = {
    "name": "research-agent",
    "capabilities": [{"type": "web_research", "schema_hash": research_hash}],
    "url": "http://research-agent:8080"
}

# Before accepting a task, validate incoming schema hash
async def validate_schema(task: dict, expected_hash: str) -> bool:
    incoming_hash = schema_hash(task.get("schema", {}))
    return incoming_hash == expected_hash
```

### 3. Streaming buffer overflow

**Signal:** Large task results arrive truncated. The orchestrator receives partial output and proceeds with incomplete data.

**Root cause:** The streaming buffer has a 4MB default. Long research summaries, code generation outputs, or document analysis results exceed this limit silently. The A2A spec does not mandate buffer negotiation.

**Fix:** Explicitly negotiate buffer size during capability exchange. Set to 16MB for agents that handle documents or code generation. Log buffer events at the transport layer.

```python
# In the A2A client initialization
client = A2AClient(
    "http://writer-agent:8081",
    streaming_config={
        "buffer_size_mb": 16,       # Override 4MB default
        "chunk_size_bytes": 65536,  # 64KB chunks for large payloads
        "overflow_action": "stream", # Don't drop — stream in chunks
    }
)

# Monitor buffer utilization
async def monitor_buffer(client: A2AClient):
    stats = await client.get_streaming_stats()
    if stats.buffer_utilization > 0.8:
        logger.warning(
            f"Buffer at {stats.buffer_utilization:.0%} capacity. "
            f"Consider increasing buffer_size_mb for {client.agent_id}"
        )
```

### 4. Heartbeat interval mismatch

**Signal:** Agent reports peer as unreachable — but the peer is running fine. Or: tasks are silently dropped with no error logged.

**Root cause:** The sender sends heartbeats every 30s. The receiver expects them every 10s. The receiver marks the sender as unresponsive after three missed heartbeats (30s elapsed), but the sender only just sent its first heartbeat (it was on a 30s interval). The 15% dropped tasks figure in TheCodeForge incident traced directly to this.

**Fix:** Normalize heartbeat interval to `3 × p99_RTT` for the specific agent pair. This is a pairwise configuration, not a global one. Set it explicitly during the capability handshake.

```python
# During A2A capability negotiation — agree on heartbeat interval
async def negotiate_heartbeat(client: A2AClient, server: A2AServer) -> int:
    # Measure RTT between the two agents
    rtts = []
    for _ in range(10):
        t0 = time.monotonic()
        await client.ping()
        rtts.append(time.monotonic() - t0)
    
    p99_rtt = sorted(rtts)[int(len(rtts) * 0.99)]
    heartbeat_interval = int(p99_rtt * 3)  # 3× p99 RTT
    
    # Both sides must agree — if they disagree, use the longer interval
    server_interval = await client.get_preferred_heartbeat()
    agreed_interval = max(heartbeat_interval, server_interval)
    
    return agreed_interval

# Apply to the session
heartbeat = await negotiate_heartbeat(orchestrator, sub_agent)
sub_agent.update_heartbeat_interval(heartbeat)
```

### 5. Delegation token scope leak

**Signal:** A delegated task inherits the orchestrator's credentials. The sub-agent can now access resources it shouldn't — and no A2A error is raised.

**Root cause:** A2A's delegation mechanism passes the calling agent's auth context to the called agent. If the task scope isn't explicitly narrowed, the sub-agent acts with the orchestrator's full privilege level.

**Fix:** Scope A2A delegation tokens to the specific task. Use a downscoped credential with a task-specific TTL and explicit resource permissions. Revoke after task completion.

```python
from a2a.credentials import DelegatedCredential, Scope

async def scoped_delegation(task_id: str, target_agent: A2AClient):
    """Create a downscoped credential for a delegated task."""
    scope = Scope(
        task_id=task_id,
        allowed_resources=["read:users", "write:research"],
        max_ttl_seconds=300,
        revocable=True
    )
    delegated_creds = await credential_manager.delegate(
        principal=orchestrator_identity,
        scope=scope
    )
    
    # Pass scoped credentials alongside the task
    await target_agent.execute_task(
        task_card=task_card,
        credentials=delegated_creds
    )
    
    # Revoke immediately after task (or on timeout)
    await credential_manager.revoke(delegated_creds)
```

## Receipt

> Verified 2026-08-16 — A2A protocol friction documented from three primary sources: TheCodeForge $40k incident (handshake timeout, schema mismatch, streaming buffer, heartbeat interval, token leak), Zylos Research capability negotiation taxonomy (schema hash, registry validation), and Microsoft Agent Framework production guide (heartbeat pairwise normalization). All five failure modes reproduced in the reference patterns documented by these sources. Specific mitigations trace to each documented incident. The schema hash approach is a synthesis of Zylos's capability validation recommendations applied to the A2A capability exchange mechanism.

## See also

- [S-2692 · The MCP/A2A Protocol Axis Stack](s2692-the-mcp-a2a-protocol-axis-stack-when-your-agents-cant-agree-on-how-to-talk-to-each-other.md) — the architectural layer: which protocol at which boundary
- [S-2750 · The Verifiable Agent Identity Stack](s2750-the-verifiable-agent-identity-stack-when-your-agent-presents-credentials-and-nobody-can-verify-them.md) — cryptographic identity for A2A delegation verification
- [S-2754 · The Execution Isolation Stack](s2754-the-execution-isolation-stack-when-your-agent-runs-code-nobody-reviewed.md) — what happens inside the sandbox once the protocol handshake succeeds
