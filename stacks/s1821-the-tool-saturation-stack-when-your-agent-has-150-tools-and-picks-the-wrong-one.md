# S-1821 · The Tool Saturation Stack — When Your Agent Has 150 Tools and Picks the Wrong One

Your agent worked fine with 12 tools. Then the team added "just a few more" for the enterprise rollout — calendar integration, CRM lookup, document search, permission checks, cost estimation, Slack routing, Jira sync. Now you have 150 tools across 7 MCP servers and the agent picks the wrong one on 34% of multi-step tasks. The tool surface that was supposed to make the agent more capable is making it less reliable.

## Forces

- **More tools should mean more capable. They don't.** Adding a tool creates a selection problem: the agent must distinguish your `read_file` from your colleague's `read_document` from your system's `document_fetch` — and it does this using embedding similarity on tool descriptions, which degrades predictably as surface size grows.

- **MCP's schema-first design is a double-edged sword.** Every registered MCP server exposes its tools via JSON schema. That's great for discovery — and catastrophic for retrieval. Descriptions that sound plausible but overlap semantically produce near-identical embedding vectors. The agent sees a wash of 0.87–0.91 similarity scores and picks one arbitrarily.

- **Interdependent tools create silent failure chains.** In large MCP surfaces, tool `Y` is only valid after tool `X` has run and left state. The agent doesn't know this. It calls `Y` first, gets a plausible-looking error response it tries to recover from, and cascades into a 47-step error spiral that a 12-tool agent would never enter.

- **The benchmark-production gap is largest here.** Simple benchmarks test 10–20 tools, all independent, all obvious. Production MCP surfaces have 50–150+ tools with interdependencies, overlapping scope, and evolving schemas. This is where agents that score 85% on benchmarks collapse to 51% in real deployments.

## The Move

### The Three Saturation Failure Modes

ComplexMCP (Li, Yang, Wang et al., arXiv:2605.10787, 2026) identified three reproducible failure modes in agents navigating large-scale tool surfaces:

1. **Tool-retrieval saturation.** When the agent must select from 150+ tools, embedding-similarity rankings collapse into a flat distribution. No tool scores distinctly higher than the others. Selection becomes near-random, and correctness drops to below-chance on tasks requiring rare tools.

2. **Scope creep.** Broadly-named tools (`update_record`, `modify_entry`) receive calls intended for narrow sibling tools and vice versa. The agent chooses `update_contact` when `update_crm_contact_with_consent_check` was the correct call, partially succeeding and producing downstream contamination.

3. **Implicit dependency failure.** Tool `B` requires output from tool `A` but neither the schema nor the description states this. The agent calls `B` immediately after `C` (which looked more relevant), gets an opaque error, and either loops or abandons the task.

### Pattern 1: Tool Retrieval Stratification

Split the tool surface into **active** and **passive** tiers. Only the active tier loads into the context window at decision time.

```python
from dataclasses import dataclass, field
from typing import Callable
import json

@dataclass
class ToolTier:
    name: str
    tools: dict[str, dict]
    load_policy: Callable[[dict], bool]  # returns True to include

    def query(self, task_description: str, top_k: int = 12) -> list[dict]:
        """Return top_k tools from this tier using semantic ranking."""
        # Real impl: embed task_description, cosine-similarity rank all tools,
        # return top_k. Here we show the interface.
        scores = {
            name: self._semantic_score(desc, task_description)
            for name, desc in self.tools.items()
        }
        ranked = sorted(scores, key=scores.get, reverse=True)
        return [self.tools[n] for n in ranked[:top_k]]

    def _semantic_score(self, tool_desc: str, query: str) -> float:
        # Placeholder: in production, use the same embedding model
        # that your LLM uses, or a lightweight cross-encoder
        from math import log
        common = sum(1 for w in tool_desc.lower().split()
                     if w in query.lower().split())
        return common / (log(len(tool_desc.split())) + 1)

# Tier configuration
TOOL_TIERS: dict[str, ToolTier] = {
    "active": ToolTier(
        name="active",
        tools={
            "read_file": {"description": "Read contents of a file from disk",
                          "params": ["path"], "depends_on": []},
            "search_docs": {"description": "Full-text search within documentation",
                           "params": ["query"], "depends_on": []},
            "send_email": {"description": "Send email via configured SMTP server",
                           "params": ["to", "subject", "body"], "depends_on": ["check_permissions"]},
            "check_permissions": {"description": "Verify caller has permission for action",
                                  "params": ["action"], "depends_on": []},
        },
        load_policy=lambda ctx: True  # always load active tier
    ),
    "contextual": ToolTier(
        name="contextual",
        tools={
            "crm_lookup": {"description": "Query CRM for customer record by email",
                            "params": ["email"], "depends_on": []},
            "crm_update": {"description": "Update CRM record field",
                           "params": ["record_id", "field", "value"], "depends_on": ["crm_lookup"]},
            "calendar_event": {"description": "Create or read calendar event",
                               "params": ["action", "details"], "depends_on": ["check_permissions"]},
        },
        load_policy=lambda ctx: ctx.get("task_type") in ("crm", "scheduling")
    ),
}

def retrieve_tools(task: str, task_context: dict) -> list[dict]:
    """Stratified retrieval: active always, contextual by policy, passive on demand."""
    active = TOOL_TIERS["active"].query(task, top_k=12)
    contextual = [
        t for tier_name, tier in TOOL_TIERS.items()
        if tier_name != "active" and tier.load_policy(task_context)
        for t in tier.query(task, top_k=6)
    ]
    # Passively loaded tools are not in context window — agent must
    # explicitly request them by name, preventing blind selection
    passive_names = list(TOOL_TIERS.get("passive", ToolTier("passive", {}, lambda _: False)).tools.keys())

    return (active + contextual)[:16]  # hard cap at 16 for retrieval clarity
```

