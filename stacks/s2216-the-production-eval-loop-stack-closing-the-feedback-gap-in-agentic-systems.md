# S-2216 · The Production Eval Loop

_When your agent deploys fine but you have no idea if it's getting better or worse week-to-week — and neither does anyone else._

## Forces

- **Benchmarks measure toy tasks, not production mess.** Standard benchmarks use curated inputs with clean ground truth. Production agents face ambiguous user intent, tool failures, and drift across turns that no benchmark captures.
- **Single-turn accuracy metrics miss the point.** BLEU and ROUGE scores don't reflect whether an agent chose the right tool, recovered gracefully, or actually completed the task versus claiming it did.
- **Human review doesn't scale but is irreplaceable.** LLM-as-judge is fast and cheap but drifts — a human sample is needed to catch "metric green, user red" failures.
- **The eval-data loop is broken by default.** Teams build agents in one silo, run evals in another, and never connect what fails in production back to what gets tested before deploy.

## The Move

The pattern that teams who ship reliable agents converge on: **close the loop between production traces and evaluation datasets, run both end-to-end and component-level checks, and treat cost/latency as first-class quality signals.**

### 1. Trace everything in production, then mine it for test cases

Every agent run emits a structured trace — tool calls, arguments, intermediate outputs, tokens consumed, latency per step, and final outcome. Production traces become the primary source for evaluation datasets. Microsoft Foundry implements this directly: intelligent sampling (using MinHash for diversity) filters out low-intent traffic and selects representative traces, producing curated datasets without manual cleanup. The same production data feeds both observability and testing.

### 2. Evaluate at two granularities: end-to-end and per-step

**End-to-end:** Did the agent complete the task correctly? Did output quality match expectations? This answers whether the agent is useful.

**Component-level:** Was the right tool selected? Were arguments correct? Did handoffs between sub-agents work? This answers where failures occur when end-to-end fails.

Amazon's evaluation workflow (published via AWS Bedrock AgentCore) formalizes this as a four-step process: define evaluation scenarios with clear success criteria, establish ground truth (human-annotated or synthetic), run automated evaluations, then layer human-in-the-loop review for high-stakes decisions.

### 3. Use two scorer types together

**Code-based scorers** handle deterministic checks: did the agent call the right API endpoint? Did the output match a known-good schema? Did it avoid PII leakage? These are fast, reproducible, and catch regressions.

**LLM-as-judge** handles the rest: response coherence, helpfulness, whether the agent correctly interpreted user intent across turns. Confident AI's DeepEval surfaces the specific failure modes judges miss — false task completion (the transcript says "done" but nothing changed), intent drift across turns, and "busywork loops" where the agent generates circular summaries or reasoning thrash without taking a real action.

### 4. Treat operational constraints as quality metrics, not ops metrics

Latency per task, cost per task, token efficiency, and tool reliability are first-class evaluation targets alongside correctness. Grid Dynamics frames this as "cost-per-quality analysis" — a 99% accuracy agent that costs $4 per query and takes 45 seconds is a different product than a 95% accurate agent at $0.02 and 2 seconds. Teams that ignore operating envelopes ship agents that look great in eval and fail in production.

### 5. Human review calibrates LLM-as-judge, not replaces it

Human rubrics on a random sample of traces (Confident AI recommends sampling from the tail — failures and borderline cases) calibrate whether the judge is scoring accurately. Amazon reinforces this: human-in-the-loop is indispensable for high-stakes agent decisions, not optional polish. The eval workflow trains the judge, the judge scales the coverage.

## Evidence

- **AWS Blog (Amazon Bedrock team, 2025):** Published a four-step evaluation workflow for agentic systems built on Bedrock. Key finding: single-model benchmarks are insufficient for agents — the new paradigm must assess emergent behaviors including tool selection accuracy, reasoning coherence, memory retrieval efficiency, and task completion rates. Human-in-the-loop review is a "critical evaluation component" for high-stakes decisions. — https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon

- **InfoQ (March 2026):** Synthesis of enterprise agent deployment lessons from Deutsche Telekom's LMOS platform and others. Key finding: "Agents are systems, not models — evaluate them accordingly." BLEU/ROUGE scores do not capture multi-turn behavior, tool failures, or recovery patterns. Organizations face 20–30% cost savings from agentic automation but "major causes of financial and reputational damage" from poor evaluation and production failures. — https://www.infoq.com/articles/evaluating-ai-agents-lessons-learned

- **AgentCompass (FutureAGI, arxiv 2509.14647, 2025):** First evaluation framework designed specifically for post-deployment monitoring of agentic workflows. Key finding: existing monitoring frameworks miss critical failure modes (cascading failures, emergent behaviors, unanticipated tool interactions) that structured 4-stage trace analysis catches. Intelligent sampling converts raw production traces into curated evaluation datasets — closing the observability-to-testing feedback loop. — https://arxiv.org/html/2509.14647v1

## Gotchas

- **Golden dataset overfitting.** A static golden dataset with 50 hand-picked cases catches regressions but doesn't represent real distribution. Supplement with production trace sampling or synthetic generation for edge cases your dataset never covered.
- **LLM-as-judge has a warm-up problem.** A judge's scoring needs to be calibrated against human-rated samples before it can reliably replace human review. Running judge-only evals on day one produces confident wrong scores.
- **Step counts are misleading.** More steps ≠ worse agent. A 20-step agent that correctly navigates a complex workflow beats a 2-step agent that got lucky. Measure task success first, step efficiency second.
- **Silent failures are the worst failures.** False task completion — the agent reports success but nothing actually changed — is the most dangerous failure mode and the hardest to catch without component-level checks on tool call outputs.
