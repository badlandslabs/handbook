# S-2433 · The Outcome Stack — When the Agent Said It Succeeded, But It Didn't

The agent handled 40 customer escalations overnight. Your automated eval judged it 97% accurate. Then you check the CRM — three accounts were charged the wrong rate, two refunds were approved for non-qualifying cases, and one VIP customer got a form-letter response instead of a human handoff. The eval passed. The agent failed. Your eval was measuring the wrong thing.

## Forces

- **Output quality and outcome quality are different things.** A warm, empathetic, grammatically correct response that takes the wrong action is worse than a clumsy one that takes the right one. Most evals grade text.
- **The trajectory matters, not just the destination.** An agent that spends 12 tool calls getting to the right answer is less reliable than one that gets there in 3. Token cost and latency compound into real money.
- **Production failures are your eval data, but nobody ships a v1 agent and waits for casualties.** You need pre-production signal, which means simulating the production environment — not just prompting the model in isolation.
- **Every domain has different stakes.** A coding agent that produces a buggy PR gets caught by tests. A customer service agent that misapplies policy might not surface the failure for weeks.

## The Move

**Evaluate the state change, not the text.** The agent's job is to change the world — a database record, a sent email, an approved refund, a code change. Measure whether that change happened correctly.

- **State diff over text diff.** In customer service, retail, and airline domains, tau-bench (Sierra Research) evaluates by comparing the environment state at conversation end against a known target. The agent's job is to update the structured database correctly — not to write a good-sounding response about having done so.
- **Build your eval harness around tool-call traces, not final outputs.** LangSmith, Trulens, and DeepEval all instrument the full agent trace: what was retrieved, what tools were called, in what order, with what parameters. The failure mode usually lives in step 3 of 7, not in the final message.
- **Pairwise comparison beats absolute scoring.** Anthropic's eval guide recommends comparing two agent outputs side-by-side rather than grading each in isolation. This reduces position bias and is more robust than rubric-based scoring.
- **Run evals against production-like sandboxes, not mocks.** AlphaEval (arXiv, 2026) found that 80%+ of reported agent systems are in production, yet most research benchmarks use retrospective curated tasks. The gap: production has implicit constraints, fragmented information, and undeclared domain expertise that synthetic evals miss.
- **Use trajectory clustering for failure discovery.** Lucidic (YC W25) clusters agent failure trajectories across hundreds of runs to surface recurring failure patterns — instead of manually specifying what to test, you discover what breaks by watching what actually breaks.
- **Span-level evaluation isolates root cause.** Rather than scoring the whole interaction, apply evaluators to specific spans within the trace. This tells you whether the failure is in retrieval, tool selection, parameter generation, or response synthesis — and aligns debugging efforts with the actual cause.

## Evidence

- **Anthropic Engineering Blog:** "Demystifying evals for AI agents" (Jan 2026) establishes the core vocabulary — Task, Trial, Grader, Transcript, Outcome — and argues the Outcome (environment state) is the ground truth, not the agent's self-reported success. Recommends code-based graders over LLM-as-judge for structured outcome checking. — [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- **Sierra Research / tau-bench (GitHub, 1,768 stars):** Evaluates customer service agents by simulating the customer with a hidden scenario LLM. The agent must gather info, explain restrictions, obtain confirmation, and update a structured database. Evaluation is state-based: compare the database at conversation end against the known target state. Works across retail, airline, telecom, and banking_knowledge domains. — [https://github.com/sierra-research/tau2-bench](https://github.com/sierra-research/tau2-bench)

- **arXiv 2604.12162 — AlphaEval:** Production-grounded benchmark from 7 companies, 94 real-world tasks, 6 O*NET occupational domains. Key finding: existing research benchmarks (SWE-bench, WebArena, OSWorld) curate tasks retrospectively and miss production complexity. AlphaEval captures implicit constraints, multi-modal inputs, and stakeholder-aligned evaluation by sourcing from actual production failures. — [https://arxiv.org/html/2604.12162](https://arxiv.org/html/2604.12162)

- **Launch HN — Lucidic (YC W25):** AI agent observability platform from Stanford AI Lab researchers. Features trajectory clustering (discover recurring failure patterns across hundreds of runs) and time-travel debugging. Built originally when their e-commerce agent kept making the same mistakes across different categories. — [https://news.ycombinator.com/item?id=44735843](https://news.ycombinator.com/item?id=44735843)

- **LangSmith / RAGAS / DeepEval / TruLens:** The 2026 eval stack splits by function: RAGAS for metric science (faithfulness, answer relevancy, context precision), DeepEval for CI/CD gates, TruLens for trace-aware observability, LangSmith for end-to-end agent tracing and release gates. All focus on span-level and trajectory-level evaluation over text-level scoring. — [https://www.langchain.com/langsmith/evaluation](https://www.langchain.com/langsmith/evaluation), [https://docs.ragas.io/en/latest/tutorials/agent](https://docs.ragas.io/en/latest/tutorials/agent)

## Gotchas

- **Don't grade the self-report.** The agent saying "I successfully processed the refund" is not evidence the refund happened. Instrument the state change directly.
- **V1 evals are always too easy.** Early eval suites are built from cases you already know how to handle. Real failures live in the long tail — trajectory clustering and production sampling catch what curated suites miss.
- **LLM-as-judge accuracy varies wildly by domain.** Agreement with human judgment hits 80%+ for general instruction-following but drops significantly for healthcare, legal, and expert domains. If you're evaluating a domain expert agent, calibrate your judge against domain experts first.
- **Cost and latency are quality metrics.** An agent that achieves 95% accuracy but burns 10x the tokens of a 90% accurate one is not the better system. Track cost-per-task in your harness alongside accuracy.
- **Test the harness itself.** Your eval pipeline can have bugs too. Run your evaluator against known-fail and known-pass cases before trusting it to gate releases.