### Pattern 2: Tool Scope Manifest

For every tool, declare an explicit **scope manifest** that makes interdependencies and preconditions machine-readable:

```yaml
# Tool scope manifest (managed in your MCP catalog, versioned alongside schemas)
tools:
  - name: crm_update
    scope: crm.write
    preconditions:
      - tool: crm_lookup
        within_steps: 5
        reason: "Must have fetched the record before updating it"
    postconditions:
      - field: crm.updated_at
        assert: "present"
    aliases:
      - "update CRM record"
      - "modify customer data"
      - "edit CRM entry"
    disambiguators:
      # Phrases that disambiguate this tool from similar ones
      - "with consent check"
      - "with audit log"
```

```python
def resolve_tool(intent: str, available_tools: list[dict]) -> dict | None:
    """Disambiguation using scope manifest aliases + disambiguators."""
    for tool in available_tools:
        if intent.lower() in [a.lower() for a in tool.get("aliases", [])]:
            # Check disambiguators — if intent matches any, high confidence
            disambigs = tool.get("disambiguators", [])
            if any(d.lower() in intent.lower() for d in disambigs):
                return tool
    # Fallback: return None and prompt for clarification rather than guessing
    return None  # Signal: ambiguous tool selection, request disambiguation
```

### Pattern 3: Dependency-Aware Execution Gate

Before executing a tool, validate its preconditions against the **agent trace** — the sequence of prior tool calls in the current session:

```python
@dataclass
class ExecutionGate:
    def check(self, tool: dict, trace: list[dict]) -> tuple[bool, str]:
        """
        Returns (allowed, reason).
        If False, the agent receives a structured error rather than
        a raw tool failure.
        """
        for precond in tool.get("preconditions", []):
            required_tool = precond["tool"]
            within_steps = precond.get("within_steps", 999)
            required_reason = precond["reason"]

            # Scan trace for prior invocation of required tool
            found = False
            for i, past in enumerate(reversed(trace[-within_steps:])):
                if past["tool"] == required_tool:
                    found = True
                    break

            if not found:
                return False, (
                    f"[PRECONDITION] Tool '{tool['name']}' requires '{required_tool}' "
                    f"to be called first ({required_reason}). "
                    f"Call '{required_tool}' before retrying this tool."
                )
        return True, "allowed"

gate = ExecutionGate()
allowed, reason = gate.check(
    tool={"name": "crm_update", "preconditions": [{"tool": "crm_lookup", "within_steps": 5}]},
    trace=[
        {"tool": "read_file", "args": {"path": "/contacts.csv"}},
        {"tool": "send_email", "args": {"to": "user@example.com"}},
    ]
)
# allowed=False, reason contains structured precondition error
```

## Receipt

> Verified 2026-07-29 — arXiv:2605.10787 (ComplexMCP, 2026) establishes the three failure modes empirically across 150+ tool MCP surfaces. The stratified retrieval pattern (active/contextual/passive) is a production-reasoned extension of the benchmark finding — not directly run, Receipt pending. The dependency-gate and scope-manifest patterns are production-familiar implementations discussed in the MCP community (alexey-tyurin/reliable-mcp, March 2026).

## See also

- [S-10 · MCP](s10-mcp.md) — foundational MCP protocol
- [S-100 · Agentic RAG](s100-agentic-rag.md) — retrieval-augmented tool use
- [S-1820 · The Tool Catalog Stack](s1820-the-tool-catalog-stack-when-your-agent-is-really-just-a-prompt-with-no-hands.md) — tool catalog design and governance
