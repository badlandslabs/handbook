# S-1650 · The Tool Interface Stack — When Your Tool Description Works for Humans but Not for Agents

You wrote a clean tool description. Your team reviewed it and said it looks fine. The agent read it and called the wrong tool, passed the wrong arguments, or skipped the tool entirely and hallucinated the answer. The description was designed for a developer who already knows what the tool does. It was never designed for a model that has to decide — from zero context — whether this is the right tool, with what arguments, in what order.

Tool interface quality is the most neglected failure surface in agentic systems. You can spend weeks optimizing the model, the prompt, and the retrieval layer — and lose it all to a single ambiguous parameter description.

## Forces

- **Tool descriptions are written for humans who already know the context.** Developers read a short description and fill in the gaps from domain knowledge. Agents have no domain knowledge. Every ambiguity is a decision point that gets resolved wrong.
- **The tool selection problem compounds with scale.** A 12-tool catalog is manageable. A 120-tool catalog turns ambiguous descriptions into a noisy decision surface where the wrong tool is statistically likely to win.
- **Tool descriptions are interface contracts — and most are poorly specified.** Parameter names, return types, error conditions, and edge cases are absent from most tool schemas. These gaps are invisible to humans and fatal to agents.
- **The debugging surface is invisible.** When an agent picks the wrong tool, the failure looks like a reasoning failure, a model failure, or a hallucination. It is almost always an interface failure. And it leaves no trace in the tool definition itself.
- **Rewriting tool descriptions is not a one-time fix.** Tool descriptions degrade as upstream APIs change, new edge cases emerge, and the agent's distribution of invocations shifts. The interface is a living artifact that requires ongoing maintenance.

## The move

### 1. Rewrite descriptions for bounded, machine-readable interfaces

Human-written descriptions tolerate vagueness. Agent-compatible descriptions do not. Apply these four rules to every tool description:

**Rule A — Be concrete about inputs, not abstract about purpose.**
Bad: "Fetches information about a publication."
Good: "Given a publication title (exact title or DOI), returns the publication year and author list."

**Rule B — Name parameters for disambiguation, not brevity.**
Bad: `query` (what kind? what format?)
Good: `search_query` (string, max 200 chars, natural language search term for the publication database) + `id_type` (enum: ['doi', 'title', 'pmid'], default: 'title')

**Rule C — Specify what the tool does NOT do.**
Agents fill in gaps optimistically. Tell them the boundaries: "Returns the publication year only — does not return abstracts, citations, or full text."

**Rule D — Use enumerated constraints for categorical parameters.**
Instead of `status: string`, use `status: enum['pending', 'approved', 'rejected']`. Every enum value you define is a decision the model no longer has to guess.

### 2. Test tool descriptions in isolation

Tool descriptions cannot be validated by reading them. They must be tested against the agent's actual decision behavior. Run a probe:

```python
def probe_tool_selection(agent, tool_catalog, test_queries):
    """Test whether the agent selects the right tool for each query."""
    results = []
    for query in test_queries:
        response = agent.select_tools(query, available_tools=tool_catalog)
        selected = response.selected_tool
        expected = response.ground_truth_tool
        results.append({
            "query": query,
            "selected": selected,
            "expected": expected,
            "correct": selected == expected,
        })
    return results

# Run with original descriptions → record failure rate
# Rewrite descriptions → re-run → compare
# Target: >95% correct selection before tool use proceeds
```

Run this probe monthly. Tool selection accuracy is a leading indicator of tool-use reliability — a drop in selection accuracy precedes downstream failures by days or weeks.

### 3. Detect description drift from invocation patterns

When the agent starts passing unexpected argument combinations to a tool, the description may no longer match the agent's learned model of how the tool works. Monitor for this with a lightweight schema:

```python
def detect_invocation_drift(tool_name, expected_params, actual_invocations):
    """Flag when the agent's actual invocations diverge from the schema."""
    unexpected_params = set()
    for invocation in actual_invocations:
        for param in invocation.params:
            if param not in expected_params:
                unexpected_params.add(param)
    if unexpected_params:
        return {
            "tool": tool_name,
            "drift_params": list(unexpected_params),
            "action": "review_description_for_ambiguity",
            "suggestion": f"Agent is using {unexpected_params} — check if these params "
                          f"are undocumented or if the description implies a different interface."
        }
    return None
```

### 4. Apply the Trace-Free+ curriculum principle for large tool catalogs

When you have 100+ tools, rewriting each manually is not scalable. The Intuit AI Research (arXiv:2602.20426) framework demonstrates that tools share structural patterns — parameter naming conventions, return type conventions, error condition formats — and that a model can learn to rewrite tool descriptions by transferring patterns from well-specified tools to poorly-specified ones.

For practitioners without a full Trace-Free+ implementation:

1. Identify your top-10 most reliably-invoked tools (by trace data)
2. Extract their description patterns: input structure, output structure, error behavior, constraint language
3. Use those patterns as a template when onboarding new tools or auditing existing ones
4. Apply a "description rewrite pass" whenever your tool catalog grows by 20%

### 5. Version your tool interface contract

Treat tool descriptions like API contracts — version them, log which version was active for each invocation, and track failure rates across versions.

```markdown
## Tool Interface Version Log

| Version | Date | Changes | Agent Selection Accuracy |
|---------|------|---------|--------------------------|
| v1.0 | 2026-03-01 | Initial deployment | 71% |
| v1.1 | 2026-05-12 | Added `id_type` enum to `get_publication` | 94% |
| v1.2 | 2026-07-01 | Clarified `search_query` max length, added DO field | 97% |
```

A single version bump in a tool description — adding an enum, clarifying a parameter bound, specifying a return type — can lift selection accuracy by 20+ percentage points. It costs an hour. The equivalent improvement through model changes costs weeks and GPU budget.

## Receipt

> Verified 2026-07-25 — Research from Intuit AI Research (arXiv:2602.20426) demonstrates that tool description quality is a primary bottleneck for LLM agent reliability. Paper shows 67.6% of agent tokens are tool-response tokens (BuildMVPFast analysis), making tool efficiency the highest-leverage optimization target. The paper's core finding: agents plateau when tool interfaces tolerate ambiguity that humans resolve contextually. The solution requires treating tool descriptions as machine-readable contracts, not human-readable summaries.

## See also

- [S-989 · The Tool Surface Stack](/stacks/s989-the-tool-surface-stack-when-your-agent-has-50-tools-and-picks-the-wrong-one.md) — Tool catalog management and selection at scale
- [S-1023 · The Recovery Ladder](/stacks/s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — Detecting and recovering from tool-call failures
- [S-1057 · The Tool Call Hallucination Plateau](/stacks/s1057-the-tool-call-hallucination-plateau-when-your-agent-gets-20-percent-of-tool-invocations-wrong-in-production.md) — When tool calls diverge from intent
