# S-2872 · The Judge-as-Infrastructure Stack — When Your Eval Loop Becomes Your Production Guardrail

Your agent has no runtime quality gate. It generates a response, sends it to the user, and only finds out it was wrong when the user complains. Meanwhile, over half of production agent teams have quietly moved their evaluation logic into the request path — running a judge LLM at inference time to verify reasoning, gate tool calls, and catch hallucinations before they cause damage. This is the judge-as-infrastructure stack: not testing your agent, but instrumenting it.

## Forces

- **Eval without runtime teeth is post-mortem quality control.** Teams build eval suites that run in CI and catch regressions — but nothing runs in production. By the time a failed trajectory surfaces in the next eval cycle, the damage is done. The knowledge from development never becomes operational policy.
- **Intrinsic self-correction doesn't work without ground truth.** Telling an agent "reflect on your output" improves nothing unless the agent has external signals to evaluate against. Ungrounded self-critique degrades reasoning performance. The LLM can't judge the quality of its own knowledge — it needs retrieved documents, user feedback, or a separate verifier to anchor the judgment.
- **Judging is simpler than generating.** A model that cannot reliably produce perfect factual answers can still reliably detect when an answer contradicts a retrieved document. This asymmetry is why small distilled judges (3B–8B parameters) achieve 85–95% accuracy at 97% lower cost than GPT-4 class models.
- **Judge placement is architecture, not configuration.** Putting a judge at the wrong boundary wastes compute and adds latency without improving outcomes. The three load-bearing boundaries — before user output, before irreversible tool calls, on memory writes — each serve fundamentally different purposes.
- **Offline evals and runtime judges require different evaluation criteria.** A judge that scores 90% on a curated eval dataset may still fail in production if the dataset doesn't reflect real distribution. Runtime judges need their own quality monitoring, calibration, and drift detection.

## The Move

The judge-as-infrastructure pattern deploys LLM-based verification into the production request path as load-bearing components — not as post-hoc grading, but as gates and guards that intercept agent behavior before it causes downstream harm.

### 1. Separate the judge modes: eval harness vs. runtime guardrail

These are different systems with different SLAs. An **offline eval judge** runs against historical traces, evaluates retrospectively, can use large expensive models, and tolerates latency. A **runtime judge** runs inline during agent execution, must complete within budget, and gates or shapes behavior at speed. Conflating them leads to either overpriced inference or unreliable gating.

### 2. Place judges at the three load-bearing boundaries

- **Before user output:** The most common placement. The judge evaluates the agent's response against user intent and retrieved context before the user ever sees it. Catches hallucinations, drift from instructions, and off-topic answers. Acts as a final quality gate.
- **Before irreversible tool calls:** Rate-limit violations, data modifications, payment triggers, database writes. The judge evaluates whether the planned action is consistent with the conversation context and known policy. More critical for agents that modify external state.
- **On memory writes:** When the agent writes to a knowledge store or updates persistent context, the judge verifies the information being stored is grounded in the conversation or retrieved sources — not confabulated. Prevents memory pollution that degrades future retrieval.

### 3. Choose judge size by placement and budget

Small distilled judges (3B–8B parameters) achieve 0.85–0.95 accuracy on classification and verification tasks at a fraction of the cost of frontier models. Use them for runtime gating. Reserve GPT-4o-class or Claude-class judges for offline eval and for calibrating the small judges. Calibrate the small judge against the large judge on a shared dataset — if they diverge beyond your threshold, flag for human review or fall back to the large judge for that case.

### 4. Build the feedback loop: eval → calibrate → deploy

Runtime judges need continuous calibration. Run offline eval batches monthly using curated real-trajectory datasets. Compare judge scores against human-annotated ground truth. If Spearman correlation drops below 0.80, retune the judge prompt or swap the model. Store all judge decisions (input, judgment, outcome) — this is your calibration dataset and also your early warning system for judge drift.

### 5. Treat judge decisions as structured audit records

Every runtime judge call should produce a structured log: input, judge_output, confidence, action_taken. This data enables post-hoc analysis, surfaces systematic false-positive/false-negative patterns, and provides the evidence trail for the eval-to-guardrail lifecycle. Without structured records, judge behavior is invisible until something blows up.

## Evidence

- **Amazon engineering blog (2025):** Documents that Amazon deployed thousands of agents and needed to shift from model benchmarks to multi-dimensional agent evaluation covering tool selection accuracy, multi-step reasoning coherence, memory retrieval efficiency, and task completion rates. Describes a 4-step automated eval workflow (define criteria → collect data → run eval → analyze) and an AI agent evaluation library in Bedrock AgentCore that provides systematic production measurements. — [aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)

- **Hacker News discussion (July–August 2025, 128 points):** Production engineers debate the role of LLM-as-critic vs. structured evals. A practitioner who owned an eval suite for a coding agent writes: "Evaluations are a vital for improving performance... I've never seen empirical evidence that 'LLM as critic' works." Another commenter (colonCapitalDee) notes: "The problem isn't that LLMs can't be critical, it's that LLMs don't have taste." The consensus: offline eval with curated datasets is the foundation; LLM-as-judge is useful for specific bounded tasks (classification, consistency checking) but not as a replacement for ground-truth-based evaluation. — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315) and [news.ycombinator.com/item?id=44715163](https://news.ycombinator.com/item?id=44715163)

- **Zylos Research (April 2026):** Finds >57% of production agent teams use judge LLMs at runtime as of 2026. Identifies 6 distinct judge patterns: offline eval, online runtime verifier, self-consistency loops, Reflexion/reflection, constitutional AI/RLAIF, and inference-time reward models. Key finding on cost: small distilled judges (3B–8B) achieve 97% cost reduction vs GPT-4 at 0.88–0.95 accuracy on classification tasks. Critically notes that intrinsic self-correction without external feedback degrades reasoning performance — only works with grounded external signals. — [zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026](https://zylos.ai/en/research/2026-04-10-llm-as-judge-production-agent-verification-2026)

## Gotchas

- **Judge placement creates latency budgets you must own.** A runtime judge adds 200–800ms per call depending on model size and context length. Budget this explicitly — if the judge is gating user-facing latency, use the smallest judge that meets your accuracy threshold and establish a timeout fallback.
- **Judge accuracy ≠ system accuracy.** A judge can score 92% on your eval set and still let through the 8% that matters most (the adversarial inputs, the high-stakes transactions). Monitor false-negative rate on your highest-risk cases, not just aggregate accuracy.
- **Ungrounded self-critique is waste.** If your agent reflects on its own output without external reference, it mostly rehearses the same reasoning with slightly different wording. Self-correction only works when the judge has access to verifiable ground truth (retrieved documents, user specifications, structured policies).
- **Judge prompts drift.** What works as a judge prompt today degrades as the agent model changes, as production distribution shifts, or as the judge model itself is updated. Treat judge prompts like production code: version-controlled, reviewed, and regression-tested against a calibration dataset on every change.
