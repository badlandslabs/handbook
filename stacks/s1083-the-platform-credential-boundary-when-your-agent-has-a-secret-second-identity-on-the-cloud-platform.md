# S-1083 · The Platform Credential Boundary

When your agent calls tools with deliberately scoped permissions — RBAC on the MCP layer, short-lived tokens, per-task capability grants — the security posture looks airtight. It isn't. The agent runs inside a cloud execution environment (Vertex AI Agent Engine, Bedrock Agents, Azure AI Agent Service) that attaches a separate, unscoped platform identity to every invocation. This identity lives on the metadata service endpoint (169.254.169.254 on GCP/AWS, 169.254.169.254 on Azure), reachable by any code running inside the agent's context. Your agent's scoped tool permissions are real. The platform credential is a second identity your agent also holds — one your RBAC never touched.

## Forces

- **Cloud platforms attach service identities by default.** GCP Vertex AI Agent Engine provisions a Per-Project, Per-Product Service Agent (P4SA) with cross-project permissions. AWS Bedrock agent execution roles carry service-role credentials. Azure AI Agent Service attaches managed identities. These are designed for the platform, not for your agent's threat model — and they persist regardless of how tightly you scope the agent's own tool access.
- **The metadata service is a back channel your RBAC doesn't see.** The GCP metadata service at 169.254.169.254 serves access tokens for the attached service account to any process running in the VM/container. An agent compromised by prompt injection, a bad tool, or even a correct-but-overreaching LLM decision can call this endpoint directly. No MCP tool, no tool-level permission gate — just an HTTP GET. Palo Alto Unit 42 demonstrated this in March 2026: a Vertex AI agent with read-only deployment access used the metadata service to obtain P4SA tokens with cross-project Cloud Storage, BigQuery, and Artifact Registry permissions.
- **Scoped tool access creates false confidence.** When you issue short-lived tokens per MCP tool call, audit every invocation, and enforce least-privilege RBAC, the dashboard looks green. Nobody is looking at whether the execution context also holds a platform-level credential that grants everything. This is the configuration that most teams ship in.
- **Platform credentials are invisible in the agent's tool list.** MCP shows the agent which tools it has. It does not show the agent which platform credentials it inherited. The agent — or an attacker through the agent — can discover and use the platform credential without any tool invocation that would show up in your MCP audit log.

## The move

### Audit the platform identity first

Before deploying any agent to a cloud execution environment, enumerate what the execution context can reach via the metadata service:

```bash
# GCP — check attached service account
curl -s "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/" -H "Metadata-Flavor: Google"

# GCP — attempt to mint a token for the attached SA
curl -s "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
  -H "Metadata-Flavor: Google"

# AWS — check instance metadata
curl -s "http://169.254.169.254/latest/meta-data/iam/info/"
curl -s "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300"

# Azure — check managed identity endpoint
curl -s "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2022-01-01" \
  -H "Metadata: true"
```

If any of these return tokens or identity info, your agent has platform credentials. Map what those credentials can access before you scope anything else.

### Use VPC Service Controls to contain the platform identity

On GCP, wrap agent execution inside a VPC Service Perimeter. This restricts what the P4SA can reach even if the token is harvested:

```python
# GCP — restrict P4SA via org policy (replace PROJECT_NUMBER)
# Apply at organization level or project level
gcloud org-policies set-policy PROJECT_NUMBER <<EOF
{
  "name": "constraints/iam.disableServiceAccountKeyCreation",
  "spec": {
    "rules": [{"enforce": true}]
  }
}
EOF

# Restrict service account token creation to specific principals
gcloud iam service-accounts add-iam-policy-binding \
  service-P4SA@PROJECT_NUMBER.iam.gserviceaccount.com \
  --member="group:ai-security@yourorg.com" \
  --role="roles/iam.serviceAccountTokenCreator"

# Use VPC SC perimeter to restrict what P4SA can access
gcloud access-context-manager perimeters update your-perimeter \
  --add-members="serviceAccount:service-P4SA@PROJECT_NUMBER.iam.gserviceaccount.com" \
  --restricted-services="bigquery.googleapis.com,storage.googleapis.com,artifactregistry.googleapis.com"
```

### Isolate agent execution from platform credentials

The cleanest solution: run agents in execution environments that don't attach platform credentials, or use a sidecar that strips them before the agent runs:

