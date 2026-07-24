# S-1552 · The AI-BOM Stack — When Your Agent Supply Chain Has No Ingredient Label

Your agent is running in production. A CVE drops in an open-source embedding model your team pulled six months ago. The security team asks: which agents use it? Nobody knows — it's in a notebook one engineer abandoned. A regulator asks: what training data shaped the model your customer-facing agent runs on? Your answer is a shrug. You're shipping AI systems built from components nobody has inventoried, and the gap between "what we think is running" and "what is actually running" is not a minor inconvenience — it is an existential compliance, security, and reliability risk.

The AI Bill of Materials (AI-BOM) is the structured inventory that closes this gap: a machine-readable record of every model, dataset, tool, MCP server, prompt template, guardrail, and agent in your supply chain. It is the ingredient label for AI systems, and like any supply chain artifact, it only works if it is continuously maintained — not generated once and forgotten.

## Forces

- **AI sprawl outpaces inventory velocity.** 83% of enterprises are deploying AI agents (Northflank, 2026), but most lack a single registry of what those agents actually use. Components are added, forked, upgraded, and abandoned faster than any manual tracking process can follow.
- **The AI supply chain has more attack surface than software's.** Unlike code dependencies, AI-BOM components include non-deterministic elements: model weights (which can be fine-tuned or poisoned), training datasets (with provenance that is often unknown), and dynamic tool configurations that execute at runtime.
- **Traditional SBOMs miss AI-specific components.** Software Bills of Materials capture code libraries and packages. They do not capture which LLM version is running, what embedding model is used for retrieval, which MCP server provides a tool, or what prompt template governs agent behavior — the AI-specific attack surface that is often the most consequential.
- **Regulatory requirements now mandate it.** The EU AI Act (Article 71) requires registration of AI systems. NIST AI RMF and ISO/IEC 42001 both require system inventory as a foundational governance activity. If you cannot list what you run, you cannot comply.
- **You cannot secure what you cannot see.** Vulnerability response, incident investigation, and compliance auditing all require answering "which systems use this component?" — a question that is unanswerable without an inventory.

## The move

**1. Define the AI-BOM scope for your organization.**

An AI-BOM captures five layers:

| Layer | Examples | What it reveals |
|-------|----------|----------------|
| **Models** | LLM provider + version, embedding model, fine-tune base | Which model shapes outputs; version drift risk |
| **Data** | Training datasets, RAG corpora, grounding data | Data provenance; PII risk; staleness |
| **Tools / MCP** | MCP servers, tool definitions, API integrations | Attack surface; trust assumptions |
| **Prompts / Guardrails** | System prompts, safety guardrails, routing policies | Behavioral boundaries; jailbreak exposure |
| **Agents** | Agent configurations, delegation chains, autonomy tiers | Decision authority; handoff complexity |

**2. Generate the AI-BOM automatically — not manually.**

Manual inventories decay instantly. Tools like **Cisco AI BOM** (source-code + container + cloud scanning), **AIBOM.dev** (bulk GitHub scanning with drift detection), **OWASP AIBOM Generator** (CycloneDX/SPDX output for Hugging Face models), and **DefenseClaw AI BoM** (MCP configurations, agent capability mappings) can produce machine-readable inventories at scale. Run them in CI/CD and on a schedule — not just at onboarding.

```bash
# Cisco AI BOM — scan codebase for AI components
pip install aibom
aibom scan --lang python,typescript --output cyclonedx.json

# AIBOM.dev — bulk GitHub org scan
npx aibom scan-github --org your-org --token $GITHUB_TOKEN --drift

# OWASP AIBOM Generator — per-model, CycloneDX format
# Available at: https://huggingface.co/spaces/GenAISecurityProject/OWASP-AIBOM-Generator
```

**3. Close the drift gap with continuous drift detection.**

Agents are updated, tools are swapped, prompts are changed. An AI-BOM generated once is already stale. Implement drift detection that re-scans on: (a) any change to agent configuration files, (b) any deployment event, (c) a weekly scheduled baseline. The diff between "last known AI-BOM" and "current AI-BOM" is your change log for AI supply chain events.

**4. Gate CI/CD on AI-BOM completeness and risk thresholds.**

Treat AI-BOM generation like test coverage: fail the build if the AI-BOM is incomplete (missing required fields) or if new critical/high risk findings appear without an explicit override. This closes the loop between supply chain discovery and security response.

```yaml
# Example: AI-BOM CI gate
- step: generate-aibom
  run: aibom scan --lang python,typescript --output aibom.json
- step: check-completeness
  run: aibom validate --required-fields model_version,provider,mcp_servers
- step: risk-gate
  run: aibom gate --critical-threshold=0 --fail-on-new-critical
```

**5. Map AI-BOM to your incident response and compliance workflows.**

When a CVE drops (model, framework, or MCP server), the AI-BOM answers "which agents are affected?" in seconds — not days. When a regulator asks for your AI system inventory, the AI-BOM is the artifact. When you onboard a new team, the AI-BOM is their map.

```python
# Example: AI-BOM-driven incident response
def affected_agents(model_version: str, bom: dict) -> list[str]:
    """Return agent IDs using a specific model version."""
    return [
        entry["agent_id"]
        for entry in bom["agents"]
        if any(
            m["version"] == model_version
            for m in entry.get("models", [])
        )
    ]
```

**6. Align AI-BOM completeness with your regulatory context.**

| Framework | Required AI-BOM fields |
|-----------|----------------------|
| EU AI Act Art. 71 | Model ID, provider, intended use, risk category |
| NIST AI RMF | Model name, version, data provenance, owner |
| ISO/IEC 42001 | System description, inputs, outputs, boundaries |
| OWASP LLM Top 10 | Model, tools, prompts, guardrails, data sources |

Start with what your regulators require. Expand to what your risk posture demands.

## Receipt

> Verified 2026-07-23 — Research synthesis from: Cisco AI BOM (cisco-ai-defense/aibom, Apache-2.0, 98 stars, 77 commits), OWASP AIBOM Generator (genai.owasp.org, Dec 2025), AIBOM.dev bulk GitHub scanning, Cycode State of Production AI 2026, Wiz AI-BOM Academy, Enzai AI System Inventory for Governance (Jul 2026), Northflank AI Agent Sandbox Guide (2026). Core finding: AI-BOM generation is now tooling-available (open-source + commercial), regulatory-mandated, and operationally tractable. The remaining gap is adoption — most organizations are not running AI-BOM scans in CI or on a schedule.

## See also

- [S-1196 · The Agent Catalog Plane](s1196-the-agent-catalog-plane-when-you-cant-govern-discover-or-trust-an-agent-you-dont-know-exists.md) — discovery layer; complements AI-BOM's supply-chain depth
- [S-941 · The Agent Audit Chain](s941-the-agent-audit-chain-stack-when-every-agent-decision-needs-a-paper-trail.md) — audit trail; AI-BOM provides the component map that audit chains annotate
- [S-1006 · The Agent Toolbelt Problem](s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — tool selection; AI-BOM captures which toolbelt is actually deployed vs. intended
