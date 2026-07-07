# S-755 · The Untyped Handoff Problem — Agent Contracts Are the Silent Production Killer

When two agents pass data in a pipeline, the failure mode is not a model error — it is an interface error. The upstream agent generates output that looks correct. The downstream agent receives it and acts on it confidently. The output is wrong. The pipeline completes silently. Nobody notices until a customer does.

## Forces

- **The real failure point is at the contract, not the model.** Multi-agent failures look like hallucination or bad reasoning. Root-cause analysis consistently shows: the upstream agent produced valid output, but in a form the downstream agent misinterpreted. The LLM did exactly what it was told; what it was told was structurally ambiguous.
- **Natural language passes data but not semantics.** When Agent A tells Agent B "here is the user's request and some context," Agent B must reconstruct what "some context" means. Different invocations produce different shapes. Downstream agents proceed with ambiguous data rather than requesting clarification — a top-3 failure category in multi-agent systems.
- **Typed contracts catch errors at the boundary; untyped pipelines propagate them silently.** A downstream agent that silently receives a list instead of a dict, or a null instead of an empty list, will either fail hard or — worse — continue with degraded assumptions.
- **Schema overhead is real but asymmetric.** Adding a contract layer costs engineering time upfront. Not having one costs debugging time, silent failures, and incident response downstream. The asymmetry favors contracts.

## The move

Enforce structured output contracts at every agent-to-agent handoff using Pydantic (Python) or equivalent type schemas. Treat the interface as the product.

- **Define explicit schemas before wiring agents together.** Specify field names, types, optionality, and whether a field can be empty or must be populated. Write the schema first; let it drive the agent's output instructions.
- **Validate at the boundary, not in the agent.** Use Pydantic models to parse and validate the output from the upstream agent before passing it to the downstream agent. Catch schema violations as exceptions, not as soft degradation.
- **Keep contracts minimal — add fields only when they are actually needed.** A schema of 4–6 fields is more maintainable than one of 20. Start lean; expand as the pipeline reveals what it actually needs.
- **Enforce explicit field semantics for ambiguous data.** If a field can be empty vs. absent, make that distinction explicit in the schema and the agent's instructions. "Null means not found; empty string means found but no value" is a rule, not an assumption.
- **Version handoff schemas when agent prompts change.** When you update the upstream agent's prompt and its output shape changes, increment the schema version. Downstream agents should pin to a schema version, not to raw prompt text.
- **Add a validation failure handler at each boundary.** When a contract violation occurs, the pipeline should surface the error with context — which agent, which schema, which field — rather than silently continuing or crashing.

## Evidence

- **Blog post (Tian Pan):** "The root cause of most multi-agent failures is interface failure. The LLM did exactly what it was told; what it was told arrived in a form that caused silent misbehavior." Documents that inter-agent communication breakdown — agents proceeding with ambiguous data rather than requesting clarification — is one of the top three failure categories in production multi-agent systems. — [tianpan.co, April 2026](https://tianpan.co/blog/2026-04-09-agent-to-agent-communication-protocols-production)
- **Engineering blog (RaftLabs):** "Untyped handoffs kill multi-agent workflows faster than any other issue." Their production data across 100+ AI products: 89% of organizations have observability but only 52% have evals — the gap explains why untyped handoff failures are often discovered in production, not testing. — [raftlabs.com, November 2025](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **HN build log (Evan Drake):** Opensoul's 6-agent marketing team uses structured task objects passed between a Director agent and specialized Strategist/Creator/Producer/Growth/Analyst agents. The explicit task schema — not natural language delegation — is what keeps the team coherent as it scales. — [github.com/iamevandrake/opensoul](https://github.com/iamevandrake/opensoul/blob/main/AGENTS.md)

## Gotchas

- **Schemas rot when agent prompts change without schema version bumps.** A prompt update that subtly changes the output shape will silently break downstream agents if the schema isn't updated in lockstep. Treat schema and prompt as one unit of change.
- **Overly permissive schemas are as dangerous as no schema.** A schema that accepts `Any` or allows all fields to be optional passes everything downstream. The validation becomes theater. Constraints should be tight enough to catch real errors, not just syntax.
- **Not every handoff needs a schema — but the high-stakes ones absolutely do.** A one-shot single-agent pipeline may not need contracts. Any pipeline where a human won't immediately review the output, or where downstream agents make decisions, needs typed boundaries.
