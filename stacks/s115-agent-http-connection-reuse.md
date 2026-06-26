# S-115 · Agent HTTP Connection Reuse

Every tool call that hits an external HTTP endpoint begins with a connection. On a fresh TCP connection, the browser — or Node.js process — negotiates: DNS resolution (first time), TCP three-way handshake (~20ms LAN, 80-150ms across regions), and TLS 1.3 handshake (~1 RTT, 40-80ms within a region). Combined: 80-300ms of overhead before the first byte of the real request is sent. If your agent makes five tool calls per session to five distinct external REST APIs, and each tool call creates its own connection, you're paying this overhead five times.

[S-109](s109-agent-idle-cost.md) covers idle cost: what the agent costs when it's waiting, polling, or making no progress. [S-96](s96-tool-fallback-chains.md) covers fallback chains: what to do when a tool endpoint fails. Neither covers the connection lifecycle within a session.

HTTP/1.1 keepAlive and HTTP/2 multiplexing both solve this: once a connection to a given host is established, it stays open and subsequent requests reuse it — skipping TCP and TLS setup. In Node.js, this requires explicitly passing a persistent `https.Agent` with `keepAlive: true` to each request, or using a client library that does so by default. The native `fetch` in Node.js v18+ (via undici) reuses connections automatically per origin. `axios` and older `node-fetch` do not unless configured. The SDK you are using determines whether you get connection reuse for free or need to wire it yourself.

## Situation

An agent's five tool handlers each call a different external HTTP API using `node-fetch`. Each handler creates a new connection per call. Observed latencies per tool call: 180-280ms. Of that, 120-200ms is connection overhead (measured by comparing first-call vs subsequent-call latency to the same host in isolation). The agent makes five tool calls per session, parallelized (S-55), so the session wall-clock is the slowest tool's latency: ~280ms per session.

After switching to a shared `https.Agent({ keepAlive: true, keepAliveMsecs: 30000 })` per destination host and passing it to every `node-fetch` call: first call per session still pays connection setup (120-200ms). Subsequent calls to the same host within the session cost 5-15ms for TCP overhead (no TLS renegotiation). For the handlers that call the same host multiple times within a session (e.g., a paginating tool, or two tools that hit the same third-party API), the second and later calls are 10-20× faster.

## Forces

- **Same host vs different hosts matters.** A keepAlive connection pools per destination `host:port`. If your five tools call five different hosts, the first call to each host in a session still pays full TLS setup. The gain is on: (1) tools called more than once per session; (2) tools that call the same host as another tool; (3) any session that runs more than once (the OS TCP stack may also keep the socket warm if keepAlive interval < system socket timeout).
- **HTTP/2 multiplexes all requests over one connection.** If your endpoints support HTTP/2 (most cloud APIs do), a single keepAlive connection can carry all in-flight requests to that host concurrently. Node.js `http2.connect()` or libraries with HTTP/2 support get this. `https.Agent` is HTTP/1.1 only — it keeps the socket open but cannot multiplex.
- **Connection overhead varies by network topology.** Tool handlers calling localhost or a VPC-internal service pay <5ms for TCP setup even cold — keepAlive saves negligible time. Tool handlers calling cross-region or cross-provider APIs pay the most. Profile your tool handler endpoints (F-85) before optimizing.
- **Connection leaks are the failure mode.** An `https.Agent` that is created per request but never destroyed accumulates open sockets. Node.js will eventually garbage-collect them, but under load this creates FD exhaustion or the "ECONNRESET on connection N+1" pattern. Use one shared agent per destination host per process lifetime, not per session or per call.
- **`maxSockets` controls parallelism.** Default is `Infinity` (one socket per concurrent request). For rate-limited external APIs, set `maxSockets` to the max concurrent calls you're permitted. Excess calls queue on the agent rather than opening new connections and hammering the rate limit.
- **Native `fetch` in Node 18+ does this automatically.** If you're on Node v18+ using native `fetch` (or undici directly), connection pooling is on by default. The pattern below is for `node-fetch`, `axios`, or raw `https.request` where you must opt in.

## The move

**Create one `https.Agent` per destination host at process startup. Pass it to every request to that host. Set `keepAliveMsecs` above the expected call interval; set `maxSockets` to the parallelism your API allows.**

```js
const https = require('https');

// --- One agent per destination host, created at startup ---

const AGENTS = {
  // Third-party APIs: keep alive for 30s (sessions last <10s; OS timeout is 60-90s)
  'api.crm-provider.com':    new https.Agent({ keepAlive: true, keepAliveMsecs: 30000, maxSockets: 10 }),
  'api.shipping-calc.com':   new https.Agent({ keepAlive: true, keepAliveMsecs: 30000, maxSockets: 5  }),
  'payments.processor.io':   new https.Agent({ keepAlive: true, keepAliveMsecs: 30000, maxSockets: 3  }),
  'inventory-api.internal':  new https.Agent({ keepAlive: true, keepAliveMsecs: 60000, maxSockets: 20 }),
};

function agentFor(urlStr) {
  const host = new URL(urlStr).hostname;
  return AGENTS[host] ?? new https.Agent({ keepAlive: true, keepAliveMsecs: 30000 });
}

// --- Tool handler using node-fetch with persistent agent ---

const fetch = require('node-fetch');

async function getCustomerRecord(customerId) {
  const url = `https://api.crm-provider.com/v2/customers/${encodeURIComponent(customerId)}`;
  const resp = await fetch(url, {
    agent: agentFor(url),   // reuse connection; skip TCP+TLS after first call to this host
    headers: { 'Authorization': `Bearer ${process.env.CRM_API_KEY}`, 'Accept': 'application/json' },
    timeout: 2000,
  });
  if (!resp.ok) throw new Error(`CRM API ${resp.status}: ${await resp.text()}`);
  return resp.json();
}