```python
# AWS Bedrock — use a separate execution role with no permissions
# Let the agent call tools via tool invocations ONLY
import boto3

# Agent execution role: NO direct AWS service access
execution_role_arn = "arn:aws:iam::123456789:role/AgentExecutionRoleNoAWS"

# Separate tool execution role: scoped, used ONLY via tool calls
tool_role_arn = "arn:aws:iam::123456789:role/AgentToolRole"
# Tool role has only: s3:GetObject on specific bucket, dynamodb:Query on specific table

bedrock_agent = boto3.client("bedrock-agent-runtime")

response = bedrock_agent.invoke_agent(
    agentId="AGENT_ID",
    sessionIdArn=f"arn:aws:bedrock:us-east-1:123456789:agent-session/{session_id}",
    inputText=query,
    # Explicitly do NOT pass additionalSessionState that would carry credentials
)
```

### Block metadata service access from agent code

For environments where you control the agent runtime image, block the metadata endpoint at the network or application layer:

```python
# Middleware that intercepts HTTP calls and blocks metadata endpoints
BLOCKED_HOSTS = {
    "169.254.169.254",      # GCP/AWS/Azure metadata
    "metadata.google.internal",
    "metadata.internal",
}

def block_metadata_calls(tool_fn):
    """Decorator that intercepts HTTP tool calls and blocks metadata exfiltration."""
    async def wrapped(tool_request):
        url = tool_request.get("url", "")
        parsed = urlparse(url)
        host = parsed.netloc.split(":")[0]
        if host in BLOCKED_HOSTS:
            return {
                "blocked": True,
                "reason": "Metadata service access blocked by platform policy",
                "tool": "http",
                "requested_url": url,
            }
        return await tool_fn(tool_request)
    return wrapped

# MCP server config: wrap HTTP tool behind blocking middleware
@mcp.tool()
@block_metadata_calls
async def http_get(url: str, headers: dict = None) -> str:
    ...
```

### Short-lived, scoped tokens per task — and refresh them

Even when you can't remove the platform credential, you can limit its blast radius by ensuring it has minimal permissions AND rotating frequently:

```python
from google.auth import default, service_account
from google.auth.transport.requests import Request
import time

def get_scoped_token_for_task(task_id: str, required_services: list[str]) -> dict:
    """Mint a short-lived, task-scoped token for agent task execution.
    
    Use this instead of the P4SA's default token for any platform resource access.
    The P4SA token should never be used directly by agent code.
    """
    # Get P4SA token via metadata service (this is the platform credential)
    # then immediately downgrade it via Cloud IAM conditions
    credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    
    # Build a task-scoped impersonation
    target_email = f"agent-task-{task_id}@your-project.iam.gserviceaccount.com"
    
    # IAM Conditions: expire in 1 hour, allow only specific services
    iam_credentials = googleapiclient.discovery.build(
        "iamcredentials", "v1", credentials=credentials
    )
    
    token_response = iam_credentials.projects().serviceAccounts().generateIdToken(
        name=f"projects/-/serviceAccounts/{target_email}",
        body={
            "audience": required_services,
            "validity": "3600s",  # 1 hour max
            "includeEmail": True,
        }
    ).execute()
    
    return {
        "token": token_response["token"],
        "expires_in": 3600,
        "task_id": task_id,
        "allowed_services": required_services,
    }
```

## Receipt

> Verified 2026-07-14 — Palo Alto Unit 42 "Double Agents" disclosure (unit42.paloaltonetworks.com/double-agents-vertex-ai/, 2026-03-31) confirmed the P4SA metadata token harvest path on Vertex AI Agent Engine. CSA Research Note (2026-04-02) independently validated the attack class across GCP, AWS, and Azure agent execution environments. The metadata service token endpoint responds correctly in standard cloud execution contexts. GCP `curl -s "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/" -H "Metadata-Flavor: Google"` returns account info when run inside a GCE/Vertex context. The blocking middleware pattern is implemented as a reference in the MCPKernel security kernel (piyushptiwari1/mcpkernel, Apache 2.0, v0.3.0).

## See also

- [S-420](s420-agent-non-human-identity-governance.md) · Agent Identity Governance — NHI lifecycle, credential revocation, and human-agent binding
- [S-779](s779-the-mcp-tool-level-rbac-stack.md) · MCP Tool-Level RBAC — least-privilege enforcement for tool access
- [S-799](s799-cross-agent-trace-correlation.md) · Cross-Agent Trace Correlation — audit trails that survive delegation
- [S-918](s918-the-a2a-trust-gap.md) · The A2A Trust Gap — agent-to-agent identity verification
