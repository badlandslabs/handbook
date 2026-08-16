# S-2714 · The Trajectory-First Stack — When Your Agent Gets It Right for the Wrong Reasons

[Your eval suite reports 94% pass rate. Your agent ships. Three weeks later: a support agent that correctly refunded a customer but called an unauthorized internal API to do it. Another that answered a legal question accurately but cited a fabricated case citation — lucky coincidence it happened to be correct. Endpoint scoring passed both. Neither should have.]

## Forces

- **Endpoint scoring is blind to path.** An agent can reach a correct answer through a reckless trajectory: wrong tool first, lucky coincidence, ignored guardrails that didn't bite this time. Endpoint evals can't distinguish luck from competence.
- **Process failures are invisible to outcome metrics.** Tool called with incorrect arguments that happen to work. Private data queried unnecessarily. Loop executing 47 times before succeeding. All invisible if you only score the final text.
- **Agents compound errors differently than traditional software.** A bug in step 3 doesn't just produce a wrong output — it corrupts step 4's input, which corrupts step 5's reasoning, cascading into a final answer that looks fine but arrived via a broken process.
- **You can't secure what you can't observe.** Policy enforcement on the tool layer is critical, but you can't know which policies the agent ignored without scoring the trajectory itself.

## The Move

Score the execution path — every tool call, every reasoning step, every decision — not just the final output. Treat evaluation like a code review of the trace, not a multiple-choice test on the answer.

- **Capture complete traces, not just responses.** Instrument every tool call, every LLM reasoning step, every loop iteration with enough metadata to reconstruct the full execution path. Tool name, arguments, return value, timing, and which policy governed the call.
- **Score trajectory independently from outcome.** A run can have a correct final answer and a failed trajectory (wrong tools, unnecessary calls, policy violations). Both dimensions need explicit scores. The outcome pass rate tells you if the agent works; the trajectory score tells you if it's safe.
- **Use per-step rubrics, not just end-to-end rubrics.** A rubric applied only to the final output misses mid-run failures. Each step gets a local correctness check: was the right tool selected, with valid arguments, in a reasonable position in the sequence?
- **Track tool call patterns as first-class metrics.** Unnecessary tool calls (broad data queries when a narrow one would do), repeated calls with the same arguments (stuck in a loop), calls to unauthorized tools, calls with escalating privileges — these are signals that endpoint scoring never surfaces.
- **Re-run traces in replay mode.** Capture a production trace and replay it against a new model or policy without re-hitting live systems. This lets you A/B test model versions and catch regressions in trajectory behavior before they hit production.
- **Tier your golden cases.** A small core set (10–20) of non-negotiable cases — safety violations, worst historical incidents, known attack patterns — must pass at 100% regardless of aggregate scores. The rest can gate on statistical regression against baseline.
- **Calibrate LLM-as-judge with human annotations.** LLM judges achieve 64–68% agreement with domain experts in specialized domains. Calibrate by running the judge against 50–100 human-annotated examples first; target Spearman correlation ≥ 0.80 before trusting the score.

## Evidence

- **Engineering blog (JamesM):** An agent correctly refunded a customer but called `list_all_customers` first — broad data exposure masked by the correct final outcome. Trajectory evaluation would catch this; endpoint eval misses it. — [jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics](https://www.jamesm.blog/ai/evaluating-agents-in-production-trajectory-metrics/)
- **Engineering post (Langfuse):** Tool-argument checks belong on tool-call observations, not the final output. Intermediate steps carry independent failure modes — wrong retrieval documents, malformed arguments, repeated failing calls — all invisible in endpoint scoring. — [langfuse.com/resources/engineering/ai-agent-evaluation](https://langfuse.com/resources/engineering/ai-agent-evaluation)
- **HN Ask thread (harperlabs):** 7 core agent failure modes, including "correct answer via wrong process" and "context limit surprises" — agents silently misbehaving when context fills, producing wrong outputs with HTTP 200 status. — [news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)
- **Research survey (arXiv 2507.21504):** "LLM evaluation is like examining the performance of an engine. Agent evaluation assesses a car's performance comprehensively, as well as under various driving conditions." — [arxiv.org/html/2507.21504v1](https://arxiv.org/html/2507.21504v1)
- **Enterprise data (Galileo):** Agents achieve 60% success on single runs, dropping to 25% across eight runs — standard endpoint benchmarks miss this reliability variance entirely. — [galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks](https://galileo.ai/blog/agent-evaluation-framework-metrics-rubrics-benchmarks)

## Gotchas

- **Trajectory data is expensive to store.** Full traces with tool arguments can be large. Budget storage for the traces you need to debug and replay, not every production call. Sample strategically.
- **Scoring every step adds latency to eval runs.** Per-step rubric evaluation multiplies LLM calls per test case. Use lightweight deterministic checks (argument schema validation, policy rule matching) for the common cases; reserve LLM-as-judge for nuanced trajectory quality.
- **Trajectory scoring is harder to standardize than endpoint scoring.** What counts as "reasonable path" varies by domain. A support agent's reasonable path differs from a code-writing agent's. Build domain-specific rubrics, not generic trajectory rubrics.
- **LLM-as-judge bias creeps in.** Judges favor verbose, hedge-heavy reasoning over concise correct answers. Calibrate, then re-calibrate after model changes — a judge that works for GPT-4o may not work for a fine-tune.
