# S-2743 · The Agent Failure Taxonomy Stack — When Your Agent Succeeds and Fails Silently

When your agent returns a result, completes a task, and logs no errors — but the result is wrong, incomplete, or based on hallucinated tool responses. The failure mode that slips past every dashboard.

## Forces

- **Failure is not an exception** — In a 5-12 step workflow, a 5% per-step failure rate gives a 34% chance something breaks somewhere (Paperclipped, 2026). Most teams only discover this in production.
- **Agents fail forward** — Unlike traditional software, an agent doesn't stop when something goes wrong. It wraps the error in a plausible response, continues the task, and returns a confident wrong answer.
- **No error code means no alert** — Tool failures produce valid HTTP 200s. Malformed tool responses parse as JSON. The agent never raises a flag.
- **Tool hallucination is invisible** — When no tool matches the agent's intent, it fabricates a tool name, constructs fake arguments, and calls it. The agent proceeds as if the tool ran.
- **Traditional testing misses the non-determinism** — Standard eval pipelines evaluate the final output only. They don't capture the reasoning chain, tool selection, or state at each step — where most failures originate.

## The Move

Build failure detection into every layer of the agent pipeline, not just at the output.

- **Structured span-level tracing** — Log every tool call as a span with input schema, output schema, and execution time. This turns the agent execution into a queryable trace rather than a black box. Tool-level latency spikes, error rates, and argument patterns become visible.
- **Layered tool validation** — Validate at two levels: (1) tool selection — does the agent's chosen tool match the request intent? — and (2) tool output — does the response conform to the expected schema? Failures caught here don't propagate into the reasoning chain.
- **Guardrails on tool descriptions** — Overlapping or ambiguous tool descriptions are a top cause of wrong tool selection. Strip descriptions to unambiguous specifics; include concrete input/output examples in every tool schema.
- **Circuit breaker per tool** — When a tool exceeds a failure threshold (rate limit, repeated errors, timeout), the agent's fallback path activates rather than retrying into a degraded state. This prevents cascading failures across a multi-step workflow.
- **Confidence scoring at output** — Use a secondary lightweight model to score the agent's final output against the original task. Low-confidence outputs trigger human review, not delivery. This catches confident wrong answers that the agent itself would never flag.
- **Multi-dimensional eval, not final-output-only** — Measure task success rate, tool call accuracy, trajectory correctness (did it follow the right steps in the right order?), latency per span, and cost per task. Run LLM-as-judge on 5–10% of production runs for qualitative assessment.

## Evidence

- **GitHub: Vectara awesome-agent-failures** — Community-curated taxonomy of production agent failures including tool hallucination, RAG-injected falsehoods, context overflow, and retry-amplified errors. Structured as a living reference with mitigations per failure mode. — [github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)
- **Blog: Paperclipped — Why AI Agents Fail in Production (2026)** — Documents 7 failure patterns from real deployments. Key finding: 3–15% tool call failure rate in production; with 8-step workflows this compounds to 34% chance of at least one failure. Root causes include overlapping tool descriptions, malformed JSON from ambiguous schemas, and rate limits under production load. — [paperclipped.de/en/blog/ai-agents-fail-production-deployment](https://www.paperclipped.de/en/blog/ai-agents-fail-production-deployment/)
- **InfoQ: Evaluating AI Agents in Practice (March 2026)** — Documents the 18% reliability collapse that appears under real-world variability but not in curated test sets. Argues for hybrid pipelines: LLM-as-judge + trace analysis + load testing for repeatability. Traditional LLM eval (BLEU, ROUGE) treats agent systems as black boxes and evaluates only the final outcome. — [infoq.com/articles/evaluating-ai-agents-lessons-learned](https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned/)

## Gotchas

- **Sampling 5–10% of runs for LLM-as-judge review is not enough if failures are rare** — If failures cluster around specific tool combinations or edge-case inputs, your sample may never hit them. Rate-limit your eval sample to target high-uncertainty trajectories, not random runs.
- **Tool hallucination is solved by tool availability signaling, not better prompting** — Adding "here are all available tools: [list]" to every prompt is more reliable than trying to instruct the model not to hallucinate tools.
- **Guardrails added after a failure are a patch, not a system** — Every time a failure slips through, the instinct is to add a check for that specific case. This accumulates into a brittle, case-specific defensive layer. Invest in schema validation and trace instrumentation instead.
- **Completion is not success** — An agent that returns a response with no error has still failed if the response is wrong. Your success metric must be task completion with verified output quality, not "agent returned without throwing."
