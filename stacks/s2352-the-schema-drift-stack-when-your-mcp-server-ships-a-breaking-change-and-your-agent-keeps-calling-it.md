# S-2352 · The Schema Drift Stack — When Your MCP Server Ships a Breaking Change and Your Agent Keeps Calling It

Your agent worked perfectly on Monday. By Wednesday it was silently failing — calling tools that no longer existed, passing parameters the server renamed, returning partial payloads the agent then hallucinated around. Your health check passed. Your tracing showed 200s. No alerts fired. This is schema drift: the public contract between your agent and its tools changing without a breaking API version bump, and your entire monitoring stack missing it.

## Forces

- **MCP schemas have no version discipline.** HTTP APIs use semver and return `410 Gone` when contracts break. MCP's `tools/list` endpoint has no versioning — a server can rename a parameter, drop a field, or retire a tool and the agent learns only by failing at the call site, with no signal before the call.
- **The health check lies.** A `tools/list` call returning 200 means "the server is up," not "the schema matches what your agent was tested against." An agent can be calling a tool whose schema changed six versions ago while every uptime monitor shows green.
- **Schema drift is invisible at the agent layer.** The LLM doesn't know the schema changed — it generates arguments against its last-known schema snapshot. When the server rejects the call or returns unexpected output, the agent often retries or fills the gap with confabulation rather than surfacing the mismatch.
- **Four distinct shapes drift takes.** From canonical JSON hashing research (AliveMCP, Jul 2026): renamed required parameters, dropped optional fields, retired tools, and type coercion changes. Each breaks a different part of the agent call chain, and none produce a trace error unless you're inspecting the response schema itself.

## The move

### 1. Snapshot the schema contract at onboarding

Lock the `tools/list` response into a versioned schema file at the point your agent passes integration testing:

```python
import hashlib, json, httpx, os

def snapshot_mcp_schema(base_url: str, output_path: str) -> str:
    """Capture and hash the current MCP tool schema contract."""
    response = httpx.get(f"{base_url}/tools/list", timeout=10)
    response.raise_for_status()
    tools = response.json()

    # Capture a deterministic representation for hashing
    normalized = json.dumps(tools, sort_keys=True, indent=None)
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:12]

    snapshot = {
        "digest": digest,
        "tool_count": len(tools.get("tools", [])),
        "schema": tools,
        # Store canonical JSON for exact comparison, not just digest
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Schema snapshot written: digest={digest}, tools={snapshot['tool_count']}")
    return digest
```

Run this in CI after MCP server deployments, not just at onboarding. The digest becomes your schema SLO.

### 2. Detect drift continuously in production

Compare the live schema against the locked snapshot on every N requests or on a schedule:

```python
def detect_schema_drift(live_url: str, snapshot_path: str) -> list[str]:
    """Compare live MCP schema against locked snapshot. Returns list of violations."""
    with open(snapshot_path) as f:
        baseline = json.load(f)

    live = httpx.get(f"{live_url}/tools/list", timeout=10).json()
    live_digest = hashlib.sha256(
        json.dumps(live, sort_keys=True, indent=None).encode()
    ).hexdigest()[:12]

    if live_digest == baseline["digest"]:
        return []  # No drift

    violations = []

    baseline_tools = {t["name"]: t for t in baseline["schema"].get("tools", [])}
    live_tools = {t["name"]: t for t in live.get("tools", [])}

    # Detect retired tools
    for name in baseline_tools:
        if name not in live_tools:
            violations.append(f"RETIRED: tool '{name}' no longer exists")

    # Detect new tools (warning only, not breaking)
    for name in live_tools:
        if name not in baseline_tools:
            violations.append(f"NEW: tool '{name}' added — verify agent tool selection")

    # Detect schema changes on retained tools
    for name in set(baseline_tools) & set(live_tools):
        b_params = baseline_tools[name].get("inputSchema", {})
        l_params = live_tools[name].get("inputSchema", {})

        if b_params != l_params:
            b_required = set(b_params.get("required", []))
            l_required = set(l_params.get("required", []))
            if l_required - b_required:
                violations.append(
                    f"PARAM_CHANGE: '{name}' added required params: {l_required - b_required}"
                )
            if b_required - l_required:
                violations.append(
                    f"PARAM_CHANGE: '{name}' removed required params: {b_required - l_required}"
                )

    return violations
```

Run this as a lightweight background check every 5 minutes or on each new session start. Alert on any `RETIRED` or `PARAM_CHANGE` finding — these are breaking changes that require an agent retest.

### 3. Catch call-site failures with schema validation

When the schema drifted past your drift detector, the next fallback is catching the mismatch at execution:

```python
from jsonschema import Draft7Validator, ValidationError

def validate_tool_args(tool_name: str, args: dict, snapshot_path: str) -> None:
    """Gate: reject tool calls whose args don't match the locked schema."""
    with open(snapshot_path) as f:
        baseline = json.load(f)

    tools = {t["name"]: t for t in baseline["schema"].get("tools", [])}
    if tool_name not in tools:
        raise ValueError(f"Schema mismatch: tool '{tool_name}' not in locked contract")

    schema = tools[tool_name].get("inputSchema", {})
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(args))
    if errors:
        raise ValidationError(
            f"Argument validation failed for '{tool_name}': "
            f"{[e.message for e in errors]}"
        )
```

This doesn't prevent the drift — it surfaces it as a concrete error instead of silent agent confabulation.

### 4. Treat schema drift as a release event

Drift in an MCP schema is a deployment of your agent's contract system. Pin it into your release process:

| Event | Action |
|-------|--------|
| Schema digest unchanged | Safe to deploy; run smoke test only |
| New tools detected | Review agent tool selection for over-selection |
| Required param added/removed | Full agent regression run required |
| Tool retired | Immediate retest + alert; agent cannot call non-existent tools |
| Type coercion changed | Full regression + LLM-as-judge evaluation |

## Receipt

> Verified 2026-08-08 — Research sources: AliveMCP blog (Jul 2026, 4 shapes of MCP schema drift), LangSight MCP Schema Drift guide (2026), mcp-sentinel GitHub (schema lockfile + drift detection), n1n.ai MCP Production Playbook (schema drift + circuit breaker patterns), AgentCheck arXiv:2607.11098 (schema drift as evaluation fault in MCP benchmark suite), DriftDesk GitHub (schema drift as #1 production failure mode, RL training environment). Real tooling: mcp-sentinel (Wannavf, schema hash lockfile + CLI diff), AgentCheck benchmark (56 fault scenarios including schema drift). Dedup: S-1006 mentions MCP servers "can silently change tool schemas" — this entry is the full stack (detection, validation, governance, response protocol) for schema drift as a distinct architectural failure mode, which S-1006 only flags as a footnote risk.

## See also

- [S-1006 · The Agent Toolbelt Problem](stacks/s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — tool selection, MCP server trust, and schema version risk at the architecture level
- [S-2346 · The Protocol Tax Stack](stacks/s2346-the-protocol-tax-stack-when-mcp-costs-32x-more-than-your-tool-deserves.md) — MCP overhead and efficiency; shares the MCP production stack lineage
- [S-1004 · The Agent Eval Stack](stacks/s1004-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-keeps-breaking.md) — offline eval gaps and why schema changes break benchmarks that never tested the contract layer
