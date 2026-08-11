# S-2467 · The MCP Server Architecture Stack — When the Protocol Standardized the Connection but Not the Server Design

MCP solved the connection problem. It did not solve the design problem. By mid-2026, over 150 million SDK downloads and 800+ community servers later, the same five architectural mistakes appear across independently-built servers: the data facade leaks prompt injections, the streaming bridge floods the context, the stateful session accumulates corruption, the tool orchestrator overwhelms the agent, and the multi-agent relay creates invisible loops. arXiv:2606.30317v1 (Rodrigues & Vas, June 2026) documents these as recurring patterns from 15 independently-developed servers. This entry is the pattern language your MCP server designs are missing.

## Forces

- **MCP is an API design problem with an unusual constraint.** The LLM picks which tool to call by reading natural language descriptions — not by consulting documentation, type signatures, or a schema browser. Every architectural decision flows from this: your server's interface must be readable by a model with no runtime type information.
- **Tool selection accuracy collapses at scale.** Tool selection accuracy drops below 90% between 10–15 tools for Haiku-class models and 20–30 tools for Sonnet-class models — before considering that each tool invocation may return unbounded data back into the context window.
- **The stdio transport is a supply chain RCE.** `StdioServerParameters` in Anthropic's official SDKs (Python, TypeScript, Java, Rust) accepts an unsanitized `command` field passed directly to `subprocess`. 14 CVEs assigned, 200,000+ exposed servers, 150M+ SDK downloads. Anthropic says it is by design. This is not a bug you can wait for a fix on.
- **Server-side data can exceed client-side context.** An MCP server that returns full query results — not summaries, not paginated slices — can exhaust a 128K-token context window with a single tool call. The architecture must manage data volume, not just tool count.
- **Prompt injection via tool responses is structural, not incidental.** MCP's tool response channel is indistinguishable from user input from the LLM's perspective. Any server that passes backend data back as a tool response is a potential injection vector.

## The Move

### The Five MCP Server Architecture Patterns

#### 1. Resource Gateway (Data Facade / Context Provider)

**Use when:** LLM agents need to read structured data from backends — databases, APIs, document stores — and ground responses in facts, not predictions.

**The pattern:** All data access goes through the gateway. Reads are exposed as MCP Resources (structured URIs with typed content), parameterized queries as Tools (with input schemas), and the gateway is responsible for sanitization and injection hardening at the boundary. The LLM never talks directly to the backend.

**Key constraints:**
- Parameterized queries (Tools) over raw SQL or API calls — prevents injection
- Resource content is retrieved by the client, not streamed — gives the client control over what enters context
- Schema changes at the backend must be reflected in the MCP schema — version the interface

```
# Resource definition: structured URI, typed content
@mcp.resource("db://customers/{customer_id}")
def get_customer(customer_id: str) -> CustomerRecord:
    # Backend query with parameterized input
    return db.query("SELECT * FROM customers WHERE id = ?", customer_id)

# Tool definition: parameterized query with schema
@mcp.tool(description="Look up a customer by email address")
def lookup_customer(email: str) -> dict:
    # Sanitized query, result truncated before return
    return truncate(db.query(...), max_tokens=512)
```

#### 2. Streaming Bridge

**Use when:** Backends produce unbounded or high-volume output — live logs, real-time streams, large file reads — and you need to feed this into an agent without exhausting the context window.

**The pattern:** The server streams data to the client in bounded chunks. The client (or a middle layer) aggregates, filters, and compresses before the LLM sees it. The server never dumps raw stream output into a single tool response.

**Key constraints:**
- Chunked retrieval with configurable window (N lines / N seconds / N tokens)
- Server-side filter before streaming — not "stream everything, hope the agent filters"
- Client-side summary step for chunks beyond a size threshold

#### 3. Stateful Session Server

**Use when:** Multi-turn interactions require continuity — the server must maintain conversation state, pending operations, or accumulated context across a session.

**The pattern:** The server manages session state explicitly: session IDs, state machines, or event logs that track where a multi-step operation is. The client passes a session handle; the server returns both data and state metadata. Clean session teardown is explicit.

**Key constraints:**
- Session state is server-authoritative, not client-negotiated — prevents state drift
- Explicit session lifecycle: `session_start` → operations → `session_end` / `session_timeout`
- State serialization for recovery — sessions must survive server restarts
- Concurrency limits per session: prevent one runaway client from exhausting the server

```
# Session lifecycle
POST /mcp/sessions       # Create session, returns session_id
GET  /mcp/sessions/{id}  # Get current state
POST /mcp/sessions/{id}/end  # Explicit teardown
```

