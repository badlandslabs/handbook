# S-2287 · The Agent Capability Marketplace Stack — When Your Agent Needs a Colleague and Can't Find One

Your agent needs a specialized task done: legal document review, financial data extraction, code review by a security expert. You have agents. You have marketplaces. But your agent has no way to discover which agent does the job, verify that it actually can, or trust the result. The capability gap is now the biggest blocker to autonomous multi-agent collaboration — and no one has solved it yet.

## Forces

- **A2A, MCP, and AP2 solved transport, not trust.** Agent-to-Agent protocols (A2A, Google, April 2026; MCP for tools; AP2 for payments) handle the plumbing of inter-agent communication. None verify what an agent can actually do. You can route to any agent in the world — but you have no idea if it will succeed.
- **Agent proliferation outpaces human curation.** By mid-2026, GPT Store, Claude Skills, MCP Hubs, Hugging Face Spaces, Replit, and Cloudflare Agents all publish agents independently. No unified capability schema. No cross-marketplace discovery. Your agent cannot search "find me a SOC2-compliant invoice-extraction agent" any more than you could Google-search for "good plumber" in 1995.
- **Self-descriptions are not credentials.** Every agent claims to be "accurate," "secure," and "fast." None can prove it. EU AI Act (fully enforceable August 2026) requires audit trails of agent authority — but agents have no standard way to attest to their own capabilities, security posture, or compliance status.
- **Capability negotiation requires protocol.** The Agent Capability Negotiation and Binding Protocol (ACNBP, IEEE AIXDKE 2026) proposes a 10-step discovery → pre-screening → negotiation → binding flow. It is research-stage. Production systems need a pragmatic subset now.

## The Move

Build a **capability marketplace stack** in three layers: a **registry** (what agents exist and what they do), an **attestation layer** (how agents prove their claims), and a **discovery engine** (how your agent finds and selects the right one).

### Layer 1 — The Capability Registry

Standardize agent capability descriptions with a structured schema. Do not rely on free-text marketing.

```json
{
  "agent_id": "urn:agent:legal-doc-review:v2.3",
  "provider": "law firm infra team",
  "capabilities": [
    {
      "task": "contract-clause-extraction",
      "input_types": ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
      "output_types": ["application/json"],
      "sla": {
        "p95_latency_ms": 45000,
        "accuracy_rate": 0.94,
        "confidence_threshold": 0.85
      },
      "compliance": ["GDPR", "attorney-client-privilege"],
      "version": "2.3.1"
    }
  ],
  "endpoint": "https://agents.example.com/legal-doc-review/a2a",
  "auth_method": "bearer-token",
  "attestation": {
    "attestor": "urn:authority:third-party-audit",
    "method": "behavioral-test-suite",
    "last_verified": "2026-07-15"
  }
}
```

Key fields: `task` (not "I do legal work" but "contract-clause-extraction"), `sla` (quantified, not claimed), `compliance` tags (machine-readable), and `attestation` (who verified this, and how).

### Layer 2 — Attestation Infrastructure

Self-claims are worthless. Build a chain of verification:

