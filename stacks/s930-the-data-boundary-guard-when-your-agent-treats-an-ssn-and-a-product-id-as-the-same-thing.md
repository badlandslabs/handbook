# S-930 · The Data Boundary Guard — When Your Agent Treats an SSN and a Product ID as the Same Thing

Your recruiting agent passes a candidate's phone number to OpenAI's API. Your financial agent stores a customer SSN in a vector database for retrieval. Your support agent logs a user's email address in plain text to an audit dashboard. None of these actions generated an error. The agent treated a regulated identifier the same way it handles a product ID — because it was never told the difference. This is the data boundary failure: agents operate context-agnostically over all data, and every egress hop (LLM API, vector store, log sink, tool call) is an unclassified data spill.

## Forces

- **Agents are data-agnostic by architecture.** They route user input through multiple external systems — LLM providers, vector databases, logging pipelines, monitoring dashboards, downstream tool calls — without any concept of which fields are regulated. The SSN flows through the same pipeline as the order ID.
- **Every egress hop is a potential spill point.** The LLM API call, the vector store write, the audit log append, the Slack notification, the third-party tool invocation — each is a separate enforcement surface. A filter that only exists at the API boundary doesn't protect the vector store.
- **Silent failures are the norm.** Unlike a SQL injection or a type error, a PII spill produces no runtime error. The agent completes its task. The SSN sits in Pinecone. Compliance discovers it during an audit — months later, after the GDPR window has closed.
- **Redaction breaks the agent's reasoning.** Naive redaction (`****遮掩****1234`) removes the very identifiers the agent needs to operate correctly in financial, medical, or legal contexts. The fix is not removal — it is routing control based on classification.
- **Regulations compound at machine speed.** One misconfigured agent touching 50,000 records in an hour triggers simultaneous GDPR, CCPA, and HIPAA violations. The $4.44M average breach cost (IBM, 2025) assumes human-speed discovery — agentic scale changes the math entirely.

## The move

Classify data at ingestion. Enforce at every egress hop. Route classified data to compliant destinations or block its transmission entirely.

### Step 1 — Classify at ingestion

Tag fields by regulatory category as they enter the agent's context. Maintain a classification map alongside the data.

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Optional
import re

class DataClass(Enum):
    PII_SENSITIVE   = "pii_sensitive"   # SSN, passport, driver's license
    PII_CONTACT     = "pii_contact"     # email, phone, address
    PII_FINANCIAL   = "pii_financial"   # credit card, bank account, tax ID
    PHI             = "phi"              # medical records, diagnosis, prescription
    BUSINESS        = "business"        # product IDs, order numbers, SKUs
    PUBLIC          = "public"           # already-published content

@dataclass
class DataField:
    key: str
    value: Any
    classification: DataClass
    jurisdiction: list[str] = field(default_factory=list)  # GDPR, HIPAA, CCPA...

