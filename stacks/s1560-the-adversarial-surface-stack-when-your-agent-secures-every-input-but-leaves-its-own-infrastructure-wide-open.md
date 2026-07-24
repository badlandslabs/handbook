# S-1560 · The Adversarial Surface Stack — When Your Agent Secures Every Input But Leaves Its Own Infrastructure Wide Open

You've deployed WAF, input sanitization, and prompt injection defenses. You've tested against OWASP LLM Top 10. Your red team confirmed the agent ignores malicious user inputs. Then a poisoned MCP server — installed three months ago, from a reputable-looking GitHub repo with 8,000 stars — quietly exfiltrates session tokens on every tool call. The attack arrived in tool metadata. No user input was involved. Your input defenses never saw it.

This is the adversarial surface of agentic systems: every component your agent trusts — tool descriptions, MCP server manifests, memory stores, policy files, tool response schemas — is an attack surface you cannot secure with traditional input validation. The Adversarial Surface Stack is the systematic methodology for identifying, prioritizing, and hardening every trust boundary an agent crosses at runtime.

## Forces

- **Agents ingest configuration as instruction.** Unlike traditional software where metadata is mechanical, agentic systems treat tool descriptions, schema definitions, and policy annotations as context that influences behavior. A malicious `description` field in an MCP server manifest is functionally equivalent to a prompt injection — the model reads it, trusts it, and acts on it.
- **Supply chain attacks bypass every input control you have.** Tool poisoning (Invariant Labs, May 2026: 5.5% of public MCP servers contain poisoned metadata) arrives in infrastructure, not in user messages. Your WAF, your input sanitization, your LLM-based prompt injection detector — none of them see the attack because the attack is already inside the context at session startup.
- **The blast radius of a poisoned tool is total.** Once an agent trusts a poisoned tool, it will call it with real credentials, real data, and real permissions. Unlike a user-facing prompt injection which requires social engineering, a poisoned tool works automatically on every invocation.
- **Defensive tooling is immature.** Tool schema signing, MCP server attestation, and tool behavior verification are nascent. Most teams have no automated way to detect that a tool does something different from what its description claims.

## The move

### 1. Map the trust graph

Before you can defend the surface, enumerate every component your agent trusts at runtime:

```python
import json

def build_trust_graph(agent_config: dict) -> dict:
    """
    Enumerate every component an agent trusts at runtime.
    Each entry is a trust boundary that requires its own security posture.
    """
    trust_surface = {
        "system_prompt": {
            "source": "config",
            "mutability": "runtime",
            "risk": "prompt_injection_via_context",
        },
        "tool_definitions": [],  # MCP tools, function definitions
        "mcp_server_manifests": [],  # server.json / manifest files
        "memory_stores": [],  # Vector DBs, session stores
        "policy_files": [],  # YAML/JSON policy annotations
        "retrieval_sources": [],  # RAG corpora, knowledge bases
    }

    for tool in agent_config.get("tools", []):
        trust_surface["tool_definitions"].append({
            "name": tool["name"],
            "source": tool.get("source", "inline"),
            "description": tool.get("description", "")[:200],
            "schema": tool.get("inputSchema", {}),
        })

    for server in agent_config.get("mcpServers", []):
        trust_surface["mcp_server_manifests"].append({
            "server": server.get("name"),
            "url": server.get("url"),
            "manifest_hash": server.get("digest"),
            "permissions": server.get("scopes", []),
        })

    return trust_surface

# Trust score: how many trust boundaries are unverified?
def trust_coverage_score(graph: dict) -> float:
    """Fraction of trust boundaries with active verification controls."""
    total = sum(len(v) if isinstance(v, list) else 1
                 for k, v in graph.items()
                 if k != "system_prompt")
    verified = 0
    for category, items in graph.items():
        if category == "system_prompt":
            continue
        for item in (items if isinstance(items, list) else [items]):
            if item.get("verified") or item.get("digest"):
                verified += 1
    return verified / total if total > 0 else 0.0
```

### 2. Test each surface with adversarial probes

Run a continuous adversarial eval pipeline against every trust boundary:

