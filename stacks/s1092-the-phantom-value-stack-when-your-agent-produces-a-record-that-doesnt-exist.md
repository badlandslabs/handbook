# S-1092 · The Phantom Value Stack — When Your Agent Produces a Record That Doesn't Exist

Your agent completes every task successfully. Every API call returns 200. Every tool invocation confirms execution. Nine hours later, a downstream system has ingested a phantom purchase order, a ghost user account, and an invoice referencing a shipment that was never created. There is no error in any log. The agent did exactly what it was asked — it fabricated a coherent record from parts that didn't exist, and every system it touched confirmed the fabrication as valid.

This is the Phantom Value Problem: agents produce intermediate identifiers — record IDs, SKU codes, user handles, session tokens — that look structurally correct but don't correspond to real entities. Downstream systems return 200 because they don't validate existence at call time. The result is a perfectly successful-looking execution that leaves ghost data throughout your infrastructure.

## Forces

- **Agents hallucinate identifiers as readily as they hallucinate text.** An LLM generating a customer support ticket number, a product SKU, or an order ID doesn't "know" these are identifiers — it treats them as strings. A plausible-looking string passes through every downstream system unchallenged.
- **HTTP 200 is not a confirmation of truth — only of syntax.** Every REST endpoint in your stack validates that a request is well-formed. None validate that the referenced entities exist. This is fine for typed clients (which hold references they know to be valid). It is catastrophic for agents, which generate references from thin air.
- **Propagation compounds the damage.** A phantom order ID doesn't just create one bad record — it generates a cascade of valid records: shipment, invoice, notification, analytics entry. Each system processed a phantom input and produced a phantom output, all logging success.
- **The failure is invisible until the humans arrive.** Phantom records often don't surface until a customer calls about a shipment that doesn't exist, an auditor finds orphaned transactions, or a reconciliation job fails. By then the blast radius is measured in hours or days of contaminated data.

## The Move

### 1. Upstream Provenance Tags

Every identifier your agent generates must carry a provenance tag stating its origin:

```python
# Wrap LLM-generated identifier extraction with provenance
def extract_order_id(agent_output: str, source_tool: str) -> str | None:
    match = re.search(r"order[_\s]?id[:\s]+([A-Z0-9-]+)", agent_output, re.IGNORECASE)
    if not match:
        return None
    raw_id = match.group(1)
    # Tag with provenance — the model generated this, it is NOT a confirmed record
    return ProvenanceTag(raw_id, source="llm_generated", confirmed=False)

class ProvenanceTag:
    def __init__(self, value, source, confirmed):
        self.value = value
        self.source = source  # "llm_generated" or "api_response"
        self.confirmed = confirmed  # False = needs existence check before use

    def __str__(self):
        return self.value
```

Flag every LLM-extracted identifier as `confirmed=False`. Treat `confirmed=False` identifiers as untrusted in downstream logic.

### 2. Existence Verification Gate

Before any identifier from an agent's output is used as an input to a downstream system, run an existence check:

```python
async def safe_create_shipment(order_id: ProvenanceTag) -> ShipmentRecord:
    # Gate: verify the order exists before creating anything downstream
    if not order_id.confirmed:
        # Query the orders service to confirm the record exists
        order = await orders_client.get(order_id.value)
        if order is None:
            raise PhantomValueError(
                f"Order {order_id.value} does not exist. "
                f"This identifier came from LLM output and failed existence verification. "
                f"Task={current_task_id}, step={current_step}"
            )
        order_id.confirmed = True

    return await shipment_client.create(order_id.value)
```

The existence check is a hard gate: if the identifier doesn't resolve, the agent's output was a phantom and the task must be retried or escalated.

### 3. Phantom Value Detector (LLM-as-Judge)

For cases where existence checks are too expensive or no verification endpoint exists, use an LLM-as-judge to score whether the full context supports the identifier:

```python
async def score_phantom_risk(context: list[dict], identifier: str, id_type: str) -> float:
    """
    Returns risk score 0-1 for whether `identifier` of type `id_type`
    (e.g. "order_id", "user_id", "SKU") is a phantom.
    Higher = more likely phantom.
    """
    prompt = f"""
    Context:
    {chr(10).join(f"- {m['role']}: {m['content'][:200]}" for m in context[-10:])}

    An agent produced the identifier: {identifier} (type: {id_type}).
    Based on the context above, rate the probability this identifier is hallucinated.
    Consider:
    - Was it read from a verified API response?
    - Was it generated or inferred by the LLM?
    - Does the surrounding context support its existence?

    Return a JSON object: {{"phantom_probability": 0.0-1.0, "reasoning": "..."}}
    """
    response = await judge_llm.complete(json.loads, prompt)
    return response["phantom_probability"]
```

Block propagation if `phantom_probability > 0.6`. For critical paths (financial records, user accounts), use a lower threshold (0.3).

### 4. Propagation Receipts

Track what each agent step consumed and produced, so phantom sources can be traced to root cause:

```python
@dataclass
class StepReceipt:
    step_id: str
    inputs: list[ProvenanceTag]   # identifiers consumed
    outputs: list[ProvenanceTag] # identifiers produced
    tool_calls: list[str]
    phantom_risk: float

# Store receipts in a trace store (e.g., OpenTelemetry span attributes)
# When a phantom is detected downstream, walk receipts backward to find the source step
```

This turns a data archaeology problem into a traversal.

### 5. Idempotency Keys as Phantom Catchers

Design your downstream APIs to reject duplicate or orphaned operations:

```python
# Use a deterministic idempotency key derived from the task + step
# If a phantom order_id was used, the idempotency key still maps to
# a real order_id on retry — the existence check catches the phantom before creation
idempotency_key = hashlib.sha256(
    f"{task_id}:{step}:{canonical_input}".encode()
).hexdigest()[:32]
```

When the agent retries with a corrected ID, the idempotency key ensures the clean run doesn't conflict with the phantom's partial side effects.

## Tradeoffs

- **Existence checks add latency.** Every phantom gate is a network call. For high-frequency paths, batch verify multiple identifiers in a single request or cache results for the duration of a task.
- **Not every identifier has a verification endpoint.** For agent-generated UUIDs, internal codes, or fictional references, fall back to the LLM-as-judge approach. Budget for cases where no verification is possible — those paths should require human confirmation.
- **Phantom detection is probabilistic, not deterministic.** The LLM-as-judge can itself hallucinate. Treat it as a risk filter, not a proof of correctness. The existence check remains the gold standard.
- **Provenance tagging requires discipline across the codebase.** Every identifier extraction must be wrapped. Without consistent tagging, phantom values slip through at the boundaries you forgot to instrument.

## See Also

- [S-1052 · The Cascade Stack](s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md) — cascade infection from hallucinated facts propagating through multi-agent pipelines
- [S-1090 · The Green Dashboard Problem](s1090-the-green-dashboard-problem-when-every-api-call-succeeds-but-your-agent-destroys-production.md) — trajectory-level failures invisible to API monitoring
- [S-1023 · The Recovery Ladder](s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — distinguishing actual success from perceived success
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — coordination failures at agent handoff boundaries
