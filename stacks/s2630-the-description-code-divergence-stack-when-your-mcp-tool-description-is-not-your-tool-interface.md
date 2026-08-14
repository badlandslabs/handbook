# [S-2630] · The Description-Code Divergence Stack

> When your MCP tool says one thing and does another — and your agent decides based on the description alone.

## Situation

You are building an agentic system on MCP. You audited every tool description, wrote security policies for dangerous tools, and gated high-privilege operations behind approval gates. Then a tool marked "Get weather for a city" turns out to silently persist the queried city to a user profile, update a recommendation engine, and emit analytics events. None of this is in the description. Your agent had no idea. Your audit had no idea. The description was honest as far as the schema spec required — and completely misleading to anything that reasoned about the tool's actual behavior.

This is **Description-Code Inconsistency (DCI)** — a structural vulnerability in the MCP ecosystem where tool descriptions do not faithfully represent what the underlying code actually does.

## Forces

- MCP exposes natural-language tool descriptions to the LLM as the primary basis for tool-selection and safety decisions — but provides no mechanism to verify description accuracy against implementation
- DCI affects **9.93% of all MCP tools** and **35% of MCP servers** (Fudan University, arXiv:2606.04769, June 2026) — one in ten tools in your catalog may be lying to your agent
- DCI is distinct from adversarial tool poisoning: it occurs in benign, production-deployed servers where developers simply omitted or obscured implementation details from the description
- The attack surface DCI opens is invisible to any defense that operates at the output layer — it operates upstream, at the tool-selection decision
- A DCI tool can be trivially promoted from "misleading" to "malicious" if an attacker identifies it and modifies the code without touching the benign description

## The move

### The DCI taxonomy

DCI splits into two axes:

**Functionality inconsistencies** — claimed capabilities ≠ actual capabilities:
- **Underclaiming**: tool does more than described (overprivileged, invisible capability)
- **Overclaiming**: tool does less than described (underdelivers, silent failure)
- **Mismatched parameters**: description references parameters the code does not use, or vice versa

**Undeclared side effects** — environmental changes not disclosed in description:
- **State mutation**: writes to databases, user profiles, caches, logs
- **Data exfiltration**: sends data to external endpoints, analytics services, recommendation engines
- **Privilege escalation**: uses ambient credentials to perform actions beyond the described scope

### The formal definition

```
DCI(T) := (Φ_claim ≠ Φ_actual) ∨ (Ψ_actual ⊈ Ψ_claim)
```

Where Φ is capability and Ψ is side-effect. A tool is DCI-free only when both the described functionality matches the implementation *and* every side-effect is documented.

### Detection with DCIChecker

Fudan University (Shi et al., 2026) built **DCIChecker** — a framework combining structure-aware static analysis with a Direct-Reverse-Arbitration prompting method to cross-validate descriptions against code:

```
git clone https://github.com/fudan-mcp/dci-checker
cd dci-checker && pip install -r requirements.txt
python dcichecker.py --server ./my-mcp-server --output report.json
```

The tool analyzes description-code pairs and produces an inconsistency report with:
- Per-tool DCI score
- Inconsistency type (functionality vs. side-effect axis)
- Severity rating

### Defense layers

**Layer 1 — Static verification (pre-registration)**:
```python
from dcichecker import DCIValidator

validator = DCIValidator(policy={
    "allow_state_mutation": False,
    "allow_external_network": False,
    "require_side_effect_documentation": True
})

for tool in mcp_server.list_tools():
    result = validator.verify(tool)
    if result.has_dci:
        raise DCIViolation(f"Tool {tool.name}: {result.summary}")
```

**Layer 2 — Behavioral sandbox (runtime)**:
- Run each new tool in an ephemeral sandbox with network egress monitoring
- Capture all state writes and outbound network calls
- Compare observed behavior against the tool's declared effects
- Flag any undeclared write or outbound connection

**Layer 3 — First-invoke approval with DCI scan**:
```bash
mcp-analyze --server ./untrusted-server --check dci,tdp,policy
# Output:
# Tool: get_weather — DCI: side-effect mutation (user_profile['last_city'])
# Tool: send_email  — DCI: undeclared network (analytics.endpoint.com)
# Decision: BLOCK both tools pending review
```

**Layer 4 — Supply chain provenance**:
- Require SBOM for third-party MCP servers
- Track tool description history (git blame on tool schemas)
- Alert on any description-only change (code untouched)

### The detection gap

```
OWASP MCP Top-10 (MCP03) covers TOOL POISONING — adversarial injection into descriptions
DCI covers DESCRIPTION-CODE GAP — the description was never accurate in the first place

Both create the same outcome: agent trusts tool description → agent makes wrong decision
Both are invisible to output-layer defenses (guardrails, approval gates, log inspection)
```

The critical insight: even a *benign* DCI tool becomes an exploitable weakness if an attacker identifies it, because the code can be modified without touching the description.

## Receipt

> Receipt pending — [2026-08-14]
> Research: arXiv:2606.04769 (Fudan University, June 2026) — DCIChecker paper; VERIK journal summary; Hermes Agent GitHub issue #16462 implementing DCI checks; promptfoo.dev LLM security database (LMVD-ID: 5b809f07, Feb 2026); OWASP MCP Top-10. Not yet validated against local MCP server scan.

## See also

- **[S-078] MCP Tool Description Poisoning** — adversarial injection into tool descriptions (OWASP MCP Top-10, CVE-2026-33032)
- **[S-035] MCP Schema Contracts** — schema drift, versioning, and the tool-contract boundary
- **[S-427] MCP Schema Contracts Stack** — the tool-schema as the security boundary
- **[S-2603] The Agentic Output Validation Stack** — type coercion, schema mismatch, downstream failure from bad tool outputs
- **[S-2512] Production Agent Observability Floor** — baseline patterns for agent behavior verification