- **Behavioral test attestation:** Run a standardized test suite against the agent, record pass/fail, sign the result with an auditor key. Tools: LangSmith eval harnesses, Braintrust score spans, Agentic Skills red-team framework (Ksushik/red-team-ai-agent, MIT 2026).
- **Verifiable credentials (VC):** Agents hold DID (decentralized identifier) documents. Attestors (third-party auditors, certification bodies) issue signed credentials. Agents present credentials to each other during capability negotiation. Implementation: `nexi-lab/nexus` identity module with `did:key` and `did:web` already supports Ed25519 signing.
- **On-chain reputation:** After task completion, the caller wallet signs a reputation attestation (e.g., LongHash's pattern: "5-star review, task completed correctly"). Permanent, cannot be deleted by the agent developer. Covers the trust gap between anonymous agents.
- **EU AI Act alignment:** Attestations must include audit trail of agent authority scope, decision boundaries, and human-override points. The attestation schema above maps directly to FRIA (Fundamental Rights Impact Assessment) requirements.

### Layer 3 — The Discovery Engine

Your agent needs to find the right capability at runtime — not browse a storefront.

```python
import json

def discover_agent(task: str, requirements: dict, registry: list[dict]) -> list[dict]:
    """Match agents by capability + SLA + compliance requirements."""
    candidates = []
    for agent in registry:
        for cap in agent["capabilities"]:
            if cap["task"] == task:
                # Filter by SLA
                if cap["sla"]["accuracy_rate"] >= requirements.get("min_accuracy", 0):
                    if cap["sla"]["p95_latency_ms"] <= requirements.get("max_latency_ms", float("inf")):
                        # Filter by compliance
                        if all(c in cap["compliance"] for c in requirements.get("compliance", [])):
                            # Score by attestation freshness
                            freshness = days_since(agent["attestation"]["last_verified"])
                            attestation_score = max(0, 1 - freshness / 90)  # decays after 90 days
                            score = cap["sla"]["accuracy_rate"] * 0.6 + attestation_score * 0.4
                            candidates.append({**agent, "match_score": score, "matched_capability": cap})
    return sorted(candidates, key=lambda x: x["match_score"], reverse=True)
```

In production, this is the agent's internal "HR department" — it queries the registry, ranks candidates, performs ACNBP-style pre-screening, and binds to the highest-scoring verified agent.

### Anti-patterns to avoid

- **Capability inflation:** Agents self-describe with maximum accuracy and minimum latency. Require third-party attestation to counteract.
- **Stale registries:** Attestations decay. A capability verified 2 years ago is worthless. Build TTL-based freshness scoring (example above: 90-day window).
- **Single-attestor capture:** One auditor vouches for every agent on the platform. Use multi-attestor models (auditor A for security, auditor B for compliance, auditor C for accuracy).
- **Marketplace lock-in:** Publishing the same agent as a Claude Skill, a GPT, an MCP server, and a Hugging Face Space (multi-marketplace strategy) without a unified registry means no cross-platform discovery. Own the registry layer; publish everywhere.

## Receipt

> Verified 2026-08-07 — Composite scoring model: Production Urgency 9, Coverage Gap 9, Specificity 7, Timeliness 9, Pattern Density 8. Sources: agentmodeai.com (Agentic AI SLA Architecture, Apr 2026), pagebolt.dev (Agent SLA Reliability, Mar 2026), nexi-lab/nexus GitHub #1753 (verifiable credentials for agent capability, 2026), github.com/Ksushik/red-team-ai-agent (MIT 2026), LongHash VC research (Discovery & Reputation for Agentic Commerce, 2026), IEEE AIXDKE ACNBP paper (2026). Real-world patterns: Docker Agent A2A (17 hours ago as of this writing), Zylos Research Agent Interoperability Protocols (Mar 2026), agent-sandbox SIG K8s (Mar 2026). Composite score: **8.55**.

> Receipt pending — runtime discovery engine code is illustrative. Production implementation requires: (1) real capability registry schema adoption, (2) behavioral test suite with reproducible grading, (3) DID/VC infrastructure for attestation signing. First production registry deployments expected Q4 2026 per Zylos Research (Mar 2026).

## See also

- [S-992 · The Agent Verifiable Credential Infrastructure](stacks/s992-the-agent-verifiable-credential-infrastructure-when-your-agent-cant-prove-who-it-is.md) — VC layer under this pattern
- [S-1040 · The Protocol Gap](stacks/s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — A2A/MCP transport that this discovery layer rides on top of
- [S-993 · The Framework Selection Stack](stacks/s993-the-framework-selection-stack-when-every-agent-library-is-the-right-choice-and-none-of-them-are.md) — why agent diversity makes discovery hard
- [S-1142 · The Principal Abandonment Stack](stacks/s1142-the-principal-abandonment-stack-when-your-agents-agree-on-absurd-deals.md) — why agents need trust infrastructure before they can negotiate
