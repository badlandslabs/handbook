# S-2828 · The Eval Harness Stack — Measuring Whether Your Agent Actually Works in Production

Your agent passes every demo. It completes tasks, calls tools, returns outputs. Then you ship it and users quietly work around its failure modes for six months before someone files a complaint. The problem isn't the agent — it's that you never measured whether it was actually correct.

## Forces

- **Task completion ≠ correctness.** An agent can declare success while producing subtly wrong results. Vindler Solutions documented a case where "95% task completion" masked only 70% actual correctness — the agent confidently reported done while being wrong 30% of the time.
- **Observability ≠ evaluation.** 89% of organizations have observability. Only 52% have proper evaluation systems. You know how fast it runs. You don't know if it's right.
- **Agents fail non-deterministically.** The same agent that passes today can fail tomorrow — on the same input, in the same trajectory, with no code change. Traditional software regression testing assumes determinism that agentic systems don't have.
- **Multi-step trajectories hide failures.** The final output might look fine. The failure is in tool selection, retrieval quality, intermediate reasoning, or boundary conditions. Evaluating only final output is evaluating the symptom, not the disease.

## The Move

Build a layered eval harness that answers three distinct questions: Did it complete the task? Was the trajectory sound? Did the output actually work for the user?

### The four evaluation layers

1. **Unit / golden dataset evals (offline)** — Curated test cases with known answers. Run in CI before every deploy. This is your regression gate. Arthur AI recommends building these from **production failures**: capture the trace, define the golden output, score it, add it to the suite. The same failure can never silently ship twice.

2. **LLM-as-judge scoring (automated)** — Use a language model to evaluate outputs against a rubric. Produces a score + written justification. Any model can judge (Claude, GPT-4, open-source). MLflow's framework documents this as the practical answer to BLEU/ROUGE limitations — those metrics measure token overlap, not correctness, groundedness, or safety. LLM-as-judge captures what humans catch but can't scale.

3. **Trajectory evaluation (not just output)** — Score the full execution path: did it use the right tools, in the right order, with the right retrieval? Anthropic's eval guide defines this explicitly: a **task** is a test case with inputs + success criteria; a **trial** is one attempt; a **grader** evaluates the attempt. Graders assess the trajectory, not just the destination.

4. **Production sampling / online monitoring** — Sample live requests, score them, detect drift. Braintrust's approach connects this directly to the offline eval loop: low-scoring production examples feed back into the golden dataset, creating systematic quality improvement over time.

### Practical tooling choices

- **DeepEval** — pytest-native, open-source, 50+ plug-and-play metrics. Best fit for engineering teams that want regression tests in CI.
- **Giskard (v3)** — Open-source, modular, built for dynamic multi-turn agent testing. Beta but actively developed.
- **Braintrust** — SaaS platform with Loop (AI that writes custom scorers from natural language descriptions). Integrates offline eval with production monitoring on one platform. Built by engineers from Google/Stripe.
- **LangSmith** — Tight integration with LangChain/LangGraph ecosystems. Eval baked into the tracing/observability bundle.
- **TruLens** — OpenTelemetry-native tracing + LLM judge scoring. Decorator-based instrumentation, results portable to any OTLP backend.

### The critical insight: evaluation as a flywheel

Production failure → captured trace → golden dataset entry → CI regression gate → shipping confidence → monitoring → new failure captured. Braintrust, Arthur AI, and Langfuse all converge on this flywheel model independently.

## Evidence

- **Engineering blog / HN (196 points):** Martin Fowler / Thoughtworks published a detailed case study on Bayer's PRINCE platform — agentic RAG for pharmaceutical research — emphasizing "harness engineering" (orchestration, validation, retries, observability, human review) as foundational to production reliability. The HN discussion surfaced the critical point that user satisfaction scores (3.1/5) don't measure correctness — you need structured eval. — [martinfowler.com/articles/reliable-llm-bayer.html](https://martinfowler.com/articles/reliable-llm-bayer.html) | [HN discussion](https://news.ycombinator.com/item?id=48615680)

- **Industry blog:** Vindler Solutions documented that 95% task completion masked only 70% actual correctness in a real deployment. 39% of AI projects fell short of expectations in 2024-2025. Only 2% of organizations have deployed agentic AI at scale. The bottleneck is evaluation, not model capability. — [vindler.solutions/blog/agent-evaluation-at-scale](https://vindler.solutions/blog/agent-evaluation-at-scale)

- **Anthropic engineering blog:** "Demystifying Evals for AI Agents" (January 2026) defines the formal structure of eval: tasks (test cases with inputs + success criteria), trials (attempts), graders (logic that scores attempts). Emphasizes that LLM-as-judge is the practical answer to automated quality assessment at scale, and recommends Braintrust as a platform combining offline eval with production observability. — [anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **GitHub / engineering blog:** The `fakoli/agent-eval` project (CI evaluation harness for multi-agent development environments) surfaces a distinct pattern: in enterprise multi-agent setups (Claude + Cursor + Copilot coexisting), agent instruction files become shared dependencies. A single-line change to CLAUDE.md or cursor rules can silently degrade productivity across repositories. The answer is behavioral regression tests that detect negative drift before it ships. — [github.com/fakoli/agent-eval](https://github.com/fakoli/agent-eval)

- **GitHub / MLflow:** MLflow's LLM-as-judge documentation provides the methodological framing: traditional metrics (BLEU, ROUGE) measure token overlap and miss hallucination, groundedness violations, and tone drift. LLM-as-judge evaluates across correctness, relevance, groundedness, safety, and helpfulness — with a score and written justification per evaluation. — [mlflow.org/llm-as-a-judge](https://mlflow.org/llm-as-a-judge)

## Gotchas

- **Golden datasets rot.** Eval cases are added without maintenance when agent behavior updates. HN commenters on agent eval tools consistently flag this: most teams add eval cases reactively and never update them. Treat the golden dataset as a living artifact, not a one-time build.
- **LLM-as-judge has a judge problem.** Judges exhibit position bias (preferring first or last options), self-preference bias (favoring outputs similar to their own), and consistency drift over time. Calibration against human ground truth is required before trusting judge scores in high-stakes domains.
- **Offline evals don't catch the production distribution.** Your curated test set covers what you thought of. Production users find inputs you never imagined. Online sampling + flywheel feedback is what closes that gap — offline evals alone give false confidence.
- **Task completion is the wrong metric to optimize.** Rate how many tasks the agent attempted to complete. Correctness rate is what actually matters. Measuring the wrong thing while the wrong thing degrades is the most common eval failure mode teams fall into.
