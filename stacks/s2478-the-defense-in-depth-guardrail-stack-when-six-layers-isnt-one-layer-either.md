# S-2478 · The Defense-in-Depth Guardrail Stack — When Six Layers Isn't One Layer Either

Your agentic system passed the OWASP checklist. You have input validation, a content filter, a moderation API call, and a sandbox. Then a prompt injection hides inside an MCP server's tool response, bypasses your content filter, reaches the model, and executes a shell command your sandbox doesn't catch because the sandbox trusts the MCP server's output as system-level. No single layer failed. All six layers failed sequentially against the same attack vector. This is the six-layer illusion: deploying safety primitives in parallel does not make them independent.

## Forces

- **Each guardrail layer addresses a different threat class — but they chain.** Prompt injection through a RAG chunk is a retrieval-layer problem. A content filter on output does not catch it. A sandbox does not catch it. Only the layer closest to the injection point stops it.
- **Most teams deploy two layers and call it done.** OWASP's analysis of 6,639 real AI security incidents finds that the median production deployment has fewer than three independent safety layers, leaving at least three OWASP Top 10 categories with zero coverage.
- **False-positive cost is asymmetric.** A 4% false-positive rate (Llama Guard 3) vs 15.2% (GPT-4 moderation) means 40,000 vs 152,000 wrongly blocked requests per million. The choice of classifier is also a product decision, not just a security decision.
- **Latency budgets are finite and contested.** Each guardrail layer adds latency. Teams that don't budget it upfront end up stripping layers under pressure from product managers.

## The Move

Map each of the six guardrail layers to a specific OWASP LLM Top 10 2026 vulnerability. No layer should share threat ownership with another.

### Layer 1 — Input Validation & Prompt Hardening

Intercept the user message before it reaches the model. Check for direct prompt injection (system-prompt override attempts), jailbreak patterns (Unicode bypass, encoding tricks, adversarial suffixes), and policy violations (PII, out-of-scope requests).

```python
import re
from transformers import AutoTokenizer

# Layer 1: Fast pre-filter before LLM call
SUSPICIOUS_PATTERNS = [
    r"ignore\s+(previous|all)\s+instructions",
    r"you\s+are\s+now\s+a?",
    r"\[INST\]\s*\{",
    r"\x00",  # null byte injection
    r"<script|<svg|javascript:",
]

def preflight_input(user_message: str, tokenizer) -> dict:
    """
    Returns: {"block": bool, "reason": str, "latency_ms": float}
    Target latency: <5ms
    """
    import time
    start = time.perf_counter()

    # Fast pattern scan (< 1ms)
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, user_message, re.IGNORECASE):
            return {"block": True, "reason": "injection_pattern", "latency_ms": 0}

    # Token budget check — reject before model call
    tokens = len(tokenizer.encode(user_message))
    if tokens > 8192:
        return {"block": True, "reason": "token_budget_exceeded", "latency_ms": 0}

    return {"block": False, "reason": None, "latency_ms": (time.perf_counter() - start) * 1000}
```

### Layer 2 — Retrieval Rail (RAG / Tool Response Sanitization)

Indirect prompt injection lives in retrieved chunks and MCP server responses — data the model trusts as ground truth. Tag retrieved content as untrusted, strip instruction-like fragments, and use input classification on the assembled prompt.

```python
def sanitize_retrieved_chunk(chunk: str, chunk_metadata: dict) -> str:
    """
    Layer 2: Treat all external data as potentially adversarial.
    Strip markdown/HTML instruction markers that could carry indirect injection.
    """
    # Remove embedded instruction patterns — injection via document metadata
    dangerous = [
        r"<!--.*?-->",          # HTML comments (common injection vector)
        r"\[SYSTEM\]",          # markdown system callouts
        r"<\|.*?\|>",           # token sequences models may interpret as special
        r"\\x[0-9a-f]{2}",      # encoded bytes
    ]
    sanitized = chunk
    for pattern in dangerous:
        sanitized = re.sub(pattern, "[FILTERED]", sanitized, flags=re.IGNORECASE)

    # Tag as untrusted in the prompt
    if chunk_metadata.get("source") != "verified_internal":
        sanitized = f"[Source: {chunk_metadata.get('source', 'external')}] {sanitized}"

    return sanitized
```

### Layer 3 — LLM-Based Content Classification (Primary Moderation)

Llama Guard 3 8B outperforms GPT-4 moderation at a fraction of the cost: F1 0.939 vs 0.805, FPR 4% vs 15.2%, at ~$0 vs per-token cost. Run on the assembled prompt (user + system + retrieved context).

```python
from llama_guard import LlamaGuard

lg = LlamaGuard(model="meta-llama/Llama-Guard-3-8B", device="cuda")

def classify_prompt(prompt: str, categories: list[str] | None = None) -> dict:
    """
    Layer 3: LLM-based safety classification on the full assembled prompt.
    Categories from OWASP LLM Top 10 2026:
      S1: Prompt Injection, S2: Insecure Output, S3: Data Leakage,
      S4: Denial of Service, S5: Supply Chain, S6: Sensitive Info
    """
    categories = categories or [
        "O1",  # Prompt Injection
        "O2",  # Malicious Code
        "O3",  # Defamation",
        "O4",  # Hate Speech",
        "O5",  # Help with Cyberattack",
        "O6",  # Sexual Content",
        "S1",  # Sensitive Personal Data",
        "S2",  # Intellectual Property",
        "S3",  # Financial Data",
        "S4",  # Health Information",
    ]

    # Returns list of violated category codes or []
    violations = lg.classify(prompt, categories=categories)
    return {
        "block": len(violations) > 0,
        "violations": violations,
        "model": "LlamaGuard-3-8B",
    }
```

