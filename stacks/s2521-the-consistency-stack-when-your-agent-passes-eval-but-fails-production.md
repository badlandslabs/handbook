# S-2521 · The Consistency Stack — When Your Agent Passes Eval but Fails Production

Your eval suite reports 74% pass rate. You ship. Within a week, tickets flood in — not from hard tasks, but from the same task the agent handled yesterday. Same input, different output. The agent is not unreliable in the sense of being wrong; it is unreliable in the sense of being inconsistent. Your single-run pass-rate eval never measured this. It can't. This is the consistency gap: the hidden dimension of agent quality that separates demo-ready from production-ready.

## Forces

- **Single-run eval pass rate ≠ production reliability.** An agent that achieves 60% success on single-run evaluations often drops to 25% when measured across 8 runs for the same task. Eval design assumes each run is independent; production users do not experience it that way.
- **Error compounding makes reliability math brutal.** At 95% reliability per step — optimistic for current LLMs — a 10-step workflow succeeds 59% of the time. A 20-step workflow succeeds 36% of the time. Production workflows routinely hit 20+ steps.
- **Eval quality and production traffic diverge.** Teams optimize for the eval, not the real distribution. The harder cases that hit production are exactly the ones not in the eval suite.
- **Latency variance compounds the problem.** Voice agents targeting <800ms P95 often see P99 latencies of 8–15 seconds — representing thousands of bad experiences daily at scale.

## The Move

Measure what actually predicts production experience: not peak accuracy, but consistency, robustness, and fault tolerance across repeated runs, perturbed inputs, and infrastructure failures.

**1. Run k-trial consistency checks (minimum k=8).** Execute identical inputs 8+ times and measure the pass rate. An agent with 60% single-run accuracy may show 25% multi-run consistency — a fundamentally different product. Log every run independently; do not aggregate into a single judgment.

**2. Test ε-robustness with perturbed inputs.** Vary phrasing, casing, Unicode edge cases (O'Brien, José, 北京), null values, empty fields, and concurrent request ordering. Agents that work on clean inputs often fail silently on slightly unexpected ones. This is where silent failures hide.

**3. Inject λ-level infrastructure faults.** Simulate API timeouts, tool failures, network drops, and rate limits. Verify that the agent degrades gracefully — retry logic triggers, partial results surface, the system recovers rather than loops. Do not deploy agents that have never been stressed.

**4. Use span-level evals to catch hallucination mid-flight.** Score each LLM span against upstream retriever span (correlation threshold of 0.85 as a starting point). Flag when the LLM generates content that has no anchor in retrieved context. This catches hallucination at the span level before it reaches the user.

**5. Gate deployment on span-level metrics, not final-answer accuracy.** Route agent traces through an observability plane with OpenTelemetry. Block or flag deployments when consistency k-trial rates drop below threshold, when hallucination scores spike, or when tool call error rates exceed tolerance.

**6. Separate code-based from semantic from human-preference evaluation.** Code-based evals validate deterministic criteria (API responses, function outputs, unit tests). LLM-based evals assess semantic correctness via rubric scoring. Human preference evals capture tone, format, and UX. Different eval types catch different failure modes — use all three.

## Evidence

- **Research paper (arXiv:2601.06112):** ReliabilityBench — proposes evaluating agents across three dimensions: k-trial consistency (same outcome on repeated runs), ε-robustness (handling perturbed inputs), and λ-fault tolerance (behavior under infrastructure failures). Notes that existing benchmarks measure single-run success only, which fails to capture production reliability. — [arXiv:2601.06112](https://arxiv.org/html/2601.06112v1)
- **Engineering blog (tianpan.co, Oct 2025):** "Agents that achieve 60% success on single-run evaluations often drop to 25% when measured across 8 runs for the same task. Consistency at scale is not the same as accuracy on a test set." Also reports P95 latency targets by agent type (simple query <1s, complex workflow <4s, multi-agent <6s, voice <800ms to first byte). — [tianpan.co](https://tianpan.co/blog/2025-10-23-ai-agent-architecture-production)
- **HN discussion (427 points, 257 comments, Jul 2025):** Practitioner who built 12+ production agent systems: "Let's do the math. 95% reliability per step = 77% over 5 steps, 59% over 10 steps, 36% over 20 steps. Production systems need 99.9%+." Notes that the hardest problems aren't AI capabilities — they are designing tools and feedback systems that agents can actually use effectively. — [HN item#44623207](https://news.ycombinator.com/item?id=44623207)
- **HN Ask HN thread (harperlabs, 6 comments, 2025):** 40%+ of AI agent projects predicted to fail by 2027 (Gartner). Core failure modes include hallucination under unexpected inputs, edge case collapse (null values, Unicode, concurrent requests), and prompt injection. — [HN item#47325105](https://news.ycombinator.com/item?id=47325105)
- **Microsoft reference architecture (GitHub, Oct 2025):** Documents four multi-agent evaluation challenges: path optimization (correct solutions via inefficient routes), error propagation (upstream failures cascade), emergent behavior (unpredictable from individual analysis), and non-deterministic outputs. Proposes evaluation taxonomy spanning code-based, LLM-based, and human-preference evaluation types. — [microsoft/multi-agent-reference-architecture](https://github.com/microsoft/multi-agent-reference-architecture/blob/main/docs/evaluation/Evaluation.md)
- **Multi-agent observability guide (futureagi.com, updated May 2026):** Recommends span-level hallucination detection by scoring LLM spans against upstream retriever spans with 0.85 correlation threshold. OpenTelemetry GenAI semantic conventions stabilized in 2026 enable consistent tracing. — [futureagi.com](https://futureagi.com/blog/trace-debug-multi-agent-systems-observability-guide)

## Gotchas

- **Chasing single-run accuracy misses the real problem.** An agent can score 80% on a 100-task eval but fail 50% of the time on the 10 tasks that matter most. Consistency measurement across repeated runs is a fundamentally different metric — it requires a different test harness, not just more tasks.
- **"Works in demo" is the worst possible signal.** Demos use clean inputs, friendly paths, and no adversarial traffic. A demo-passing agent can have catastrophic consistency and robustness profiles. Treat demo performance as zero information about production readiness.
- **Infrastructure fault tolerance is almost never tested pre-deploy.** Most agent teams test happy paths. Lambda-level fault injection — API timeouts, tool failures, rate limits — almost always reveals failure modes that would otherwise surface as production incidents.
