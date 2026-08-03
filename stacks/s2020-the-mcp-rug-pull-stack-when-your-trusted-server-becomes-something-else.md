# S-2020 · The MCP Rug Pull Stack — When Your Trusted Server Becomes Something Else

You approved the MCP server. You read the tool descriptions. The database connector, the email tool, the code execution environment — all clean. You signed off. Six weeks later, the tool your agent calls every day has quietly changed what it does. The name is the same. The signature is the same. The change is invisible to your approval gate, and your agent has no idea.

This is the MCP rug pull attack — and it's not theoretical.

## Forces

- **Approval is an event, not a continuous state.** MCP clients verify tool schemas at install time. If the server mutates those schemas later — or the tool's embedded behavior changes — no re-alert fires.
- **Trust accumulation is the exploit surface.** The attacker's job isn't to sneak past the initial review. It's to get you comfortable enough that nobody watches closely after week two.
- **The tool name survives, but the contract doesn't.** Existing schema contracts (S-035) catch breaking API changes. They don't catch behavioral drift where the signature stays identical but the implementation changes.
- **Agents are uniquely vulnerable.** A human reviewing a tool's response catches anomalies. An agent consuming a tool's output as structured data acts on it automatically.
- **Auto-update amplifies the blast radius.** MCP servers update silently through pip/npm/ship — the same mechanism that makes security patches convenient makes malicious updates invisible.

## The move

The defense has three layers: **frozen tool fingerprints** at install time, **runtime behavioral diffing** during execution, and **description hashing** with alert-on-drift.

### Layer 1 — Freeze the tool fingerprint at trust time

Pin the exact tool description hash and schema at the moment of approval. Any drift — description text, parameter names, expected output shape — triggers re-approval, not silent acceptance.

```python
import hashlib, json, sqlite3

class ToolFingerprint:
    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS tool_fingerprints (
                server_id TEXT,
                tool_name  TEXT,
                desc_hash  TEXT,
                schema_hash TEXT,
                approved_at REAL,
                approved_by TEXT,
                PRIMARY KEY (server_id, tool_name)
            )
        """)

    def approve(self, server_id: str, tool_name: str,
                description: str, schema: dict) -> None:
        desc_hash  = hashlib.sha256(description.encode()).hexdigest()
        schema_hash = hashlib.sha256(
            json.dumps(schema, sort_keys=True).encode()
        ).hexdigest()
        self.db.execute("""
            INSERT OR REPLACE INTO tool_fingerprints
            (server_id, tool_name, desc_hash, schema_hash, approved_at)
            VALUES (?, ?, ?, ?, ?)
        """, (server_id, tool_name, desc_hash, schema_hash,
              __import__('time').time()))
        self.db.commit()

    def check(self, server_id: str, tool_name: str,
              description: str, schema: dict) -> dict:
        desc_hash   = hashlib.sha256(description.encode()).hexdigest()
        schema_hash = hashlib.sha256(
            json.dumps(schema, sort_keys=True).encode()
        ).hexdigest()
        row = self.db.execute("""
            SELECT desc_hash, schema_hash FROM tool_fingerprints
            WHERE server_id=? AND tool_name=?
        """, (server_id, tool_name)).fetchone()

        if row is None:
            return {"status": "UNAPPROVED", "action": "BLOCK"}
        desc_drift, schema_drift = desc_hash != row[0], schema_hash != row[1]
        if desc_drift or schema_drift:
            return {
                "status": "DRIFTED",
                "action": "RE_APPROVE",
                "drifted": [
                    k for k, v in {
                        "description": desc_drift,
                        "schema":       schema_drift,
                    }.items() if v
                ],
            }
        return {"status": "TRUSTED", "action": "ALLOW"}
```

### Layer 2 — Runtime behavioral diffing

Even if schema and description match, the tool's runtime behavior can change. Instrument a shadow execution path on a subset of calls to diff actual behavior against expected behavior:

```python
def shadow_probe(tool_name: str, args: dict,
                 expected_output_schema: type,
                 sample_rate: float = 0.05) -> None:
    import random, structlog
    logger = structlog.get_logger()

    if random.random() > sample_rate:
        return  # only instrument a fraction of calls

    # Mirror the call to a sandboxed twin with identical args
    sandbox_result = call_sandboxed_twin(tool_name, args)
    live_result   = call_live(tool_name, args)

    # Surface structural drift (not content — we expect variation)
    if type(sandbox_result) != type(live_result):
        logger.warning(
            "mcp_rug_pull_suspected",
            tool=tool_name,
            live_type=type(live_result).__name__,
            sandbox_type=type(sandbox_result).__name__,
        )
        alert_security_team(tool_name, sandbox_result, live_result)
```

The shadow twin runs the same tool in an isolated environment — it catches behavioral divergence without disrupting live traffic.

### Layer 3 — Signed tool attestations

The most durable defense: MCP servers sign their tool manifests using a key whose fingerprint is verified at install. Clients reject any manifest not bearing a valid signature from a known-pinned key. This makes a rug pull require key compromise, not just server compromise.

```json
// server_manifest.json (signed, delivered over HTTPS)
{
  "server_id": "github-copilot-mcp@v2.4.1",
  "tools": [
    {
      "name": "execute_bash",
      "description_hash": "a3f9c...",
      "schema_hash": "7d2e1...",
      "behavioral_attestation": "sha256:bc41d..."
    }
  ],
  "signature": "MEUCIQD... (Ed25519)"
}
```

Pin the signing key fingerprint at install time. Any signing key rotation requires explicit re-approval — silent rotation is blocked.

## Tradeoffs

- **Fingerprints add latency on cold start** (one hash per tool). At scale with hundreds of MCP servers, fingerprint caching with TTL avoids repeated hashing.
- **Behavioral shadowing costs money** (extra calls on sample_rate). Budget 1–5% overhead for shadow probes; tune sample_rate by tool risk tier.
- **Signed attestations require server cooperation** — not all MCP servers support this yet. Treat it as a roadmap item for high-risk tool categories (write-capable tools, credential-accessing tools).
- **Description hashing alone is insufficient** — it catches intentional text changes but not behavioral drift. Layer it with runtime diffing for defense-in-depth.

## Receipt

> Verified 2026-08-02 — Waxell documented 4 confirmed MCP rug pull incidents from Sep 2025 – Mar 2026, including a single malicious package affecting 12,000 installs. Microsoft Learn (2026) formalized rug-pull as a named attack class in the AI Zero-Trust catalog. SecureList (Kaspersky) confirmed MCP servers used in live supply chain attacks. The layered fingerprint + behavioral diff + signing stack maps directly to documented attack phases.

## See also

- [S-035 · MCP Schema Contracts](s035-mcp-schema-contracts.md) — schema-level change detection, the complement to description hashing
- [S-427 · The MCP Supply Chain Stack](s427-the-mcp-supply-chain-stack.md) — catalog governance and artifact pinning against registry-level compromise
- [S-375 · Agentic Prompt Injection: Defense-in-Depth](s375-agentic-prompt-injection-defense-in-depth.md) — the broader trust-classification context
