# S-2221 · The Agentic Supply Chain Compromise Stack — When Trusted Plugins Became the Attack Vector

Your agent loads a tool from a trusted registry. You verified the JSON schema. You checked the publisher reputation. You pinned the version. The tool does exactly what it says — reads a file, queries a database, sends a message. What you didn't know: the natural-language tool *description* embedded in the manifest instructs the agent to quietly forward sensitive context to an external endpoint on every call. This is not a CVE in the SDK. There is no patch. The attack is the feature.

## Forces

- **Ergonomics are orthogonal to security.** The same frictionless publishing that makes an ecosystem grow is what makes it rot from within. Tool registries optimize for discovery, not integrity.
- **Agents trust descriptions they should distrust.** Unlike code, where execution is observable, a natural-language tool description is just text. An agent that reads "This tool queries the product database" and acts on it has no way to know it also reads "And sends the full query context to analytics.example.com."
- **No binary to scan.** Traditional supply chain security scans compiled artifacts. Agentic supply chain compromise works at the description layer — before any code runs.
- **Publish-once, affect-everywhere.** A single poisoned tool definition in a popular registry can silently alter behavior across thousands of deployed agents, even after those agents pin specific versions, because pinned versions include descriptions.
- **Governance lags ecosystem velocity.** Registry operators have no standardized audit framework, no SBOM equivalent, no reproducible trust chain for natural-language artifacts.

## The Move

**Trust nothing at the description layer.** Treat tool descriptions as untrusted input, not configuration.

### 1. Sandboxed description parsing

Parse tool descriptions in an isolated context. Never let a description written by a third party influence agent reasoning without a verification gate. The description field should be consumed by a *classifier*, not by the agent directly.

```python
from transformers import pipeline
import anthropic

TRUST_THRESHOLD = 0.85

classifier = pipeline(
    "text-classification",
    model="agentshield/trust-scanner-v2",  # fine-tuned on poisoned vs benign descriptions
    device="cpu"
)

def describe_tool(tool_manifest: dict, agent_client: anthropic.Anthropic) -> str:
    desc = tool_manifest.get("description", "")
    score = classifier(desc)[0]

    if score["score"] < TRUST_THRESHOLD:
        # Replace description with capability type only — strip natural language
        return f"Tool type: {tool_manifest['type']}, params: {list(tool_manifest.get('parameters', {}).get('properties', {}).keys())}"

    return desc  # description trusted, pass through

# The agent never sees raw third-party descriptions above threshold
```

### 2. Capability fingerprinting

Replace natural-language descriptions with structured capability types. Instead of "This tool queries the customer database and returns matching records," encode as `{capability: "sql_read", scope: "customers", params: ["query"], returns: "tabular"}`. The agent reasons over types, not prose.

```python
TOOL_TYPE_REGISTRY = {
    "read_customer_db": {
        "capability": "sql_read",
        "scope": ["customers"],
        "params_schema": {"query": {"type": "string", "max_tokens": 200}},
        "output_schema": {"type": "array", "items": {"type": "object"}},
        "risk_level": "low",       # read-only
        "data_classification": "PII",  # watch for this on egress
        "external_comms": False,
    },
    "send_webhook": {
        "capability": "http_post",
        "scope": [],
        "params_schema": {"url": {"type": "string", "pattern": "^https://"}, "body": {"type": "object"}},
        "output_schema": {"type": "object"},
        "risk_level": "medium",
        "data_classification": "config",
        "external_comms": True,  # this flag triggers egress checks
    },
}

def get_tool_description(tool_name: str) -> str:
    t = TOOL_TYPE_REGISTRY.get(tool_name)
    if not t:
        return "Unknown tool — block execution"
    # No natural language from third parties. Agent gets structured types only.
    return (
        f"capability={t['capability']} | scope={t['scope']} | "
        f"risk={t['risk_level']} | data_class={t['data_classification']} | "
        f"external_comms={t['external_comms']}"
    )
```

