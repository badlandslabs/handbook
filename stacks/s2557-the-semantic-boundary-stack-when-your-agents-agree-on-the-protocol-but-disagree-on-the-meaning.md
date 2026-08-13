# S-2557 · The Semantic Boundary Stack — When Your Agents Agree on the Protocol but Disagree on the Meaning

Your MCP and A2A stacks are clean. The tool definitions are consistent. The agent cards are published. The protocol handshake completes successfully. And yet your multi-agent pipeline produces contradictory outputs, duplicated work, and silent data loss. The agents are speaking the same language — they simply don't agree on what the words mean. This is the semantic boundary problem: the gap between protocol interoperability and semantic consistency. The 2026 enterprise multi-agent stack has three pillars — MCP for tool access, A2A for inter-agent coordination, and a governed context layer for shared meaning. Most teams have built two of the three.

## Forces

- **Protocols standardize communication syntax, not domain semantics.** MCP and A2A define message formats, transport, authentication, and discovery. They say nothing about what "customer," "order," "approved," or "priority=high" actually mean to each agent. Two agents can speak perfectly valid protocol and operate on fundamentally incompatible interpretations of the same concept.
- **Agents learn from context, not from schemas.** Unlike traditional software systems where data models are enforced at the type or database layer, LLM-based agents construct their understanding of domain concepts from conversation context, tool descriptions, and retrieved documents. Without a governed semantic layer, each agent develops its own implicit ontology — and they diverge silently as context changes.
- **The seam between agents is where semantic drift compounds.** A planning agent interprets "escalate to human review" as "pause and notify the supervisor." A routing agent interprets it as "requeue with priority flag." Both are reasonable. Neither is wrong by their own context. But the handoff fails: the routing agent never pauses, the planning agent never knows, and the case falls through.
- **Schema consistency is not semantic consistency.** Two fields named `customer_id` with the same type and format can represent different concepts: one agent's `customer_id` is a CRM primary key, another's is a billing account number. They look identical in the protocol payload and diverge silently in the business logic.

## The Move

Build an explicit **semantic boundary layer** between agents — a governed schema-plus-definition registry that agents consult before and after every inter-agent handoff. This is not a shared database. It is a *controlled vocabulary with embedded definitions* that lives between the protocol layer and the agent's reasoning context.

**The three components:**

**1. Semantic Contract Registry.** A versioned registry of domain concepts — `customer`, `order`, `task`, `escalation` — with human-readable definitions, examples, canonical value sets, and allowed aliases. Think of it as a shared glossary that agents can query at runtime, not a document they read once at onboarding. Treat it like an API schema with intent, not just format.

```python
# Semantic Contract Registry — simplified concept definition
from dataclasses import dataclass
from typing import Optional
import hashlib

@dataclass
class SemanticConcept:
    name: str                           # canonical name: "customer"
    version: str                        # "v3.2"
    definition: str                     # "An individual or organization with an
                                       # active billing account in the CRM"
    canonical_type: str                # "CRM_Account_Reference"
    examples: list[str]                 # ["CUST-88321-AX", "CUST-00442-R9"]
    aliases: list[str]                   # ["account_holder", "client", "billing_entity"]
    boundary_rules: list[str]           # ["never use display_name as identifier"]
    contract_hash: str                  # SHA-256 of definition + type + rules

# Agent queries the registry before sending a cross-agent payload
async def validate_handoff(
    payload: dict,
    concept_name: str,
    sender_agent: str,
    recipient_agent: str
) -> dict:
    concept = registry.get(concept_name)
    violations = []

    for field, value in payload.items():
        # Check canonical type compliance
        if field in concept.canonical_type:
            continue  # type-valid

        # Check if field is a recognized alias
        if field in concept.aliases:
            # Normalize to canonical name in the payload
            payload[concept.canonical_type] = payload.pop(field)
            continue

        violations.append(
            f"Field '{field}' not in concept '{concept_name}'. "
            f"Known fields: {[concept.canonical_type] + concept.aliases}"
        )

    # Verify semantic integrity of the handoff
    handoff_manifest = {
        "sender": sender_agent,
        "recipient": recipient_agent,
        "concept": concept_name,
        "version": concept.version,
        "contract_hash": concept.contract_hash,
        "payload_keys": list(payload.keys()),
    }
    await audit_log.emit("semantic_handoff", handoff_manifest)

    if violations:
        raise SemanticBoundaryViolation(
            f"Handoff from {sender_agent} to {recipient_agent} "
            f"violates semantic contract '{concept_name}': {violations}"
        )

    return payload
```

**2. Semantic Handoff Manifest.** Every inter-agent message includes a structured manifest — `{concept, version, contract_hash, sender, recipient, timestamp}` — that the receiving agent validates against the registry before processing. If the `contract_hash` doesn't match the current canonical definition, the agent rejects or flags the handoff rather than proceeding on ambiguous context. This prevents silent semantic drift across agent versions.

**3. Shared Concept Context Injection.** At the start of each agent session, inject the relevant domain concept definitions directly into the agent's system context — not as prose, but as structured definitions the agent can reference during tool selection and output generation. This ensures agents start from the same semantic baseline, not from whatever context they last operated in.

**The governance rule:** When two agents need to coordinate, they must agree on the semantic contract *before* the protocol handshake. The protocol says "can I reach you?" The semantic layer says "do we mean the same thing?"

## Receipt

> Verified 2026-08-13 — Pattern derived from BabyBots "A2A Protocol in 2026" (Aug 2026), Zylos Research "A2A and MCP Interoperability" (Feb 2026), RetailNews.ai "Protocol War: MCP, A2A, UCP, AP2" (Aug 2026), and Microsoft Learn "Multi-agent patterns" guidance. The "two-layer stack (MCP + A2A) without governed context produces inconsistent results" finding is documented by BabyBots as the primary failure mode in enterprise multi-agent deployments. The Semantic Boundary Stack operationalizes this finding as a three-component architectural pattern.

## See also

- [S-2467 · The MCP Server Architecture Stack](s2467-the-mcp-server-architecture-stack-when-the-protocol-standardized-the-connection-but-not-the-server-design.md) — protocol-level design decisions that shape the tool layer
- [S-2470 · The A2A Protocol Trust Stack](s2470-the-a2a-protocol-trust-stack-when-the-protocol-authenticates-the-session-but-not-the-agent.md) — trust and identity at the protocol seam
- [S-2556 · The Three-Tier Memory Stack](s2556-the-three-tier-memory-stack-when-your-agent-forgets-everything-between-sessions.md) — memory architecture that complements semantic consistency