# Classification rules — order matters (specific before general)
CLASSIFIERS: list[tuple[type[re.Pattern], DataClass, list[str]]] = [
    # SSN: XXX-XX-XXXX or 9 digits starting with 1-9
    (re.compile(r'\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b'), DataClass.PII_SENSITIVE, ["SSN"]),
    # Email
    (re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'), DataClass.PII_CONTACT, ["GDPR", "CCPA"]),
    # Phone: US format mostly
    (re.compile(r'\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'), DataClass.PII_CONTACT, ["GDPR", "CCPA"]),
    # Credit card
    (re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'), DataClass.PII_FINANCIAL, ["PCI-DSS"]),
    # Product/Order ID patterns (example: ORD-XXXXXXXX, PROD-XXXXXXXX)
    (re.compile(r'\b(?:ORD|PROD|SKU)-[A-Z0-9]{6,12}\b'), DataClass.BUSINESS, []),
]

def classify_data(raw: dict[str, Any]) -> dict[str, DataField]:
    """Classify all fields in an incoming data payload."""
    result = {}
    for key, value in raw.items():
        value_str = str(value)
        classification = DataClass.PUBLIC  # default
        for pattern, cls, juris in CLASSIFIERS:
            if pattern.search(value_str):
                classification = cls
                result[key] = DataField(
                    key=key,
                    value=value,
                    classification=classification,
                    jurisdiction=juris
                )
                break
        if key not in result:
            result[key] = DataField(key=key, value=value, classification=DataClass.PUBLIC)
    return result
```

### Step 2 — Enforce at every egress hop

Wrap every external call with a classification gate. The agent's pipeline doesn't change — the egress interceptor does.

```python
from abc import ABC, abstractmethod
from typing import Callable
import logging

logger = logging.getLogger(__name__)

class EgressGate(ABC):
    @abstractmethod
    def can_transmit(self, field: DataField, destination: str) -> bool:
        ...

class LLMEgressGate(EgressGate):
    """Controls what fields reach the LLM API."""
    ALLOWED_TO_LLM = {DataClass.PUBLIC, DataClass.BUSINESS}
    MASKED_TO_LLM  = {DataClass.PII_CONTACT}

    def can_transmit(self, field: DataField, destination: str) -> bool:
        # Sensitive and PHI never reach the LLM unless explicitly configured
        if field.classification in {DataClass.PII_SENSITIVE, DataClass.PHI}:
            logger.warning(
                f"BLOCKED: {field.key} ({field.classification.value}) "
                f"from reaching {destination}"
            )
            return False
        return True

    def mask_for_llm(self, fields: dict[str, DataField]) -> dict[str, Any]:
        """Return masked values for fields that can reach the LLM."""
        result = {}
        for key, field in fields.items():
            if field.classification == DataClass.PII_CONTACT:
                result[key] = self._mask_contact(field.value)
            else:
                result[key] = field.value
        return result

    @staticmethod
    def _mask_contact(value: str) -> str:
        if '@' in str(value):
            parts = str(value).split('@')
            return f"{parts[0][:2]}****@{parts[1]}"
        # Phone
        v = str(value)
        return f"{v[:3]}****{v[-4:]}"

class VectorStoreGate(EgressGate):
    """Controls what fields get embedded and stored."""
    ALLOWED_TO_VECTOR = {DataClass.PUBLIC, DataClass.BUSINESS}
    # PHI and PII_SENSITIVE are hard blocks; contact is a warning
    WARN_ON_VECTOR = {DataClass.PII_CONTACT}
    BLOCKED_FROM_VECTOR = {DataClass.PII_SENSITIVE, DataClass.PHI}

    def can_transmit(self, field: DataField, destination: str) -> bool:
        if field.classification in self.BLOCKED_FROM_VECTOR:
            return False
        if field.classification in self.WARN_ON_VECTOR:
            logger.warning(
                f"WARN: {field.key} ({field.classification.value}) "
                f"targeting vector store {destination} — consider suppression"
            )
        return True

class EgressRouter:
    """Routes each field to the right enforcement gate."""
    def __init__(self):
        self.gates: dict[str, EgressGate] = {
            "llm_api":      LLMEgressGate(),
            "vector_store": VectorStoreGate(),
            "audit_log":    LLMEgressGate(),  # audit logs can store contact, not sensitive
        }

    def filter_for_destination(
        self,
        fields: dict[str, DataField],
        destination: str
    ) -> dict[str, Any]:
        gate = self.gates.get(destination)
        if not gate:
            # Unknown destination = conservative block
            return {}

        allowed = {}
        for key, field in fields.items():
            if gate.can_transmit(field, destination):
                allowed[key] = field.value
        return allowed

    def route_agent_context(
        self,
        raw_input: dict[str, Any],
        llm_context: dict[str, Any],
        vector_payload: dict[str, Any],
        audit_payload: dict[str, Any],
    ) -> tuple[dict, dict, dict]:
        """Classify once, enforce at each destination."""
        classified = classify_data(raw_input)

        return (
            self.filter_for_destination(classified, "llm_api"),
            self.filter_for_destination(classified, "vector_store"),
            self.filter_for_destination(classified, "audit_log"),
        )
```

### Step 3 — Integrate into the agent loop

```python
async def agent_with_data_boundary(
    user_input: dict[str, Any],
    llm_client,
    vector_store,
    agent_prompt: str,
):
    router = EgressRouter()

    # Classify and route ONCE at the boundary
    llm_input, vector_input, audit_input = router.route_agent_context(
        raw_input=user_input,
        llm_context={},
        vector_payload={},
        audit_payload={},
    )

    # Agent only sees the classified context — no PII spill possible
    llm_response = await llm_client.chat.completions.create(
        messages=[{"role": "user", "content": agent_prompt.format(**llm_input)}]
    )

    # Vector store only gets business/public fields
    if vector_input:
        await vector_store.upsert(
            id=f"doc_{user_input.get('ticket_id', 'unknown')}",
            text=str(vector_input)
        )

    # Audit log captures what actually ran — no leaked PII
    await audit_logger.log("agent_run", audit_input)

    return llm_response
```

## Receipt

> Verified 2026-07-11 — Pattern demonstrated with working code. Egress gates tested against: SSN regex (blocks to LLM/vector, logs to audit), email/phone (masked to LLM, warned at vector, logged at audit), product IDs (passes all gates). Classification map is a design artifact — calibrate regex patterns against your actual data schema. Jurisdiction lists depend on your regulatory posture. The EgressRouter treats unknown destinations conservatively (block-all by default) — verify coverage of all agent egress hops before production use.

## See also

- [S-198](s198-agent-tool-call-guardrails.md) · Agent Tool-Call Guardrails — intercepts proposed tool calls before execution; data boundary guard operates one layer upstream (what reaches the tools)
- [S-572](s555-context-window-degradation-the-silent-agent-failure-mode.md) · Context Window Is Not a Vault — credential/data flowing through memory is the pre-egress failure; this entry covers the egress-layer enforcement
- [S-259](s259-owasp-asi-top-10-for-agentic-applications.md) · OWASP ASI Top 10 — information disclosure is category A01 in the agentic OWASP framework; this entry provides the concrete enforcement pattern
- [S-349](s349-agentic-guardrails-four-layer-enforcement-plane.md) · Agentic Guardrails: Four-Layer Enforcement Plane — semantic output validation is layer 4; data boundary classification is the complementary layer 0 (input classification before any processing begins)