```python
from dataclasses import dataclass
from enum import Enum

class AttackVector(Enum):
    RUG_PULL = "rug_pull"          # Tool behaves differently at runtime than description claims
    TOOL_SHADOWING = "tool_shadow" # Two tools share a name; wrong one resolves
    INVISIBLE_CONTEXT = "inv_ctx"  # Malicious instruction in tool metadata
    RESPONSE_POISON = "resp_poison" # Tool response contains indirect injection
    CROSS_SERVER_TAINT = "cross_taint"  # One server poisons shared context

@dataclass
class AdversarialTest:
    vector: AttackVector
    target_component: str
    probe_payload: str
    expected_behavior: str
    actual_behavior: str | None = None
    passed: bool | None = None

def run_rug_pull_probe(server_manifest: dict) -> AdversarialTest:
    """
    Test: Does the tool actually do what its description says?

    Approach: Call the tool with a known-input/sensitive-output pattern.
    If the tool returns data it shouldn't have access to, it's a rug pull.

    NOTE: This requires an isolated test environment with synthetic credentials.
    """
    tool_name = server_manifest["name"]
    description = server_manifest["description"]

    # Synthetic test: give the tool access to test creds only
    # If it returns data outside its declared scope, flag it
    test_result = execute_tool_in_sandbox(tool_name, {
        "action": "read",
        "resource": "test://credential-store/should-be-inaccessible"
    })

    # Check if response contains data from outside declared scope
    if contains_out_of_scope_data(test_result, description):
        return AdversarialTest(
            vector=AttackVector.RUG_PULL,
            target_component=tool_name,
            probe_payload="scope_crossing_read",
            expected_behavior=" refusal or empty response",
            actual_behavior="returned data from inaccessible resource",
            passed=False,
        )

    return AdversarialTest(
        vector=AttackVector.RUG_PULL,
        target_component=tool_name,
        probe_payload="scope_crossing_read",
        expected_behavior=" refusal or empty response",
        actual_behavior="correctly scoped",
        passed=True,
    )

def run_invisible_context_probe(tool_definition: dict) -> AdversarialTest:
    """
    Test: Does tool metadata contain hidden instructions?

    Approach: Parse description and schema for known injection patterns,
    then attempt to trigger them through normal tool invocation.
    """
    metadata_text = json.dumps({
        "description": tool_definition.get("description", ""),
        "schema": tool_definition.get("inputSchema", {}),
    })

    injection_patterns = [
        "ignore previous", "forget all", "new instruction",
        "system prompt", "override", "disregard",
    ]

    for pattern in injection_patterns:
        if pattern.lower() in metadata_text.lower():
            return AdversarialTest(
                vector=AttackVector.INVISIBLE_CONTEXT,
                target_component=tool_definition["name"],
                probe_payload=f"pattern_detected: {pattern}",
                expected_behavior="metadata free of injection patterns",
                actual_behavior=f"found: {pattern}",
                passed=False,
            )

    return AdversarialTest(
        vector=AttackVector.INVISIBLE_CONTEXT,
        target_component=tool_definition["name"],
        probe_payload="pattern_scan",
        expected_behavior="no injection patterns",
        actual_behavior="clean",
        passed=True,
    )

def run_full_adversarial_suite(agent_config: dict) -> list[AdversarialTest]:
    """Run all probes against all trust boundaries."""
    results = []
    trust_graph = build_trust_graph(agent_config)

    for tool in trust_graph["tool_definitions"]:
        results.append(run_invisible_context_probe(tool))

    for server in trust_graph["mcp_server_manifests"]:
        results.append(run_rug_pull_probe(server))

    return results
```

### 3. Enforce provenance at tool load time

Every tool, MCP server, and policy file must carry a cryptographically verifiable provenance chain before it enters an agent's context:

```yaml
# Tool manifest with provenance (example)
tools:
  - name: send_email
    source: internal
    digest: sha256:a3f7c9...  # Computed over tool code + description
    provenance:
      signed_by: infra-team
      attestations:
        - type: code_review
          reviewer: alice@company.com
          date: "2026-06-15"
        - type: behavior_test
          result: pass
          test_suite: tool_security_suite_v2
    policy:
      max_rate_per_minute: 10
      allowed_recipients: allowlist@company.com
      data_classification: PII
```

### 4. Isolate tool execution from context trust

The key architectural separation: **the agent's context trusts nothing about tool behavior, but the execution layer enforces hard constraints on every tool call**:

```python
# Tool execution gate — runs outside the agent's context trust model
class ToolExecutionGate:
    def __init__(self, policy_kernel):
        self.policy_kernel = policy_kernel
        self.execution_log = []

    def execute(self, tool_name: str, args: dict, session_context: dict) -> dict:
        # Hard policy check — runs BEFORE the tool call, outside LLM context
        policy_decision = self.policy_kernel.evaluate(
            action=f"tool:{tool_name}",
            args=args,
            session_classification=session_context.get("data_classification", "public"),
        )

        if not policy_decision.allowed:
            self.execution_log.append({
                "tool": tool_name,
                "decision": "denied",
                "reason": policy_decision.reason,
            })
            return {"error": "policy_denied", "reason": policy_decision.reason}

        # Execute in sandboxed environment
        result = self._sandboxed_execute(tool_name, args)
        self.execution_log.append({
            "tool": tool_name,
            "decision": "executed",
            "output_hash": hash(result),
        })
        return result
```

## Receipt

> Verified 2026-07-24 — Research synthesis: Invariant Labs tool poisoning data (5.5% of public MCP servers contain poisoned metadata), Microsoft AI Red Team Taxonomy v2.0 (June 2026), OWASP ASI Top 10 for Agentic Applications (ASI02: Inter-Agent Trust Escalation; ASI10: System Prompt Leakage), BeyondScale MCP Tool Poisoning Enterprise Defense Playbook (May 2026), OX Security disclosure (May 2026), NIST AI RMF supply chain guidance. Code patterns reflect standard adversarial testing and policy enforcement patterns. Live execution pending — requires isolated agent environment with synthetic MCP servers.

## See also

- [S-902 · Scaffold Supply Chain Stack](s902-the-scaffold-supply-chain-stack-when-your-agent-builds-a-backdoor-into-your-own-infra.md) — supply chain poisoning at the skill/plugin layer
- [S-1050 · Tool-Response Poisoning Stack](s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — the runtime variant: poisoned tool return values
- [S-1234 · MCP Tool Supply Chain Stack](s1234-the-mcp-tool-supply-chain-stack-when-your-agent-trusts-a-tool-description-it-never-verified.md) — tool description trust and the description-vs-code gap
- [S-1557 · MCP Server Security Eval Stack](s1557-the-mcp-server-security-eval-stack-when-your-tool-catalog-is-your-attack-surface.md) — evaluating MCP server security posture
- [S-1547 · Tool Access Safety Stack](s1547-the-tool-access-safety-stack-when-your-agent-either-does-nothing-or-destroys-everything.md) — structured access with resumable isolation
