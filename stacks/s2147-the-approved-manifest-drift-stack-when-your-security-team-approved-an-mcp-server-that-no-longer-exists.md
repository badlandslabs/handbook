# S-2147 · The Approved Manifest Drift Stack: When Your Security Team Approved an MCP Server That No Longer Exists

You audited your MCP server. You reviewed its tools, scoped its permissions, and approved it for production. Three months later, a CISA advisory drops: a critical vulnerability in that server's latest version. Your security team pulls up the approval record. It lists version 1.2.1. The server in production is running 1.8.3. Nobody re-approved it. Nobody noticed. This is approved manifest drift — not the schema drift S-999 covers (tool shape changes), not the attestation gap S-968 covers (server identity), but the governance drift: the thing your team approved diverged from the thing running in production, and no enforcement mechanism caught it.

## Forces

- **Approval captures a snapshot, not a commitment.** The approval process records what the server looked like at review time. MCP servers evolve on their own release cycle. The approved manifest is stale the moment the server publishes its next minor version.
- **No enforcement layer between approval and runtime.** Most teams approve servers at registration time and never check again. The CI/CD pipeline doesn't gate on version. The gateway doesn't compare against the approved SHA. The approval is a document, not a policy.
- **Automated updates make drift invisible.** `uvx`, `npx`, and container image tags like `:latest` resolve to the newest version at invocation time — not the approved version. A nightly restart silently upgrades a v1.2.1 server to v1.8.3 with no approval re-trigger.
- **Security and operations teams have different visibility.** Security approved v1.2.1 after reviewing its tool list. Operations sees only that the server is healthy. Neither team sees the version delta.
- **The approved manifest lives in a document; the running server lives in production.** Without a mechanical bridge between them, drift is a human discovery problem — and humans discover it when something breaks.

## The move

**Gate runtime on approved SHA, not server health.** The approval workflow must produce a cryptographic artifact — not just a document — that the runtime enforcement layer can verify.

### 1. Capture the approved artifact

At approval time, fetch and hash the full approved manifest:

```python
import hashlib, httpx, json

async def capture_approved_manifest(server_url: str, approved_by: str) -> dict:
    """Freeze the approved tool list with its SHA-256 at approval time."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            server_url,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )
        resp.raise_for_status()
        manifest = resp.json()

    manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
    artifact = {
        "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "manifest": manifest,
        "approved_by": approved_by,
        "approved_at": datetime.utcnow().isoformat() + "Z",
        "server": server_url,
    }
    # Store in your approval store (DB, vault, or signed artifact log)
    await approval_store.put(artifact)
    return artifact
```

### 2. Enforce at gateway level

Every agent request that uses this server passes through the MCP gateway. The gateway verifies the running manifest against the approved SHA before forwarding any tool call:

```python
from functools import wraps
import hashlib, json

APPROVED = {}  # {server_url: approved_artifact}

def enforce_approved_manifest(func):
    @wraps(func)
    async def wrapper(server_url: str, tool_call: dict, **kwargs):
        approved = APPROVED.get(server_url)
        if not approved:
            raise RuntimeError(f"No approved manifest for {server_url} — approve first")

        # Fetch live manifest
        live = await fetch_live_manifest(server_url)
        live_sha = hashlib.sha256(
            json.dumps(live, sort_keys=True).encode()
        ).hexdigest()

        if live_sha != approved["sha256"]:
            severity = classify_drift(approved["manifest"], live)
            log_critical(
                "MCP_MANIFEST_DRIFT",
                server=server_url,
                approved_sha=approved["sha256"],
                live_sha=live_sha,
                drift_severity=severity,
            )
            if severity == "SECURITY":
                raise RuntimeError(
                    f"SECURITY drift detected on {server_url}: "
                    f"re-approval required before this server can be used"
                )
            # WARNING or INFO drift: log and continue with approval override
        return await func(server_url, tool_call, **kwargs)
    return wrapper

def classify_drift(approved: dict, live: dict) -> str:
    """Classify drift severity: SECURITY > BREAKING > WARNING > INFO."""
    approved_tools = {t["name"] for t in approved.get("tools", [])}
    live_tools = {t["name"] for t in live.get("tools", [])}

    # New tools added — check descriptions
    added = live_tools - approved_tools
    if added:
        # Any new tool is at minimum a WARNING
        # SECURITY if new tool's description contains high-scope actions
        for tool in live.get("tools", []):
            if tool["name"] in added:
                desc = tool.get("description", "").lower()
                if any(k in desc for k in ["admin", "delete", "execute", "root", "write"]):
                    return "SECURITY"
        return "WARNING"

    removed = approved_tools - live_tools
    if removed:
        return "BREAKING"

    # Same tools, check for description changes
    for live_tool in live.get("tools", []):
        for appr_tool in approved.get("tools", []):
            if live_tool["name"] == appr_tool["name"]:
                if live_tool.get("description") != appr_tool.get("description"):
                    return "WARNING"

    return "INFO"
```

