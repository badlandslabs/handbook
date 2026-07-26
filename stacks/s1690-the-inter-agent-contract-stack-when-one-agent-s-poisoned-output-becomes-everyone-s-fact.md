# S-1690 · The Inter-Agent Contract Stack — When One Agent's Poisoned Output Becomes Everyone's Fact

Your multi-agent pipeline looks solid. Planner agent outputs a structured task list. Executor agent processes each task. Compliance agent reviews the output. Reporter agent writes the summary. All four agents pass their own tests. The final report cites a hallucinated figure from the planner as gospel. This is not a hallucination problem. It is a contract problem — the upstream output carries no schema enforcement at the handoff boundary, so downstream agents trust and propagate garbage as if it were confirmed fact.

Single-agent failures are local. Multi-agent failures are *compositional* — one agent's bad output becomes another agent's input, which produces another bad output, which downstream agents cite and elaborate on until the error has accumulated so much apparent legitimacy that nothing looks wrong anymore.

## Forces

- **Agents conflate confidence with correctness.** An LLM outputs high-confidence text regardless of whether it retrieved facts or hallucinated them. Downstream agents — receiving this confident output as their input — treat it as a reliable signal. Confidence is not a validity marker.
- **Validation at the consumer is too late.** If the compliance agent validates planner output, it only catches errors after the planner has already influenced executor behavior. Validation must happen at the *handoff boundary*, before downstream processing begins.
- **Schema drift accumulates invisibly.** A planner outputs `{"status": "complete"}`. The executor interprets "complete" as "don't need to retry." Six months later someone renames the field to `{"task_status": "done"}` and nobody audits every agent pair that reads it.
- **Cascading failures have a Knight Capital precedent.** In August 2012, one misconfigured server triggered a $440M loss in 45 minutes — not because one system failed, but because one system's bad state propagated to others that trusted it. Agentic pipelines have the same failure topology.

## The Move

Treat inter-agent handoffs as *enforced contracts*, not free-form text passing.

**Schema gates at every boundary.** Define Pydantic or JSON Schema output schemas for every agent-to-agent handoff. Before the receiver reads the output, a validation layer checks schema compliance. Non-compliant output triggers a retry, fallback, or escalation — it does not silently proceed downstream. This is the agentic equivalent of a type system: if the output doesn't match the contract, compilation fails.

**Constrained decoding as the first line of defense.** Use tools like Instructor, Outlines, or DSPy constraints to force the LLM to produce structured output at the generation boundary, not just validate after the fact. This eliminates the class of errors where the model "almost" follows the schema but slightly misstructures a nested field.

**Orchestrator circuit breakers at the pipeline level.** The orchestrator tracks the error rate at each stage. If the executor rejects planner output more than N times in a row (suggesting systemic planner degradation), the orchestrator pauses the pipeline and alerts. This prevents the pipeline from grinding forward on a broken planner indefinitely.

**Output provenance tracking.** Every piece of data that flows through the pipeline carries metadata: which agent produced it, which model generated it, what timestamp, what version of the prompt was used. When the reporter cites a figure, it should be traceable to the source agent. This is what makes RCA possible — without provenance, you cannot distinguish a downstream hallucination from an upstream hallucination.

**Replay from the last checkpoint.** When a failure is detected mid-pipeline, the pipeline rolls back to the last successful handoff and retries from there. This requires checkpointing at each boundary — storing the validated output of each stage before proceeding. LangGraph's checkpointing primitives support this; explicit implementation is required.

## Evidence

- **Zylos Research (2026):** Analyzes the error accumulation pattern in 4-agent pipelines where each stage has 80% accuracy. The final output is correct only 40.96% of the time (0.8⁴). Proposes three-layer validation stack: constrained decoding at generation, schema gates at handoffs, circuit breakers at the orchestrator level. — [URL](https://zylos.ai/research/2026-06-21-structured-output-validation-multi-agent-workflows/)
- **OWASP ASI08 (2026):** Classifies cascading failures in agentic AI as a distinct threat category, mapping it to prompt injection (LLM01:2025) as a primary trigger. Documents that autonomous agents propagating corrupted state across sessions creates compounding risk that exceeds any single-agent failure. — [URL](https://adversa.ai/blog/cascading-failures-in-agentic-ai-complete-owasp-asi08-security-guide-2026)
- **HN Ask: Multi-Agent Orchestration (2025):** Practitioner discussion confirming that inter-agent data passing is the primary failure point — one respondent describes a MongoDB shared state layer between agents as their solution, while another validates every JSON output with Zod before the receiver processes it. — [URL](https://news.ycombinator.com/item?id=47660705)
- **Weiseer/ai-agent-qa-eval-pack (2025):** Documents cascading failure testing for LangGraph and CrewAI, showing that malformed agent output fed into downstream agents produces errors that "look correct" in isolation but compound across the pipeline. Proposes deterministic schema-enforced test cases as the mitigation. — [URL](https://github.com/weiseer/ai-agent-qa-eval-pack-starter/blob/main/docs/guides/test-multi-agent-cascading-failure-crewai-langgraph.md)

## Gotchas

- **Schema enforcement adds latency.** Validating output against a schema before the downstream agent processes it adds a round-trip. Budget this into pipeline SLAs — teams that skip validation to save time often spend more time on RCA.
- **Overly strict schemas break under distribution shift.** If the executor expects `{"items": [...]}` but the planner occasionally returns an empty list, a strict schema will fail on legitimate cases. Use soft schemas with required vs. optional field contracts.
- **Schema versions must be tracked.** A schema change in the planner that isn't propagated to the executor's validation layer creates a silent contract drift. Treat schema versions as a first-class artifact with changelog discipline.
- **Confidence ≠ correctness — don't trust the model to self-validate.** The LLM will confidently produce structured output that matches the schema but contains hallucinated values. Schema validation checks *format*, not *truth*. Truth validation requires ground-truth checks (database lookups, API calls, or deterministic rules) at the boundary.
