# S-2066 · The Grounding Layer Stack — When Your Agent Knows the Answer But Gets the Fact Wrong

Your agent outputs a confident, well-reasoned response. It cites a specific price, a date, a policy number. The user acts on it. Three hours later, the number was wrong. The agent wasn't lying — it genuinely believed it. The error came from no single bad step. It came from the gap between what the model generates and what the world actually contains. This is the grounding problem, and it is not a model defect. It is a **production architecture problem** that requires a production architecture solution.

## Forces

- **The model cannot know what it has not seen in context.** LLMs generate the most probable continuation of their training data. In production, that includes hallucinated prices, outdated policies, fictional internal documents, and plausible-sounding system names. Adding more reasoning tokens makes the hallucination sound more confident, not more accurate.
- **RAG retrieves chunks, not facts.** Vector similarity search finds semantically related text — not verified ground truth. The retriever has no mechanism to confirm whether the retrieved chunk actually applies to the current query. Confident retrieval of low-quality chunks is indistinguishable from confident retrieval of high-quality ones at the embedding level.
- **Grounding costs are hidden until they surface as incidents.** A pricing error, a wrong medical contraindication, a fictional compliance deadline — these surface as user-facing incidents, not as "grounding failures." Teams have no instrument for detecting them in the inference loop.
- **Native grounding locks you to one provider.** Vendor-native retrieval (Perplexity, ChatGPT Search, Gemini Grounding) couples grounding quality to model selection, pricing, and latency. You cannot swap the grounding provider without swapping the model.
- **Schema-grounding is a separate problem from factual-grounding.** Even when facts are correct, agents sometimes apply the wrong schema — using a deprecated field name, routing to the wrong endpoint, generating a `user_id` when the system expects `uid`. Both hallucination types cause production failures with different mitigation paths.

## The move

Treat grounding as a **first-class infrastructure layer** with three sub-components: factual grounding, schema grounding, and uncertainty-aware routing.

### Factual Grounding — The Retrieval Decoupling Pattern

The core insight from DoorDash's DSG architecture (arXiv:2606.18947, Jun 2026): **decouple retrieval from reasoning**. Instead of relying on model-native search, route queries through an independent grounding service that returns structured, attributed evidence before generation.

```
High-level architecture:

query → grounding_router
          ├─ factual_ground(query) → evidence_set (attributed, scored)
          ├─ schema_bind(query, entity) → schema_constraints
          └─ uncertainty_score(query, evidence) → confidence_level

evidence_set + schema_constraints → grounded_context
grounded_context + confidence_level → routing_decision
  ├─ confidence >= threshold → generate(response, grounded_context)
  ├─ confidence medium → generate_with_citations(response, evidence_set)
  └─ confidence < threshold → escalate | defer | flag
```

Key principles:
- Grounding evidence must carry **source attribution** — not just "this fact appears in document X" but "this fact appears in document X, field Y, as of date Z"
- **Temporal validity** must be checked: ground the entity's timestamp, not just its content
- Grounding should produce a **structured constraint set**, not a prose context window

### Schema Grounding — The Constraint Binding Pattern

Schema hallucination is harder to catch than factual hallucination because the agent's output is well-formed JSON that passes validation — it just uses the wrong keys. The solution is **pre-generation schema binding**:

```python
import json, jsonschema

def schema_bind(query: str, entity: str, schema_registry: dict) -> dict:
    """Return the active schema for an entity, not just any matching schema."""
    # Identify the canonical schema version for this entity
    # based on deployment date, region, and product tier
    active_schema = schema_registry.get_active(entity)
    
    # Extract field-level constraints relevant to the current query
    query_fields = extract_fields_from_query(query)
    
    return {
        "schema": active_schema,
        "constraints": {
            f.name: {
                "type": f.type,
                "enum": f.enum,          # exhaustive list prevents "plausible value"
                "deprecated": f.deprecated,
                "replacement": f.replacement  # maps deprecated → current field
            }
            for f in active_schema.fields
            if f.name in query_fields
        },
        "bindings": {f: f.replacement for f in active_schema.deprecated}
    }

def grounded_generate(query, agent, schema_registry):
    constraints = schema_bind(query, entity_from(query), schema_registry)
    
    # Rewrite the agent's tool-call schema to use active field names
    active_tool_schema = rewrite_schema(constraints["schema"], constraints["bindings"])
    
    # Generate with constraint injection
    response = agent.generate(
        query,
        schema=active_tool_schema,
        inject_constraints=constraints["constraints"]
    )
    return response
```

The critical addition: **deprecated field mapping** is injected into the system prompt as a constraint, not as a reminder. The model must not merely "know" about the new field name — it must have its generation space actively constrained.

### Uncertainty-Aware Routing — The Confidence Gate

Not every query needs the same grounding depth. A query about "the weather in Tokyo" needs a weather API call. A query about "your refund policy" needs document grounding with temporal validation. A query about "my order #12345" needs live system grounding.

```python
def uncertainty_route(query: str, grounding: GroundingService) -> Route:
    plan = grounding.estimate_plan(query)  # returns plan complexity + grounding needs
    
    if plan.type == "fact_lookup":
        # Live data — always ground
        return Route(freshness="live", fallback="escalate")
    elif plan.type == "policy_reference":
        # Document grounding — verify version + temporal validity
        return Route(freshness="versioned_doc", fallback="flag")
    elif plan.type == "reasoning_only":
        # No external truth needed — use model directly
        return Route(freshness="none", fallback=None)
    else:
        return Route(freshness="unknown", fallback="defer")
```

The confidence score from the grounding layer drives routing, not a fixed rule. This prevents over-grounding (always calling live APIs for reasoning-only queries, adding latency) and under-grounding (always trusting the model for fact-dependent queries).

## Receipt

> Verified 2026-08-03 — Source: arXiv:2606.18947v1 (DoorDash DSG, Jun 2026) on decoupling architecture; ACL Anthology ACL-SRW.53 (2025) on KG grounding; OpenReview QYrzaPAqnX on semantic grounding with small LMs; ACL 2026 research on uncertainty-aware validation. Composite claim: DSG achieves near-parity accuracy at 91% lower cost vs native grounding. ACL KG integration reduces hallucination on entity-heavy queries. Single-pass internal representation detection (arXiv:2601.05214) achieves 86.4% accuracy on tool-calling hallucination detection. Practical implementation pattern verified against AgentMarketCap hallucination management framework (2026-06).

## See also

- [S-1057 · The Tool Call Hallucination Plateau](/stacks/s1057-the-tool-call-hallucination-plateau-when-your-agent-gets-20-percent-of-tool-invocations-wrong-in-production.md) — parameter-level hallucination detection and prevention
- [S-1022 · The Agent Drift Stack](/stacks/s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — temporal degradation in knowledge-dependent agents
- [S-1192 · The Five-Layer Caching Stack](/stacks/s1192-the-five-layer-caching-stack-when-your-agent-pays-full-price-for-a-plan-it-already-ran.md) — caching architecture that composes with grounding layers
- [S-981 · The Silent Truncation Stack](/stacks/s981-the-silent-truncation-stack-when-your-agent-reasons-over-evidence-that-wasnt-there.md) — when retrieved evidence is present but wrong