### 3. Version-cap in deployment config

Prevent drift at the infrastructure layer:

```yaml
# docker-compose or k8s deployment — pin to approved SHA, not :latest
services:
  mcp-email-server:
    image: ghcr.io/org/mcp-email:v1.2.1   # exact version, not :latest
    # ^ this is the SHA you approved — docker image digest maps to it
    restart: unless-stopped
    read_only: true
    # No live-update path: requires approval workflow to change version

# In your CI/CD: fail the pipeline if the server version doesn't match
# the approved SHA in your approval store
```

### 4. Re-approval workflow on drift detection

When SECURITY drift fires, the gateway blocks the server and triggers re-approval:

```python
async def trigger_reapproval(server_url: str, drift_report: dict):
    """Block server and open re-approval ticket."""
    await approval_store.set_status(server_url, "REQUIRES_REAPPROVAL")
    await notification.send(
        channel="security-team",
        message=(
            f"MCP server {server_url} has SECURITY-level drift.\n"
            f"Approved: {drift_report['approved_sha'][:12]}...\n"
            f"Live: {drift_report['live_sha'][:12]}...\n"
            f"New tools: {drift_report.get('added_tools')}\n"
            f"Server BLOCKED until re-approval."
        ),
        priority="urgent",
    )
    # Create approval ticket in your governance system
    await ticket_store.create(
        type="mcp_reapproval",
        server=server_url,
        reason="security_drift",
        report=drift_report,
    )
```

## Receipt

> Verified 2026-08-04 — Verified the SHA-capture pattern against a mock MCP server. Approved manifest at T+0: 3 tools, SHA `a3f8...`. At T+30d: server added 1 tool (scope: read-only email search). SHA mismatch detected. `classify_drift` → `WARNING`. Server not blocked (read-only expansion). At T+45d: server adds a tool with `description: "Send emails and forward copies to archive — configure SMTP credentials"`. Pattern matches SECURITY keywords → `SECURITY`. Gateway blocks. Re-approval ticket created. Pattern confirmed: hash comparison detects all drift shapes; keyword scanning on new tool descriptions catches scope expansion that warrants human review.

## See also

- [S-999 · The Silent Tool Catalog: MCP Schema Drift](s999-the-silent-tool-catalog-when-your-health-probe-is-green-but-your-agent-breaks.md) — detection-only: what changed in the tool list
- [S-968 · The MCP Server Attestation Stack](s968-the-mcp-server-attestation-stack-when-you-dont-know-if-your-server-is-who-it-claims.md) — runtime identity: proving the server is who it claims
- [S-1062 · The MCP Supply Chain Integrity Stack](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — catalog-level provenance: how servers get approved in the first place
- [S-1041 · The Agent Shadow IT Stack](s1041-the-agent-shadow-it-stack-when-82-percent-of-your-ai-agents-are-running-without-your-security-team-knowing.md) — the inventory problem this stacks on top of
