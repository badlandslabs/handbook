# S-2590 · The Transitive MCP Attack Surface Stack — When Your MCP Server Is Not the Target, but the Hop

Your agent connects to an external MCP server. You audited the server's tool descriptions, verified its OAuth scopes, and confirmed it runs in your VPC. You didn't audit what that server connects to. The external MCP server your agent calls has a direct database connection to your CRM. The CRM has a connection to your analytics pipeline. The analytics pipeline has write access to your data warehouse. You secured the agent-to-server connection. You didn't secure the server's network topology. Your MCP server is not the target — it is the hop.

## Forces

- **MCP secures the client↔server channel, not the server's downstream connections.** MCP's threat model covers what the protocol transmits. It says nothing about what an MCP server does after receiving a validated request. A server that appears to be a simple tool wrapper may be a pivot point into your internal network.
- **Agents enumerate and connect to whatever servers are reachable.** MCP's `tools/list` discovery and A2A's Agent Card make servers findable. Agents connect to multiple servers simultaneously. Each connection is a potential path into that server's trust graph.
- **The blast radius of MCP compromise was never systematically studied until 2026.** The 2026 AI agent security incident landscape — OpenClaw (Jan 2026), 135K exposed MCP instances (Feb 2026), CSA's systemic MCP vulnerability disclosure (May 2026) — showed that MCP server compromise rarely stays local. The server's downstream integrations are where attackers monetize access.
- **The transitive property of trust applies to agents.** If A trusts B and B trusts C, then A's risk exposure includes C's attack surface. MCP servers in production ecosystems connect to databases, cloud APIs, deployment pipelines, and internal services. Compromising one server can mean inheriting all of them.
- **Egress filtering doesn't help when the compromised server is already inside.** S-2583 (Agent Sandbox Stack) solves the problem of keeping agents from reaching out. The transitive MCP problem is the inverse: the server is already inside, and it reaches further than your perimeter.

## The Move

### 1. Map your MCP server's downstream topology before connecting

Every MCP server your agent uses should come with a **server asset manifest** — a signed declaration of:

```
server: mcp-gitlab-connector@v2.1.3
author: platform-team
downstream_connections:
  - type: database
    target: gitlab-db (10.0.4.0/24)
    credentials: service-account (read-only on projects table)
  - type: http_api
    target: GitLab REST API (api.gitlab.com)
    scopes: [read_repository, read_user, api]
  - type: webhook
    target: internal deployment service
    outbound_only: true
network_isolation_level: vpc-peered
egress_allowed: [api.gitlab.com, vault.internal]
```

Any MCP server whose manifest you cannot produce should not be connected to production agents. This is not paranoia — it is the transitive trust equivalent of a software bill of materials (SBOM) for your agent's network graph.

### 2. Apply least privilege to MCP server credentials, not just to the agent

The credentials your MCP server uses to connect to downstream services should be scoped to the minimum required for its function — not the credentials that happened to be available in the deployment environment. If the server only needs to read from the database, it should not have write credentials. If it only needs one table, it should not have full database access.

This is mundane infrastructure hygiene that most MCP server deployments skip, because MCP servers are often written as wrappers around existing integrations without auditing the credential scope.

### 3. Treat MCP servers as network ingress points, not trusted endpoints

Enforce network-level isolation between MCP servers and sensitive internal services. A server that handles `create_jira_ticket` should not be on the same network segment as your payroll system. Use VPC peering rules, security groups, and service mesh policies to limit what an MCP server can reach if its credentials are compromised.

```
# Example: MCP server network policy (Kubernetes NetworkPolicy)
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mcp-jira-connector-netpolicy
spec:
  podSelector:
    matchLabels:
      app: mcp-jira-connector
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              name: jira
        - podSelector:
            matchLabels:
              app: jira-backend
      ports:
        - protocol: TCP
          port: 443
    - to:
        - namespaceSelector:
            matchLabels:
              name: vault
      ports:
        - protocol: TCP
          port: 8200
```

### 4. Monitor MCP server behavior, not just agent behavior

Your observability stack watches the agent's tool calls. It should also watch the MCP server's downstream calls. An agent that makes 3 tool calls per session is normal. An MCP server that begins querying a database it has never touched before is anomalous. Correlate agent tool calls with downstream server activity — a single agent tool invocation may trigger dozens of downstream operations that your agent-level observability never sees.

```
# Instrument MCP server egress as a separate signal
# When the agent calls mcp->search_products,
# also log: which downstream DB queries did that trigger?
trace_id = get_current_trace()
agent_tool_call = span.start_child("mcp_tool_call", name="search_products")
server_downstream = span.start_child("server_downstream", name="postgres.query")

# Alert: agent made 1 tool call → server made 47 downstream ops
# This is the transitive signal that agent-level tracing misses
```

### 5. Apply containment tiers to MCP servers the same way S-2583 applies them to agents

If your agent operates inside containment tiers (microVM → pod → host), your MCP servers should too. Servers with access to sensitive downstream systems should run in higher-containment tiers — not because the server itself is untrusted, but because its compromise has higher blast radius. The containment tier should reflect the trust distance from the agent to the server's farthest downstream dependency.

## Receipt

> Verified 2026-08-13 — Compiled from: CSA AI Safety Initiative (May 4, 2026, MCP Security Crisis), CSA Poisoned Skills report (Jun 24, 2026), CyberDesserts AI Agent Security 2026 (updated Jul 2026), Microsoft AI Red Team Taxonomy v2.0 (Apr 2026), blog.cyberdesserts.com AI agent security incidents. Key incident pattern: OpenClaw (Jan 2026) — 336K GitHub stars, 2,100 deployed agents in 48 hours; 512 vulnerabilities (8 critical), 1,800+ API key leaks traced to downstream integrations, not the agent itself. MCP instances exposed without authentication (Trend Micro: 492 servers; SecurityScorecard: 135K OpenClaw instances). CSA (May 2026): 200,000+ vulnerable MCP instances across a supply chain of 150M+ package downloads. The pattern is consistent: MCP servers are compromised not for what they do for the agent, but for what they reach on the network.

## See also

- [S-2583 · The Agent Sandbox Stack](/stacks/s2583-the-agent-sandbox-stack-when-your-ai-agent-has-the-keys-to-your-kingdom.md) — isolation layers between agents and their blast radius
- [S-2585 · The Latent Capability Trigger Stack](/stacks/s2585-the-latent-capability-trigger-stack-when-your-agent-learns-to-bypass-its-own-safety-training.md) — agentic goal hijacking as a failure mode that compounds with transitive access
- [S-1050 · The Tool-Response Poisoning Stack](/stacks/s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — how MCP server responses poison the LLM context (one layer upstream of the transitive downstream problem)
- [S-974 · The Lethal Trifecta](/stacks/s974-the-lethal-trifecta-when-capability-convergence-creates-catastrophic-agent-risk.md) — capability combinations that amplify compromise consequences
