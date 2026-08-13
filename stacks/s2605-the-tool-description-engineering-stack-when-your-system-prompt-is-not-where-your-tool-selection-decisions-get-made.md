# S-2605 · The Tool Description Engineering Stack — When Your System Prompt Is Not Where Your Tool-Selection Decisions Get Made

Your agent has 12 tools. The agent picks the wrong one. You spend two days rewriting the system prompt. Nothing changes. The agent is still picking the wrong tool — because the selection decision was never driven by the system prompt. It was driven by the tool descriptions, and you never touched those.

## Situation

You have a customer-service agent with tools: `get_order_status`, `issue_refund`, `escalate_to_human`, `search_knowledge_base`. A user asks "I want to talk to someone about my order." The agent calls `issue_refund`. You update the system prompt to say "Always escalate emotional customers to humans." Still calls `issue_refund`. You add more instructions. Still wrong. You pull the tool descriptions open for the first time and find `issue_refund` says "Use when the customer wants to resolve their issue." `escalate_to_human` says "Use for billing complaints only." The model chose the wrong tool not because the system prompt was wrong, but because the description text made `issue_refund` look like the better fit.

This is the tool description problem. The model decides which tool to call based on the description text in the function schema — not the system prompt, not the task description, not the context. The description is the instruction. If it is ambiguous, contradictory, or missing key discriminators, no amount of system-prompt engineering will fix it.

## Forces

- **The model reads the description, not the intent.** Tool selection in most LLM function-calling pipelines uses the description field from the tool schema. The model matches the user's query against this text. The system prompt is background; the description is the decision signal. Most developers engineer the system prompt and treat descriptions as metadata.
- **Similar names and overlapping capabilities create selection ambiguity.** When two tools have similar purposes or their descriptions use overlapping vocabulary, the model defaults to heuristics that are brittle: alphabetical order, the first matching term, the most recently described tool. A developer who adds a tool to solve a narrow case often finds the model ignoring it in favor of a broader, previously-established tool.
- **Descriptions are static; the world is not.** A `search_database` tool was written when the database had 10 tables. Now it has 200. The description says "searches the database" — it does not say "returns up to 500 rows and times out after 8 seconds." The model calls it confidently, the tool times out, the agent retries with exponential backoff and bills you.
- **The BFCL plateau hides a description problem.** Berkeley Function-Calling Leaderboard scores show ~5% per-call error rates persisting across all frontier models. These scores are measured with clean, well-written schemas. Production tools have descriptions written by developers who were focused on functionality, not selection clarity. The real-world rate is higher, and the dominant cause is description text, not model capability.
- **Parameter descriptions compound the problem.** Even when the right tool is selected, wrong parameters follow from poorly described parameter fields. AgentEval (arXiv:2604.23581) measured parameter errors at 22% of failures, with 62% cascading to wrong final answers — meaning most parameter errors produce wrong results, not graceful errors.

## The move

### 1. Treat descriptions as the primary instruction layer for tool selection

Every tool description is a classification instruction. Write it to answer one question: *given a user query, why is THIS tool better than every other available tool?*

Bad: `search_knowledge_base` — "Searches the internal knowledge base for relevant articles."
Better: `search_knowledge_base` — "Use when the customer's question matches a documented policy or procedure (e.g. 'what is your return policy', 'how do I change my password'). Use when you need factual grounding before drafting a response. Do NOT use for real-time data like order status or account balances."

The second version is a classifier. It tells the model when to pick this tool versus alternatives.

### 2. Write descriptions in pairwise discrimination form

For each tool, compare it directly to the tools it is most likely to be confused with:

```
vs_get_order_status: search_knowledge_base returns POLICY answers. 
  get_order_status returns LIVE DATA. Use this when the answer 
  exists in documentation; use that when the answer requires a live query.

vs_escalate_to_human: search_knowledge_base resolves issues autonomously.
  escalate_to_human hands off to an agent. Exhaust this tool first.
```

Pairwise discrimination eliminates the ambiguity that comes from overlapping general-purpose descriptions.

### 3. Anchor with concrete triggers, not abstract goals

Descriptions that describe the tool's goal ("helps customers resolve issues") fail because every tool implicitly claims to help. Descriptions that describe the triggering condition ("use when the customer says X or Y") succeed because they are pattern-matchable against user input.

Concrete triggers:
- Exact phrases: `"I want to talk to someone"`, `"this is ridiculous"`, `"speak to a manager"`
- Task type: `"change"`, `"update"`, `"cancel"`, `"refund"`
- Data type: `"live"`, `"current"`, `"real-time"` vs `"policy"`, `"documented"`, `"historical"`

### 4. Name the parameters with selection-relevant metadata

Parameter descriptions are not API documentation. They are tool-selection context. A parameter named `query` with description "the search query" tells the model nothing about how to fill it. A parameter named `query` with description "natural-language question — be specific and include relevant identifiers (order numbers, product names, dates)" guides the model toward better calls.

For enum parameters, describe not just the enum values but the decision logic:
```
status: "order status value — use 'pending' when no tracking exists, 
  'shipped' when carrier has it, 'delivered' when confirmed. 
  Do NOT use 'delivered' if customer says 'it hasn't arrived' — 
  that is a delivery exception, not a delivered order."
```

### 5. Test descriptions, not just tool calls

Build a description regression suite alongside your tool-call tests. For each tool pair, create a test case: "User says X. Which tool should fire?" Run it against your descriptions in isolation. When adding a new tool, add negative test cases: "User says Y. Which tool should NOT fire?"

Measure description quality by selection accuracy, not by whether the tool eventually succeeded. A tool can be correctly selected and still fail — that is a different problem.

### 6. Monitor description drift

Tool capabilities evolve. A tool added for one use case gets repurposed. The description stays static while the tool changes. Add a quarterly description audit: compare the current description against the actual tool behavior by inspecting recent call logs. When the two diverge, update the description.

## Receipt

> Verified 2026-08-13 — Tool description engineering as a distinct engineering surface is not covered by existing entries. S-767 covers the tool-call hallucination plateau (symptom: function-schema-level errors, BFCL scores, retry strategies). S-03 covers tool-use mechanics. S-1006 covers toolbelt design (which tools to include). This entry covers the missing middle: how to write the description text that drives selection decisions, with pairwise discrimination, concrete triggers, and parameter-level selection metadata. Research sources: Adaline Labs (May 2026) — tool description as primary engineering surface; AgentEval arXiv:2604.23581 — wrong tool selection 18% of failures, parameter errors 22% with 62% cascade; τ-bench ~25% success rate indicating systemic selection ambiguity; Micheal Lanham "The Tool Selection Crisis" (Apr 2026).

## See also

- [S-767 · The Tool-Call Hallucination Plateau](/stacks/s767-the-tool-call-hallucination-plateau.md) — the symptom (one in five tool calls fails) and the BFCL plateau data that motivates this fix
- [S-1006 · The Agent Toolbelt Problem](/stacks/s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — which tools to include in the agent's toolbelt; this entry covers how to write each one
- [S-1052 · The Cascade Stack](/stacks/s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md) — downstream cascade when wrong tools propagate wrong facts through multi-agent pipelines