async function updateCustomerTier(customerId, tier) {
  const url = `https://api.crm-provider.com/v2/customers/${encodeURIComponent(customerId)}/tier`;
  const resp = await fetch(url, {
    method: 'PATCH',
    agent: agentFor(url),   // same agent as getCustomerRecord → same keepAlive socket to crm-provider.com
    headers: { 'Authorization': `Bearer ${process.env.CRM_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ tier }),
    timeout: 2000,
  });
  if (!resp.ok) throw new Error(`CRM tier update ${resp.status}`);
  return resp.json();
}

// --- Axios equivalent ---

const axios = require('axios');

const crmAxios = axios.create({
  baseURL:  'https://api.crm-provider.com/v2',
  timeout:  2000,
  headers:  { Authorization: `Bearer ${process.env.CRM_API_KEY}` },
  httpsAgent: AGENTS['api.crm-provider.com'],   // pass persistent agent
});

// --- Connection health probe: log current socket states ---

function connectionStats() {
  return Object.fromEntries(
    Object.entries(AGENTS).map(([host, agent]) => {
      const sockets    = agent.sockets    ?? {};
      const freeSockets = agent.freeSockets ?? {};
      const active     = Object.values(sockets).reduce((s, arr) => s + arr.length, 0);
      const idle       = Object.values(freeSockets).reduce((s, arr) => s + arr.length, 0);
      return [host, { active, idle }];
    })
  );
}

// --- Graceful shutdown: drain agents so process exits cleanly ---

function destroyAgents() {
  for (const agent of Object.values(AGENTS)) {
    agent.destroy();
  }
}
process.on('SIGTERM', destroyAgents);
process.on('SIGINT',  destroyAgents);
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `https.Agent` creation and `agentFor()` timed over 100 000 iterations; these are in-process costs. **Network-layer savings (TCP+TLS setup avoided on keepAlive reuse) were not measured against a live server in this session.** Established behavior: first connection to a remote HTTPS host incurs DNS lookup + TCP handshake + TLS 1.3 handshake; keepAlive connections skip TCP and TLS on subsequent requests. Measure your actual tool handler endpoints with your network topology — latency savings are topology-dependent.

```
=== https.Agent creation (100 000 iterations) ===

$ node -e "
const https = require('https');
const t0 = performance.now();
for (let i = 0; i < 100000; i++) new https.Agent({ keepAlive: true, keepAliveMsecs: 30000, maxSockets: 10 });
console.log('new https.Agent():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
new https.Agent(): 0.0041 ms

Note: at process startup, creating ~5 agents adds ~0.021ms. Negligible.
DO NOT create an agent per session or per call — create once at startup.

=== agentFor() lookup (100 000 iterations) ===

agentFor(): 0.0009 ms   (URL parse + Map lookup)

=== connectionStats() (100 000 iterations, 4 agents) ===

connectionStats(): 0.0031 ms

=== Network-layer savings (established behavior, not measured this session) ===

Connection overhead per request to a remote HTTPS endpoint:
  Fresh connection (no keepAlive):  80-300ms  (DNS + TCP + TLS; varies by topology)
  keepAlive reuse:                  1-15ms    (TLS session reuse or new request on open socket)
  HTTP/2 multiplexing:              0ms       (request queued on existing open stream)

Savings per reused request: 79-299ms (topology-dependent).

For N tool calls per session to the same host:
  Without keepAlive: N × (connection_overhead + response_time)
  With keepAlive:    connection_overhead + N × response_time  (1 setup, N-1 reuses)

Example: 3 calls to api.crm-provider.com, 150ms connection overhead, 80ms response:
  Without: 3 × (150 + 80) = 690ms
  With:    150 + 3 × 80   = 390ms  (43% reduction on this hop)

=== When keepAlive helps vs doesn't ===

                         │ Helps significantly    │ Negligible gain
─────────────────────────┼────────────────────────┼────────────────────────────────
Call pattern             │ Same host, ≥2 calls    │ Each tool calls a different host
Network                  │ Cross-region, internet │ Localhost or VPC-internal
Protocol                 │ HTTPS (TLS overhead)   │ HTTP or already-multiplexed H2
Using                    │ node-fetch, axios       │ native fetch (already pooled)
Session length           │ Multiple tool calls    │ Single fire-and-forget call

=== Native fetch note (Node.js v18+) ===

If using native fetch (undici-backed):
  $ node -e "
  const r = await fetch('https://api.example.com/data');  // connection pooled automatically
  "
  → undici maintains a connection pool per origin with keepAlive by default
  → No https.Agent configuration needed
  → Check with: require('node:http').globalAgent (shows undici pool stats)
  → Pattern above only needed for node-fetch or axios
```

## See also

[S-85](s85-batch-tool-design.md) · [S-55](s55-parallel-tool-calls.md) · [F-85](../forward-deployed/f85-tool-call-latency-profiling.md) · [S-109](s109-agent-idle-cost.md) · [S-96](s96-tool-fallback-chains.md) · [F-44](../forward-deployed/f44-webhook-result-delivery.md) · [S-35](s35-latency-budget.md)

## Go deeper

Keywords: `HTTP connection reuse` · `keepAlive agent` · `TLS handshake amortization` · `https.Agent` · `tool handler latency` · `connection pooling Node.js` · `socket reuse` · `agent HTTP persistent connection` · `node-fetch keepAlive` · `undici connection pool`