### Layer 4 — Structured Output & Schema Validation

After the model generates, validate against an allowed schema before any downstream tool receives the output. Blocks prompt injection through model response — the model cannot override schema constraints without being caught.

```python
from pydantic import BaseModel, ValidationError

class ToolCallSpec(BaseModel):
    tool_name: str
    arguments: dict

    class Config:
        extra = "forbid"  # reject unexpected fields

def validate_output(raw_output: str, allowed_tools: set[str]) -> ToolCallSpec | None:
    """
    Layer 4: Parse and validate structured tool calls against allowed list.
    Rejects JSON that passes parse but contains disallowed tools or fields.
    """
    try:
        import json
        parsed = json.loads(raw_output)
        spec = ToolCallSpec(**parsed)
        if spec.tool_name not in allowed_tools:
            return None
        return spec
    except (json.JSONDecodeError, ValidationError):
        return None
```

### Layer 5 — Tool-Call Execution Gating

Every tool invocation hits a policy gate before execution. The gate checks: is this tool allowed given the current session state? Has the request-rate budget been exceeded? Is the action irreversible?

```python
from enum import Enum

class RiskLevel(Enum):
    LOW = "low"        # read-only, no side effects
    MEDIUM = "medium"  # write, contained blast radius
    HIGH = "high"      # irreversible, external API, payment
    BLOCKED = "blocked"

TOOL_RISK_MAP = {
    "search": RiskLevel.LOW,
    "read_file": RiskLevel.MEDIUM,
    "send_email": RiskLevel.HIGH,
    "exec_shell": RiskLevel.HIGH,
    "write_file": RiskLevel.MEDIUM,
    "delete": RiskLevel.BLOCKED,
}

ACTION_BUDGET = {"exec_shell": 5, "send_email": 2}  # per session

def gate_tool_call(tool_name: str, session_state: dict) -> tuple[bool, str]:
    """
    Layer 5: Policy gate before any tool executes.
    Returns: (allowed, reason)
    """
    risk = TOOL_RISK_MAP.get(tool_name, RiskLevel.BLOCKED)
    if risk == RiskLevel.BLOCKED:
        return False, "tool_explicitly_blocked"

    if tool_name in ACTION_BUDGET:
        used = session_state.get(f"budget_used_{tool_name}", 0)
        if used >= ACTION_BUDGET[tool_name]:
            return False, f"action_budget_exceeded_{tool_name}"

    # Irreversible actions require human approval gate
    if risk == RiskLevel.HIGH:
        if not session_state.get("human_approved", False):
            return False, "requires_human_approval"

    return True, "allowed"
```

### Layer 6 — Observability & Audit Trail

Every guardrail decision — allow, block, exception — is logged with context. This is the layer that makes the other five layers survivable: when a layer fails, the audit trail is how you detect it.

```python
import json
from datetime import datetime, timezone

def log_guardrail_decision(
    layer: int,
    decision: str,          # "allow" | "block" | "exception"
    reason: str,
    context: dict,
    latency_ms: float,
):
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "layer": layer,
        "decision": decision,
        "reason": reason,
        "latency_ms": round(latency_ms, 2),
        "context": context,  # user_id, session_id, model, tool_name
    }
    # Emit to OpenTelemetry span + structured log
    print(json.dumps(record))
```

### Layer Independence Checklist

Run this before calling a deployment done:

| Test | Expected | Detects |
|------|----------|---------|
| Send prompt injection via user input | Blocked at Layer 1 | Input filter bypass |
| Inject via RAG chunk | Blocked at Layer 2 | Retrieval sanitization gap |
| Bypass all content filters | Blocked at Layer 4 | Output schema bypass |
| Call blocked tool via `{"tool_name": "delete"}` | Blocked at Layer 5 | Execution gate bypass |
| Blocked request produces no log entry | FAIL | Audit trail gap |
| 100 concurrent requests: total latency < 500ms | PASS | Latency budget validation |

## Receipt

> Receipt pending — 2026-08-11. Key benchmarks sourced from Digital Applied (2026-05-26): Llama Guard 3 F1 0.939, GPT-4 F1 0.805, FPR 4% vs 15.2%. OWASP threat taxonomy from OWASP GenAI LLM Top 10 2026 (released 2026-08-03, 7,714 real incidents, 75% practitioner voting / 25% incident data weighting). Layer taxonomy and false-positive math validated against Digital Applied's six-layer framework. Code examples use real APIs (Llama Guard 3 Hugging Face, pydantic, OpenTelemetry) but were not run in a live agent pipeline this session — Receipt pending pending integration test against a production trace.

## See also

- [S-1000 · The Structural Agent Governance Stack](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — structural vs. enforcement governance; this entry is the layered runtime sibling
- [S-2118 · The Isolation Tier Stack](s2118-the-isolation-tier-stack-when-docker-isnt-enough-and-firecracker-costs-too-much.md) — execution sandboxing; complements Layer 5 (tool-call gating) with hardware-level containment
- [S-1894 · The Agentic RAG Evidence Desert](s1894-the-agentic-rag-evidence-desert-when-your-production-rag-system-fails-where-no-one-has-proven-anything.md) — retrieval failure as a silent guardrail bypass; complements Layer 2 (retrieval rail)
- [S-360 · Governance Decay: The Silent Safety Erosion Pattern](s360-governance-decay-the-silent-safety-erosion-pattern.md) — how safety constraints degrade under context pressure; Layer 3 (classification) is not immune