#### 4. Tool Orchestrator

**Use when:** Multiple backend systems need to be queried in a coordinated way — data from one system informs the query to the next, or multiple systems must be queried in parallel and their results merged.

**The pattern:** The server acts as a query planner. It receives a high-level intent, decomposes it into sub-queries for individual backends, executes them (sequentially or in parallel), and returns a merged result. The agent sees one tool; the server handles the choreography.

**Key constraints:**
- Decompose, don't flatten — preserve the query plan so failures can be attributed
- Timeout and circuit-breaker per backend call — a slow backend should not block the entire result
- Result schema is stable regardless of which backends were available — agents must not see partial failures as random output

#### 5. Multi-Agent Relay (A2A Bridge)

**Use when:** An agent needs to delegate to another agent — not call a tool, but hand off a task with context, intent, and result passing across agent boundaries.

**The pattern:** The MCP server acts as an A2A (Agent-to-Agent) message broker. It maintains agent registries, handles capability discovery, routes task handoffs, and ensures result delivery. The relay is not a tool — it is a coordination layer. MCP provides the transport; the relay provides the semantics.

**Key constraints:**
- Task state is tracked at the relay, not buried in the delegating agent's memory
- Result delivery is guaranteed (ack + retry), not fire-and-forget
- Capability registry: agents register what they can do; the relay matches delegators to delegates by capability, not by name

### Anti-Patterns to Kill

**1. The Monolithic Tool** — One tool that wraps an entire backend API. Returns everything, expects the agent to filter. Collapses tool selection accuracy and floods the context window simultaneously.

**2. The Unbounded Streaming Sink** — Streaming data piped directly into tool responses with no chunking. Causes context exhaustion and, if the stream is adversarial, injection amplification.

**3. The Stateless Tool With Stateful Expectations** — A server that appears stateless but requires sequential calls to function (e.g., `begin_transaction` → operations → `commit`). The client has no way to know this contract exists.

**4. The Tool That Generates Tools** — A tool that returns dynamic tool definitions based on runtime state. Breaks the LLM's ability to reason about tool capabilities — it cannot predict what tools will exist.

### The Security Baseline (Non-Negotiable)

Every MCP server — regardless of pattern — must implement these before going to production:

```
# 1. Command allowlist (StdioServerParameters RCE mitigation)
ALLOWED_COMMANDS = frozenset(["python3", "/usr/local/bin/mcp-server"])
# NEVER pass raw command args from config to subprocess

# 2. Tool response sanitization
def sanitize_response(data: Any, max_tokens: int = 1024) -> str:
    serialized = json.dumps(data)
    if count_tokens(serialized) > max_tokens:
        return summarize(serialized)
    return serialized

# 3. Input validation (parameterized queries, not string interpolation)
# BAD: f"SELECT * FROM users WHERE id = {user_id}"
# GOOD: db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

## Receipt

> Verified 2026-08-11 — Pattern catalog synthesized from arXiv:2606.30317v1 (Rodrigues & Vas, June 2026, 5 production + 10 public MCP servers), The Agent Report (July 2026, 14 CVEs, 200,000+ exposed servers), CSA Research Note on MCP STDIO RCE (May 2026), and AgentSeal audit data (66% of 1,808 servers had security findings). The five-pattern taxonomy, tool selection accuracy thresholds, and stdio RCE numbers are directly from cited sources. Tool belt / tool surface patterns (S-989, S-1006) cover the agent-side selection problem; this entry covers the server-side design patterns — distinct, complementary coverage. MCP supply chain (S-1062) and protocol trust (S-2466) cover the ecosystem security surface; this entry covers the internal architecture decisions a server author makes.

## See also

- [S-1062 · The MCP Supply Chain Integrity Stack](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — the ecosystem security layer; this entry is the internal design layer
- [S-2466 · The MCP Protocol Trust Stack](s2466-the-mcp-protocol-trust-stack-when-the-protocol-assumes-your-server-is-honest.md) — the protocol's trust model; this entry is what to build within that model
- [S-989 · The Tool Surface Stack](s989-the-tool-surface-stack-when-your-agent-has-50-tools-and-picks-the-wrong-one.md) — agent-side tool selection failure; this entry is the server-side design that either helps or hurts
- [S-1358 · The Stochastic-Deterministic Boundary](s1358-the-stochastic-deterministic-boundary-when-your-agent-proposes-the-wrong-action-and-the-system-runs-it-anyway.md) — the general seam between LLM output and system action; MCP servers are a specific instance of that seam
