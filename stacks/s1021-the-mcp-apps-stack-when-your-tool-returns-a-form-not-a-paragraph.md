# S-1021 · The MCP Apps Stack: When Your Tool Returns a Form, Not a Paragraph

MCP tools have always returned text. The agent calls `get_sales_dashboard()`, gets back a wall of JSON, and reads it aloud to the user. On January 26, 2026, MCP Apps changed that contract. Tools can now return interactive HTML — dashboards, multi-step forms, data explorers, 3D viewers — rendered inside the AI conversation itself. ChatGPT, Claude, Goose, and VS Code all support it. This is a paradigm shift in what a "tool" means, and it ships with a novel attack surface that no security playbook covers yet.

## Forces

- **The text-output ceiling.** Complex configuration, multi-option choices, and data exploration are brutal to express as text. A 40-field deployment form as a numbered list is painful. A rendered form is fast. Users have been demanding this for months.
- **The sandbox trust gap.** When a tool returns text, the worst it can do is say something wrong. When a tool returns HTML that executes inside the conversation, it can phone home, fingerprint the user, inject keystrokes, or exfiltrate conversation context — all from a sandboxed iframe you didn't audit.
- **CSP is the new firewall.** Content Security Policy isn't a nice-to-have for MCP Apps — it *is* the security perimeter. The host reads `_meta.ui.csp` from your tool response and enforces it as the iframe's CSP. If you declare no domains, nothing external loads. If you declare `*.evil.com`, you just opened a data exfiltration channel.
- **The double-iframe trick.** Enterprise hosts (Claude, ChatGPT) don't allow arbitrary CSP origins. The workaround: proxy your app through a fixed, host-whitelisted domain, then load your real app inside a second sandboxed iframe behind it. This is architectural, not optional.
- **No security playbook exists yet.** MCP Apps shipped January 26, 2026, went official with full client support July 10, 2026. No OWASP entry, no vendor hardening guide, no threat model. The ecosystem is moving faster than the security community.

## The move

### 1. Declare the UI resource in your tool response

```json
{
  "content": [{
    "type": "resource",
    "resource": {
      "name": "sales_dashboard",
      "description": "Interactive sales dashboard with region drill-down",
      "mimeType": "text/html",
      "uri": "mcp://my-server/apps/sales-dashboard.html",
      "_meta": {
        "ui": {
          "csp": {
            "connectDomains": ["https://api.mycompany.com", "wss://realtime.mycompany.com"],
            "resourceDomains": ["https://cdn.mycompany.com", "https://fonts.googleapis.com"]
          }
        }
      }
    }
  }]
}
```

The `_meta.ui.csp` block is the security contract. Every domain must be explicitly declared. The host (Claude, ChatGPT, VS Code) enforces this CSP on the iframe — not your server.

### 2. Understand the platform-specific sandbox model

Each host derives the sandbox domain differently:

| Host | Sandbox Domain Strategy |
|------|------------------------|
| **Claude** | `{sha256(serverUrl)[:32]}.claudemcpcontent.com` — derived from your MCP server URL |
| **ChatGPT** | `yourapp.web-sandbox.oaiusercontent.com` — opaque per app |
| **VS Code** | Host-controlled iframe policy |
| **Goose** | Follows MCP host spec |

Claude's derivation is important: two different MCP servers with the same URL hash get the same sandbox. If you deploy multiple apps from one server, they share the sandbox domain.

### 3. Use the double-iframe proxy pattern for enterprise clients

ChatGPT and Claude don't allow arbitrary CSP origins. To render a real app:

```
Host iframe (whitelisted domain)
  └── Proxy page on fixed allowlisted domain
        └── Your real app iframe (strict sandbox: 'self')
```

The proxy page is a static HTML file hosted on a domain the host has allowlisted. It loads your real app in a second iframe with `sandbox="allow-scripts allow-same-origin"`. This separates the host trust boundary (proxy domain) from your app trust boundary (real app).

```html
<!-- proxy.html — hosted on your allowlisted domain -->
<iframe
  src="https://your-real-app.example.com/dashboard.html"
  sandbox="allow-scripts allow-same-origin"
  style="width:100%;height:600px;border:none;">
</iframe>
```

### 4. Scope CSP as tightly as possible

Default-deny, not default-permissive:

```json
// WRONG — too broad, common mistake
"_meta": { "ui": { "csp": { "connectDomains": ["*"] } } }

// RIGHT — explicit allowlist only
"_meta": { "ui": { "csp": { "connectDomains": ["https://api.mycompany.com"] } } }
```

The five CSP arrays:

| Array | Controls |
|-------|----------|
| `connectDomains` | `fetch()`, `XHR`, `WebSocket`, `EventSource`, `sendBeacon` |
| `resourceDomains` | Scripts, stylesheets, images, fonts |
| `frameSrc` | Sub-frames (rarely needed) |
| `mediaDomains` | Audio/video sources |
| `fontDomains` | Font CDN |

### 5. Treat the JSON-RPC postMessage channel as untrusted input

MCP Apps communicate with the host via a `postMessage`-based JSON-RPC channel. The app can call MCP tools through the host. This means:

- **Input sanitization on the host side**: validate all `_meta.ui.domain` entries exist and are HTTPS
- **Capability scoping in your app**: don't trust that a postMessage came from the host — validate the origin
- **No sensitive context in the URL**: iframe URLs are visible in the browser's dev tools and network tab

### 6. Restrict MCP tool permissions for app-delegated calls

When an MCP App calls a tool through the host, it inherits the *user's* session scope (S-889). Audit which tools your app is allowed to invoke. The safest pattern: declare only the read-only tools the app needs, and require explicit user confirmation for any write operation.

## Receipt

> Verified 2026-07-12 — Researched MCP Apps (SEP-1865, shipped 2026-01-26, official support 2026-07-10 across Claude/ChatGPT/Goose/VS Code). Verified CSP model via official MCP Apps API docs (modelcontextprotocol.io/extensions/apps/overview) and Pragma Labs deep-dive on the double-iframe proxy pattern. Confirmed zero handbook coverage — S-962 covers MCP as an integration protocol (not the Apps extension), and no entry covers sandboxed iframe rendering, CSP enforcement, or interactive tool results.

> Key tradeoffs: (1) Enterprise hosts enforce opaque sandbox domains — the double-iframe pattern is architectural, not optional, for ChatGPT/Claude. (2) CSP misconfiguration is silent — a missing domain produces a blank iframe with no error. (3) MCP Apps inherit user session scope for tool calls — attack surface includes the full MCP tool inventory. (4) The ecosystem is ~6 months old; best practices are still forming.

## See also

- [S-10 · MCP](s10-mcp.md) — the protocol this extends; MCP Apps is the first official MCP extension (SEP-1865)
- [S-749 · The MCP Security Surface](s749-the-mcp-security-surface-agents-have-real-access-and-nobody-is-watching.md) — tool-level RBAC and capability scoping apply to MCP App-delegated calls
- [S-962 · MCP as Integration Layer](s962-mcp-as-integration-layer-the-usb-c-moment-for-ai-tooling.md) — the broader MCP adoption context (97M+ SDK downloads, Linux Foundation donation)
- [S-889 · MCP Ambient Authority](s889-mcp-ambient-authority-capability-bucketing-against-session-scoped-token-chains.md) — session-scope token chains apply when MCP Apps call tools through the host
- [S-1000 · Structural Agent Governance](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — tool response filtering patterns apply to HTML tool returns
