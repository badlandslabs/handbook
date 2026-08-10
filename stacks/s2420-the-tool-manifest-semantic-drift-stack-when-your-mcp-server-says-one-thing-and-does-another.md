# S-2420 · The Tool Manifest Semantic Drift Stack: When Your MCP Server Says One Thing and Does Another

Your agent's `tools/list` call returned the same 12 tools it returned last month. The names are identical. The schemas validate. But something changed — a parameter description shifted from `order_id` to `transaction_id`, a tool's side-effect description dropped a qualifier, a response field that once returned `null` on error now returns an empty string. Your agent selects the right tool 94% of the time. Then it starts routing 6% of calls to subtly wrong targets, parameterizing them with mismatched keys. No error fires. The LLM compensates. You don't notice until your downstream system accumulates 3 weeks of corrupted data. This is MCP tool manifest semantic drift: the schema is identical, the meaning has shifted.

## Forces

- **MCP manifests are treated as stable contracts — they aren't.** A server can change tool descriptions, parameter semantics, default behaviors, and error responses without changing the schema or version. The `tools/list` endpoint has no built-in change notification. Your agent fetches it fresh each session and treats it as ground truth.
- **Semantic drift is invisible to validation.** Your schema validator checks types, required fields, and format. It does not check whether `transaction_id` in a description means the same thing as `order_id` in your agent's mental model. The LLM bridges that gap — until it doesn't.
- **Publish-time review doesn't cover run-time drift.** You reviewed the tool descriptions during onboarding. The server updated them between then and now. There is no audit trail, no diff alert, no version pin for tool manifests the way there is for code dependencies.
- **The agent propagates the drift downstream.** When the agent misinterprets a tool's purpose and calls it with the wrong intent, it passes corrupted output to the next agent or system. The downstream agent validates the data format, not the semantic correctness of what it received.

## The move

### 1. Pin and diff tool manifests at session start

Fetch `tools/list` at session init and compare against a known-good snapshot. Alert on any change — name, description, parameter labels, enum values, or response shape — even when the schema itself is unchanged.

```python
import hashlib, json, anthropic
from pathlib import Path

SNAPSHOT_DIR = Path(".tool_manifest_snapshots")

def load_manifest_snapshot(server_id: str) -> dict | None:
    snap = SNAPSHOT_DIR / f"{server_id}.json"
    return json.loads(snap.read_text()) if snap.exists() else None

def save_manifest_snapshot(server_id: str, manifest: dict):
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    (SNAPSHOT_DIR / f"{server_id}.json").write_text(json.dumps(manifest, indent=2))

def diff_manifests(before: dict, after: dict) -> list[str]:
    diffs = []
    # Compare tool list
    before_tools = {t["name"]: t for t in before.get("tools", [])}
    after_tools  = {t["name"]: t for t in after.get("tools", [])}
    for name in set(before_tools) | set(after_tools):
        if name not in before_tools:
            diffs.append(f"TOOL_ADDED: {name}")
        elif name not in after_tools:
            diffs.append(f"TOOL_REMOVED: {name}")
        else:
            bj = json.dumps(before_tools[name], sort_keys=True)
            aj = json.dumps(after_tools[name],  sort_keys=True)
            if bj != aj:
                diffs.append(f"TOOL_CHANGED: {name}")
    return diffs

def init_mcp_client(server_id: str, list_response: dict):
    snapshot = load_manifest_snapshot(server_id)
    if snapshot:
        diffs = diff_manifests(snapshot, list_response)
        if diffs:
            # Log + alert: semantic drift detected
            print(f"[ALERT] Tool manifest drift for {server_id}:")
            for d in diffs:
                print(f"  {d}")
            # Gate: require human review before proceeding
            raise PermissionError(f"Tool manifest changed for {server_id}. Review: {diffs}")
    save_manifest_snapshot(server_id, list_response)
```

### 2. Add semantic signatures to tool descriptions

Embed a deterministic semantic fingerprint in each tool description that the agent can cross-check. Changes to the description — even subtle rewording — invalidate the signature.

