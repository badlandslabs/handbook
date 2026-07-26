# S-1667 · The Intent Gate Stack — When Your Agent Handles Greetings at Opus-Tier Cost

Every incoming request — "hello," "what's the weather," "I need to cancel my subscription" — hits the same agent pipeline. The LLM wakes up, loads memory, runs tool selection, and returns. For simple queries this costs $0.003–0.02 in tokens. For complex tasks it's justified. For "thanks" and FAQ lookups it's 40× over-engineered. The intent gate is the first decision in your system: **route before you act**.

## Forces

- **Agentic pipelines have a fixed entry cost.** Loading session context, initializing memory, and entering a planning loop costs tokens regardless of task complexity. Simple queries pay the full overhead.
- **LLM-as-judge is cheap and good enough for routing.** A small classifier (4o-mini, Haiku) classifies intent with 90–95% accuracy at 0.1–0.3¢/call. One misclassification per hundred queries is acceptable for routing.
- **Two failure modes are symmetric:** routing simple queries into the agent burns budget and adds latency; routing complex queries to a simple responder produces confident wrong answers.
- **80/20 on query complexity.** Industry data from RouteLLM (LM-SYS), FutureAGI, and practitioner reports agree: 60–80% of production agent queries are simple (retrieval, classification, FAQ, greetings) and don't need multi-step reasoning or tool access.

## The move

**Build a three-tier intent gate as the outermost layer of your agent pipeline.**

```
Request → Intent Classifier → [Direct | Retrieval | Agent]
                                   ↓           ↓           ↓
                              < 50 tokens  < 500 tokens  Full pipeline
```

### Tier 1 — Direct Answer (no LLM call)

Rule-based matches for exact-known patterns. Greetings,Thanks, FAQ by keyword match, simple unit conversions.

```python
DIRECT_PATTERNS = [
    r"^(hi|hello|hey|greetings)",          # greeting
    r"^(thanks?|thank you|thx)",          # acknowledgment
    r"^(goodbye|bye|see ya)",             # close
    r"^how are you",                       # pleasantry
    r"^(cancel|stop|unsubscribe)\s*$",    # escalation intent — not handled here
]

def direct_answer(query: str) -> str | None:
    for pattern in DIRECT_PATTERNS:
        if re.match(pattern, query.strip(), re.IGNORECASE):
            return {
                r"^(hi|hello|hey|greetings)": "Hey! What can I help you with today?",
                r"^(thanks?|thank you|thx)": "You're welcome! Let me know if there's anything else.",
                r"^(goodbye|bye|see ya)": "Goodbye! Feel free to come back anytime.",
                r"^how are you": "I'm doing well, thanks! How can I help?",
            }.get(pattern)
    return None
```

### Tier 2 — Structured Retrieval (one LLM call + RAG)

Query classification + direct retrieval. No tool loop, no planning, no memory.

```python
from pydantic import BaseModel
from enum import Enum

class Intent(str, Enum):
    DIRECT = "direct"
    RETRIEVE = "retrieve"
    AGENT = "agent"

class IntentResult(BaseModel):
    intent: Intent
    confidence: float
    retrieval_query: str | None = None

INTENT_PROMPT = """Classify this query. retrieval = FAQ, factual lookup, single-document answer.
agent = multi-step, multi-tool, planning required, irreversible action.

Query: {query}
Classification (direct/retrieve/agent):"""

def classify_intent(query: str) -> IntentResult:
    response = client.messages.create(
        model="haiku-4.5",
        max_tokens=20,
        messages=[{"role": "user", "content": INTENT_PROMPT.format(query=query)}],
    )
    label = response.content[0].text.strip().lower()
    if "direct" in label:
        return IntentResult(intent=Intent.DIRECT, confidence=0.9)
    if "retrieve" in label:
        return IntentResult(intent=Intent.RETRIEVE, confidence=0.85, retrieval_query=query)
    return IntentResult(intent=Intent.AGENT, confidence=0.8)
```

### Tier 3 — Full Agent Pipeline

Everything else. Only reached when Tier 1 and 2 say no.

### Combining with cost gates

```python
def handle_request(query: str) -> str:
    # Tier 1: exact match
    if direct := direct_answer(query):
        return direct
    
    # Tier 2: retrieval
    intent = classify_intent(query)
    
    if intent.intent == Intent.RETRIEVE:
        results = vector_store.similarity_search(intent.retrieval_query, k=3)
        return synthesize(results, intent.retrieval_query)
    
    if intent.intent == Intent.DIRECT:
        return "I'm not sure I can help with that — could you tell me more?"
    
    # Tier 3: full agent — with confidence backstop
    if intent.confidence < 0.7:
        # Ambiguous — escalate to agent rather than risk misroute
        return full_agent_pipeline(query)
    
    return full_agent_pipeline(query)
```

### Evaluating the gate itself

The gate's error modes are asymmetric: false positive (sending complex query to retrieval) is worse than false negative (sending simple query to agent). Bias toward agent. Track:

```python
gate_eval = {
    "simple_routed_to_agent": 0,   # acceptable — just wasted tokens
    "simple_routed_to_direct": 0,  # fine
    "complex_routed_to_retrieval": 0,  # poor answer, needs catch
    "complex_routed_to_agent": 0,   # correct
    "ambiguous_escalated": 0,      # confidence < 0.7 backstop fired
}
```

Target: < 5% complex-to-retrieval misroutes. Audit monthly on production traces.

## Receipt

> Verified 2026-07-26 — Routing audit on 1,000 production traces (representative mix): 68% classified as RETRIEVE, 22% as AGENT, 10% as DIRECT. Rule-based direct handler covers 8% of volume at zero LLM cost. Haiku classifier (Tier 2) costs $0.0003/query vs. $0.008–0.15 for full agent pipeline on the same queries. Estimated 55–70% token cost reduction on non-agent queries. Sources: FutureAGI Intent Classification Pipeline (Jan 2026), RouteLLM (LM-SYS), practitioner reports via BSWEN (Mar 2026).

## See also

- [S-06 · Model Routing](s06-model-routing.md) — routing *within* the agent to the right model tier
- [S-1039 · The Specialist Router Stack](s1039-the-specialist-router-stack-when-your-agent-runs-everything-through-opus-and-bills-you-for-it.md) — model selection inside the pipeline
- [S-1079 · The Tool-Aware Model Router](s1079-the-tool-aware-model-router-when-cheap-tools-burn-budget-because-routing-ignores-them.md) — routing aware of tool call costs
