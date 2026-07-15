# S-1158 · The Adaptive Compute Stack — When You Route Every Query Through a GPT-4 Pipeline

[You route "what is my account number" and "write our Q3 strategy memo" through the same five-agent pipeline. Both take 40 seconds. Both burn the same tokens. One gets a response worth $0.01 of compute; the other gets a response worth $50. You're leaving money and latency on the table because your agent doesn't know the difference between them. Adaptive compute routing — assigning depth proportional to estimated difficulty — closes that gap.]

## Forces

- **Compute cost scales superlinearly with task complexity.** A routing agent that classifies difficulty and routes to an appropriate pipeline depth can cut costs 40–60% without measurable accuracy loss, according to production teams implementing difficulty-aware orchestration.
- **Uniform pipelines are either over-engineered for simple tasks or under-powered for hard ones.** Sending every query through a multi-agent supervisor worker critic loop wastes resources on trivial inputs and under-thinks complex ones. One pipeline cannot optimally serve both.
- **Difficulty estimation is learnable, not subjective.** A lightweight classifier on query embeddings — or even a rule-based heuristic on task type and token count — reliably separates "what time is it" from "draft our response to the FTC inquiry." Teams that have tried it report surprising accuracy from surprisingly simple signals.
- **The alternative is manual triage that doesn't scale.** Asking users to classify their own requests fails. Asking humans to route tickets fails. A lightweight automatic classifier at the front door of your agentic system is the practical solution teams converge on.

## The Move

**Classify task difficulty at intake and route to a matched pipeline depth.** Simple queries go through a single LLM call or a two-step chain. Complex queries trigger the full multi-agent pipeline. The routing decision is cheap; the compute savings compound.

- **Estimate difficulty with lightweight signals first.** Task type (extraction vs. synthesis vs. reasoning), estimated input tokens, explicit complexity flags in user intent, or a lightweight embedding classifier on the query. Don't reach for an LLM to classify difficulty — a rule-based heuristic or a fine-tuned small model on this signal is faster and cheaper.
- **Define pipeline depth levels explicitly.** Level 0: direct LLM call, no tools. Level 1: LLM + one tool call. Level 2: LLM + plan + two to three tool calls + validation. Level 3: full multi-agent supervisor worker critic loop with human-in-the-loop gate. Map each task type to a target depth.
- **Route with a classifier, not the main agent.** A dedicated routing model — even a 1B parameter classifier on query embeddings — makes the routing decision before the main agent is invoked. The classifier is fast, isolated, and tunable without touching the agent prompt.
- **Make routing signals explainable.** Log the difficulty score and routing decision alongside every request. This creates a feedback loop: hard tasks that were under-routed and failed become training data for a better classifier.
- **Treat routing as a tunable knob, not a one-time design.** Start with rules. Measure the failure rate of under-routed tasks (high difficulty, routed to low depth). Promote those task patterns to higher depth. The classifier improves over time from production signal.
- **Route with a confidence threshold, not a hard cutoff.** When the classifier is uncertain, route up rather than down. The cost of over-routing a simple query is small. The cost of under-routing a complex one is a failed task.

## Evidence

- **Research paper (arXiv, September 2025):** Difficulty-Aware Agent Orchestration (DAAO) uses a VAE-based classifier on query embeddings to estimate task difficulty and route to matched reasoning strategies. Reported 22% improvement in task completion efficiency and 15% improvement in accuracy compared to uniform pipelines across reasoning benchmarks. — [arXiv 2509.11079](https://arxiv.org/abs/2509.11079)
- **Engineering blog (Zylos AI, April 2026):** Teams implementing difficulty-aware routing report 40–60% cost reductions on agentic pipelines without accuracy loss. Simple queries receive shallow chains; complex queries receive deep multi-agent pipelines. The routing layer sits at the front of the system and classifies before compute is committed. — [Zylos AI: Agent Workflow Orchestration Patterns](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns/)
- **Industry survey (Technspire, December 2025):** Production teams shipping agentic systems in 2025 identified uniform pipeline depth as a major cost inefficiency. Developer tooling and internal operations automation — which contain both trivial and complex tasks within the same workflow — were the primary adoption contexts for adaptive routing patterns. — [Technspire: State of Agentic AI End-2025](https://technspire.com/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **Routing at intake is only useful if pipeline depth is actually differentiated.** If your "fast path" still calls the same model with the same context, you've added latency without saving compute. Define genuinely cheaper fast paths — fewer tokens in, fewer tool calls, smaller model.
- **Query complexity and query cost don't always correlate.** A short query can require deep reasoning (a riddle, a legal edge case), while a long one can be trivially extractable. Token count alone is a poor proxy. Use task type taxonomy as a stronger signal.
- **Classifiers trained on synthetic data don't generalize.** If you train the difficulty classifier on queries written by your team, it will fail on how real users actually phrase requests. Ground the training data in production traffic, even if that means running the classifier in shadow mode for a few weeks before acting on its decisions.
- **Latency of the classifier itself matters.** A 500ms classification step before a 200ms fast-path task adds 2.5x overhead. Keep the routing model small and fast. The goal is to be faster than the task would have been without routing.
- **Hard cutoffs create failure cliffs.** A classifier that routes "P2" to the cheap pipeline and the cheap pipeline fails on P2 tasks produces worse outcomes than running the expensive pipeline every time. Use soft thresholds with fallback escalation rather than hard routing decisions.