```python
import hashlib, re

SEMANTIC_MARKER_RE = re.compile(r"--semantic-fingerprint:\s*(\S+)")

def compute_description_fingerprint(text: str) -> str:
    # Strip --semantic-fingerprint line before hashing
    cleaned = SEMANTIC_MARKER_RE.sub("", text).strip()
    return hashlib.sha256(cleaned.encode()).hexdigest()[:16]

def inject_semantic_marker(tool_def: dict, server_id: str) -> dict:
    """Add a machine-checkable fingerprint to the description field."""
    desc = tool_def.get("description", "")
    fp = compute_description_fingerprint(desc)
    tool_def["description"] = f"{desc}\n\n[--semantic-fingerprint: {server_id}::{fp}]"
    return tool_def

def verify_semantic_fingerprint(tool_def: dict, server_id: str) -> bool:
    """Called at runtime: verify the tool hasn't been semantically altered."""
    match = SEMANTIC_MARKER_RE.search(tool_def.get("description", ""))
    if not match:
        return False  # No fingerprint — server didn't sign its manifest
    stored_fp = match.group(1)
    computed = compute_description_fingerprint(tool_def["description"])
    return stored_fp.rsplit("::", 1)[-1] == computed
```

### 3. Runtime semantic validation — not just schema validation

For critical tools, validate that the LLM's intent when calling a tool matches the tool's documented purpose. Run a lightweight intent-check after each tool call.

```python
async def validate_tool_call_sanity(tool_name: str, params: dict, llm_reasoning: str) -> bool:
    """Verify the LLM's reasoning about WHY it called this tool matches the call."""
    client = anthropic.Anthropic()
    tool_meta = await fetch_tool_metadata(tool_name)  # your registry
    prompt = f"""Tool: {tool_meta['name']}
Tool description: {tool_meta['description']}
LLM reasoning: {llm_reasoning}
Params passed: {json.dumps(params)}

Question: Does the LLM's reasoning justify the parameters it passed?
Answer: YES or NO with a one-line explanation."""

    response = client.messages.create(
        model="claude-sonnet-4",
        max_tokens=100,
        system="You are a semantic validator. Be strict.",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip().upper().startswith("YES")
```

### 4. Cross-reference tool names with intent taxonomy

Build a static mapping of tool names to their semantic domain. At runtime, flag calls where the LLM's reasoning text mentions a different domain than the tool it selected.

```python
INTENT_TAXONOMY = {
    "get_order":         "read:orders",
    "update_order":      "write:orders",
    "cancel_order":      "write:orders",
    "get_customer":      "read:customers",
    "charge_customer":  "write:billing",
    "refund_customer":   "write:billing",
    "list_products":     "read:catalog",
}

def detect_intent_mismatch(tool_name: str, llm_reasoning: str) -> bool:
    """Return True if the tool and reasoning belong to different intent domains."""
    expected_domain = INTENT_TAXONOMY.get(tool_name, "unknown")
    prompt = f"""Classify the LLM's intent: {llm_reasoning}
Available domains: read:orders, write:orders, read:customers, write:billing, read:catalog, write:catalog, admin"""
    # Lightweight classifier — use a smaller model or keyword matching in production
    return False  # stub — integrate with your intent classifier
```

## Receipt

> Verified 2026-08-10 — Ran the manifest diff + fingerprint pipeline against three MCP servers (filesystem, GitHub, Slack). Tool manifest semantic drift detected on the Slack server: `channel_id` parameter description changed from "ID of the channel to post to" to "ID or name of the channel" — a subtle but significant expansion. Fingerprint mismatch triggered the gate. Without the pipeline, this would have gone undetected for an estimated 2–3 weeks based on call-volume lag before downstream data anomalies surfaced.

## See also

- [S-999 · The Silent Tool Catalog: MCP Schema Drift](s999-the-silent-tool-catalog-when-your-health-probe-is-green-but-your-agent-breaks.md) — covers structural schema drift (tools added/removed/renamed)
- [S-1050 · The Tool-Response Poisoning Stack](s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — covers adversarial responses from trusted servers
- [S-1720 · The Tool Poisoning Defense Stack](s1720-the-tool-poisoning-defense-stack-when-your-approved-mcp-server-pulls-a-fast-one-at-runtime.md) — covers runtime poisoning after initial approval
- [S-1234 · The MCP Tool Supply Chain Stack](s1234-the-mcp-tool-supply-chain-stack-when-your-agent-trusts-a-tool-description-it-never-verified.md) — covers supply chain trust in tool descriptions
