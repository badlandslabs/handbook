# S-1177 · The Semantic Tool Router — When Your Agent Sends 200 Tool Schemas to Call One Function

You built a unified agent. It connects HubSpot, Jira, Slack, NetSuite, Greenhouse, Zendesk, and a dozen more services. Now every time a user asks to "create an issue," Claude receives descriptions for all 200+ available tools — most of which have nothing to do with the request. The model wastes tokens, latency climbs, and occasionally it picks `create_issue` from Confluence instead of Jira. The fix is not better prompting. It's routing before the prompt.

## Forces

- **Monolithic prompt anti-pattern:** Sending every tool schema on every request wastes tokens (5–40% of context per turn), inflates latency (each tool description is 200–2000 tokens), and makes tool selection harder for the model — not easier.
- **LLM-based routing is expensive and slow:** A separate LLM call to decide which tools to use adds 500ms–5,000ms of latency and costs real money on every request. At scale, this is the largest line item nobody tracks.
- **Tool hallucinations are real:** Models invent tool names, especially when many tools share similar descriptions. Restricting the visible tool set eliminates this class of error.
- **Threshold ambiguity is solvable:** When the semantic match is unclear (top-2 scores within 0.05), escalate to LLM — but only for those cases, not every request.

## The move

Replace LLM-based tool selection with **vector similarity routing** at the tool-activation layer. Encode every tool's description and trigger utterances into embeddings. At request time, encode the user query and retrieve the top-K semantically similar tools. Pass only those to the agent's prompt.

**Architecture (4 steps):**

```python
# Step 1: Index tools at startup or schema registration time
from openai import OpenAI
import numpy as np

client = OpenAI()

TOOLS = [
    {"name": "jira_create_issue", "description": "Create a Jira issue in a project", "examples": ["create issue", "log bug", "open ticket in Jira"]},
    {"name": "hubspot_create_contact", "description": "Create a contact in HubSpot CRM", "examples": ["add contact", "new lead", "create prospect"]},
    # ... N tools
]

def embed(texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [r.embedding for r in resp.data]

# Index: encode description + examples per tool
tool_texts = [f"{t['description']} {' '.join(t['examples'])}" for t in TOOLS]
tool_vectors = embed(tool_texts)

# Step 2: Route at request time
def route_tools(query: str, threshold: float = 0.72, top_k: int = 5) -> list[dict]:
    q_vec = embed([query])[0]

    # Cosine similarity
    scores = []
    for i, v in enumerate(tool_vectors):
        score = np.dot(q_vec, v) / (np.linalg.norm(q_vec) * np.linalg.norm(v))
        scores.append((score, TOOLS[i]))

    scores.sort(reverse=True)
    best = scores[0]

    # Step 3: Ambiguity check — escalate to LLM on near-ties
    if len(scores) >= 2 and (scores[0][0] - scores[1][0]) < 0.05:
        # LLM tiebreaker — only for ambiguous cases
        return scores[0][1], scores[1][1]  # return top-2 for LLM to pick
    elif best[0] < threshold:
        return []  # no confident match — escalate to full tool set

    return [tool for score, tool in scores[:top_k] if score >= threshold]

# Step 4: Build the filtered tool prompt
def build_system_prompt(query: str) -> str:
    matched = route_tools(query)
    if not matched:
        # Fallback: use LLM to guess from full set (rare)
        return "Use all available tools to best answer the query."

    tools_section = "\n\n".join(
        f"## {t['name']}\n{t['description']}" for t in matched
    )
    return f"You have access to these tools:\n\n{tools_section}\n\nUse only the tools above."
```

**Key parameters:**
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Embedding model | `text-embedding-3-small` | 1536 dims, low cost, good quality |
| Threshold | 0.72 | Tune on your eval set — below this, false-positive rate climbs |
| Top-K | 5–8 | Enough to cover multi-tool tasks; beyond 8, diminishing returns |
| Ambiguity delta | 0.05 | When top-2 scores are within 5%, let the LLM decide |

**Token savings are real:** A unified agent with 200 tools sending full schemas on 10-turn conversations burns ~40K tokens/turn in tool descriptions alone. Semantic routing cuts that to ~2K. At $0.15/1M tokens for Haiku, that's $0.006/request vs. $0.12/request — a 20× reduction.

**Latency savings:** Embedding lookup (100ms) vs. LLM routing call (500ms–5,000ms). At scale, this is the difference between 110ms and 5,100ms per routing decision.

**Operational requirements:**
- Re-index tool vectors whenever tool descriptions change (version your index)
- Monitor the escalation rate — if >20% of requests escalate to LLM routing, your threshold is too high or your examples are too sparse
- Log every routing decision with top-3 scores; use this to grow the example utterances over time

## See also

- [S-989 · The Tool Surface Stack](s989-the-tool-surface-stack-when-your-agent-has-50-tools-and-picks-the-wrong-one.md) — tool surface design and description quality
- [S-06 · Model Routing](s06-model-routing.md) — tier-based model selection
- [S-989 · The Tool Granularity Stack](s1175-the-tool-granularity-stack-when-giving-your-agent-more-tools-makes-it-worse.md) — how tool count degrades reliability
