# S-735 · The Evaluation Floor: What Separates Shipping Agents from Expensive Pilots

Every team that builds agents hits the same wall at the same moment: the demo works, the pilot flatters, but production reveals that you have no idea if your agent is right. The gap between "it seems to work" and "we know it's working" is where most agent investments stall. Closing that gap — the evaluation floor — is the single most underrated architectural decision.

## Forces

- **Goodhart's Law hits agents faster than most software.** Once you define a metric, the model optimizes for it, not the underlying goal. Teams that measure "task completion" get agents that claim completion without achieving outcomes. Teams that don't measure anything ship blind.
- **The observability tools market is immature and fragmented.** Cleanlab's 2025 survey of 95 production agent teams found that fewer than 1 in 3 were satisfied with their observability and guardrail solutions — making it the weakest link in the stack. Yet 63% planned to improve it in the next year. The tooling hasn't caught up with the need.
- **Evaluation is architecturally expensive to retrofit.** Measuring agent quality isn't a feature you add at the end. It requires instrumenting tool calls, tracking state transitions, capturing ground-truth comparisons, and building feedback loops — all of which are deeply entangled with orchestration design. Teams that skip it early pay 3–5x to add it later.

## The Move

Build the evaluation floor before the agent, not after it. The specific pattern that ships:

- **Multi-dimensional LLM judges.** Assign different judges for different failure modes — one for factual accuracy, one for instruction adherence, one for output format. Shopify's Sidekick team runs this at scale: they found that single judges game reward systems, so they use multiple specialized judges with statistical correlation against human evaluators. A single composite score hides which dimension is actually failing.
- **Procedural + semantic validation in tandem.** Rule-based checks (schema validation, boundary conditions, forbidden operations) catch structural failures cheaply and deterministically. LLM-based evaluation catches meaning failures that rules can't express. Use rules as a fast gate; use LLMs as the deep check. Running only LLM judges on every output is slow and expensive — filter with rules first.
- **User simulators for pre-production stress testing.** Real users are too slow and too expensive for iterative development cycles. Build simulators that model typical user goals, edge-case inputs, and adversarial behavior. Shopify invested in realistic simulators specifically to avoid testing against live merchants during development. The simulator doesn't need to be perfect — it needs to be diverse enough to catch failure modes before users do.
- **Closed-loop guardrails from evaluation data.** Every failure caught in evaluation becomes a test case in the regression suite. Over time, the guardrail system learns from production failures, not just hypothesized ones. This turns evaluation from a reporting tool into a learning system.
- **Budget and latency as first-class outputs.** Track cost-per-task and latency-per-step alongside quality metrics. Cleanlab found that 70% of regulated enterprises rebuild their agent stack every 3 months — often because cost exploded or latency became unacceptable in ways that weren't visible until production load hit. Measure inference cost per interaction, not just in aggregate.

## Evidence

- **Survey (Cleanlab, 2025):** Of 1,837 engineering and AI leaders surveyed, only 95 had AI agents live in production. Among those 95, less than 1 in 3 were satisfied with their observability and guardrail solutions. 63% planned to prioritize evaluation and observability improvements in the next year. — [https://cleanlab.ai/ai-agents-in-production-2025/](https://cleanlab.ai/ai-agents-in-production-2025/)
- **Engineering post (Shopify, 2025):** Shopify's Sidekick team built multiple specialized LLM judges aligned with human judgment for automated evaluation. Key finding: expect reward hacking and plan for iterative judge refinement as new failure modes surface. They combined procedural validation (rule-based checks) with semantic validation (LLM judges) for robust reward signals. — [https://shopify.engineering/building-production-ready-agentic-systems](https://shopify.engineering/building-production-ready-agentic-systems)
- **Engineering post (Technspire, December 2025):** Across production deployments, the consistent differentiator between shipping and stalling was the feedback loop structure. Developer tooling (coding agents) shipped fastest because compile + test + human review provided a tight, automatic feedback loop. Research agents stalled most often because evaluation criteria were unclear and feedback was slow. — [https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **Using a single evaluation metric is a trap.** Accuracy alone misses safety violations. Task completion alone misses hallucination. Latency alone misses cost. Build a measurement stack, not a measurement point.
- **Human evaluation doesn't scale but is the ground truth.** Every automated evaluation system needs periodic human calibration. Without it, your judges drift from user intent and you don't know it.
- **Eval quality is not proportional to eval quantity.** 1,000 test cases that don't cover failure modes are worse than 50 that do. Invest in failure mode discovery, not test volume.
- **Guardrails added post-hoc are brittle.** The natural place to add validation is at the tool-call boundary, where the agent decides to act. Adding it at the output stage means the model has already spent inference budget on the wrong path.
