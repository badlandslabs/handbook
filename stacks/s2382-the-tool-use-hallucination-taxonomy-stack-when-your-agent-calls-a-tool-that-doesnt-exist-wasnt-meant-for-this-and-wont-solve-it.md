# S-2382 · The Tool-Use Hallucination Taxonomy Stack

Your agent calls `send_email_to_customer` when no such function exists in your tool catalog. It passes `{"amount": "-$50.00"}` to a payment API that rejects negative values. It spends forty steps on a web-scraping plan when the company blocked web access last quarter. These are not the same failure. They come from different cognitive misfires, require different fixes, and are measured differently. This is the tool-use hallucination taxonomy — a precision map of the five distinct failure modes that all produce the same symptom: a tool call that shouldn't have happened.

## Forces

- **Tool-call hallucinations compound faster than they look.** A single hallucinated tool call can corrupt the state that downstream steps depend on. By the time you notice the wrong answer, the hallucination has already propagated.
- **Existing entries cover the aftermath, not the taxonomy.** S-1007/S-1057 measure the plateau rate (3–7% of tool invocations wrong). S-1158 covers post-call confabulation (agent narrates success when the call failed). S-1293 covers action hallucination (agent claims it called a tool it didn't). None systematically map the pre-execution subtypes — the five distinct wrong-tool calls that happen before execution.
- **R\_NTA measures what existing benchmarks miss.** Normalized Tool-calling Accuracy (R\_NTA) and step-localization accuracy (AgentHallu, Liu et al. 2026) are the new measurement layer. They distinguish which hallucination subtype occurred, not just whether the call succeeded.
- **Mitigation strategies are subtype-specific.** You cannot fix tool-selection hallucination with better argument parsing. You cannot fix solvability hallucination with more tool descriptions. The wrong fix wastes effort and leaves the real failure intact.

## The move

**The five subtypes, in order of how much existing stacks cover them:**

### 1. Tool-Selection Hallucination
The agent picks the wrong tool entirely. The task requires `query_database` but the agent calls `search_web`. This is the most common subtype, and it is partially covered by S-1007/S-1057 (the plateau) — but those entries treat it as a rate problem. This subtype is a *matching* problem: the agent's internal tool vocabulary doesn't align with the available catalog.

Root causes: underspecific descriptions in the tool schema, similar tool names that confuse the model, missing tools not being surfaced as "unavailable" rather than absent.

### 2. Tool-Usage Hallucination
The right tool, wrong arguments. The agent calls `transfer_funds` with `{"recipient": "John", "amount": "fifty dollars"}` when the schema requires a numeric amount field and a user ID. This is the highest-volume production failure. BFCL benchmarks (Berkeley Function-Calling Leaderboard) show argument-type errors dominate — JSON structure mismatches, missing required fields, wrong enum values.

Root causes: schema descriptions that describe intent instead of format, enum values that aren't enumerated, required fields that aren't marked required, model treating natural-language parameter descriptions as schemas rather than examples.

### 3. Solvability Hallucination
The agent calls a tool that cannot possibly solve the task. The database was migrated to a new system — `query_database` returns data that no longer exists. Web access was blocked — `fetch_url` gets a 403 from the proxy. The agent assumes solvability without checking feasibility.

This is distinct from tool-selection (picking wrong *tool*) and tool-usage (wrong *arguments*). Solvability hallucination is wrong *assumptions about the current state of the world*.

Root causes: tools presented as available without availability checks, stale catalog data, agent not validating preconditions before committing to a tool-based plan.

### 4. Tool-Induced Myopia (TIM)
This is the newest identified subtype (Han et al., ACL 2026). The agent has access to a tool — typically a code interpreter — and starts deferring all reasoning to it, even problems it could solve internally. It empirical-checks its way through mathematical proofs instead of deriving them. It calls `calculate_median` when it should be doing arithmetic in context.

The danger: TIM produces correct answers via broken reasoning. The final output looks right, the trace looks reasonable, but the agent would fail on a slight variant. The agent's reasoning has been narrowed by tool access.

Root causes: tool access making external computation feel more authoritative than internal reasoning; training data that conflates "uses tools" with "is intelligent."

### 5. RAG / Retrieval-Induced Tool Hallucination
The agent's tool descriptions are served from a RAG system — documents about APIs, internal tooling, runbooks. The retrieval results include a tool called `deprecated_batch_processor` that nobody has used in two years. The agent calls it because it appeared in the retrieved context with a plausible description.

This overlaps with S-1067 (hallucination laundry — shared state converts one agent's error into everyone's fact) but is specifically about the tool *description pipeline* introducing hallucinated catalog entries, not shared execution state.

Root causes: RAG retrieval serving stale or fabricated tool documentation, vector similarity matching tools by description similarity rather than functional relevance, no canonical source-of-truth for the tool catalog.

### Mitigation Layer

| Subtype | Primary Fix | Key Metric |
|---------|-------------|------------|
| Tool-selection | Better schema descriptions, tool grouping by domain, "unavailable" signals | R\_NTA |
| Tool-usage | Typed schemas, enum validation, example parameters | BFCL argument accuracy |
| Solvability | Precondition checks, availability endpoints, plan feasibility gate | Step-localization accuracy |
| Tool-induced myopia | Curriculum learning, reasoning-vs-execution prompts, TIM-aware fine-tuning | Task-variant robustness |
| RAG-induced | Catalog as source of truth, retrieval-time freshness scoring, synthetic tool description audits | Hallucination recall |

## Receipt

> Verified 2026-08-09 — ArXiv 2412.04141 (Reliability Alignment / RelyToolBench) confirms tool-selection and tool-usage as primary subtypes with R\_NTA metric. ArXiv 2601.06818 (AgentHallu, Liu et al. Jan 2026) provides 5-category taxonomy across 693 trajectories with step-localization accuracy. ACL 2026 (Han et al.) formally defines Tool-Induced Myopia. AgentHallu tool-use hallucination category maps directly to this entry's scope. Deduplication: S-1007/S-1057 cover the rate/benchmark dimension; S-1158/S-1293 cover post-execution confabulation. This entry fills the pre-execution subtype taxonomy gap.

## See also

- [S-1007 · The Tool-Call Hallucination Plateau](s1007-tool-call-hallucination-plateau.md) — the 3–7% rate problem
- [S-1158 · The Action Confirmation Hallucination Stack](s1158-the-action-confirmation-hallucination-stack-when-your-agent-succeeded-and-didnt.md) — post-call confabulation
- [S-1293 · The Action Hallucination Stack](s1293-the-action-hallucination-stack-when-your-agent-says-it-did-something-it-didnt.md) — claiming a tool was called that wasn't
- [S-03 · Tool Use](s03-tool-use.md) — foundational tool definition patterns
- [S-1022 · The MCP Tool Catalog](s1022-the-mcp-tool-catalog-a-shared-vocabulary-for-agentic-tool-use.md) — catalog architecture