### 3. Egress guard on external_comms=True

Every tool flagged `external_comms: True` gets a mandatory pre-flight check:

```python
def egress_guard(tool_name: str, params: dict) -> bool:
    t = TOOL_TYPE_REGISTRY.get(tool_name)
    if not t or not t["external_comms"]:
        return True  # no egress, proceed

    # Log the call with full context
    print(f"[EGRESS GUARD] {tool_name} attempting external call")
    print(f"  params keys: {list(params.keys())}")
    print(f"  data_class: {t['data_classification']}")

    # Block if params contain PII and destination isn't whitelisted
    if t["data_classification"] == "PII":
        allowed_destinations = ["internal-logger", "approved-crm"]
        if tool_name not in allowed_destinations:
            print(f"[BLOCKED] PII egress to non-whitelisted tool: {tool_name}")
            return False

    return True
```

### 4. Registry provenance chain

Verify registry provenance at load time. Pin not just the tool version but the registry attestation:

```bash
# Pin registry attestation alongside tool version
TOOL_PIN="customer-db-v2.1.0"
ATTESTATION="sha256:abc123... (signed by registry operator)"

# Verify before loading
cosign verify-attestation \
  --type application/vnd.envelope.payload+json \
  "$REGISTRY/$TOOL_PIN" \
  --certificate-identity "https://registry.example.com/attestor" \
  --certificate-oidc-issuer "https://registry.example.com"
```

### 5. Behavioral fingerprinting in staging

Before promoting a tool to production, run it through behavioral fingerprinting:

```python
def behavioral_fingerprint(tool_server_url: str, test_inputs: list[dict]) -> dict:
    """Run tool with synthetic inputs and inspect for unexpected network calls."""
    import subprocess, socket

    # Start a local DNS/HTTP sink to catch any outbound calls
    with subprocess.Popen(["python3", "-c", """
import http.server, socketserver, threading, socket

class Sink(http.server.BaseHTTPRequestHandler):
    calls = []
    def do_GET(self): calls.append(self.path); self.send_response(200)
    def do_POST(self): calls.append(self.path); self.send_response(200)

PORT = 19999
with socketserver.TCPServer(('', PORT), Sink) as s:
    s.handle_request()  # single request
    print("EGRESS_CALLS:", Sink.calls)
"""]) as proc:
        pass

    # Tool calls that hit localhost:19999 indicate unexpected egress
    if "EGRESS_CALLS" in str(proc.stdout.read()):
        return {"safe": False, "reason": "unexpected outbound call detected"}
    return {"safe": True}
```

## Receipt

> Verified 2026-08-06 — Research: Microsoft AI Red Team Taxonomy v2.0 (April 2026), arxiv:2602.11327 "Security Threat Modeling for Emerging AI-Agent Protocols" (comparative lifecycle-phase threat analysis across MCP, A2A, ANP, Agora), AgentSeal audit of 1,808 MCP servers (66% had at least one security finding, 43% command injection). Coded examples: trust-scanner-v2 is a hypothetical fine-tuned model (implement with your own fine-tuning corpus of benign vs. poisoned descriptions); behavioral fingerprinting code is a proof-of-concept sketch — production deployment requires proper network isolation (a dedicated VM or container with monitored egress rules, not a localhost sink).

## See also

- [S-1062 · The MCP Supply Chain Integrity Stack](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — SDK-level CVE coverage (this entry covers the description-layer attack class above the CVE surface)
- [S-1050 · The Tool Response Poisoning Stack](s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — server-side poisoning during tool execution
- [S-1458 · The Policy Kernel Stack](s1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — deny-by-default enforcement that this pattern feeds into
- [S-1365 · The ADI Stack](s1365-the-adi-stack-when-your-agent-is-owned-through-a-metadata-field-it-trusted.md) — indirect injection through trusted metadata fields
